from types import SimpleNamespace as Reply
import math
import unittest

from dual_arm_coordinator.gateways.vision import CalibrationMonitor, ImageMonitor, VisionObserver, VisionPickObserver
from dual_arm_coordinator.workflow.ports import GridView, PlaceView, TaskCancelled, TaskFault, ZoneView


class Services:
    def __init__(self):
        self.calls = []
        self.zone_reply = Reply(success=True, message='', a_has_object=True, b_has_object=False, b_arm_clear=True, c_object_count=2)
        self.pick_reply = Reply(success=True, message='', x=0.05, y=-0.1, z=0.01)
        self.grid_reply = Reply(success=True, message='', occupied=[True, True] + [False] * 6)
        self.verify_reply = Reply(success=True, message='', placed=True, order_ok=True)

    def zone(self):
        self.calls.append('zone')
        return self.zone_reply

    def pick(self):
        self.calls.append('pick')
        return self.pick_reply

    def grid(self):
        self.calls.append('grid')
        return self.grid_reply

    def verify(self, slot):
        self.calls.append(('verify', slot))
        return self.verify_reply


class Base(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.services = Services()
        self.calibration = CalibrationMonitor(3.0, clock=lambda: self.now)
        self.images = ImageMonitor(clock=lambda: self.now)
        self.guard_error = None
        self.deliver_images = True
        self.transform_error = None
        self.observer = VisionObserver(self.services, self.to_target, self.calibration, self.images, self.guard,
                                       0.2, 5.0, clock=lambda: self.now, sleep=self.sleep)
        for camera in ('env', 'arm1', 'arm2'):
            self.calibration.on_status(camera, True, [])

    def guard(self):
        if self.guard_error:
            raise self.guard_error

    def to_target(self, _arm, x, y, z):
        if self.transform_error:
            raise self.transform_error
        return (-0.1 + y, 0.08725 - x, z + 0.014)

    def sleep(self, seconds):
        self.now += seconds
        if self.deliver_images:
            for camera in ('env', 'arm1', 'arm2'):
                self.images.on_image(camera)
            for camera in ('env', 'arm1', 'arm2'):
                self.calibration.on_status(camera, *self.calibration_state.get(camera, (True, [])))

    calibration_state = {}


class Conversions(Base):
    def test_zone_is_copied(self):
        view = self.observer.zone()
        self.assertEqual(view, ZoneView(True, '', True, False, True, 2))

    def test_pick_is_converted_to_target_frame(self):
        view = self.observer.pick_target()
        self.assertTrue(view.success)
        self.assertAlmostEqual(view.x, -0.2)
        self.assertAlmostEqual(view.y, 0.03725)
        self.assertAlmostEqual(view.z, 0.024)

    def test_grid_and_verify(self):
        self.assertEqual(self.observer.grid(), GridView(True, '', (True, True) + (False,) * 6))
        self.assertEqual(self.observer.verify_place(3), PlaceView(True, '', True, True))
        self.assertIn(('verify', 3), self.services.calls)


class ServiceFailures(Base):
    def test_unsuccessful_replies_are_invalid(self):
        for attribute, method in (('zone_reply', 'zone'), ('pick_reply', 'pick_target'), ('grid_reply', 'grid')):
            with self.subTest(method):
                setattr(self.services, attribute, Reply(success=False, message='no target'))
                view = getattr(self.observer, method)()
                self.assertFalse(view.success)
                self.assertEqual(view.message, 'no target')

    def test_verify_failure_is_invalid(self):
        self.services.verify_reply = Reply(success=False, message='image timeout')
        self.assertFalse(self.observer.verify_place(1).success)

    def test_non_finite_pick_is_invalid(self):
        self.services.pick_reply = Reply(success=True, message='', x=math.nan, y=-0.1, z=0.01)
        self.assertIn('non-finite', self.observer.pick_target().message)

    def test_missing_transform_is_invalid(self):
        self.transform_error = TaskFault('No transform')
        view = self.observer.pick_target()
        self.assertFalse(view.success)
        self.assertIn('No transform', view.message)


class CalibrationGate(Base):
    def test_invalid_calibration_blocks_before_the_service_is_called(self):
        self.calibration.on_status('arm1', False, ['Calibration not validated'])
        view = self.observer.pick_target()
        self.assertFalse(view.success)
        self.assertIn('not valid', view.message)
        self.assertNotIn('pick', self.services.calls)

    def test_each_query_checks_its_own_camera(self):
        self.calibration.on_status('env', False, ['bad'])
        self.assertFalse(self.observer.zone().success)
        self.assertTrue(self.observer.pick_target().success)

    def test_missing_status_blocks(self):
        calibration = CalibrationMonitor(3.0, clock=lambda: self.now)
        self.assertIn('No calibration status', calibration.problem('arm1'))

    def test_stale_status_blocks(self):
        self.now += 10.0
        self.assertIn('stale', self.calibration.problem('arm1'))

    def test_calibration_lost_while_waiting_blocks(self):
        def fail_arm1(seconds):
            self.now += seconds
            self.images.on_image('arm1')
            self.calibration.on_status('arm1', False, ['moved'])
        self.observer._sleep = fail_arm1
        self.assertFalse(self.observer.pick_target().success)
        self.assertNotIn('pick', self.services.calls)


class ImageFreshness(Base):
    def test_image_from_before_settling_is_not_enough(self):
        self.images.on_image('arm1')
        self.deliver_images = False
        view = self.observer.pick_target()
        self.assertFalse(view.success)
        self.assertIn('No new image', view.message)
        self.assertNotIn('pick', self.services.calls)

    def test_waits_past_the_settling_time(self):
        self.observer.pick_target()
        self.assertGreaterEqual(self.now, 100.2)

    def test_cancel_interrupts_waiting(self):
        self.deliver_images = False
        def cancel(seconds):
            self.now += seconds
            self.guard_error = TaskCancelled('stop')
        self.observer._sleep = cancel
        with self.assertRaises(TaskCancelled):
            self.observer.pick_target()


class Composite(unittest.TestCase):
    def test_only_pick_comes_from_vision(self):
        truth = Reply(zone=lambda: 'truth zone', grid=lambda: 'truth grid', verify_place=lambda slot: f'truth {slot}',
                      b_pick_target=lambda: 'truth b')
        vision = Reply(pick_target=lambda: 'vision pick')
        observer = VisionPickObserver(truth, vision)
        self.assertEqual((observer.zone(), observer.grid(), observer.verify_place(2), observer.pick_target(),
                          observer.b_pick_target()),
                         ('truth zone', 'truth grid', 'truth 2', 'vision pick', 'truth b'))


if __name__ == '__main__':
    unittest.main()
