import unittest

from dual_arm_coordinator.safety_monitor import SafetyMonitor

ESTOP_AGE, PERMIT_AGE = 2.0, 1.0


class Base(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.monitor = SafetyMonitor(ESTOP_AGE, PERMIT_AGE, clock=lambda: self.now)

    def healthy(self):
        self.monitor.on_estop(False)
        self.monitor.on_permit()


class Latching(Base):
    def test_healthy_inputs_do_not_trip(self):
        self.healthy()
        self.assertFalse(self.monitor.update())
        self.assertIsNone(self.monitor.reason)

    def test_missing_heartbeat_fails_closed(self):
        self.assertTrue(self.monitor.update())
        self.assertIn('not been received', self.monitor.reason)

    def test_stale_heartbeat_trips(self):
        self.healthy()
        self.now += ESTOP_AGE + 0.1
        self.monitor.on_permit()
        self.assertTrue(self.monitor.update())
        self.assertIn('stale', self.monitor.reason)

    def test_asserted_estop_trips_immediately(self):
        self.healthy()
        self.monitor.on_estop(True)
        self.assertTrue(self.monitor.update())
        self.assertIn('asserted', self.monitor.reason)

    def test_silent_coordinator_trips(self):
        self.healthy()
        self.now += PERMIT_AGE + 0.1
        self.monitor.on_estop(False)
        self.assertTrue(self.monitor.update())
        self.assertIn('Coordinator', self.monitor.reason)

    def test_coordinator_never_seen_does_not_trip(self):
        self.monitor.on_estop(False)
        self.now += 100.0
        self.monitor.on_estop(False)
        self.assertFalse(self.monitor.update())

    def test_update_reports_the_trip_only_once(self):
        self.assertTrue(self.monitor.update())
        self.assertFalse(self.monitor.update())

    def test_latch_survives_inputs_recovering(self):
        self.monitor.update()
        self.healthy()
        self.monitor.update()
        self.assertIsNotNone(self.monitor.reason)

    def test_first_reason_is_kept(self):
        self.healthy()
        self.monitor.on_estop(True)
        self.monitor.update()
        self.now += 10.0
        self.monitor.update()
        self.assertIn('asserted', self.monitor.reason)


class Reset(Base):
    def trip(self):
        self.monitor.on_estop(True)
        self.monitor.update()

    def test_refused_while_estop_is_asserted(self):
        self.trip()
        self.assertIn('asserted', self.monitor.reset())
        self.assertIsNotNone(self.monitor.reason)

    def test_refused_while_coordinator_is_silent(self):
        self.healthy()
        self.monitor.update()
        self.now += PERMIT_AGE + 0.1
        self.monitor.on_estop(False)
        self.monitor.update()
        self.assertIn('Coordinator', self.monitor.reset())

    def test_succeeds_once_inputs_are_healthy(self):
        self.trip()
        self.healthy()
        self.assertIsNone(self.monitor.reset())
        self.assertIsNone(self.monitor.reason)
        self.assertFalse(self.monitor.update())

    def test_can_trip_again_after_reset(self):
        self.trip()
        self.healthy()
        self.monitor.reset()
        self.monitor.on_estop(True)
        self.assertTrue(self.monitor.update())


class Configuration(unittest.TestCase):
    def test_ages_must_be_positive(self):
        for ages in ((0, 1.0), (1.0, 0)):
            with self.assertRaises(ValueError):
                SafetyMonitor(*ages)

    def test_heartbeat_can_be_optional(self):
        monitor = SafetyMonitor(1.0, 1.0, require_estop=False)
        self.assertFalse(monitor.update())


if __name__ == '__main__':
    unittest.main()
