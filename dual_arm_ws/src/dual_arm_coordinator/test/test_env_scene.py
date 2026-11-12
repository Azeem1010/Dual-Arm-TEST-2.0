from pathlib import Path
from types import SimpleNamespace as Reply
import unittest

import yaml

from dual_arm_coordinator.gateways.env_scene import SCENE_LAG_S, EnvSceneObserver, require_world_frame
from dual_arm_coordinator.gateways.vision import ImageMonitor
from dual_arm_coordinator.workflow.ports import TaskCancelled, TaskFault, WorkflowSettings

PACKAGE = Path(__file__).resolve().parents[1]
CONFIG = yaml.safe_load((PACKAGE / 'config' / 'sim' / 'coordinator.yaml').read_text(encoding='utf-8'))
SETTINGS = WorkflowSettings.from_config(CONFIG)
HOME_A = (-0.166, -0.028, 0.14)


def cap(x_mm, y_mm):
    return Reply(x_mm=x_mm, y_mm=y_mm)


def scene(**changes):
    values = dict(valid=True, message='', coords_source='standard', arm1_valid=True, arm2_valid=True,
                  c_slots_valid=True, a_objects=[cap(-200.0, 0.0), cap(-150.0, -20.0)], b_objects=[],
                  c_occupied=[True, True] + [False] * 6, c_occupied_count=2)
    values.update(changes)
    return Reply(**values)


class Base(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.images = ImageMonitor(clock=lambda: self.now)
        self.reply = Reply(success=True, message='', scene=scene())
        self.calls = 0
        self.home = {'arm1': True, 'arm2': True}
        self.unreachable = set()
        self.deliver_images = True
        self.deliver_until = float('inf')
        self.guard_error = None
        self.observer = EnvSceneObserver(self.scene_call, self.images, self.home.get, self.can_reach,
                                         lambda _arm: HOME_A, SETTINGS, self.guard, 0.2, 5.0,
                                         clock=lambda: self.now, sleep=self.sleep)

    def set_scene(self, **changes):
        self.reply = Reply(success=True, message='', scene=scene(**changes))

    def scene_call(self):
        self.calls += 1
        return self.reply

    def can_reach(self, _arm, xyz):
        if (round(xyz[0], 3), round(xyz[1], 3)) in self.unreachable:
            raise TaskFault('unreachable')

    def guard(self):
        if self.guard_error:
            raise self.guard_error

    def sleep(self, seconds):
        self.now += seconds
        if self.deliver_images and self.now <= self.deliver_until:
            self.images.on_image('env')


class Zones(Base):
    def test_zone_maps_counts_and_uses_home_state_for_b_clear(self):
        self.set_scene(b_objects=[cap(0.0, 0.0)])
        view = self.observer.zone()
        self.assertEqual((view.success, view.a_has_object, view.b_has_object, view.b_arm_clear, view.c_object_count),
                         (True, True, True, True, 2))
        for state in (False, None):
            with self.subTest(state):
                self.home['arm2'] = state
                self.assertFalse(self.observer.zone().b_arm_clear)


class Validity(Base):
    def test_estimated_coords_are_refused(self):
        self.set_scene(coords_source='estimated')
        for method in ('zone', 'pick_target', 'b_pick_target', 'grid'):
            with self.subTest(method):
                view = getattr(self.observer, method)()
                self.assertFalse(view.success)
                self.assertIn('estimated', view.message)
        self.assertFalse(self.observer.verify_place(1).success)

    def test_validity_is_checked_per_use(self):
        self.set_scene(arm2_valid=False, b_objects=[cap(0.0, 0.0)])
        self.assertTrue(self.observer.pick_target().success)
        self.assertFalse(self.observer.b_pick_target().success)
        self.assertFalse(self.observer.grid().success)
        self.assertFalse(self.observer.verify_place(1).success)
        self.set_scene(c_slots_valid=False)
        self.assertFalse(self.observer.grid().success)
        self.assertFalse(self.observer.verify_place(1).success)
        self.assertFalse(self.observer.zone().success)

    def test_service_failure_and_invalid_scene(self):
        self.reply = Reply(success=False, message='no image', scene=scene())
        self.assertEqual(self.observer.zone().message, 'no image')
        self.set_scene(valid=False, message='field not found')
        self.assertIn('field not found', self.observer.pick_target().message)

    def test_requires_world_target_frame(self):
        require_world_frame({'target_frame': 'world'})
        with self.assertRaises(ValueError):
            require_world_frame({'target_frame': 'arm1_base'})


class Targets(Base):
    def test_pick_target_nearest_reachable(self):
        self.set_scene(a_objects=[cap(-250.0, 50.0), cap(-170.0, -30.0), cap(-200.0, -20.0)])
        view = self.observer.pick_target()
        self.assertTrue(view.success)
        self.assertEqual((round(view.x, 3), round(view.y, 3), view.z), (-0.17, -0.03, SETTINGS.cap_top_z))
        self.unreachable.add((-0.17, -0.03))
        view = self.observer.pick_target()
        self.assertEqual((round(view.x, 3), round(view.y, 3)), (-0.2, -0.02))
        self.unreachable.update({(-0.2, -0.02), (-0.25, 0.05)})
        view = self.observer.pick_target()
        self.assertFalse(view.success)
        self.assertEqual(view.message, 'No reachable object in zone A')

    def test_b_target_requires_exactly_one(self):
        for objects in ([], [cap(0.0, 0.0), cap(30.0, 0.0)]):
            with self.subTest(len(objects)):
                self.set_scene(b_objects=objects)
                view = self.observer.b_pick_target()
                self.assertFalse(view.success)
                self.assertIn(str(len(objects)), view.message)
        self.set_scene(b_objects=[cap(12.0, -8.0)])
        view = self.observer.b_pick_target()
        self.assertTrue(view.success)
        self.assertEqual((round(view.x, 3), round(view.y, 3), view.z), (0.012, -0.008, SETTINGS.cap_top_z))

    def test_grid_copies_occupancy(self):
        view = self.observer.grid()
        self.assertEqual(view.occupied, (True, True) + (False,) * 6)

    def test_verify_place_order(self):
        self.set_scene(c_occupied=[True, True, True] + [False] * 5)
        view = self.observer.verify_place(3)
        self.assertEqual((view.success, view.placed, view.order_ok), (True, True, True))
        self.set_scene(c_occupied=[True, False, True] + [False] * 5)
        view = self.observer.verify_place(3)
        self.assertEqual((view.placed, view.order_ok), (True, False))


class ImageGate(Base):
    def test_waits_for_image_after_settle(self):
        self.deliver_images = False
        view = self.observer.zone()
        self.assertFalse(view.success)
        self.assertEqual(view.message, 'No new image from env after the arm settled')
        self.assertEqual(self.calls, 0)

    def test_scene_needs_images_past_its_processing_lag(self):
        # env_scene answers with its latest result and debounces C slots over several frames, so an
        # image right after the arms settle is not enough: the scene must have had time to change.
        self.deliver_until = self.now + 0.2 + SCENE_LAG_S / 2
        view = self.observer.grid()
        self.assertFalse(view.success)
        self.assertEqual(self.calls, 0)

    def test_scene_lag_covers_the_slot_debounce(self):
        self.assertGreaterEqual(SCENE_LAG_S, 0.4)

    def test_cancel_while_waiting(self):
        self.deliver_images = False
        self.guard_error = TaskCancelled('stop')
        with self.assertRaises(TaskCancelled):
            self.observer.zone()


if __name__ == '__main__':
    unittest.main()
