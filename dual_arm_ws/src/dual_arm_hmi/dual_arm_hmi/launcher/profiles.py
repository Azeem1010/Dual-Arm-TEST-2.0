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


_CAMERA_DEVICES = ('env_cam_device', 'arm1_cam_device', 'arm2_cam_device')
# ROS 2 domain ids that stay clear of the ports of other DDS participants on Linux.
_DOMAIN_RANGE = range(0, 102)


@dataclass(frozen=True)
class LaunchPlan:
    command: Tuple[str, ...] = ()
    problem: str = ''
    # Added to the environment of what is started, on top of the interface's own.
    environment: Tuple[Tuple[str, str], ...] = ()
    # Starts anyway, but the operator should know.
    notice: str = ''


def domain_for(mode, profiles, environ=os.environ):
    """The ROS domain a mode runs on. Hardware has its own, so simulation traffic never reaches it."""
    if mode.is_hardware:
        return str((profiles.get('hardware') or {}).get('ros_domain_id', '')).strip()
    return str(environ.get('ROS_DOMAIN_ID', '')).strip()


def domain_problem(profiles, environ=os.environ):
    """Why the hardware domain cannot be used, or ''."""
    hardware = domain_for(Mode.HARDWARE_READ_ONLY, profiles, environ)
    if not hardware.isdigit() or int(hardware) not in _DOMAIN_RANGE:
        return f'hardware.ros_domain_id 必須是 0～101 的整數，目前是 {hardware!r}'
    simulation = domain_for(Mode.SIMULATION, profiles, environ)
    if simulation.isdigit() and int(simulation) == int(hardware):
        return f'hardware.ros_domain_id {hardware} 和模擬用的 ROS_DOMAIN_ID 相同，實機會收到模擬的資料'
    return ''


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


def build_plan(mode, profiles, workspace, journal_path, cycles, environ=os.environ) -> LaunchPlan:
    if mode is Mode.SIMULATION:
        sim = profiles.get('simulation') or {}
        return LaunchPlan(('ros2', 'launch', 'dual_arm_bringup', 'hmi_sim.launch.py', f'gz_args:={sim.get("gz_args", "-r -s")}',
                           f'cycles:={int(cycles)}', f'prefilled_slots:={int(sim.get("prefilled_slots", 0))}',
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
        return _hardware_plan(mode, profiles, environ)
    if mode is Mode.HARDWARE_PROTOTYPE:
        return _prototype_plan(profiles, journal_path, cycles, environ)
    return LaunchPlan(problem='請先選擇模式')


def _hardware_plan(mode, profiles, environ):
    hardware = profiles.get('hardware') or {}
    port = hardware.get('port') or ''
    if not port:
        return LaunchPlan(problem='設定檔未填控制板路徑 hardware.port')
    problem = domain_problem(profiles, environ)
    if problem:
        return LaunchPlan(problem=problem)
    words = ['dual_arm_bringup', 'hardware.launch.py', f'port:={port}']
    if hardware.get('calibration_file'):
        words.append(f'calibration_file:={hardware["calibration_file"]}')
    if mode is Mode.HARDWARE_MOTION:
        if not hardware.get('controllers_file'):
            return LaunchPlan(problem='實機動作需要實測容差的 hardware.controllers_file')
        words += ['enable_motion:=true', f'controllers_file:={hardware["controllers_file"]}']
    # The environment camera decides; the arm cameras only monitor and take turns (USB bandwidth).
    vision = ['dual_arm_bringup', 'vision_hardware.launch.py']
    if hardware.get('vision_calib_dir'):
        vision.append(f'calib_dir:={hardware["vision_calib_dir"]}')
    devices = {name: str(hardware.get(name) or '').strip() for name in _CAMERA_DEVICES}
    vision += [f'{name}:={path}' for name, path in devices.items() if path]
    missing = [name for name, path in devices.items() if not path]
    notice = (f'設定檔未填 {"、".join(missing)}，改用 vision_pkg 的 config/cameras.yaml；兩處都空的相機不會啟動'
              if missing else '')
    return LaunchPlan(_together(_launch(*words), _launch(*vision)),
                      environment=(('ROS_DOMAIN_ID', domain_for(mode, profiles, environ)),), notice=notice)


def _prototype_plan(profiles, journal_path, cycles, environ):
    """One launch: arms on the prototype settings, hardware vision and the coordinator."""
    hardware = profiles.get('hardware') or {}
    port = hardware.get('port') or ''
    if not port:
        return LaunchPlan(problem='設定檔未填控制板路徑 hardware.port')
    problem = domain_problem(profiles, environ)
    if problem:
        return LaunchPlan(problem=problem)
    words = ['ros2', 'launch', 'dual_arm_bringup', 'hardware_prototype.launch.py', f'port:={port}',
             f'cycles:={int(cycles)}', f'journal_path:={journal_path}']
    if hardware.get('vision_calib_dir'):
        words.append(f'calib_dir:={hardware["vision_calib_dir"]}')
    words += [f'{name}:={path}' for name in _CAMERA_DEVICES if (path := str(hardware.get(name) or '').strip())]
    return LaunchPlan(tuple(words), environment=(('ROS_DOMAIN_ID', domain_for(Mode.HARDWARE_PROTOTYPE, profiles, environ)),),
                      notice='PROTOTYPE：估計校正，CM-530 電源開關是唯一急停')


def workspace_from_prefix(prefix):
    """<workspace>/install/dual_arm_hmi gives <workspace>."""
    return str(Path(prefix).resolve().parent.parent)


def journal_settings(state):
    return state.get('journal_path') or str(Path('~/.ros/dual_arm_hmi/journals/sim_journal.json').expanduser())


def new_journal_path(stamp):
    return str(Path(f'~/.ros/dual_arm_hmi/journals/sim_journal_{stamp}.json').expanduser())


def as_environment(values: Dict[str, str]):
    return {key: str(value) for key, value in values.items()}
