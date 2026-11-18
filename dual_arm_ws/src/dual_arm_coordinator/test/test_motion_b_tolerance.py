"""B 'above' may use a looser arrival check than B contact (field run 2026-11-18, user: 6 counts)."""
import unittest

from dual_arm_coordinator.gateways.motion import MotionGateway


def gateway(teach):
    g = MotionGateway.__new__(MotionGateway)
    g._b_teach = teach
    g._contact_lift = {}
    g._b = lambda arm: {'above': 'ABOVE', 'release': 'CONTACT'}
    g.checked = []
    g._move_taught = lambda arm, target, label, contact, t, tolerance=None: g.checked.append(
        (target, tolerance or t['arrival_tolerance_raw']))
    return g


class CAboveTolerance(unittest.TestCase):
    def test_slot_above_uses_the_looser_value_and_release_keeps_its_own(self):
        g = MotionGateway.__new__(MotionGateway)
        g._teach = {'arrival_tolerance_raw': 4, 'above_arrival_tolerance_raw': 6}
        g._slot = lambda arm, slot: {'above': 'ABOVE', 'release': 'RELEASE'}
        checked = []
        g._move_taught = lambda arm, target, label, contact, t, tolerance=None: checked.append((target, tolerance))
        g.move_slot('arm2', 7, 'above')
        g.move_slot('arm2', 7, 'release', contact=True)
        self.assertEqual(checked, [('ABOVE', 6), ('RELEASE', 4)])


class BAboveTolerance(unittest.TestCase):
    def test_above_uses_the_looser_value_and_contact_keeps_its_own(self):
        g = gateway({'arrival_tolerance_raw': 4, 'above_arrival_tolerance_raw': 6})
        g.move_b('arm1', 'above')
        g.move_b('arm1', 'contact', contact=True)
        self.assertEqual(g.checked, [('ABOVE', 6), ('CONTACT', 4)])

    def test_without_the_key_both_use_arrival_tolerance(self):
        g = gateway({'arrival_tolerance_raw': 4})
        g.move_b('arm2', 'above')
        g.move_b('arm2', 'contact', contact=True)
        self.assertEqual(g.checked, [('ABOVE', 4), ('CONTACT', 4)])


if __name__ == '__main__':
    unittest.main()
