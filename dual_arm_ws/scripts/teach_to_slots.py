"""Taught C-slot readings to the prototype c_slot_teach block, with a model report; reads files only.

Usage: teach_to_slots.py [--csv-dir DIR | --from-config] [--config YAML] [--calibration YAML]

Takes the last READ of teach_arm2_C_<n>.csv (n = 1..8) in --csv-dir (or, with
--from-config, the counts already in c_slot_teach.raw), converts it
with the calibration the driver uses, and prints:
  - the raw block to paste under c_slot_teach.raw;
  - per slot, the model TCP of the taught pose, its tool tilt, the approach pose
    straight above it (j1 change in counts), the drift of the joint line between
    them, and the distance to the configured zones.c_slots_xy_m;
  - when the config has b_teach, the same for both arms' taught B pose.
The model numbers carry the estimated zeros; the taught counts themselves do not.
"""
import argparse
import csv
import math
from pathlib import Path
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src/dual_arm_coordinator'))
from dual_arm_coordinator.homes import load_b_joints, load_slot_joints  # noqa: E402
from dual_arm_coordinator.kinematics import CadKinematics  # noqa: E402
from dual_arm_coordinator.motion_math import (joint_line, line_drift, prepare_b_poses, prepare_slot_poses,  # noqa: E402
                                              tcp_position, tool_tilt_deg)

URDF = ROOT / 'src/dual_arm_description/urdf/dual_arm_cad.urdf.xacro'
CONFIG = ROOT / 'src/dual_arm_coordinator/config/prototype/coordinator.yaml'
CALIBRATION = ROOT / 'src/cm530_hardware/config/calibration_prototype.yaml'
CSV_DIR = ROOT / 'docs/evidence/hardware/20261111_H1'
RAD_PER_COUNT = math.radians(300.0) / 1023.0


def last_read(path):
    with open(path, newline='', encoding='utf-8') as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f'{path} has no readings')
    return [int(rows[-1][name]) for name in ('j1', 'j2', 'j3', 'j4')]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--csv-dir', type=Path, default=CSV_DIR)
    parser.add_argument('--config', type=Path, default=CONFIG)
    parser.add_argument('--calibration', type=Path, default=CALIBRATION)
    parser.add_argument('--from-config', action='store_true',
                        help='report the counts already in c_slot_teach.raw instead of the CSV files')
    args = parser.parse_args(argv)

    config = yaml.safe_load(args.config.read_text(encoding='utf-8'))
    if args.from_config:
        raw = config['c_slot_teach']['raw']
    else:
        raw = [last_read(args.csv_dir / f'teach_arm2_C_{slot}.csv') for slot in range(1, 9)]
    teach = dict(config.get('c_slot_teach') or {'release_lift_m': 0.0})
    teach.update(arm='arm2', raw=raw)
    joints = load_slot_joints({'c_slot_teach': teach}, calibration_path=str(args.calibration))
    model = CadKinematics(URDF.read_text(encoding='utf-8'), 'arm2', config['motion']['max_tool_tilt_deg'])
    poses = prepare_slot_poses(model, joints['release'], teach, config['heights']['approach_z_m'])

    print('c_slot_teach.raw (j1, j2, j3, j4):')
    for slot, counts in enumerate(raw, start=1):
        print(f'    - [{", ".join(map(str, counts))}]   # C{slot}')
    print()
    print('slot  release TCP x,y,z mm   tilt deg  above z mm  above tilt  above j1 counts  line drift mm  '
          'to c_slots_xy_m mm')
    for slot, (pose, xy) in enumerate(zip(poses, config['zones']['c_slots_xy_m']), start=1):
        x, y, z = (1000 * value for value in tcp_position(model, pose['release']))
        tilt = tool_tilt_deg(model, pose['release'])
        above_tilt = tool_tilt_deg(model, pose['above'])
        j1 = (pose['above'][0] - pose['release'][0]) / RAD_PER_COUNT
        drift = 1000 * line_drift(model, joint_line(pose['above'], pose['release'], 0.01))
        gap = 1000 * math.hypot(pose['xy'][0] - xy[0], pose['xy'][1] - xy[1])
        print(f'C{slot}   {x:6.1f} {y:6.1f} {z:5.1f}    {tilt:5.1f}    {1000 * pose["above_z"]:6.1f}      '
              f'{above_tilt:5.1f}       {j1:+6.2f}          {drift:6.2f}         {gap:6.1f}')
    if config.get('b_teach'):
        report_b(config, args.calibration)
    return 0


def report_b(config, calibration):
    """The b_teach block of the config: both arms' contact pose, approach above it, drift, distance."""
    teach = config['b_teach']
    joints = load_b_joints(config, calibration_path=str(calibration))
    urdf = URDF.read_text(encoding='utf-8')
    models = {arm: CadKinematics(urdf, arm, config['motion']['max_tool_tilt_deg']) for arm in joints}
    poses = prepare_b_poses(models, joints, teach['contact_lift_m'], config['heights']['approach_z_m'])
    b_place = config['zones']['b_place_xy_m']
    print()
    print(f'b_teach ({teach["source"]}):')
    print('arm   raw                   contact TCP x,y,z mm   tilt deg  above z mm  line drift mm  '
          'to b_place_xy_m mm')
    for arm, pose in poses.items():
        x, y, z = (1000 * value for value in tcp_position(models[arm], pose['release']))
        tilt = tool_tilt_deg(models[arm], pose['release'])
        drift = 1000 * line_drift(models[arm], joint_line(pose['above'], pose['release'], 0.01))
        gap = 1000 * math.hypot(pose['xy'][0] - b_place[0], pose['xy'][1] - b_place[1])
        print(f'{arm}  {str(teach["raw"][arm]):20s}  {x:6.1f} {y:6.1f} {z:5.1f}     {tilt:5.1f}    '
              f'{1000 * pose["above_z"]:6.1f}       {drift:6.2f}         {gap:6.1f}')
    first, second = poses['arm1']['xy'], poses['arm2']['xy']
    print(f'arm1 to arm2 contact points: {1000 * math.hypot(first[0] - second[0], first[1] - second[1]):.1f} mm')


if __name__ == '__main__':
    sys.exit(main())
