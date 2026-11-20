from pathlib import Path
import tempfile
import unittest

import numpy as np
import yaml

from dual_arm_coordinator.home_pose import convert_home
from dual_arm_coordinator.homes import load_b_joints, load_homes, load_slot_joints
from dual_arm_coordinator.kinematics import CadKinematics
from dual_arm_coordinator.motion_math import (MIN_SLOT_CLEARANCE_M, SLOT_APPROACH_STEP_M, joint_line, line_drift,
                                              line_points, prepare_b_poses, prepare_slot_poses, solve_line, tcp_error,
                                              tcp_position, tool_tilt_deg, trapezoid_times)

PACKAGE = Path(__file__).resolve().parents[1]
PROTOTYPE_CONFIG = PACKAGE / 'config' / 'prototype' / 'coordinator.yaml'
PROTOTYPE_CALIBRATION = PACKAGE.parent / 'cm530_hardware' / 'config' / 'calibration_prototype.yaml'
URDF = PACKAGE.parent / 'dual_arm_description' / 'urdf' / 'dual_arm_cad.urdf.xacro'
RUNTIME = PACKAGE / 'config' / 'sim' / 'runtime.json'
CALIBRATION = PACKAGE.parent / 'cm530_hardware' / 'config' / 'calibration.yaml'
SIM = {'mode': 'simulation', 'home_source': 'runtime_json'}
HARDWARE = {'mode': 'hardware', 'home_source': 'calibration'}


class Lines(unittest.TestCase):
    def test_points_end_exactly_and_respect_step(self):
        points = line_points([0, 0, 0.054], [0, 0, 0.0243], 0.002)
        self.assertEqual(len(points), 15)
        np.testing.assert_allclose(points[-1], [0, 0, 0.0243])
        gaps = np.linalg.norm(np.diff(np.array(points), axis=0), axis=1)
        self.assertLessEqual(gaps.max(), 0.002 + 1e-12)

    def test_zero_distance_has_no_points(self):
        self.assertEqual(line_points([1, 2, 3], [1, 2, 3], 0.002), [])

    def test_step_must_be_positive(self):
        with self.assertRaises(ValueError):
            line_points([0, 0, 0], [0, 0, 1], 0)


class JointPaths(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = CadKinematics(URDF.read_text(encoding='utf-8'), 'arm1')

    def test_descent_stays_on_line_with_tool_down(self):
        above, below = np.array([-0.14, -0.03, 0.054]), np.array([-0.14, -0.03, 0.0243])
        start = self.model.solve(above)
        path = solve_line(self.model, start, line_points(above, below, 0.002), 0.15)
        for q in path:
            position = tcp_position(self.model, q)
            np.testing.assert_allclose(position[:2], above[:2], atol=1e-4)
            self.assertLess(tool_tilt_deg(self.model, q), 0.5)
        self.assertLess(tcp_error(self.model, path[-1], below), 1e-4)

    def test_joint_jump_is_refused(self):
        above, below = [-0.14, -0.03, 0.054], [-0.14, -0.03, 0.0243]
        start = self.model.solve(above)
        with self.assertRaises(ValueError):
            solve_line(self.model, start, line_points(above, below, 0.002), 1e-6)

    def test_unreachable_target_is_refused(self):
        with self.assertRaises(ValueError):
            self.model.solve([1.0, 1.0, 0.05])


class TiltedSuction(unittest.TestCase):
    """Slot 8 (0.17, -0.055) has no straight-down solution; about 5 deg at contact."""
    SLOT_8 = [0.17, -0.055, 0.0243]

    @classmethod
    def setUpClass(cls):
        urdf = URDF.read_text(encoding='utf-8')
        cls.down = CadKinematics(urdf, 'arm2')
        cls.tilted = CadKinematics(urdf, 'arm2', 9.0)
        cls.tight = CadKinematics(urdf, 'arm2', 4.0)

    def test_straight_down_only_refuses_slot_8(self):
        with self.assertRaisesRegex(ValueError, 'downward suction axis'):
            self.down.solve(self.SLOT_8)

    def test_smallest_tilt_reaches_slot_8(self):
        q = self.tilted.solve(self.SLOT_8)
        self.assertLess(tcp_error(self.tilted, q, self.SLOT_8), 1e-5)
        self.assertGreater(tool_tilt_deg(self.tilted, q), 4.5)
        self.assertLess(tool_tilt_deg(self.tilted, q), 5.5)

    def test_tilt_above_the_limit_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'within 4 deg'):
            self.tight.solve(self.SLOT_8)

    def test_reachable_targets_stay_straight_down(self):
        q = self.tilted.solve([0.135, 0.05, 0.0243])
        self.assertLess(tool_tilt_deg(self.tilted, q), 0.3)

    def test_seeded_solution_keeps_the_shoulder_low(self):
        # From HOME the solution nearest the seed is used; the smallest-tilt one
        # (shoulder near 0.96 rad) collides with the base in MoveIt.
        home = [0.399, -0.329, 0.064, 1.602]
        q = self.tilted.solve([0.17, -0.055, 0.054], home)
        self.assertLess(tcp_error(self.tilted, q, [0.17, -0.055, 0.054]), 1e-5)
        self.assertLessEqual(tool_tilt_deg(self.tilted, q), 9.0 + 1e-6)
        self.assertLess(q[1], 0.8)

    def test_tilted_descent_has_no_branch_jump(self):
        start = self.tilted.solve([0.17, -0.055, 0.054], [0.399, -0.329, 0.064, 1.602])
        path = solve_line(self.tilted, start, line_points([0.17, -0.055, 0.054], self.SLOT_8, 0.002), 0.15)
        self.assertLess(tcp_error(self.tilted, path[-1], self.SLOT_8), 1e-5)
        self.assertLessEqual(max(tool_tilt_deg(self.tilted, q) for q in path), 9.0 + 1e-6)
        self.assertLess(max(q[1] for q in path), 0.8)

    def test_limit_must_be_in_range(self):
        for value in (-1.0, 90.0):
            with self.assertRaises(ValueError):
                CadKinematics(URDF.read_text(encoding='utf-8'), 'arm2', value)


class Timing(unittest.TestCase):
    def peak_speed(self, path, times):
        speeds = [max(abs(a - b) for a, b in zip(p, q)) / (t2 - t1)
                  for p, q, t1, t2 in zip(path, path[1:], times, times[1:])]
        return max(speeds)

    def test_times_start_at_zero_and_increase(self):
        path = [[value, 0, 0, 0] for value in np.linspace(0, 1, 50)]
        times = trapezoid_times(path, 0.25, 0.25)
        self.assertEqual(times[0], 0.0)
        self.assertTrue(all(b > a for a, b in zip(times, times[1:])))

    def test_long_move_cruises_at_the_limit(self):
        path = [[value, 0, 0, 0] for value in np.linspace(0, 2, 400)]
        times = trapezoid_times(path, 0.25, 0.25)
        self.assertLessEqual(self.peak_speed(path, times), 0.25 * 1.05)
        # 2 rad at 0.25 rad/s with one second ramps at each end.
        self.assertAlmostEqual(times[-1], 9.0, places=2)

    def test_short_move_is_triangular(self):
        path = [[value, 0, 0, 0] for value in np.linspace(0, 0.01, 11)]
        times = trapezoid_times(path, 0.25, 0.25)
        self.assertAlmostEqual(times[-1], 2 * (0.01 / 0.25) ** 0.5, places=3)

    def test_fastest_joint_sets_the_time(self):
        path = [[0, 0, 0, 0], [0.1, 1.0, 0, 0]]
        self.assertGreater(trapezoid_times(path, 0.5, 1.0)[-1], 2.0)

    def test_no_motion_has_no_times(self):
        self.assertEqual(trapezoid_times([[0, 0, 0, 0], [0, 0, 0, 0]], 0.5, 1.0), [])

    def test_limits_must_be_positive(self):
        with self.assertRaises(ValueError):
            trapezoid_times([[0, 0, 0, 0], [1, 0, 0, 0]], 0, 1)

    def test_repeated_points_keep_times_increasing(self):
        path = [[0, 0, 0, 0], [0.5, 0, 0, 0], [0.5, 0, 0, 0], [1, 0, 0, 0]]
        times = trapezoid_times(path, 0.5, 1.0)
        self.assertTrue(all(b > a for a, b in zip(times, times[1:])))


class Homes(unittest.TestCase):
    def calibration_file(self, folder, **changes):
        data = yaml.safe_load(CALIBRATION.read_text(encoding='utf-8'))
        data.update(status='PASS', evidence_kind='physical', hardware_use_allowed=True)
        for name, joint in data['joints'].items():
            joint.update(zero_raw=512, direction=1, min_raw=0, max_raw=1023)
        data.update(changes)
        path = Path(folder) / 'calibration.yaml'
        path.write_text(yaml.safe_dump(data), encoding='utf-8')
        return path

    def test_simulation_home_comes_from_runtime(self):
        homes = load_homes(SIM, runtime_path=RUNTIME)
        self.assertEqual(sorted(homes), ['arm1', 'arm2'])
        self.assertEqual(len(homes['arm1']), 4)

    def test_hardware_cannot_use_runtime_home(self):
        with self.assertRaises(ValueError):
            load_homes({'mode': 'hardware', 'home_source': 'runtime_json'}, runtime_path=RUNTIME)

    def test_shipped_calibration_template_is_refused(self):
        with self.assertRaises(ValueError):
            load_homes(HARDWARE, calibration_path=CALIBRATION)

    def test_measured_calibration_is_converted(self):
        with tempfile.TemporaryDirectory() as folder:
            homes = load_homes(HARDWARE, calibration_path=self.calibration_file(folder))
        # expected_home of the shipped calibration.yaml: firmware v18 HOME on both arms (1f24a25)
        self.assertEqual(homes['arm1'], convert_home([256, 512, 512, 512], [512] * 4, [1] * 4))
        self.assertEqual(homes['arm2'], convert_home([256, 512, 512, 512], [512] * 4, [1] * 4))

    def test_calibration_must_be_physical_and_authorized(self):
        for change in (dict(status='NOT_RUN'), dict(evidence_kind='none'), dict(hardware_use_allowed=False)):
            with self.subTest(change), tempfile.TemporaryDirectory() as folder:
                with self.assertRaises(ValueError):
                    load_homes(HARDWARE, calibration_path=self.calibration_file(folder, **change))

    def test_unmeasured_joint_is_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self.calibration_file(folder)
            data = yaml.safe_load(path.read_text(encoding='utf-8'))
            data['joints']['arm1_arm_elbow_flex_joint']['zero_raw'] = None
            path.write_text(yaml.safe_dump(data), encoding='utf-8')
            with self.assertRaises(ValueError):
                load_homes(HARDWARE, calibration_path=path)

    def test_paths_and_source_are_required(self):
        with self.assertRaises(ValueError):
            load_homes(SIM)
        with self.assertRaises(ValueError):
            load_homes(HARDWARE)
        with self.assertRaises(ValueError):
            load_homes({'mode': 'simulation', 'home_source': 'srdf'})


class JointLines(unittest.TestCase):
    def test_joint_line_ends_exactly_and_respects_step(self):
        path = joint_line([0, 0, 0, 0], [0.05, -0.02, 0, 0.031], 0.01)
        self.assertEqual(path[0], [0, 0, 0, 0])
        np.testing.assert_allclose(path[-1], [0.05, -0.02, 0, 0.031])
        self.assertLessEqual(np.abs(np.diff(np.array(path), axis=0)).max(), 0.01 + 1e-12)
        self.assertEqual(len(joint_line([1, 2, 3, 4], [1, 2, 3, 4], 0.01)), 2)
        with self.assertRaises(ValueError):
            joint_line([0] * 4, [1] * 4, 0)

    def test_drift_is_zero_on_a_straight_tcp_line_and_seen_on_a_curve(self):
        model = CadKinematics(URDF.read_text(encoding='utf-8'), 'arm2', 9.0)
        start = model.solve([0.13, -0.02, 0.05])
        straight = solve_line(model, start, line_points(tcp_position(model, start), [0.13, -0.02, 0.025], 0.002), 0.15)
        self.assertLess(line_drift(model, straight), 1e-5)
        swing = joint_line(start, [start[0] + 0.5] + list(start[1:]), 0.01)
        # A 0.5 rad j1 swing at about 0.13 m radius bows about 4 mm off the chord: past the 3 mm prototype limit.
        self.assertGreater(line_drift(model, swing), 0.003)


class SlotPoses(unittest.TestCase):
    """The prototype's taught counts through the estimated calibration (model only)."""

    @classmethod
    def setUpClass(cls):
        config = yaml.safe_load(PROTOTYPE_CONFIG.read_text(encoding='utf-8'))
        cls.teach, cls.approach_z = config['c_slot_teach'], config['heights']['approach_z_m']
        cls.taught = load_slot_joints(config, calibration_path=str(PROTOTYPE_CALIBRATION))['release']
        cls.model = CadKinematics(URDF.read_text(encoding='utf-8'), 'arm2', config['motion']['max_tool_tilt_deg'])
        cls.poses = prepare_slot_poses(cls.model, cls.taught, cls.teach, cls.approach_z)

    def test_release_is_the_taught_pose_and_above_keeps_j1(self):
        for slot, (q, pose) in enumerate(zip(self.taught, self.poses), start=1):
            with self.subTest(slot=slot):
                self.assertEqual(pose['release'], list(q))
                self.assertAlmostEqual(pose['above'][0], q[0], places=4)
                above = tcp_position(self.model, pose['above'])
                np.testing.assert_allclose(above, [*pose['xy'], pose['above_z']], atol=1e-5)
                self.assertGreaterEqual(pose['above_z'] - pose['release_z'], MIN_SLOT_CLEARANCE_M)

    def test_a_slot_approaches_lower_only_instead_of_tilting_further(self):
        # With the 11-11 teach slot 8 came in 2 mm lower; the 2026-11-18 re-teach reaches approach_z_m
        # everywhere. Either way: approach_z_m or whole steps below it, never past the tilt limit.
        for slot, pose in enumerate(self.poses, start=1):
            with self.subTest(slot=slot):
                steps = (self.approach_z - pose['above_z']) / SLOT_APPROACH_STEP_M
                self.assertGreaterEqual(steps, -1e-9)
                self.assertAlmostEqual(steps, round(steps), places=6)
                self.assertLessEqual(tool_tilt_deg(self.model, pose['above']), 9.0 + 1e-6)

    def test_vertical_joint_lines_stay_within_the_configured_drift(self):
        for slot, pose in enumerate(self.poses, start=1):
            with self.subTest(slot=slot):
                drift = line_drift(self.model, joint_line(pose['above'], pose['release'], 0.01))
                self.assertLess(drift, self.teach['max_line_drift_m'])

    def test_release_lift_raises_the_release_pose(self):
        poses = prepare_slot_poses(self.model, self.taught[:1], {**self.teach, 'release_lift_m': 0.003},
                                   self.approach_z)
        start = tcp_position(self.model, self.taught[0])
        np.testing.assert_allclose(tcp_position(self.model, poses[0]['release']), start + [0, 0, 0.003], atol=1e-5)

    def test_too_low_approach_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'Taught slot 1: approach height'):
            prepare_slot_poses(self.model, self.taught[:1], self.teach, self.poses[0]['release_z'] + 0.01)


class BPoses(unittest.TestCase):
    """The prototype's taught B counts of both arms through the estimated calibration (model only)."""

    @classmethod
    def setUpClass(cls):
        config = yaml.safe_load(PROTOTYPE_CONFIG.read_text(encoding='utf-8'))
        cls.teach, cls.approach_z = config['b_teach'], config['heights']['approach_z_m']
        cls.taught = load_b_joints(config, calibration_path=str(PROTOTYPE_CALIBRATION))
        urdf = URDF.read_text(encoding='utf-8')
        cls.models = {arm: CadKinematics(urdf, arm, config['motion']['max_tool_tilt_deg']) for arm in ('arm1', 'arm2')}
        cls.poses = prepare_b_poses(cls.models, cls.taught, cls.teach['contact_lift_m'], cls.approach_z)

    def test_contact_is_the_taught_pose_and_above_is_straight_over_it(self):
        for arm, pose in self.poses.items():
            with self.subTest(arm=arm):
                self.assertEqual(pose['release'], list(self.taught[arm]))
                self.assertAlmostEqual(pose['above'][0], self.taught[arm][0], places=4)
                np.testing.assert_allclose(tcp_position(self.models[arm], pose['above']),
                                           [*pose['xy'], pose['above_z']], atol=1e-5)
                self.assertEqual(pose['above_z'], self.approach_z)

    def test_both_arms_meet_near_the_b_centre(self):
        # Model only (estimated zeros): the two taught points are about 4 mm apart near b_place (0, 0).
        # Since the 2026-11-17 arm2 re-teach its contact lies 5 mm below arm 1's (pressed harder).
        first, second = self.poses['arm1'], self.poses['arm2']
        self.assertLess(np.hypot(*np.subtract(first['xy'], second['xy'])), 0.015)
        for pose in (first, second):
            self.assertLess(np.hypot(*pose['xy']), 0.03)
            self.assertLess(abs(pose['release_z'] - second['release_z']), 0.006)

    def test_vertical_joint_lines_stay_within_the_configured_drift(self):
        for arm, pose in self.poses.items():
            with self.subTest(arm=arm):
                drift = line_drift(self.models[arm], joint_line(pose['above'], pose['release'], 0.01))
                self.assertLess(drift, self.teach['max_line_drift_m'])

    def test_errors_name_the_arm(self):
        with self.assertRaisesRegex(ValueError, 'Taught B arm1: approach height'):
            prepare_b_poses(self.models, {'arm1': self.taught['arm1']}, 0.0, self.poses['arm1']['release_z'] + 0.01)


if __name__ == '__main__':
    unittest.main()


class FramePoints(unittest.TestCase):
    """Overlap lanes take the x range of every chain frame."""

    @classmethod
    def setUpClass(cls):
        urdf = URDF.read_text(encoding='utf-8')
        cls.models = {arm: CadKinematics(urdf, arm) for arm in ('arm1', 'arm2')}

    def test_last_frame_is_the_tcp_and_first_the_base(self):
        for arm, model in self.models.items():
            q = [0.1, -0.3, 0.5, 0.2]
            points = model.frame_points(q)
            np.testing.assert_allclose(points[-1], model.forward(q)[:3, 3])
            self.assertEqual(points.shape[1], 3)

    def test_arms_stand_on_their_own_side(self):
        upright = [0.0, 0.0, 0.0, 0.0]
        self.assertLess(self.models['arm1'].frame_points(upright)[:, 0].max(), 0.0)
        self.assertGreater(self.models['arm2'].frame_points(upright)[:, 0].min(), 0.0)
