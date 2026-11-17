"""Prototype fixed_transits: a non-contact move runs a checked joint line instead of a MoveIt plan (2026-11-17)."""
import itertools
from pathlib import Path
import unittest

from dual_arm_coordinator.gateways import motion
from dual_arm_coordinator.gateways.motion import MotionGateway
from dual_arm_coordinator.kinematics import CadKinematics
from dual_arm_coordinator.motion_math import trapezoid_times
from dual_arm_coordinator.workflow.ports import TaskCancelled, TaskFault

PACKAGE = Path(__file__).resolve().parents[1]
URDF = PACKAGE.parent / 'dual_arm_description' / 'urdf' / 'dual_arm_cad.urdf.xacro'


def solve(model, xyz):
    for seed in itertools.product((-1.0, 0.0, 1.0), (-0.6, 0.0, 0.6), (-1.0, 0.0, 1.0), (-1.0, 0.0, 1.0)):
        try:
            return [float(value) for value in model.solve(xyz, list(seed))]
        except ValueError:
            pass
    raise ValueError(xyz)


class Logger:
    def __init__(self):
        self.lines = []

    def info(self, text):
        self.lines.append(('info', text))

    def warning(self, text):
        self.lines.append(('warning', text))


class FixedTransit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = CadKinematics(URDF.read_text(encoding='utf-8'), 'arm1', 9.0)
        cls.above_a = solve(cls.model, (-0.20, 0.0, 0.052))
        cls.above_b = solve(cls.model, (0.0, 0.0, 0.052))

    def setUp(self):
        g = self.gateway = MotionGateway.__new__(MotionGateway)
        g._models = {'arm1': self.model}
        g._cfg = {'max_velocity_rad_s': 0.5, 'max_acceleration_rad_s2': 1.0, 'planning_s': 10.0,
                  'planning_attempts': 3}
        g._speeds = {'transport_scale': 0.6, 'contact_scale': 0.2, 'acceleration_scale': 0.3}
        g._arms = {'arm1': {'planning_group': 'arm1', 'controller': 'arm1_controller'}}
        g._move_group, g._execute = 'move_group', 'execute'
        g._fixed_transits, g._lanes = True, None
        self.logger = Logger()
        g._node = type('Node', (), {'get_logger': lambda _self: self.logger})()
        g._wait_still = lambda arm, label: None
        g.current = lambda arm: list(self.above_a)
        self.checked, self.actions = [], []
        g._require_valid_all = lambda arm, path, label: self.checked.append(path)
        g._run_action = lambda client, goal, label: self.actions.append((client, goal))

    def test_runs_the_checked_joint_line_without_planning(self):
        self.gateway._plan_and_move('arm1', self.above_b, 'arm1 above B')
        self.assertEqual([client for client, _ in self.actions], ['execute'])
        trajectory = self.actions[0][1].trajectory.joint_trajectory
        points = [list(point.positions) for point in trajectory.points]
        self.assertEqual(points[0], self.above_a)
        for actual, wanted in zip(points[-1], self.above_b):
            self.assertAlmostEqual(actual, wanted)
        # Every waypoint after the start was checked, as for contact lines.
        self.assertEqual(len(self.checked), 1)
        self.assertEqual(len(self.checked[0]), len(points) - 1)
        self.assertEqual(self.actions[0][1].controller_names, ['arm1_controller'])

    def test_runs_at_transport_speed(self):
        self.gateway._plan_and_move('arm1', self.above_b, 'arm1 above B')
        trajectory = self.actions[0][1].trajectory.joint_trajectory
        path = [list(point.positions) for point in trajectory.points]
        last = trajectory.points[-1].time_from_start
        self.assertAlmostEqual(last.sec + last.nanosec * 1e-9, trapezoid_times(path, 0.3, 0.3)[-1], places=6)

    def test_switched_off_plans_with_moveit(self):
        self.gateway._fixed_transits = False
        self.gateway._plan_and_move('arm1', self.above_b, 'arm1 above B')
        self.assertEqual([client for client, _ in self.actions], ['move_group'])
        self.assertEqual(self.checked, [])

    def test_a_colliding_waypoint_falls_back_to_moveit(self):
        def refuse(arm, path, label):
            raise TaskFault(f'{label}: state is invalid')
        self.gateway._require_valid_all = refuse
        self.gateway._plan_and_move('arm1', self.above_b, 'arm1 above B')
        self.assertEqual([client for client, _ in self.actions], ['move_group'])
        self.assertTrue(any(level == 'warning' and 'MoveIt' in text for level, text in self.logger.lines))

    def test_a_path_dipping_below_its_ends_falls_back_to_moveit(self):
        # The board has no collision geometry, so a joint line that lowers the tool is not taken.
        saved = motion._FIXED_DIP_M
        motion._FIXED_DIP_M = -1.0  # every path now counts as dipping
        self.addCleanup(setattr, motion, '_FIXED_DIP_M', saved)
        self.gateway._plan_and_move('arm1', self.above_b, 'arm1 above B')
        self.assertEqual([client for client, _ in self.actions], ['move_group'])
        self.assertEqual(self.checked, [])

    def test_a_cancel_during_the_checks_is_not_turned_into_a_fallback(self):
        def cancel(arm, path, label):
            raise TaskCancelled('Task canceled')
        self.gateway._require_valid_all = cancel
        with self.assertRaises(TaskCancelled):
            self.gateway._plan_and_move('arm1', self.above_b, 'arm1 above B')
        self.assertEqual(self.actions, [])

    def test_the_line_from_a_to_b_stays_above_its_ends(self):
        """The real prototype transit A -> B passes the dip check on the model."""
        path = motion.joint_line(self.above_a, self.above_b, motion._JOINT_LINE_STEP_RAD)
        self.assertIsNone(self.gateway._fixed_problem('arm1', path))


if __name__ == '__main__':
    unittest.main()
