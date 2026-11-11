"""Which command starts each mode. Free of ROS and Qt so it can be unit tested."""
from dataclasses import dataclass
import os
from pathlib import Path
import shlex
from typing import Dict, Tuple

import yaml

from ..model.state import Mode

USER_PROFILES = Path('~/.ros/dual_arm_hmi/profiles.yaml').expanduser()
_MOCK_CALIBRATION = 'src/cm530_hardware/test/fixtures/calibration_mock.yaml'


@dataclass(frozen=True)
class LaunchPlan:
    command: Tuple[str, ...] = ()
    problem: str = ''


def load_profiles(packaged, user=USER_PROFILES):
    data = yaml.safe_load(Path(packaged).read_text(encoding='utf-8')) or {}
    if Path(user).exists():
        override = yaml.safe_load(Path(user).read_text(encoding='utf-8')) or {}
        for key, value in override.items():
            data[key] = {**data.get(key, {}), **value} if isinstance(value, dict) else value
    return data


def apply_environment(profiles, environ=os.environ):
    """Fill ROS_DOMAIN_ID and GZ_PARTITION unless already set, so the interface and what it starts agree."""
    for key, value in (profiles.get('environment') or {}).items():
        environ.setdefault(key, str(value))
    return {key: environ[key] for key in (profiles.get('environment') or {})}


def _launch(*words):
    return 'ros2 launch ' + ' '.join(shlex.quote(word) for word in words)


def _together(*commands):
    """Several launches in one process group, so one signal stops them all."""
    return ('bash', '-c', ' & '.join(commands) + ' & wait')


def build_plan(mode, profiles, workspace, journal_path, cycles) -> LaunchPlan:
    if mode is Mode.SIMULATION:
        sim = profiles.get('simulation') or {}
        return LaunchPlan(('ros2', 'launch', 'dual_arm_bringup', 'hmi_sim.launch.py', f'gz_args:={sim.get("gz_args", "-r -s")}',
                           f'cycles:={int(cycles)}', f'prefilled_slots:={int(sim.get("prefilled_slots", 2))}',
                           f'journal_path:={journal_path}', f'calib_dir:={sim.get("calib_dir", "~/.ros/dual_arm_calib/sim")}'))
    if mode is Mode.MOCK:
        return LaunchPlan(('ros2', 'launch', 'dual_arm_bringup', 'mock.launch.py', 'rviz:=false'))
    if mode is Mode.MOCK_SERIAL:
        calibration = (profiles.get('mock_serial') or {}).get('calibration_file') or str(Path(workspace) / _MOCK_CALIBRATION)
        if not Path(calibration).expanduser().exists():
            return LaunchPlan(problem=f'找不到 Mock Serial 校正檔 {calibration}')
        return LaunchPlan(('ros2', 'launch', 'dual_arm_bringup', 'hardware.launch.py', 'use_mock_serial:=true',
                           f'calibration_file:={calibration}'))
    if mode in (Mode.HARDWARE_READ_ONLY, Mode.HARDWARE_MOTION):
        return _hardware_plan(mode, profiles.get('hardware') or {})
    return LaunchPlan(problem='請先選擇模式')


def _hardware_plan(mode, hardware):
    port = hardware.get('port') or ''
    if not port:
        return LaunchPlan(problem='設定檔未填控制板路徑 hardware.port')
    words = ['dual_arm_bringup', 'hardware.launch.py', f'port:={port}']
    if hardware.get('calibration_file'):
        words.append(f'calibration_file:={hardware["calibration_file"]}')
    if mode is Mode.HARDWARE_MOTION:
        if not hardware.get('controllers_file'):
            return LaunchPlan(problem='實機動作需要實測容差的 hardware.controllers_file')
        words += ['enable_motion:=true', f'controllers_file:={hardware["controllers_file"]}']
    vision = ['vision_pkg', 'vision.launch.py', 'show_debug:=false', 'publish_debug_image:=true']
    calibration = ['dual_arm_bringup', 'calibration.launch.py', 'mode:=hardware', 'use_sim_time:=false']
    if hardware.get('vision_calib_dir'):
        vision.append(f'calib_dir:={hardware["vision_calib_dir"]}')
        calibration.append(f'calib_dir:={hardware["vision_calib_dir"]}')
    return LaunchPlan(_together(_launch(*words), _launch(*vision), _launch(*calibration)))


def workspace_from_prefix(prefix):
    """<workspace>/install/dual_arm_hmi gives <workspace>."""
    return str(Path(prefix).resolve().parent.parent)


def journal_settings(state):
    return state.get('journal_path') or str(Path('~/.ros/dual_arm_hmi/journals/sim_journal.json').expanduser())


def new_journal_path(stamp):
    return str(Path(f'~/.ros/dual_arm_hmi/journals/sim_journal_{stamp}.json').expanduser())


def as_environment(values: Dict[str, str]):
    return {key: str(value) for key, value in values.items()}
