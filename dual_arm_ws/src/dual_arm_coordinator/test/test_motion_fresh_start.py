"""MotionGateway._fresh_start: a trajectory starts where the arm is now (field 2026-11-17)."""
import math
import unittest

from dual_arm_coordinator.gateways.motion import MotionGateway
from dual_arm_coordinator.workflow.ports import TaskFault

COUNT = math.radians(300.0) / 1023.0
PATH = [[0.0, 0.5, 0.5, 0.0], [0.0, 0.52, 0.48, 0.0], [0.0, 0.54, 0.46, 0.0]]


class FreshStart(unittest.TestCase):
    def make(self, now):
        gateway = MotionGateway.__new__(MotionGateway)
        gateway.current = lambda arm: now
        return gateway

    def test_a_crept_joint_becomes_the_start(self):
        # The elbow crept 3 counts while the waypoints were checked: more than 0.01 rad.
        now = [0.0, 0.5, 0.5 - 3 * COUNT, 0.0]
        path = self.make(now)._fresh_start('arm1', PATH, 'arm1 lift')
        self.assertEqual(path[0], now)
        self.assertEqual(path[1:], PATH[1:])

    def test_a_large_change_is_refused(self):
        now = [0.0, 0.5, 0.5 - 12 * COUNT, 0.0]
        with self.assertRaises(TaskFault) as caught:
            self.make(now)._fresh_start('arm1', PATH, 'arm1 lift')
        self.assertIn('moved 12.0 counts', str(caught.exception))


if __name__ == '__main__':
    unittest.main()
