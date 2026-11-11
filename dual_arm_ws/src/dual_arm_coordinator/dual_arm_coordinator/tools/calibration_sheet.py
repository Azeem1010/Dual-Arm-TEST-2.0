"""Offline check of a joint calibration worksheet. Opens no port and writes no file.

It reports candidate zero_raw and direction values for a person to review; only a
person may copy them into calibration.yaml. Acceptance limits have no defaults
because they must be derived from measured clearances.
"""
import argparse
import json
import math
from pathlib import Path
import sys

import numpy as np
import yaml

from ..kinematics import CadKinematics
from ..motion_math import tcp_error, tool_tilt_deg

COUNTS_PER_RADIAN = 1023.0 / math.radians(300.0)
JOINT_SUFFIXES = ('arm_shoulder_pan_joint', 'arm_shoulder_lift_joint', 'arm_elbow_flex_joint', 'arm_wrist_flex_joint')
MIN_SAMPLES = 3
MIN_VERIFICATION_POSES = 3
_LIMITS = ('max_fit_ticks', 'min_span_rad', 'max_position_error_m', 'max_tilt_error_deg')


class SheetError(ValueError):
    """The worksheet is incomplete or inconsistent."""


def _number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise SheetError(f'{name} must be a measured finite number')
    return float(value)


def fit_joint(samples):
    """Best zero_raw and direction for the AX-12 scale; returns (zero_raw, direction, worst residual in ticks)."""
    angles = np.array([sample[0] for sample in samples])
    raws = np.array([sample[1] for sample in samples])
    best = None
    for direction in (1, -1):
        predicted = direction * angles * COUNTS_PER_RADIAN
        zero = float(np.mean(raws - predicted))
        residual = float(np.max(np.abs(raws - (zero + predicted))))
        if best is None or residual < best[2]:
            best = (zero, direction, residual)
    return best


def _samples(entry, name):
    if not isinstance(entry, dict) or not isinstance(entry.get('samples'), list):
        raise SheetError(f'{name} needs a samples list')
    if len(entry['samples']) < MIN_SAMPLES:
        raise SheetError(f'{name} needs at least {MIN_SAMPLES} samples')
    return [(_number(item.get('angle_rad'), f'{name} angle_rad'), _number(item.get('raw'), f'{name} raw')) for item in entry['samples']]


def _vector(value, length, name):
    if not isinstance(value, list) or len(value) != length:
        raise SheetError(f'{name} must list {length} values')
    return [_number(item, name) for item in value]


def check_sheet(sheet, urdf_text):
    """Return a report; status is PASS only when every limit is met."""
    if not isinstance(sheet, dict):
        raise SheetError('Worksheet must be a mapping')
    acceptance = sheet.get('acceptance') or {}
    limits = {name: _number(acceptance.get(name), f'acceptance.{name}') for name in _LIMITS}
    arms = sheet.get('arms')
    if not isinstance(arms, list) or not arms or any(arm not in ('arm1', 'arm2') for arm in arms):
        raise SheetError('arms must list arm1 and/or arm2')
    problems, joints = [], {}
    report = {'written_to_calibration': False, 'joints': joints, 'verification': []}
    for arm in arms:
        fitted = []
        for suffix in JOINT_SUFFIXES:
            name = f'{arm}_{suffix}'
            samples = _samples((sheet.get('joints') or {}).get(name), name)
            zero, direction, residual = fit_joint(samples)
            span = max(item[0] for item in samples) - min(item[0] for item in samples)
            joints[name] = {'zero_raw': zero, 'direction': direction, 'max_residual_ticks': residual, 'span_rad': span}
            fitted.append((zero, direction))
            if span < limits['min_span_rad']:
                problems.append(f'{name}: angle span {span:.3f} rad is too small')
            if residual > limits['max_fit_ticks']:
                problems.append(f'{name}: residual {residual:.2f} ticks is too large')
        poses = (sheet.get('verification') or {}).get(arm)
        if not isinstance(poses, list) or len(poses) < MIN_VERIFICATION_POSES:
            raise SheetError(f'{arm} needs at least {MIN_VERIFICATION_POSES} independent verification poses')
        model = CadKinematics(urdf_text, arm)
        for index, pose in enumerate(poses):
            label = f'{arm} verification {index + 1}'
            raw = _vector(pose.get('raw'), 4, f'{label} raw')
            tcp = _vector(pose.get('tcp_m'), 3, f'{label} tcp_m')
            tilt = _number(pose.get('tilt_deg'), f'{label} tilt_deg')
            q = [direction * (count - zero) / COUNTS_PER_RADIAN for count, (zero, direction) in zip(raw, fitted)]
            position_error, tilt_error = tcp_error(model, q, tcp), abs(tool_tilt_deg(model, q) - tilt)
            report['verification'].append({'pose': label, 'position_error_m': position_error, 'tilt_error_deg': tilt_error})
            if position_error > limits['max_position_error_m']:
                problems.append(f'{label}: position error {position_error * 1000:.1f} mm is too large')
            if tilt_error > limits['max_tilt_error_deg']:
                problems.append(f'{label}: tilt error {tilt_error:.2f} deg is too large')
    report['status'] = 'FAIL' if problems else 'PASS'
    report['problems'] = problems
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description='Check a calibration worksheet offline. Moves nothing and writes nothing.')
    parser.add_argument('worksheet')
    parser.add_argument('--urdf', default='')
    args = parser.parse_args(argv)
    try:
        urdf_path = args.urdf
        if not urdf_path:
            from ament_index_python.packages import get_package_share_directory
            urdf_path = str(Path(get_package_share_directory('dual_arm_description')) / 'urdf' / 'dual_arm_cad.urdf.xacro')
        sheet = yaml.safe_load(Path(args.worksheet).read_text(encoding='utf-8'))
        report = check_sheet(sheet, Path(urdf_path).read_text(encoding='utf-8'))
    except (OSError, SheetError, yaml.YAMLError) as error:
        print(json.dumps({'status': 'FAIL', 'written_to_calibration': False, 'error': str(error)}))
        return 1
    print(json.dumps(report, indent=2))
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
