"""Overlapped transfer (prototype): arm 1 picks the next object while arm 2 carries the previous one."""
from dataclasses import replace
import threading
import time
import unittest

from dual_arm_coordinator.lanes import XLanes
from dual_arm_coordinator.workflow.ports import TaskCancelled, TaskFault

from test_workflow import SETTINGS, Base, World

OVERLAP = replace(SETTINGS, overlap=True)
PROTOTYPE = replace(SETTINGS, overlap=True, b_joints=True, c_slot_joints=True)
C_MOVES = ('move_slot',)


class ThreadWorld(World):
    """World with a lock around each call, and a record of anything entering B while it is taken."""

    def __init__(self, journal_path, objects=8):
        super().__init__(journal_path, objects)
        self.lock = threading.RLock()
        self.b_violations = []
        self.hooks = []

    def _call(self, name, *args):
        for hook in self.hooks:
            hook(name, *args)
        with self.lock:
            super()._call(name, *args)

    def _enter(self, arm, xy):
        if self._at_b(xy):
            other = 'arm2' if arm == 'arm1' else 'arm1'
            if self._at_b(self.position[other]):
                self.b_violations.append((arm, other))

    def move_b(self, arm, pose, contact=False):
        with self.lock:
            self._enter(arm, SETTINGS.b_place)
        super().move_b(arm, pose, contact)

    def move_to(self, arm, xyz, contact=False):
        with self.lock:
            self._enter(arm, xyz[:2])
        super().move_to(arm, xyz, contact)


def grasps(world, arm):
    return [index for index, call in enumerate(world.calls) if call[:3] == ('suction', arm, 'grasp')]


class OverlapBase(Base):
    settings = OVERLAP

    def setUp(self):
        self.world = ThreadWorld(None)
        super().setUp()
        self.world.journal_path = self.path

    def wait_in_arm2_c_move_until_arm1_grasped(self, count):
        """Hold arm 2's first move to C until arm 1 has grasped count objects (or 5 s pass)."""
        seen = {'overlapped': False, 'done': False}

        def hook(name, *args):
            if seen['done'] or args[:1] != ('arm2',) or not (name == 'move_to' and args[1][:2] in SETTINGS.c_slots
                                                             or name == 'move_slot'):
                return
            seen['done'] = True
            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline:
                with self.world.lock:
                    if len(grasps(self.world, 'arm1')) >= count:
                        seen['overlapped'] = True
                        return
                time.sleep(0.005)
        self.world.hooks.append(hook)
        return seen


class OverlappedRun(OverlapBase):
    def test_delivers_every_object_in_slot_order(self):
        self.assertEqual(self.transfer.run(3), 'SUCCEEDED')
        self.assertEqual(self.world.c, [True] * 3 + [False] * 5)
        self.assertEqual(self.world.a_objects, 5)
        self.assertEqual(self.state['completed'], 3)
        self.assertEqual(self.state['holding'], {'arm1': 'empty', 'arm2': 'empty'})
        self.assertEqual(self.state['b_owner'], '')
        self.assertEqual(self.world.b_violations, [])

    def test_arm1_picks_the_next_object_while_arm2_carries_one(self):
        seen = self.wait_in_arm2_c_move_until_arm1_grasped(2)
        self.assertEqual(self.transfer.run(2), 'SUCCEEDED')
        self.assertTrue(seen['overlapped'], 'arm 1 did not pick its second object before arm 2 reached C')
        self.assertEqual(self.world.c, [True, True] + [False] * 6)
        self.assertEqual(self.world.b_violations, [])

    def test_arm1_waits_for_arm2_to_leave_b_before_placing(self):
        self.transfer.run(3)
        calls = self.world.calls
        b_releases = [index for index, call in enumerate(calls) if call[:3] == ('suction', 'arm1', 'release')]
        b_grasps = grasps(self.world, 'arm2')
        # arm 1's k+1-th release in B comes after arm 2 took the k-th object out of B.
        for k in range(1, len(b_releases)):
            self.assertLess(b_grasps[k - 1], b_releases[k])

    def test_fills_c_and_reports_full(self):
        self.world.c = [True] * 6 + [False] * 2
        self.journal.update(occupied=self.world.c[:])
        self.assertEqual(self.transfer.run(5), 'FULL')
        self.assertEqual(self.world.c, [True] * 8)
        self.assertEqual(len(grasps(self.world, 'arm1')), 2)

    def test_zone_a_running_empty_ends_the_run(self):
        self.world.a_objects = 2
        self.assertEqual(self.transfer.run(4), 'SUCCEEDED')
        self.assertEqual(self.world.c, [True, True] + [False] * 6)
        self.assertIn('Zone A was empty after 2', self.state['message'])

    def test_object_left_in_b_is_delivered_first(self):
        self.world.b_object = True
        self.assertEqual(self.transfer.run(2), 'SUCCEEDED')
        self.assertEqual(self.world.c, [True, True] + [False] * 6)
        self.assertEqual(len(grasps(self.world, 'arm1')), 1)

    def test_b_poses_and_every_slot_are_checked_before_any_motion(self):
        self.settings = PROTOTYPE
        self.make()
        self.transfer.run(3)
        calls = self.world.calls
        first_grasp = grasps(self.world, 'arm1')[0]
        checked = [call[1:] for call in calls[:first_grasp] if call[0] in ('check_b', 'check_slot')]
        self.assertIn(('arm1',), checked)
        self.assertIn(('arm2',), checked)
        self.assertTrue({('arm2', slot) for slot in (1, 2, 3)} <= set(checked))

    def test_unreachable_later_slot_stops_before_taking_anything(self):
        self.settings = PROTOTYPE
        self.make()
        self.world.unreachable.add(('arm2', 3))
        self.assert_faulted('cannot reach taught slot 3', limit=3)
        self.assertEqual(self.world.a_objects, 8)


class OverlappedFaults(OverlapBase):
    def fail_arm2_in_c_while_arm1_holds(self):
        """arm 2 fails its first move to C once arm 1 holds its second object; arm 1 is slowed down
        on its way HOME so the failure is in before it could place that object in B."""
        state = {'failed': False}

        def hook(name, *args):
            if args[:1] == ('arm2',) and name == 'move_to' and args[1][:2] in SETTINGS.c_slots:
                deadline = time.monotonic() + 5.0
                while len(grasps(self.world, 'arm1')) < 2 and time.monotonic() < deadline:
                    time.sleep(0.005)
                if not state['failed']:
                    state['failed'] = True
                    raise TaskFault('injected arm2 C')
            if args[:1] == ('arm1',) and name == 'move_home' and len(grasps(self.world, 'arm1')) >= 2:
                time.sleep(0.3)
        self.world.hooks.append(hook)

    def test_arm2_fault_lets_arm1_finish_its_pick_then_stops(self):
        self.fail_arm2_in_c_while_arm1_holds()
        self.assert_faulted('injected arm2 C', limit=3)
        self.assertEqual(self.state['holding']['arm1'], 'held')
        self.assertTrue(self.world.at_home('arm1'))
        self.assertEqual(len(grasps(self.world, 'arm1')), 2)
        self.assertEqual([call for call in self.world.calls if call[:3] == ('suction', 'arm1', 'release')][1:], [])

    def test_arm1_fault_lets_arm2_finish_its_object(self):
        # arm 1's second pick fails while arm 2 carries the first object, which it still delivers.
        def hook(name, *args):
            if name == 'pick_target' and self.world.counts.get('pick_target', 0) == 1:
                deadline = time.monotonic() + 5.0
                while not grasps(self.world, 'arm2') and time.monotonic() < deadline:
                    time.sleep(0.005)
        self.world.hooks.append(hook)
        self.world.fail = {'pick_target': 2}
        self.assert_faulted('injected pick_target', limit=3)
        self.assertEqual(self.world.c, [True] + [False] * 7)
        self.assertEqual(self.state['holding'], {'arm1': 'empty', 'arm2': 'empty'})

    def test_cancel_stops_both_arms(self):
        self.world.cancel_after = 6
        with self.assertRaises(TaskCancelled):
            self.transfer.run(3)
        self.assertEqual(self.state['state'], 'FAULT')

    def test_auto_resume_does_not_continue_while_arm1_holds(self):
        self.fail_arm2_in_c_while_arm1_holds()
        notes = []
        with self.assertRaises(TaskFault):
            self.transfer.run_resuming(3, 2, notes.append)
        self.assertIn('arm1, arm2 may still hold an object', notes[-1])


class Lanes(unittest.TestCase):
    def setUp(self):
        self.standing = {'arm1': (-0.10, -0.085), 'arm2': (0.10, 0.115)}
        self.now = [0.0]
        self.lanes = XLanes(lambda arm: self.standing[arm], 0.02, 1.0, clock=lambda: self.now[0])

    def test_separate_ranges_are_granted(self):
        self.assertEqual(self.lanes.reserve('arm1', -0.30, -0.08, lambda: None, 'a'), (-0.32, -0.06))
        self.assertEqual(self.lanes.reserve('arm2', 0.02, 0.17, lambda: None, 'b'), (0.0, 0.19))

    def test_overlap_with_a_moving_arm_waits_and_times_out(self):
        self.lanes.reserve('arm2', 0.0, 0.17, lambda: None, 'b')

        def guard():
            self.now[0] += 0.6
        with self.assertRaises(TaskFault) as caught:
            self.lanes.reserve('arm1', -0.10, 0.03, guard, 'arm1 to B')
        self.assertIn('waited', str(caught.exception))

    def test_finish_releases_the_lane(self):
        self.lanes.reserve('arm2', 0.0, 0.17, lambda: None, 'b')
        threading.Timer(0.1, lambda: self.lanes.finish('arm2')).start()
        self.lanes._wait = 5.0
        self.lanes.reserve('arm1', -0.10, 0.03, lambda: None, 'arm1 to B')
        self.assertIsNotNone(self.lanes.moving('arm1'))

    def test_standing_arm_blocks_too(self):
        self.standing['arm2'] = (0.02, 0.11)  # arm 2 is standing in B

        def guard():
            self.now[0] += 0.6
        with self.assertRaises(TaskFault):
            self.lanes.reserve('arm1', -0.10, 0.03, guard, 'arm1 to B')

    def test_cancel_ends_the_wait(self):
        self.lanes.reserve('arm2', 0.0, 0.17, lambda: None, 'b')

        def guard():
            raise TaskCancelled('canceled')
        with self.assertRaises(TaskCancelled):
            self.lanes.reserve('arm1', -0.10, 0.03, guard, 'arm1 to B')
        self.assertIsNone(self.lanes.moving('arm1'))


if __name__ == '__main__':
    unittest.main()
