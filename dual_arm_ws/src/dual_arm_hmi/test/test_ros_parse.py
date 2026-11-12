import json

import pytest

from dual_arm_hmi.model.state import Mode, Phase
from dual_arm_hmi.sources.ros_parse import (FpsMeter, calibration_from_diagnostics, calibration_raw_limits, firmware_counts, infer_phase, limits_from_urdf,
                                            mode_from_urdf, safety_from_json, task_from_json)

STATUS = {'state': 'ARM1:LIFT_A', 'active_arm': 'arm1', 'holding': {'arm1': 'cap_3', 'arm2': 'empty'}, 'b_owner': '',
          'occupied': [True, True, False, False, False, False, False, False], 'slot': 3, 'completed': 1, 'cycle_id': 'x',
          'message': '', 'config_fingerprint': 'y', 'busy': True, 'recovery_token': '', 'suction_step': '', 'suction_token': ''}
CONTROLLERS_ACTIVE = {'joint_state_broadcaster': 'active', 'arm1_controller': 'active', 'arm2_controller': 'active'}


def test_status_as_published_by_the_coordinator():
    task = task_from_json(json.dumps(STATUS))
    assert task.state == 'ARM1:LIFT_A' and task.busy and task.slot == 3 and task.completed == 1
    assert task.held_by('arm1') == 'cap_3' and task.held_by('arm2') == 'empty'
    assert task.occupied[:3] == (True, True, False) and len(task.occupied) == 8


@pytest.mark.parametrize('text', ('not json', '{}', '[]', '{"state": "IDLE"}', '{"state": "IDLE", "occupied": 3}'))
def test_unreadable_status_gives_nothing(text):
    assert task_from_json(text) is None


def test_safety_status():
    safety = safety_from_json('{"latched": true, "reason": "Operator software stop", "controllers_stopped": true}')
    assert safety.latched and safety.reason == 'Operator software stop' and safety.controllers_stopped
    assert safety_from_json('nope') is None and safety_from_json('{}') is None


@pytest.mark.parametrize('urdf,controllers,expected', (
    ('', {}, Mode.UNKNOWN),
    ('<robot/>', {}, Mode.UNKNOWN),
    ('<plugin>gz_ros2_control/GazeboSimSystem</plugin>', {}, Mode.SIMULATION),
    ('<plugin>mock_components/GenericSystem</plugin>', {}, Mode.MOCK),
    ('<plugin>cm530_hardware/CM530SystemInterface</plugin><param>/dev/serial/by-id/x</param>', {}, Mode.HARDWARE_READ_ONLY),
    ('<plugin>cm530_hardware/CM530SystemInterface</plugin><param>/dev/x</param>', {'arm1_controller': 'inactive'}, Mode.HARDWARE_MOTION),
    ('<plugin>cm530_hardware/CM530SystemInterface</plugin><param>/tmp/cm530_mock_serial</param>', {}, Mode.MOCK_SERIAL),
))
def test_mode_comes_from_the_loaded_hardware_plugin(urdf, controllers, expected):
    assert mode_from_urdf(urdf, controllers) is expected


def test_limits_from_urdf():
    urdf = '<robot><joint name="a" type="revolute"><limit lower="-1.5" upper="1.5"/></joint><joint name="b" type="fixed"/></robot>'
    assert limits_from_urdf(urdf) == {'a': (-1.5, 1.5)}
    assert limits_from_urdf('<not closed') == {} and limits_from_urdf('') == {}


def test_real_model_limits_cover_every_joint():
    from pathlib import Path
    from dual_arm_hmi.model.joints import JOINT_NAMES
    text = (Path(__file__).resolve().parents[2] / 'dual_arm_description' / 'urdf' / 'dual_arm_cad.urdf.xacro').read_text(encoding='utf-8')
    names = [name for name in JOINT_NAMES if f'name="{name}"' in text]
    assert names == list(JOINT_NAMES)


@pytest.mark.parametrize('mode,controllers,connected,expected', (
    (Mode.SIMULATION, CONTROLLERS_ACTIVE, False, Phase.STOPPED),
    (Mode.SIMULATION, CONTROLLERS_ACTIVE, True, Phase.READY),
    (Mode.SIMULATION, {'joint_state_broadcaster': 'active'}, True, Phase.STARTING),
    (Mode.HARDWARE_READ_ONLY, {'joint_state_broadcaster': 'active'}, True, Phase.READ_ONLY),
    (Mode.HARDWARE_MOTION, {'joint_state_broadcaster': 'active', 'arm1_controller': 'inactive', 'arm2_controller': 'inactive'}, True, Phase.READ_ONLY),
    (Mode.MOCK_SERIAL, {}, True, Phase.STARTING),
))
def test_phase_inference(mode, controllers, connected, expected):
    assert infer_phase(mode, controllers, connected) is expected


def test_calibration_status_defaults_to_fail():
    result = calibration_from_diagnostics([('calibration/env', 'PASS'), ('calibration/arm1', 'FAIL'), ('calibration/arm2', 'odd'), ('other/x', 'PASS')])
    assert result == {'env': 'PASS', 'arm1': 'FAIL', 'arm2': 'FAIL'}


def test_fps_meter():
    meter = FpsMeter()
    assert meter.rate(0.0) == 0.0
    for tick in range(11):
        meter.tick(tick * 0.1)
    assert meter.rate(1.0) == pytest.approx(10.0)
    assert meter.rate(10.0) == 0.0


def test_firmware_counts_from_dynamic_joint_states():
    names = ('arm1_arm_shoulder_pan_joint', 'arm1_arm_shoulder_lift_joint')
    interfaces = ((('position', 'velocity', 'raw_position', 'raw_target'), (0.1, 0.0, 90.0, 92.0)),
                  (('position', 'velocity', 'raw_position', 'raw_target'), (0.2, 0.0, 567.0, float('nan'))))
    assert firmware_counts(names, interfaces) == {names[0]: (90, 92), names[1]: (567, None)}


def test_simulation_has_no_firmware_counts():
    interfaces = ((('position', 'velocity'), (0.1, 0.0)),)
    assert firmware_counts(('arm1_arm_shoulder_pan_joint',), interfaces) == {}


def test_out_of_protocol_counts_are_dropped_not_clamped():
    interfaces = ((('raw_position', 'raw_target'), (1500.0, -3.0)),)
    assert firmware_counts(('j',), interfaces) == {'j': (None, None)}


def test_calibration_raw_limits_come_from_the_driver_calibration_file(tmp_path):
    calibration = tmp_path / 'calibration.yaml'
    calibration.write_text('joints:\n'
                           '  arm1_arm_shoulder_pan_joint: {motor_id: 17, zero_raw: 512, direction: 1, min_raw: 40, max_raw: 980}\n'
                           '  arm1_arm_shoulder_lift_joint: {motor_id: 3, zero_raw: null, direction: null, min_raw: null, max_raw: null}\n',
                           encoding='utf-8')
    urdf = (f'<robot name="r"><ros2_control name="s" type="system"><hardware><plugin>cm530_hardware/CM530SystemInterface</plugin>'
            f'<param name="calibration_file">{calibration}</param></hardware></ros2_control></robot>')
    assert calibration_raw_limits(urdf) == {'arm1_arm_shoulder_pan_joint': (40, 980)}


@pytest.mark.parametrize('urdf', ('', 'not xml', '<robot name="r"/>',
                                  '<robot name="r"><param name="calibration_file">/nonexistent/calibration.yaml</param></robot>'))
def test_missing_calibration_gives_no_limits(urdf):
    assert calibration_raw_limits(urdf) == {}


def test_at_home_needs_an_explicit_true_for_both_arms():
    from dual_arm_hmi.sources.ros_parse import task_from_json
    base = {'state': 'IDLE', 'occupied': [False] * 8}
    home = task_from_json(json.dumps({**base, 'at_home': {'arm1': True, 'arm2': True}}))
    assert home.both_at_home
    for value in ({'arm1': True, 'arm2': None}, {'arm1': True, 'arm2': 'yes'}, {'arm1': True}, None):
        task = task_from_json(json.dumps({**base, 'at_home': value}))
        assert not task.both_at_home, value
    assert not task_from_json(json.dumps(base)).both_at_home


def test_latched_simulation_stays_ready_but_hardware_does_not():
    from dual_arm_hmi.model.state import Mode, Phase
    from dual_arm_hmi.sources.ros_parse import infer_phase
    stopped = {'joint_state_broadcaster': 'active', 'arm1_controller': 'inactive', 'arm2_controller': 'inactive'}
    assert infer_phase(Mode.SIMULATION, stopped, True, latched=True) is Phase.READY
    assert infer_phase(Mode.SIMULATION, stopped, True, latched=False) is Phase.STARTING
    assert infer_phase(Mode.HARDWARE_MOTION, stopped, True, latched=True) is Phase.READ_ONLY


def test_parse_arm_camera_state():
    from dual_arm_hmi.sources.ros_parse import arm_camera_rotation
    assert arm_camera_rotation('{"want": "arm1", "streaming": "arm1", "phase": "on", "message": ""}') ==         {'arm1': 'on', 'arm2': 'off'}
    assert arm_camera_rotation('{"want": "arm2", "streaming": "", "phase": "switching", "message": ""}') ==         {'arm1': 'switching', 'arm2': 'switching'}
    assert arm_camera_rotation('{"want": "arm2", "streaming": "arm1", "phase": "error", "message": "x"}') ==         {'arm1': 'on', 'arm2': 'error'}
    assert arm_camera_rotation('nope') is None
    assert arm_camera_rotation('{"phase": "dancing"}') is None
