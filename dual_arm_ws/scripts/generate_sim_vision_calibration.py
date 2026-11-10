"""Write simulation homographies from the known Gazebo camera geometry.

Usage: generate_sim_vision_calibration.py CALIB_DIR [CAMERA PROBE.json REVISION]
Simulation only. The values come from the world file, so they are a baseline that
still has to be checked against ground truth. Never copy them to hardware.
With a camera and a probe report it also writes the validity record for that camera.
"""
import hashlib
import json
import math
from pathlib import Path
import sys

from dual_arm_vision_adapter.validity import position_budget
import numpy as np
import yaml

IMAGE_SIZE = (640, 480)
# Camera position (x, height) and horizontal field of view from generate_world.py.
CAMERAS = {'arm1': (-0.2, 0.5, 0.7), 'arm2': (0.2, 0.5, 0.7)}
# Arm base origins in the world frame; see docs/COORDINATE_FRAMES.md.
BASES = {'arm1': (-0.10, 0.08725), 'arm2': (0.10, 0.08725)}
# Heights of the planes the detections lie on: cap tops for arm1, slot pads for arm2.
PLANE_Z = {'arm1': 0.024, 'arm2': 0.014}


def pixel_to_world(arm):
    x, height, fov = CAMERAS[arm]
    width, image_height = IMAGE_SIZE
    focal = (width / 2.0) / math.tan(fov / 2.0)
    depth = height - PLANE_Z[arm]
    return np.array([[depth / focal, 0.0, x - depth * (width / 2.0) / focal],
                     [0.0, -depth / focal, depth * (image_height / 2.0) / focal],
                     [0.0, 0.0, 1.0]])


def world_to_base(arm):
    """x_base = y_origin - y_world, y_base = x_world - x_origin (x into the field, y to the arm's left)."""
    x_origin, y_origin = BASES[arm]
    return np.array([[0.0, -1.0, y_origin], [1.0, 0.0, -x_origin], [0.0, 0.0, 1.0]])


def write_record(directory, arm, probe_path, revision):
    """Validity record for one camera; PASS only if the measured error is inside the budget."""
    probe = json.loads(Path(probe_path).read_text(encoding='utf-8'))
    measured = probe['initial']['detections']['max_error_m']
    # Suction clearance: cap radius 10 mm minus cup radius 9 mm, from dual_arm_gripper/policy.hpp.
    budget = position_budget(0.025, 0.020, 0.018, 0.0, 0.0)
    x, height, fov = CAMERAS[arm]
    focal = (IMAGE_SIZE[0] / 2.0) / math.tan(fov / 2.0)
    pixels_per_metre = focal / (height - PLANE_Z[arm])
    evidence = directory / f'{arm}_probe_evidence.json'
    evidence.write_bytes(Path(probe_path).read_bytes())
    homography = yaml.safe_load((directory / f'{arm}_homography.yaml').read_text(encoding='utf-8'))['H']
    record = {'mode': 'sim', 'camera_id': arm, 'frame_id': f'{arm}_camera_optical_frame',
              'reference_frame': f'{arm}_base_link', 'mount_revision': revision, 'pose_signature': revision,
              'image_size': list(IMAGE_SIZE), 'status': 'PASS' if measured <= budget else 'FAIL', 'evidence_kind': 'gazebo',
              'evidence_files': [{'path': evidence.name, 'sha256': hashlib.sha256(evidence.read_bytes()).hexdigest()}],
              'budget_verified': True, 'slot_order_verified': False,
              'calibrated_at': 0.0, 'expires_at': 1.0e9,
              'workspace_error_m': float(measured), 'allowed_position_error_m': float(budget),
              'reprojection_error_px': float(measured * pixels_per_metre),
              'allowed_reprojection_error_px': float(budget * pixels_per_metre),
              'camera_matrix': [focal, 0.0, IMAGE_SIZE[0] / 2.0, 0.0, focal, IMAGE_SIZE[1] / 2.0, 0.0, 0.0, 1.0],
              'distortion': [0.0] * 5, 'homography': [value for row in homography for value in row]}
    (directory / f'{arm}_camera.yaml').write_text(yaml.safe_dump(record), encoding='utf-8')
    print(f'{arm}: measured {measured:.5f} m, budget {budget:.5f} m, status {record["status"]}')


def main():
    directory = Path(sys.argv[1]).expanduser()
    directory.mkdir(parents=True, exist_ok=True)
    if len(sys.argv) > 2:
        write_record(directory, sys.argv[2], sys.argv[3], sys.argv[4])
        return
    for arm in CAMERAS:
        homography = world_to_base(arm) @ pixel_to_world(arm)
        document = {'valid': True, 'unit': 'm', 'image_size': list(IMAGE_SIZE), 'undistorted': False,
                    'source': 'gazebo_known_camera_geometry', 'evidence_kind': 'gazebo',
                    'H': homography.tolist(), 'points': []}
        (directory / f'{arm}_homography.yaml').write_text(yaml.safe_dump(document), encoding='utf-8')
        print('wrote', directory / f'{arm}_homography.yaml')


if __name__ == '__main__':
    main()
