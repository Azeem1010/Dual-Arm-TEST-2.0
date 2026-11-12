"""ROS entry point for the A-to-B-to-C task. Task decisions live in workflow/."""
import json
from pathlib import Path
import threading
import time

from ament_index_python.packages import get_package_share_directory
import rclpy
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile
from std_msgs.msg import Bool, String
from std_srvs.srv import Trigger

from dual_arm_interfaces.srv import ConfirmStep

from .confirmation import TokenError, TokenGate
from .gateways.env_scene import wire_env_scene
from .gateways.gripper import create_gripper
from .gateways.motion import MotionGateway
from .gateways.truth import TruthObserver, wire_truth
from .gateways.vision import VisionPickObserver, wire_vision
from .homes import load_homes
from .journal import Journal, config_fingerprint
from .task_config import load
from .workflow.ports import TaskCancelled, TaskFault, TaskIO, WorkflowSettings
from .workflow.transfer import RECOVERY, Transfer

_NEEDS_RECOVERY = ('FAULT', 'FULL')


class CoordinatorIO(TaskIO):
    def __init__(self, motion, suction_backend, observer, guard):
        self._motion, self._suction, self._observer, self._guard = motion, suction_backend, observer, guard

    def guard(self):
        self._guard()

    def zone(self):
        return self._observer.zone()

    def pick_target(self):
        return self._observer.pick_target()

    def b_pick_target(self):
        return self._observer.b_pick_target()

    def grid(self):
        return self._observer.grid()

    def verify_place(self, slot):
        return self._observer.verify_place(slot)

    def check_reachable(self, arm, xyz):
        self._motion.check_reachable(arm, xyz)

    def move_home(self, arm):
        self._motion.move_home(arm)

    def move_to(self, arm, xyz, contact=False):
        self._motion.move_to(arm, xyz, contact=contact)

    def at_home(self, arm):
        return self._motion.at_home(arm)

    def suction(self, arm, operation):
        self._suction.suction(arm, operation)

    def attach(self, arm):
        self._motion.attach(arm)

    def detach(self, arm):
        self._motion.detach(arm)

    def scene_reset(self):
        self._motion.scene_reset()

    def scene_add_b_object(self):
        self._motion.scene_add_b_object()

    def scene_remove_b_object(self):
        self._motion.scene_remove_b_object()

    def scene_add_slot_object(self, slot):
        self._motion.scene_add_slot_object(slot)


def _default_path(package, *parts):
    return str(Path(get_package_share_directory(package)).joinpath(*parts))


class CoordinatorNode(Node):
    def __init__(self, context=None):
        super().__init__('dual_arm_coordinator', context=context)
        declare = lambda name, value: self.declare_parameter(name, value).value
        config_path = declare('config_path', '') or _default_path('dual_arm_coordinator', 'config', 'sim', 'coordinator.yaml')
        urdf_path = declare('urdf_path', '') or _default_path('dual_arm_description', 'urdf', 'dual_arm_cad.urdf.xacro')
        srdf_path = declare('srdf_path', '') or _default_path('dual_arm_moveit_config', 'config', 'dual_arm.srdf')
        runtime_path = declare('runtime_path', '') or _default_path('dual_arm_coordinator', 'config', 'sim', 'runtime.json')
        calibration_path = declare('calibration_path', '')
        journal_path = declare('journal_path', '')
        self.cycles = declare('cycles', 1)
        prefilled = declare('simulation_prefilled_slots', 0)
        self.safety_max_age = declare('safety_max_age_s', 2.0)
        require_safety = declare('require_safety', False)
        token_ttl = declare('recovery_token_ttl_s', 3600.0)
        calibration_max_age = declare('calibration_status_max_age_s', 3.0)
        observation_source = declare('observation_source', 'truth')
        if observation_source not in ('truth', 'vision_pick', 'env_scene'):
            raise ValueError('observation_source must be truth, vision_pick or env_scene')

        self.config = load(config_path)
        if type(self.cycles) is not int or not 1 <= self.cycles <= 8:
            raise ValueError('cycles must be an integer in 1..8')
        if self.config['mode'] != 'simulation':
            raise RuntimeError('Hardware mode is BLOCKED until the vision gateway and safety supervisor exist')
        self.require_safety = require_safety

        self.group, self.lock = ReentrantCallbackGroup(), threading.RLock()
        self.cancel, self.busy, self.worker = threading.Event(), False, None
        self.estop_latched, self.safety = False, (None, 0.0)
        self.recovery_gate = TokenGate(token_ttl)
        self.suction_gate = TokenGate(self.config['gripper']['reply_timeout_s'] * 2.0)
        self.suction_request = None

        urdf = Path(urdf_path).read_text(encoding='utf-8')
        srdf = Path(srdf_path).read_text(encoding='utf-8')
        fingerprint = config_fingerprint({**self.config, 'simulation_prefilled_slots': prefilled,
                                          'observation_source': observation_source}, urdf + srdf)
        self.journal = Journal(journal_path or self.config['journal_path'], fingerprint)
        self._prefill(prefilled)

        homes = load_homes(self.config, runtime_path=runtime_path, calibration_path=calibration_path or None)
        self.motion = MotionGateway(self, self.config, urdf, homes, self.guard, self.group)
        self.observer = TruthObserver(self.config, lambda arm: self.motion.tcp_report(arm)['tcp_m'],
                                      self.motion.check_reachable, self.motion.home_tcp, prefilled)
        wire_truth(self, self.observer, self.group)
        self.suction_backend = create_gripper(self, self.config, self.guard, locator=self.observer.cap_under_tool,
                                              gate=self.suction_gate, announce=self._on_suction_request,
                                              callback_group=self.group)
        observations = self.observer
        if observation_source == 'vision_pick':
            observations = VisionPickObserver(self.observer, wire_vision(self, self.config, self.guard, self.group,
                                                                         calibration_max_age))
        settings = WorkflowSettings.from_config(self.config)
        if observation_source == 'env_scene':
            # The truth observer stays: the simulated gripper still locates caps through it.
            observations = wire_env_scene(self, self.config, settings, self.motion, self.guard, self.group)
        task_io = CoordinatorIO(self.motion, self.suction_backend, observations, self.guard)
        self.transfer = Transfer(task_io, settings, self.journal, self.recovery_gate)

        qos = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.status_publisher = self.create_publisher(String, '/dual_arm/status', qos)
        self.handoff_publisher = self.create_publisher(String, '/handoff/b_state', qos)
        self.permit_publisher = self.create_publisher(Bool, '/dual_arm/permit', 10)
        self.create_subscription(Bool, '/safety/estop', self._on_estop, 10, callback_group=self.group)
        self.create_service(Trigger, '/dual_arm/start', self._start, callback_group=self.group)
        self.create_service(Trigger, '/dual_arm/cancel', self._cancel, callback_group=self.group)
        self.create_service(ConfirmStep, '/dual_arm/confirm', self._confirm, callback_group=self.group)
        self.create_service(ConfirmStep, '/dual_arm/recover', self._recover, callback_group=self.group)
        # success = the operator confirmed the tools and zone B are clear; the token is not used.
        self.create_service(ConfirmStep, '/dual_arm/go_home', self._go_home, callback_group=self.group)
        self.create_timer(0.1, self._watchdog, callback_group=self.group)
        self.create_timer(0.2, self.publish_status, callback_group=self.group)
        self.publish_status()

    def _prefill(self, prefilled):
        """Simulation only: treat the first slots as used, since slot 1 is out of reach in this layout."""
        if type(prefilled) is not int or not 0 <= prefilled <= 8:
            raise ValueError('simulation_prefilled_slots must be an integer in 0..8')
        data = self.journal.data
        if prefilled and data['state'] == 'IDLE' and not any(data['occupied']):
            self.journal.update(occupied=[True] * prefilled + [False] * (8 - prefilled))

    # --- safety ---

    def _on_estop(self, message):
        self.safety = (message.data, time.monotonic())
        self.estop_latched = self.estop_latched or message.data

    def guard(self):
        if self.cancel.is_set():
            raise TaskCancelled('Task canceled')
        if self.estop_latched:
            raise TaskCancelled('Emergency-stop input is latched')
        if self.require_safety:
            value, stamp = self.safety
            if value is not False or time.monotonic() - stamp > self.safety_max_age:
                raise TaskCancelled('Emergency-stop heartbeat is missing or stale')

    def _watchdog(self):
        try:
            self.guard()
            allowed = self.journal.data['state'] != 'FAULT'
        except TaskFault as error:
            allowed = False
            with self.lock:
                if self.busy and not self.cancel.is_set():
                    self.get_logger().error(f'Stopping the task: {error}')
                    self.cancel.set()
        self.permit_publisher.publish(Bool(data=allowed))

    # --- status ---

    def _on_suction_request(self, arm, operation, token):
        self.suction_request = {'arm': arm, 'operation': operation, 'token': token}
        self.publish_status()

    def publish_status(self):
        data = self.journal.data
        token, operation = self.recovery_gate.current
        if data['state'] in _NEEDS_RECOVERY and token is None:
            # An expired recovery token must not leave the task stuck.
            token, operation = self.recovery_gate.issue(RECOVERY), RECOVERY
        with self.lock:
            busy = self.busy
        suction_token, suction_step = self.suction_gate.current
        status = {**data, 'busy': busy, 'recovery_token': token if operation == RECOVERY else '',
                  'suction_step': suction_step or '', 'suction_token': suction_token or '',
                  # null when the joint state is missing or old, so a display never assumes HOME.
                  'at_home': {arm: self.motion.home_state(arm) for arm in ('arm1', 'arm2')}}
        self.status_publisher.publish(String(data=json.dumps(status, sort_keys=True)))
        self.handoff_publisher.publish(String(data=json.dumps({'owner': data['b_owner'], 'state': data['state']})))

    # --- services ---

    def _start(self, _request, response):
        with self.lock:
            if self.busy or self.journal.data['state'] in _NEEDS_RECOVERY:
                response.success, response.message = False, 'Busy, faulted or full; see /dual_arm/status'
                return response
            self.cancel.clear()
            try:
                self.guard()
            except TaskFault as error:
                response.success, response.message = False, str(error)
                return response
            self.busy = True
            self.worker = threading.Thread(target=self._run_task, daemon=True)
            self.worker.start()
        response.success, response.message = True, 'Accepted; the result is reported on /dual_arm/status'
        return response

    def _run_task(self):
        try:
            result = self.transfer.run(self.cycles)
            self.get_logger().info(f'Task finished: {result}')
        except Exception as error:
            self.get_logger().error(f'Task stopped: {error}')
        finally:
            with self.lock:
                self.busy = False
            self.publish_status()

    def _cancel(self, _request, response):
        with self.lock:
            response.success = self.busy
            if self.busy:
                self.cancel.set()
        response.message = 'Cancellation requested' if response.success else 'No task is running'
        return response

    def _confirm(self, request, response):
        confirm = getattr(self.suction_backend, 'confirm', None)
        if confirm is None:
            response.accepted, response.message = False, 'This suction backend needs no operator confirmation'
            return response
        try:
            confirm(request.token, request.success, request.message)
            response.accepted, response.message = True, 'Confirmation recorded'
        except TokenError as error:
            response.accepted, response.message = False, str(error)
        return response

    def _go_home(self, request, response):
        """Start moving both arms HOME; like start, the outcome is reported on /dual_arm/status."""
        with self.lock:
            if self.busy:
                response.accepted, response.message = False, 'A task is running'
                return response
            self.cancel.clear()
            try:
                self.guard()
            except TaskFault as error:
                response.accepted, response.message = False, str(error)
                return response
            problem = self.transfer.home_problem(request.success, self.config['mode'] == 'simulation')
            if problem is not None:
                response.accepted, response.message = False, problem
                return response
            self.busy = True
            self.worker = threading.Thread(target=self._run_home, daemon=True)
            self.worker.start()
        response.accepted, response.message = True, 'Accepted; HOME is reported as at_home on /dual_arm/status'
        return response

    def _run_home(self):
        try:
            order = self.transfer.go_home()
            self.get_logger().info(f'Both arms are HOME (moved in order {order})')
        except Exception as error:
            self.get_logger().error(f'HOME stopped: {error}')
        finally:
            with self.lock:
                self.busy = False
            self.publish_status()

    def _recover(self, request, response):
        with self.lock:
            if self.busy:
                response.accepted, response.message = False, 'A task is running'
                return response
            self.busy = True
            self.cancel.clear()
        try:
            self.transfer.recover(request.token, request.success)
            response.accepted, response.message = True, 'Recovered; send a new start'
        except (TaskFault, TokenError, RuntimeError) as error:
            response.accepted, response.message = False, str(error)
        finally:
            with self.lock:
                self.busy = False
            self.publish_status()
        return response

    def shutdown(self):
        self.cancel.set()
        worker = self.worker
        if worker is not None:
            worker.join(timeout=10.0)
        self.journal.close()


def main(args=None):
    rclpy.init(args=args)
    node = CoordinatorNode()
    executor = MultiThreadedExecutor(num_threads=6)
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        node.shutdown()
        executor.shutdown()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
