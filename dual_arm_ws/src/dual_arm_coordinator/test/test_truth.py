from pathlib import Path
import unittest

import yaml

from dual_arm_coordinator.gateways.truth import CAPS, MAX_POSE_AGE_S, TruthObserver
from dual_arm_coordinator.workflow.ports import TaskFault

PACKAGE = Path(__file__).resolve().parents[1]
CONFIG = yaml.safe_load((PACKAGE / 'config' / 'sim' / 'coordinator.yaml').read_text(encoding='utf-8'))
Z = 0.019
HOME_A = (-0.166, -0.028, 0.14)
HOME_C = (0.15, -0.035, 0.14)
# Parked outside every zone, so individual tests only see the caps they place.
PARKED = (-0.5, 0.5, Z)


class Base(unittest.TestCase):
    def setUp(self):
        self.now = 0.0
        self.tcp = {'arm1': HOME_A, 'arm2': HOME_C}
        self.unreachable = set()
        self.observer = self.make()
        self.park_all()

    def make(self, prefilled=0):
        return TruthObserver(CONFIG, self.tcp.__getitem__, self.can_reach, lambda _arm: HOME_A,
                             prefilled, clock=lambda: self.now)

    def can_reach(self, _arm, xyz):
        if xyz[:2] in self.unreachable:
            raise TaskFault('unreachable')

    def park_all(self, observer=None):
        for name in CAPS:
            (observer or self.observer).on_pose(name, PARKED)

    def place(self, name, x, y, z=Z):
        self.observer.on_pose(name, (x, y, z))


class Zones(Base):
    def test_empty_field(self):
        view = self.observer.zone()
        self.assertTrue(view.success)
        self.assertFalse(view.a_has_object or view.b_has_object)
        self.assertTrue(view.b_arm_clear)
        self.assertEqual(view.c_object_count, 0)

    def test_objects_are_assigned_to_zones(self):
        self.place('cap_1', -0.14, -0.03)
        self.place('cap_2', 0.0, -0.02)
        self.place('cap_3', 0.1675, -0.055)
        view = self.observer.zone()
        self.assertTrue(view.a_has_object and view.b_has_object)
        self.assertEqual(view.c_object_count, 1)

    def test_held_object_belongs_to_no_zone(self):
        self.place('cap_1', 0.0, -0.02, z=0.05)
        self.assertFalse(self.observer.zone().b_has_object)

    def test_arm_over_b_is_not_clear(self):
        self.tcp['arm2'] = (0.0, -0.02, 0.05)
        self.assertFalse(self.observer.zone().b_arm_clear)

    def test_missing_pose_is_invalid(self):
        observer = self.make()
        observer.on_pose('cap_1', PARKED)
        self.assertFalse(observer.zone().success)
        self.assertFalse(observer.grid().success)
        self.assertFalse(observer.pick_target().success)

    def test_stale_pose_is_invalid(self):
        self.now = MAX_POSE_AGE_S + 0.1
        self.assertFalse(self.observer.zone().success)
        with self.assertRaises(TaskFault):
            self.observer.cap_under_tool('arm1')


class Targets(Base):
    def test_picks_cap_closest_to_home_with_object_top_height(self):
        self.place('cap_1', -0.14, 0.1)
        self.place('cap_5', -0.14, -0.03)
        target = self.observer.pick_target()
        self.assertTrue(target.success)
        self.assertEqual((target.x, target.y), (-0.14, -0.03))
        self.assertAlmostEqual(target.z, 0.024)

    def test_skips_unreachable_caps(self):
        self.place('cap_1', -0.14, 0.1)
        self.place('cap_5', -0.14, -0.03)
        self.unreachable.add((-0.14, -0.03))
        self.assertEqual(self.observer.pick_target().y, 0.1)

    def test_no_reachable_cap_is_invalid(self):
        self.place('cap_5', -0.14, -0.03)
        self.unreachable.add((-0.14, -0.03))
        self.assertFalse(self.observer.pick_target().success)

    def test_empty_zone_a_is_invalid(self):
        self.assertFalse(self.observer.pick_target().success)


class Slots(Base):
    def test_grid_marks_cap_in_slot(self):
        self.place('cap_1', 0.1675, -0.09)
        self.assertEqual(self.observer.grid().occupied, (True,) + (False,) * 7)

    def test_cap_off_slot_center_is_not_counted(self):
        self.place('cap_1', 0.1675 - 0.005, -0.09)
        self.assertFalse(any(self.observer.grid().occupied))

    def test_verify_place_checks_slot_and_order(self):
        self.place('cap_1', 0.1675, -0.09)
        view = self.observer.verify_place(1)
        self.assertTrue(view.placed and view.order_ok)
        self.assertFalse(self.observer.verify_place(2).placed)

    def test_out_of_order_slot_is_reported(self):
        self.place('cap_1', 0.1325, -0.09)
        view = self.observer.verify_place(2)
        self.assertTrue(view.placed)
        self.assertFalse(view.order_ok)


class Prefilled(Base):
    def setUp(self):
        super().setUp()
        self.observer = self.make(prefilled=2)
        self.park_all()

    def test_prefilled_slots_count_as_occupied(self):
        self.assertEqual(self.observer.grid().occupied, (True, True) + (False,) * 6)
        self.assertEqual(self.observer.zone().c_object_count, 2)

    def test_placing_next_slot_keeps_order(self):
        self.place('cap_5', 0.1675, -0.055)
        view = self.observer.verify_place(3)
        self.assertTrue(view.placed and view.order_ok)
        self.assertEqual(self.observer.zone().c_object_count, 3)

    def test_invalid_count_is_refused(self):
        for value in (-1, 9, True):
            with self.assertRaises(ValueError):
                self.make(prefilled=value)


class Locator(Base):
    def test_finds_cap_under_tool(self):
        self.place('cap_5', -0.14, -0.03)
        self.tcp['arm1'] = (-0.1401, -0.03, 0.0243)
        self.assertEqual(self.observer.cap_under_tool('arm1'), 'cap_5')

    def test_nothing_under_tool_is_a_fault(self):
        self.place('cap_5', -0.14, -0.03)
        self.tcp['arm1'] = (0.2, -0.03, 0.0243)
        with self.assertRaises(TaskFault):
            self.observer.cap_under_tool('arm1')


if __name__ == '__main__':
    unittest.main()
