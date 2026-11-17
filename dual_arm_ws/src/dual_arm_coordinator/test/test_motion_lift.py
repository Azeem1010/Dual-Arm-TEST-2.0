"""Vertical lift that keeps the cup's orientation (field run 2026-11-17, arm 1 releasing in B)."""
import math
from pathlib import Path
import unittest

import numpy as np

from dual_arm_coordinator.gateways.motion import MotionGateway
from dual_arm_coordinator.kinematics import CadKinematics
from dual_arm_coordinator.motion_math import (line_points, solve_line, solve_line_holding_tool, tcp_position,
                                              tool_tilt_deg)
from dual_arm_coordinator.workflow.ports import TaskFault

PACKAGE = Path(__file__).resolve().parents[1]
URDF = PACKAGE.parent / 'dual_arm_description' / 'urdf' / 'dual_arm_cad.urdf.xacro'
COUNT = math.radians(300.0) / 1023.0
# arm1's taught B release (350, 731, 702, 697) through calibration_prototype.yaml, in radians.
RELEASE = [(350 - 192.3) * COUNT, (731 - 631.35) * COUNT, (702 - 699.55) * COUNT, (697 - 512) * COUNT]


class HoldingTool(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = CadKinematics(URDF.read_text(encoding='utf-8'), 'arm1', 12.0)

    def lift(self, start, z=0.057):
        p = tcp_position(self.model, start)
        return p, solve_line_holding_tool(self.model, start, line_points(p, (p[0], p[1], z), 0.002), 0.15)

    def test_the_tilted_taught_pose_lifts_straight_up(self):
        self.assertGreater(tool_tilt_deg(self.model, RELEASE), 3.0)
        start, path = self.lift(RELEASE)
        for q in path:
            tcp = tcp_position(self.model, q)
            self.assertLess(math.hypot(tcp[0] - start[0], tcp[1] - start[1]), 1e-4)
            self.assertAlmostEqual(q[0], RELEASE[0], places=6)  # the base does not turn
            self.assertAlmostEqual(tool_tilt_deg(self.model, q), tool_tilt_deg(self.model, RELEASE), places=3)
        self.assertAlmostEqual(float(tcp_position(self.model, path[-1])[2]), 0.057, places=4)

    def test_a_release_off_the_taught_j1_stays_where_it_is(self):
        start_q = list(RELEASE)
        start_q[0] -= 2 * COUNT
        _start, path = self.lift(start_q)
        self.assertTrue(all(abs(q[0] - start_q[0]) < 1e-6 for q in path))

    def test_the_downward_solver_cannot_do_this(self):
        # Why the lift needs its own solver: forcing the cup down flips the wrist at once.
        p = tcp_position(self.model, RELEASE)
        with self.assertRaises(ValueError):
            solve_line(self.model, RELEASE, line_points(p, (p[0], p[1], 0.057), 0.002), 0.15)


class LiftVertical(unittest.TestCase):
    def setUp(self):
        self.gateway = MotionGateway.__new__(MotionGateway)
        self.gateway._models = {'arm1': CadKinematics(URDF.read_text(encoding='utf-8'), 'arm1', 12.0)}
        self.gateway._cfg = {'waypoint_step_m': 0.002, 'waypoint_joint_jump_rad': 0.15}
        self.gateway._wait_still = lambda arm, label: None
        self.gateway.current = lambda arm: list(RELEASE)
        self.paths, self.reports = [], []
        self.gateway._execute_path = lambda arm, path, label: self.paths.append(path) or path[-1]
        self.gateway._confirm_arrival = lambda arm, xyz, label: None
        self.gateway._report_arrival = lambda arm, xyz, commanded, label: self.reports.append(xyz)

    def test_sends_a_straight_path_up_from_the_current_tool(self):
        self.gateway.lift_vertical('arm1', 0.057)
        start = tcp_position(self.gateway._models['arm1'], RELEASE)
        self.assertEqual(len(self.paths), 1)
        np.testing.assert_allclose(self.reports[0], (start[0], start[1], 0.057))

    def test_refuses_to_go_down(self):
        with self.assertRaises(TaskFault):
            self.gateway.lift_vertical('arm1', 0.01)
        self.assertEqual(self.paths, [])


if __name__ == '__main__':
    unittest.main()
