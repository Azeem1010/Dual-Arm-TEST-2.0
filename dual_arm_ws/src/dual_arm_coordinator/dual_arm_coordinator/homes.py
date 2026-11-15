"""HOME joint angles per configured source. SRDF named states are never used.

The SRDF is generated from simulation values, so hardware HOME can only come
from a measured calibration file.
"""
import json
from pathlib import Path

import yaml

from .home_pose import convert_home

JOINT_SUFFIXES = ('arm_shoulder_pan_joint', 'arm_shoulder_lift_joint',
                  'arm_elbow_flex_joint', 'arm_wrist_flex_joint')
ARMS = ('arm1', 'arm2')


def _from_runtime(path):
    home = json.loads(Path(path).read_text(encoding='utf-8'))['home']
    return {arm: convert_home(home[arm]['raw'], home[arm]['raw_at_cad_zero'], home[arm]['direction'])
            for arm in ARMS}


def _read_calibration(path):
    data = yaml.safe_load(Path(path).read_text(encoding='utf-8'))
    if data.get('status') != 'PASS' or data.get('evidence_kind') != 'physical' or data.get('hardware_use_allowed') is not True:
        raise ValueError('HOME needs a calibration with status PASS, physical evidence and hardware use allowed')
    return data


def load_slot_joints(config, calibration_path=None):
    """Taught C-slot joints in radians, or None when the config has no c_slot_teach.

    The counts go through the same calibration file as the driver, which turns
    the radians back into exactly the taught counts; a wrong zero cannot move them.
    """
    teach = config.get('c_slot_teach')
    if teach is None:
        return None
    if calibration_path is None:
        raise ValueError('Taught slot joints need the calibration file the driver uses')
    data = _read_calibration(calibration_path)
    arm = teach['arm']
    poses = [_taught_joints(data, arm, raw, f'Slot {slot}') for slot, raw in enumerate(teach['raw'], start=1)]
    return {'arm': arm, 'release': poses}


def load_b_joints(config, calibration_path=None):
    """Taught B hand-over joints in radians per arm, or None when the config has no b_teach.

    Same conversion as load_slot_joints, so the motors receive exactly the taught counts.
    """
    teach = config.get('b_teach')
    if teach is None:
        return None
    if calibration_path is None:
        raise ValueError('Taught B joints need the calibration file the driver uses')
    data = _read_calibration(calibration_path)
    return {arm: _taught_joints(data, arm, teach['raw'][arm], f'B {arm}') for arm in ARMS}


def _taught_joints(data, arm, raw, label):
    joints = [data['joints'][f'{arm}_{suffix}'] for suffix in JOINT_SUFFIXES]
    for count, joint, suffix in zip(raw, joints, JOINT_SUFFIXES):
        if not joint['min_raw'] <= count <= joint['max_raw']:
            raise ValueError(f'{label} {suffix} count {count} is outside '
                             f'{joint["min_raw"]}..{joint["max_raw"]} of the calibration')
    return convert_home(raw, [joint['zero_raw'] for joint in joints], [joint['direction'] for joint in joints])


def _from_calibration(path):
    data = _read_calibration(path)
    homes = {}
    for arm in ARMS:
        joints = [data['joints'][f'{arm}_{suffix}'] for suffix in JOINT_SUFFIXES]
        homes[arm] = convert_home(data['expected_home'][arm], [joint['zero_raw'] for joint in joints],
                                  [joint['direction'] for joint in joints])
    return homes


def load_homes(config, runtime_path=None, calibration_path=None):
    source = config['home_source']
    if source == 'runtime_json':
        if config['mode'] != 'simulation' or runtime_path is None:
            raise ValueError('runtime.json HOME is only for simulation and needs its path')
        return _from_runtime(runtime_path)
    if source == 'calibration':
        if calibration_path is None:
            raise ValueError('Calibration HOME needs the calibration file path')
        return _from_calibration(calibration_path)
    raise ValueError(f'Unknown home_source {source}')
