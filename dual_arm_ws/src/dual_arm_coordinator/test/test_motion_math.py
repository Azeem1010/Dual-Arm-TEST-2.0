from pathlib import Path
import tempfile
import unittest

import numpy as np
import yaml

from dual_arm_coordinator.home_pose import convert_home
from dual_arm_coordinator.homes import load_homes
from dual_arm_coordinator.kinematics import CadKinematics
from dual_arm_coordinator.motion_math import (line_points, solve_line, tcp_error, tcp_position,
                                              tool_tilt_deg, trapezoid_times)

PACKAGE = Path(__file__).resolve().parents[1]
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
        self.assertEqual(homes['arm1'], convert_home([90, 567, 712, 825], [512] * 4, [1] * 4))
        self.assertEqual(homes['arm2'], convert_home([590, 567, 712, 825], [512] * 4, [1] * 4))

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


if __name__ == '__main__':
    unittest.main()
