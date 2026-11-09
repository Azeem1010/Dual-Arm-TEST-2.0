import json

import pytest

from dual_arm_hmi.model.state import Mode, Phase
from dual_arm_hmi.sources.ros_parse import (FpsMeter, calibration_from_diagnostics, infer_phase, limits_from_urdf,
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
