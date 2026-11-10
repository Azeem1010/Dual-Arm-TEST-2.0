"""Turns ROS payloads into interface state. Free of rclpy so it can be unit tested."""
from collections import deque
import json
from pathlib import Path
import xml.etree.ElementTree as ElementTree

import yaml

from ..model.joints import firmware_count
from ..model.state import Mode, Phase, SafetyStatus, TaskStatus

ARM_CONTROLLERS = ('arm1_controller', 'arm2_controller')
BROADCASTER = 'joint_state_broadcaster'
_MOCK_SERIAL_PORT = '/tmp/cm530_mock_serial'
_FPS_WINDOW_S = 2.0
_CAMERAS = ('env', 'arm1', 'arm2')


def task_from_json(text):
    """A TaskStatus from /dual_arm/status, or None when the message cannot be read."""
    try:
        data = json.loads(text)
        holding = data.get('holding') or {}
        return TaskStatus(
            state=str(data['state']), active_arm=str(data.get('active_arm', '')),
            holding=(('arm1', str(holding.get('arm1', 'empty'))), ('arm2', str(holding.get('arm2', 'empty')))),
            b_owner=str(data.get('b_owner', '')), occupied=tuple(bool(value) for value in data['occupied']),
            slot=int(data.get('slot', 0)), completed=int(data.get('completed', 0)), message=str(data.get('message', '')),
            busy=bool(data.get('busy', False)), recovery_token=str(data.get('recovery_token', '')),
            suction_step=str(data.get('suction_step', '')), suction_token=str(data.get('suction_token', '')),
            at_home=_at_home(data.get('at_home')))
    except (ValueError, KeyError, TypeError, AttributeError):
        return None


def _at_home(value):
    """Only an explicit true counts as HOME; anything else is unknown."""
    value = value if isinstance(value, dict) else {}
    return tuple((arm, value[arm] if isinstance(value.get(arm), bool) else None) for arm in ('arm1', 'arm2'))


def safety_from_json(text):
    """A SafetyStatus from /safety/status, or None when the message cannot be read."""
    try:
        data = json.loads(text)
        return SafetyStatus(latched=bool(data['latched']), reason=str(data.get('reason', '')),
                            controllers_stopped=bool(data.get('controllers_stopped', False)))
    except (ValueError, KeyError, TypeError):
        return None


def mode_from_urdf(urdf, controllers):
    """The running configuration, read from the hardware plugin in the loaded robot description."""
    if not urdf:
        return Mode.UNKNOWN
    if 'gz_ros2_control/GazeboSimSystem' in urdf:
        return Mode.SIMULATION
    if 'mock_components/GenericSystem' in urdf:
        return Mode.MOCK
    if 'cm530_hardware/CM530SystemInterface' in urdf:
        if _MOCK_SERIAL_PORT in urdf:
            return Mode.MOCK_SERIAL
        return Mode.HARDWARE_MOTION if any(name in controllers for name in ARM_CONTROLLERS) else Mode.HARDWARE_READ_ONLY
    return Mode.UNKNOWN


def limits_from_urdf(urdf):
    """Joint name to (lower, upper) in radians. A malformed description gives no limits."""
    try:
        root = ElementTree.fromstring(urdf)
    except (ElementTree.ParseError, TypeError):
        return {}
    limits = {}
    for joint in root.findall('joint'):
        limit = joint.find('limit')
        if limit is None:
            continue
        try:
            limits[joint.get('name')] = (float(limit.get('lower')), float(limit.get('upper')))
        except (TypeError, ValueError):
            continue
    return limits


def firmware_counts(joint_names, interfaces):
    """Joint name to (raw_position, raw_target) from /dynamic_joint_states.

    interfaces holds one (interface_names, values) pair per joint. Only the CM-530 driver
    exports these interfaces, so simulation gives an empty result. A value that is not a
    whole count in 0..1023 becomes None rather than a guess.
    """
    counts = {}
    for name, (names, values) in zip(joint_names, interfaces):
        found = dict(zip(names, values))
        if 'raw_position' in found or 'raw_target' in found:
            counts[name] = (firmware_count(found.get('raw_position')), firmware_count(found.get('raw_target')))
    return counts


def calibration_raw_limits(urdf):
    """Joint name to (min_raw, max_raw) from the calibration file the driver was started with.

    The path is the calibration_file hardware parameter in the robot description. Anything
    missing or unreadable gives no limits, so nothing is highlighted rather than guessed.
    """
    try:
        root = ElementTree.fromstring(urdf)
    except (ElementTree.ParseError, TypeError):
        return {}
    path = next((param.text for param in root.iter('param') if param.get('name') == 'calibration_file'), None)
    if not path:
        return {}
    try:
        joints = (yaml.safe_load(Path(path).read_text(encoding='utf-8')) or {}).get('joints') or {}
    except (OSError, UnicodeDecodeError, yaml.YAMLError, AttributeError):
        return {}
    limits = {}
    for name, joint in joints.items():
        low, high = (joint or {}).get('min_raw'), (joint or {}).get('max_raw')
        if type(low) is int and type(high) is int and low <= high:
            limits[name] = (low, high)
    return limits


def infer_phase(mode, controllers, connected, latched=False):
    """Without a launcher the phase comes from what the controller manager reports.

    A safety latch deactivates the arm controllers. Without a torque step (simulation, Mock) the
    system is still up, so it stays READY and the latch is shown on its own.
    """
    if not connected:
        return Phase.STOPPED
    if all(controllers.get(name) == 'active' for name in ARM_CONTROLLERS):
        return Phase.READY
    if latched and not mode.has_torque_step and all(name in controllers for name in ARM_CONTROLLERS):
        return Phase.READY
    if controllers.get(BROADCASTER) == 'active' and (mode.has_torque_step or mode is Mode.HARDWARE_READ_ONLY):
        return Phase.READ_ONLY
    return Phase.STARTING


def calibration_from_diagnostics(statuses):
    """Camera name to PASS or FAIL from (name, message) pairs; an unknown message counts as FAIL."""
    result = {}
    for name, message in statuses:
        prefix, _, camera = name.partition('/')
        if prefix == 'calibration' and camera in _CAMERAS:
            result[camera] = 'PASS' if message == 'PASS' else 'FAIL'
    return result


class FpsMeter:
    def __init__(self):
        self._times = deque()

    def tick(self, now):
        self._times.append(now)
        self._trim(now)

    def _trim(self, now):
        while self._times and now - self._times[0] > _FPS_WINDOW_S:
            self._times.popleft()

    def rate(self, now):
        self._trim(now)
        if len(self._times) < 2:
            return 0.0
        span = now - self._times[0]
        return (len(self._times) - 1) / span if span > 0 else 0.0
