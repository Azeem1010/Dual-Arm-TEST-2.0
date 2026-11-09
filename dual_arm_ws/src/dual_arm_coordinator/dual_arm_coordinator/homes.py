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


def _from_calibration(path):
    data = yaml.safe_load(Path(path).read_text(encoding='utf-8'))
    if data.get('status') != 'PASS' or data.get('evidence_kind') != 'physical' or data.get('hardware_use_allowed') is not True:
        raise ValueError('HOME needs a calibration with status PASS, physical evidence and hardware use allowed')
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
