"""MotionGateway._correct_descent: re-aim a contact descent that stopped short (field 2026-11-17)."""
import unittest

from dual_arm_coordinator.gateways.motion import InvalidState, MotionGateway
from dual_arm_coordinator.workflow.ports import TaskFault

TARGET = (-0.14, -0.03, 0.0223)


class Logger:
    def __init__(self):
        self.lines = []

    def warning(self, text):
        self.lines.append(text)

    info = warning


class Node:
    def __init__(self):
        self.logger = Logger()

    def get_logger(self):
        return self.logger


class Arm:
    """The tool stops `sag` metres above wherever it is aimed."""

    def __init__(self, sag, start_z):
        self.sag, self.z, self.aims = sag, start_z, []

    def move(self, _arm, xyz, _label):
        self.aims.append(xyz[2])
        self.z = xyz[2] + self.sag
        return [0.0, 0.0, 0.0, 0.0]


class Descent(unittest.TestCase):
    def make(self, sag, start_short):
        gateway = MotionGateway.__new__(MotionGateway)
        gateway._descent = {'tolerance_m': 0.002, 'max_extra_m': 0.005, 'attempts': 2}
        gateway._node = Node()
        gateway._heights = {'surface_z_m': 0.012}
        gateway._wait_still = lambda arm, label: None
        arm = Arm(sag, TARGET[2] + start_short)
        gateway._move_straight = arm.move
        gateway._tcp = lambda name: [TARGET[0], TARGET[1], arm.z]
        return gateway, arm

    def test_close_enough_is_left_alone(self):
        gateway, arm = self.make(sag=0.001, start_short=0.001)
        self.assertIsNone(gateway._correct_descent('arm1', TARGET, 'arm1 A'))
        self.assertEqual(arm.aims, [])

    def test_a_short_stop_is_re_aimed_by_the_shortfall(self):
        # Stops 3 mm short; aiming 3 mm lower lands within tolerance.
        gateway, arm = self.make(sag=0.003, start_short=0.003)
        self.assertIsNotNone(gateway._correct_descent('arm1', TARGET, 'arm1 A'))
        self.assertEqual(len(arm.aims), 1)
        self.assertAlmostEqual(arm.aims[0], TARGET[2] - 0.003)
        self.assertLessEqual(arm.z - TARGET[2], 0.002)
        self.assertIn('3.0 mm above the target', gateway._node.logger.lines[0])

    def test_extra_descent_is_capped(self):
        # Sags 8 mm whatever it is told: the aim never goes more than 5 mm below the target.
        gateway, arm = self.make(sag=0.008, start_short=0.008)
        with self.assertRaises(TaskFault) as caught:
            gateway._correct_descent('arm1', TARGET, 'arm1 A')
        self.assertTrue(all(aim >= TARGET[2] - 0.005 - 1e-12 for aim in arm.aims))
        self.assertIn('above the target', str(caught.exception))

    def test_a_colliding_correction_is_skipped_and_the_height_kept(self):
        # Field run 2026-11-18: the re-aim at a far zone A cap hit arm1 link_2/base in the model.
        gateway, arm = self.make(sag=0.003, start_short=0.003)

        def collide(_arm, xyz, label):
            arm.aims.append(xyz[2])
            raise InvalidState(f"{label}: state is invalid ['arm1_cad_link_2/arm1_base_link']")
        gateway._move_straight = collide
        self.assertIsNone(gateway._correct_descent('arm1', TARGET, 'arm1 A'))
        self.assertEqual(len(arm.aims), 1)
        self.assertIn('correction skipped', gateway._node.logger.lines[-1])

    def test_other_faults_during_a_correction_still_stop(self):
        gateway, arm = self.make(sag=0.003, start_short=0.003)

        def fail(_arm, _xyz, label):
            raise TaskFault(f'{label}: controller aborted')
        gateway._move_straight = fail
        with self.assertRaises(TaskFault):
            gateway._correct_descent('arm1', TARGET, 'arm1 A')

    def test_attempts_are_limited(self):
        gateway, arm = self.make(sag=0.0045, start_short=0.0045)
        gateway._descent = {'tolerance_m': 0.002, 'max_extra_m': 0.01, 'attempts': 1}
        # One re-aim of 4.5 mm lands at the target: fine within one attempt.
        gateway._correct_descent('arm1', TARGET, 'arm1 A')
        self.assertEqual(len(arm.aims), 1)

    def test_never_aims_into_the_board(self):
        # Zone A press 6 mm: target 16.3 mm. Held up by the cap 4 mm short, the correction may go
        # only to 13 mm (1 mm above the 12 mm board), not 5 mm below the target.
        deep = (TARGET[0], TARGET[1], 0.0163)
        gateway, arm = self.make(sag=0.0, start_short=0.0)
        arm.z = 0.020

        def held_up(_arm, xyz, _label):
            arm.aims.append(xyz[2])
            arm.z = max(xyz[2], 0.020)  # the cap stops the cup at 20 mm
            return [0.0] * 4
        gateway._move_straight = held_up
        with self.assertRaises(TaskFault):
            gateway._correct_descent('arm1', deep, 'arm1 A')
        self.assertTrue(arm.aims)
        self.assertTrue(all(aim >= 0.013 - 1e-12 for aim in arm.aims))

    def test_never_aims_above_where_it_already_is(self):
        gateway, arm = self.make(sag=0.003, start_short=0.003)
        gateway._correct_descent('arm1', TARGET, 'arm1 A')
        self.assertTrue(all(aim < TARGET[2] for aim in arm.aims))


if __name__ == '__main__':
    unittest.main()
