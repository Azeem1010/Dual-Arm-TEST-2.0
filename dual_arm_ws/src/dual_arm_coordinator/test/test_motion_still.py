"""MotionGateway._wait_still: a move starts only once the arm has stopped (field runs 2026-11-17)."""
import math
import unittest

from dual_arm_coordinator.gateways import motion
from dual_arm_coordinator.gateways.motion import MotionGateway
from dual_arm_coordinator.workflow.ports import TaskCancelled, TaskFault

COUNT = math.radians(300.0) / 1023.0


class Clock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class Still(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self._saved = motion.time.monotonic, motion.time.sleep
        motion.time.monotonic, motion.time.sleep = self.clock.monotonic, self.clock.sleep
        self.addCleanup(self._restore)
        self.gateway = MotionGateway.__new__(MotionGateway)
        self.gateway._cfg = {'settle_s': 0.5, 'arrival_timeout_s': 30.0, 'joint_state_max_age_s': 1.0}
        self.gateway._guard = lambda: None
        self.path, self.reads = None, 0
        self.gateway._sample = self.sample

    def _restore(self):
        motion.time.monotonic, motion.time.sleep = self._saved

    def sample(self, _arm):
        """A new joint reading every 10 ms, from self.path(time)."""
        self.reads += 1
        return self.path(self.clock.now), int(self.clock.now * 100), 0.0

    def test_waits_until_a_sagging_joint_stops(self):
        # Sags 6 counts over the first 2 s, then holds.
        self.path = lambda t: [0.0, -6 * COUNT * min(t, 2.0) / 2.0, 0.0, 0.0]
        self.gateway._wait_still('arm1', 'arm1 home')
        # Not while it still sags (3 counts/s), and within two windows after it stops.
        self.assertGreaterEqual(self.clock.now, 2.0)
        self.assertLess(self.clock.now, 3.1)

    def test_a_faster_sag_is_never_taken_as_still(self):
        # 3 counts/s for 5 s: every window sees more than one count of movement.
        self.path = lambda t: [0.0, -3 * COUNT * min(t, 5.0), 0.0, 0.0]
        self.gateway._wait_still('arm1', 'arm1 home')
        self.assertGreaterEqual(self.clock.now, 5.0)

    def test_a_still_arm_waits_two_windows(self):
        self.path = lambda t: [0.1, 0.2, 0.3, 0.4]
        self.gateway._wait_still('arm1', 'arm1 home')
        self.assertLess(self.clock.now, 1.1)

    def test_one_count_flicker_counts_as_still(self):
        self.path = lambda t: [0.0, COUNT * (int(t * 100) % 2), 0.0, 0.0]
        self.gateway._wait_still('arm1', 'arm1 home')
        self.assertLess(self.clock.now, 1.1)

    def test_a_hunting_joint_counts_as_still(self):
        # Field 2026-11-17: the arm2 elbow swung 4 counts at rest; the old range test never passed.
        self.path = lambda t: [0.0, 0.0, 2 * COUNT * math.sin(2 * math.pi * 3.0 * t), 0.0]
        self.gateway._wait_still('arm2', 'arm2 home')
        self.assertLess(self.clock.now, 1.6)

    def test_an_arm_that_never_stops_faults(self):
        self.path = lambda t: [0.0, 0.05 * t, 0.0, 0.0]
        with self.assertRaises(TaskFault) as caught:
            self.gateway._wait_still('arm1', 'arm1 home')
        self.assertIn('did not stop moving', str(caught.exception))

    def test_stale_readings_do_not_count(self):
        self.path = lambda t: [0.0, 0.0, 0.0, 0.0]
        self.gateway._sample = lambda arm: (self.path(self.clock.now), int(self.clock.now * 100), 5.0)
        with self.assertRaises(TaskFault):
            self.gateway._wait_still('arm1', 'arm1 home')

    def test_stop_request_ends_the_wait(self):
        self.path = lambda t: [0.0, 0.05 * t, 0.0, 0.0]

        def guard():
            if self.clock.now > 1.0:
                raise TaskCancelled('Task canceled')
        self.gateway._guard = guard
        with self.assertRaises(TaskCancelled):
            self.gateway._wait_still('arm1', 'arm1 home')

    def test_no_window_means_no_wait(self):
        self.gateway._cfg['settle_s'] = None
        self.path = None
        self.gateway._wait_still('arm1', 'arm1 home')
        self.assertEqual(self.reads, 0)


if __name__ == '__main__':
    unittest.main()
