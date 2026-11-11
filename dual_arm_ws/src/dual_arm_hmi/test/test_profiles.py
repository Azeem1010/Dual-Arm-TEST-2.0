from pathlib import Path

import pytest

from dual_arm_hmi.launcher.profiles import apply_environment, build_plan, load_profiles, workspace_from_prefix
from dual_arm_hmi.model.state import Mode

PACKAGED = Path(__file__).resolve().parents[1] / 'config' / 'profiles.yaml'
WORKSPACE = Path(__file__).resolve().parents[3]


@pytest.fixture
def profiles(tmp_path):
    return load_profiles(PACKAGED, tmp_path / 'missing.yaml')


def test_simulation_uses_the_interface_launch_with_cycles_and_journal(profiles):
    plan = build_plan(Mode.SIMULATION, profiles, WORKSPACE, '/tmp/j.json', 3)
    assert not plan.problem
    assert plan.command[:4] == ('ros2', 'launch', 'dual_arm_bringup', 'hmi_sim.launch.py')
    assert 'cycles:=3' in plan.command and 'journal_path:=/tmp/j.json' in plan.command and 'prefilled_slots:=2' in plan.command


def test_mock_disables_rviz(profiles):
    assert build_plan(Mode.MOCK, profiles, WORKSPACE, '', 1).command[-1] == 'rviz:=false'


def test_mock_serial_uses_the_workspace_fixture(profiles):
    plan = build_plan(Mode.MOCK_SERIAL, profiles, WORKSPACE, '', 1)
    assert not plan.problem and 'use_mock_serial:=true' in plan.command
    assert any('calibration_mock.yaml' in word for word in plan.command)


def test_mock_serial_missing_fixture_is_refused(profiles, tmp_path):
    assert '找不到' in build_plan(Mode.MOCK_SERIAL, profiles, tmp_path, '', 1).problem


def test_hardware_needs_a_port(profiles):
    assert 'hardware.port' in build_plan(Mode.HARDWARE_READ_ONLY, profiles, WORKSPACE, '', 1).problem


def test_hardware_read_only_never_enables_motion(profiles):
    profiles['hardware'] = {**profiles['hardware'], 'port': '/dev/serial/by-id/x', 'controllers_file': '/m.yaml'}
    command = build_plan(Mode.HARDWARE_READ_ONLY, profiles, WORKSPACE, '', 1).command
    assert command[0] == 'bash' and 'enable_motion' not in command[2] and 'publish_debug_image:=true' in command[2]


def test_hardware_motion_needs_measured_controllers(profiles):
    profiles['hardware'] = {**profiles['hardware'], 'port': '/dev/serial/by-id/x'}
    assert 'controllers_file' in build_plan(Mode.HARDWARE_MOTION, profiles, WORKSPACE, '', 1).problem
    profiles['hardware']['controllers_file'] = '/measured.yaml'
    command = build_plan(Mode.HARDWARE_MOTION, profiles, WORKSPACE, '', 1).command[2]
    assert 'enable_motion:=true' in command and 'controllers_file:=/measured.yaml' in command


def test_unknown_mode_is_refused(profiles):
    assert build_plan(Mode.UNKNOWN, profiles, WORKSPACE, '', 1).problem


def test_user_profile_overrides_single_keys(tmp_path):
    user = tmp_path / 'profiles.yaml'
    user.write_text('hardware:\n  port: /dev/serial/by-id/mine\nstartup_warning_s: 60\n')
    data = load_profiles(PACKAGED, user)
    assert data['hardware']['port'] == '/dev/serial/by-id/mine' and 'controllers_file' in data['hardware']
    assert data['startup_warning_s'] == 60


def test_environment_does_not_override_what_is_already_set(profiles):
    environ = {'ROS_DOMAIN_ID': '7'}
    applied = apply_environment(profiles, environ)
    assert environ['ROS_DOMAIN_ID'] == '7' and environ['GZ_PARTITION'] == 'dual_arm_pipeline_demo'
    assert applied == {'ROS_DOMAIN_ID': '7', 'GZ_PARTITION': 'dual_arm_pipeline_demo'}


def test_workspace_from_install_prefix(tmp_path):
    prefix = tmp_path / 'ws' / 'install' / 'dual_arm_hmi'
    prefix.mkdir(parents=True)
    assert workspace_from_prefix(prefix) == str((tmp_path / 'ws').resolve())
