"""Read-only view of the running system. It subscribes and queries; it can never command."""
from collections import deque
import threading
import time

from control_msgs.msg import JointTrajectoryControllerState
from controller_manager_msgs.srv import ListControllers
from diagnostic_msgs.msg import DiagnosticArray
from rcl_interfaces.srv import GetParameters
import rclpy
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.context import Context
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, qos_profile_sensor_data
from sensor_msgs.msg import Image, JointState
from std_msgs.msg import String
from vision_interfaces.msg import GridState, ZoneState
from vision_pkg.node_common import image_msg_to_bgr

from ..model.joints import JOINT_NAMES, JointSample
from ..model.state import (CAMERA_STALE_S, GAZEBO_VIEWS, CameraStatus, CommandFeedback, EventRecord, Level, Mode, Phase, Snapshot, ZoneView)
from .base import DataSource
from .ros_parse import FpsMeter, calibration_from_diagnostics, infer_phase, limits_from_urdf, mode_from_urdf, safety_from_json, task_from_json

CAMERAS = ('env', 'arm1', 'arm2')
_POLL_PERIOD_S = 1.0
_CALL_TIMEOUT_S = 3.0
_CONTROLLERS_MAX_AGE_S = 3.0
_STATUS_MAX_AGE_S = 1.5
_COMMAND_MAX_AGE_S = 1.0
_CONNECTED_MAX_AGE_S = 2.0
_ANNOTATION_MAX_AGE_S = 1.0
_VIEW_MAX_AGE_S = 3.0
# Gazebo can run several times slower than real time, so simulation-clocked data arrives late.
# Only applied in simulation; hardware keeps the strict limits.
_SIMULATION_STALE_FACTOR = 4.0
_EVENT_LIMIT = 200
_LATCHED = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
_REFUSED = '唯讀監看，不會送出指令'


class _Stream:
    def __init__(self):
        self.message, self.received, self.meter = None, None, FpsMeter()

    def push(self, message, now):
        self.message, self.received = message, now
        self.meter.tick(now)

    def age(self, now):
        return None if self.received is None else now - self.received


class _Stamped:
    """A value with the time it arrived, so old data can be refused rather than shown."""

    def __init__(self):
        self.value, self.received = None, None

    def set(self, value, now):
        self.value, self.received = value, now

    def fresh(self, now, max_age):
        return None if self.received is None or now - self.received > max_age else self.value


class RosSource(DataSource):
    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._lock = threading.Lock()
        self._images = {f'raw/{name}': _Stream() for name in CAMERAS}
        self._images.update({f'debug/{name}': _Stream() for name in CAMERAS})
        self._images.update({key: _Stream() for key, _ in GAZEBO_VIEWS})
        self._joints, self._task, self._safety = _Stamped(), _Stamped(), _Stamped()
        self._zones, self._grid, self._calibration, self._controllers = _Stamped(), _Stamped(), _Stamped(), _Stamped()
        self._commands = {'arm1': _Stamped(), 'arm2': _Stamped()}
        self._urdf, self._limits, self._observation = '', {}, ''
        self._controllers_pending, self._controllers_sent = None, 0.0
        self._parameters_pending = None
        self._ever_connected, self._feedback, self._last_phase = False, None, Phase.STOPPED
        self._stale_factor = 1.0
        self._expect_down = False
        self._events, self._previous = deque(maxlen=_EVENT_LIMIT), {}
        self._context = Context()
        rclpy.init(context=self._context)
        self._node = Node('dual_arm_hmi_monitor', context=self._context)
        self._group = ReentrantCallbackGroup()
        self._subscribe()
        self._controller_client = self._node.create_client(ListControllers, '/controller_manager/list_controllers', callback_group=self._group)
        self._parameter_client = self._node.create_client(GetParameters, '/dual_arm_coordinator/get_parameters', callback_group=self._group)
        self._node.create_timer(_POLL_PERIOD_S, self._poll, callback_group=self._group)
        self._executor = MultiThreadedExecutor(num_threads=4, context=self._context)
        self._executor.add_node(self._node)
        self._thread = threading.Thread(target=self._executor.spin, daemon=True)
        self._thread.start()

    # --- subscriptions ---

    def _subscribe(self):
        subscribe = lambda kind, topic, callback, qos: self._node.create_subscription(kind, topic, callback, qos, callback_group=self._group)  # noqa: E731
        for name in CAMERAS:
            subscribe(Image, f'/{name}_cam/image_raw', self._image_callback(f'raw/{name}'), qos_profile_sensor_data)
            subscribe(Image, f'/vision/{name}/debug_image', self._image_callback(f'debug/{name}'), qos_profile_sensor_data)
        for key, _ in GAZEBO_VIEWS:
            subscribe(Image, f'/{key}/image_raw', self._image_callback(key), qos_profile_sensor_data)
        subscribe(JointState, '/joint_states', self._on_joints, qos_profile_sensor_data)
        for arm in self._commands:
            subscribe(JointTrajectoryControllerState, f'/{arm}_controller/controller_state', self._command_callback(arm), qos_profile_sensor_data)
        subscribe(String, '/dual_arm/status', lambda message: self._store(self._task, task_from_json(message.data)), _LATCHED)
        subscribe(String, '/safety/status', lambda message: self._store(self._safety, safety_from_json(message.data)), _LATCHED)
        subscribe(String, '/robot_description', self._on_description, _LATCHED)
        subscribe(ZoneState, '/vision/env/zone_state', self._on_zones, 10)
        subscribe(GridState, '/vision/arm2/grid_state', self._on_grid, 10)
        subscribe(DiagnosticArray, '/vision/calibration_status', self._on_calibration, 10)

    def _store(self, slot, value):
        with self._lock:
            slot.set(value, self._clock())

    def _image_callback(self, key):
        stream = self._images[key]

        def receive(message):
            with self._lock:
                stream.push(message, self._clock())
        return receive

    def _command_callback(self, arm):
        def receive(message):
            self._store(self._commands[arm], dict(zip(message.joint_names, message.reference.positions)))
        return receive

    def _on_joints(self, message):
        positions = dict(zip(message.name, message.position))
        velocities = dict(zip(message.name, message.velocity))
        self._store(self._joints, (positions, velocities))

    def _on_description(self, message):
        with self._lock:
            self._urdf, self._limits = message.data, limits_from_urdf(message.data)

    def _on_zones(self, message):
        zones = ZoneView(message.a_has_object, message.b_has_object, message.b_arm_clear, message.c_object_count) if message.valid else None
        self._store(self._zones, zones)

    def _on_grid(self, message):
        self._store(self._grid, tuple(message.wrong_slots) if message.valid and message.order_checked else ())

    def _on_calibration(self, message):
        self._store(self._calibration, calibration_from_diagnostics((item.name, item.message) for item in message.status))

    # --- read-only queries ---

    def _poll(self):
        now = self._clock()
        self._poll_controllers(now)
        self._poll_observation_source()

    def _poll_controllers(self, now):
        if self._controllers_pending is not None:
            if not self._controllers_pending.done():
                if now - self._controllers_sent < _CALL_TIMEOUT_S:
                    return
            else:
                result = self._controllers_pending.result()
                if result is not None:
                    self._store(self._controllers, {item.name: item.state for item in result.controller})
            self._controllers_pending = None
        if self._controller_client.service_is_ready():
            self._controllers_sent, self._controllers_pending = now, self._controller_client.call_async(ListControllers.Request())

    def _poll_observation_source(self):
        if self._parameters_pending is not None:
            if not self._parameters_pending.done():
                return
            result, self._parameters_pending = self._parameters_pending.result(), None
            if result is not None and result.values:
                self._observation = result.values[0].string_value
        elif not self._observation and self._parameter_client.service_is_ready():
            self._parameters_pending = self._parameter_client.call_async(GetParameters.Request(names=['observation_source']))

    # --- DataSource ---

    def select_mode(self, mode):
        pass

    def expect_disconnect(self, expected):
        """A shutdown the operator asked for is recorded as such, not as a failure."""
        self._expect_down = expected

    def invoke(self, action):
        self._feedback = CommandFeedback(action, '已拒絕', _REFUSED)
        self._note(Level.WARN, f'{action.value}：{_REFUSED}')

    def close(self):
        self._executor.shutdown(timeout_sec=2.0)
        self._node.destroy_node()
        rclpy.shutdown(context=self._context)

    def frame(self, camera, annotated):
        now, factor = self._clock(), self._stale_factor
        with self._lock:
            if camera in dict(GAZEBO_VIEWS):
                stream, max_age = self._images[camera], _VIEW_MAX_AGE_S * factor
            else:
                raw, debug = self._images[f'raw/{camera}'], self._images[f'debug/{camera}']
                raw_limit, debug_limit = CAMERA_STALE_S * factor, _ANNOTATION_MAX_AGE_S * factor
                age = raw.age(now)
                if age is None or age > raw_limit:
                    return None
                debug_age = debug.age(now)
                stream, max_age = (debug, debug_limit) if annotated and debug_age is not None and debug_age <= debug_limit else (raw, raw_limit)
            age, message = stream.age(now), stream.message
        if age is None or age > max_age:
            return None
        try:
            return image_msg_to_bgr(message)
        except ValueError:
            return None

    def _note(self, level, message):
        self._events.appendleft(EventRecord(time.strftime('%H:%M:%S'), level, message))

    def _note_changes(self, snapshot):
        current = {'phase': snapshot.phase, 'mode': snapshot.mode, 'connected': snapshot.ros_connected,
                   'state': snapshot.task.state if snapshot.task else None, 'latched': snapshot.latched,
                   'message': snapshot.task.message if snapshot.task else ''}
        previous, self._previous = self._previous, current
        if not previous:
            return
        if current['mode'] != previous['mode']:
            self._note(Level.NEUTRAL, f'模式：{current["mode"].value}')
        if current['connected'] != previous['connected']:
            if current['connected']:
                self._note(Level.OK, 'ROS 已連線')
            elif self._expect_down:
                self._note(Level.NEUTRAL, 'ROS 已斷線（系統關閉）')
            else:
                self._note(Level.DANGER, 'ROS 連線中斷')
        if current['phase'] != previous['phase']:
            self._note(Level.NEUTRAL, f'系統：{current["phase"].value}')
        if current['state'] != previous['state'] and current['state'] is not None:
            self._note(Level.DANGER if current['state'] == 'FAULT' else Level.BUSY if ':' in current['state'] else Level.NEUTRAL,
                       f'任務：{current["state"]}')
        if current['latched'] != previous['latched']:
            self._note(Level.DANGER if current['latched'] else Level.OK, '安全鎖定' if current['latched'] else '安全鎖定解除')
        if current['message'] and current['message'] != previous['message']:
            self._note(Level.DANGER, f'任務訊息：{current["message"]}')

    def _camera_status(self, name, now, calibration):
        raw, debug = self._images[f'raw/{name}'], self._images[f'debug/{name}']
        debug_age = debug.age(now)
        factor = self._stale_factor
        return CameraStatus(fps=raw.meter.rate(now), age_s=raw.age(now), calibration=calibration.get(name, 'NOT_RUN'),
                            has_annotation=debug_age is not None and debug_age <= _ANNOTATION_MAX_AGE_S * factor,
                            stale_after_s=CAMERA_STALE_S * factor)

    def _joint_samples(self, now):
        data = self._joints.value
        if data is None:
            return ()
        positions, velocities = data
        commands = {}
        for slot in self._commands.values():
            commands.update(slot.fresh(now, _COMMAND_MAX_AGE_S) or {})
        samples = []
        for name in JOINT_NAMES:
            if name in positions:
                lower, upper = self._limits.get(name, (None, None))
                samples.append(JointSample(name, positions[name], velocities.get(name, 0.0), lower, upper, commands.get(name)))
        return tuple(samples)

    def snapshot(self):
        now = self._clock()
        with self._lock:
            factor = _SIMULATION_STALE_FACTOR if mode_from_urdf(self._urdf, {}) is Mode.SIMULATION else 1.0
            self._stale_factor = factor
            # Not scaled: service replies and /joint_states keep arriving at wall-clock pace even when Gazebo is slow,
            # and a lost system must be announced quickly.
            controllers = self._controllers.fresh(now, _CONTROLLERS_MAX_AGE_S)
            joint_age = None if self._joints.received is None else now - self._joints.received
            connected = controllers is not None or (joint_age is not None and joint_age <= _CONNECTED_MAX_AGE_S)
            self._ever_connected = self._ever_connected or connected
            known = controllers or {}
            mode = mode_from_urdf(self._urdf, known)
            if connected:
                phase = infer_phase(mode, known, True)
                self._last_phase = phase
            else:
                # After losing a running system, keep the phase so the loss is announced.
                phase = self._last_phase if self._ever_connected else Phase.STOPPED
            calibration = self._calibration.fresh(now, _STATUS_MAX_AGE_S * factor) or {}
            cameras = {name: self._camera_status(name, now, calibration) for name in CAMERAS
                       if self._images[f'raw/{name}'].received is not None} if connected or self._ever_connected else {}
            views = {key: CameraStatus(fps=self._images[key].meter.rate(now), age_s=self._images[key].age(now))
                     for key, _ in GAZEBO_VIEWS if (self._images[key].age(now) or 1e9) <= _VIEW_MAX_AGE_S * factor}
            # The coordinator's own timers run on wall time, so these limits stay strict.
            task = self._task.fresh(now, _STATUS_MAX_AGE_S)
            safety = self._safety.fresh(now, _STATUS_MAX_AGE_S)
            zones = self._zones.fresh(now, _STATUS_MAX_AGE_S * factor)
            authoritative = mode.is_hardware
            wrong = (self._grid.fresh(now, _STATUS_MAX_AGE_S * factor) or ()) if authoritative else ()
            joints = self._joint_samples(now)
        snapshot = Snapshot(
            mode=mode, phase=phase, ros_connected=connected, monitor_only=True, task=task, safety=safety,
            controllers_active=all(known.get(name) == 'active' for name in ('arm1_controller', 'arm2_controller')),
            decision_source=self._observation if task is not None else '', joints=joints, joint_age_s=joint_age, cameras=cameras,
            zones=zones, zones_authoritative=authoritative, wrong_slots=wrong, gazebo_views=views, feedback=self._feedback)
        self._note_changes(snapshot)
        return Snapshot(**{**snapshot.__dict__, 'events': tuple(self._events)})
