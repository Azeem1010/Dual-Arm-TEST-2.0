from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml

from dual_arm_coordinator.confirmation import TokenError, TokenGate
from dual_arm_coordinator.journal import Journal, JournalError, config_fingerprint
from dual_arm_coordinator.workflow.ports import (GridView, PickView, PlaceView, TaskCancelled,
                                                 TaskFault, TaskIO, WorkflowSettings, ZoneView)
from dual_arm_coordinator.workflow.transfer import RECOVERY, Transfer

PACKAGE = Path(__file__).resolve().parents[1]
CONFIG = yaml.safe_load((PACKAGE / 'config' / 'sim' / 'coordinator.yaml').read_text(encoding='utf-8'))
SETTINGS = WorkflowSettings.from_config(CONFIG)
FINGERPRINT = 'fingerprint-a'
MOTIONS = ('move_home', 'move_to')


class World(TaskIO):
    """A small physical model, so the tests observe outcomes rather than call order."""

    def __init__(self, journal_path, objects=8):
        self.journal_path = journal_path
        self.a_objects, self.b_object, self.c = objects, False, [False] * 8
        self.position = {'arm1': None, 'arm2': None}
        self.calls, self.snapshots, self.counts = [], [], {}
        self.fail, self.cancel_after = {}, None
        self.cancelled = False
        self.zone_patch, self.grid_patch, self.pick_patch, self.place_patch = None, None, None, None
        self.unreachable = set()

    def _call(self, name, *args):
        self.counts[name] = self.counts.get(name, 0) + 1
        self.calls.append((name, *args))
        self.snapshots.append(json.loads(Path(self.journal_path).read_text(encoding='utf-8')))
        if self.fail.get(name) == self.counts[name]:
            raise TaskFault(f'injected {name}')

    def _after_motion(self):
        count = sum(1 for call in self.calls if call[0] in MOTIONS)
        if self.cancel_after == count:
            self.cancelled = True

    def guard(self):
        if self.cancelled:
            raise TaskCancelled('canceled')

    def _arm_in_b(self):
        return any(xy == SETTINGS.b_place for xy in self.position.values())

    def zone(self):
        self._call('zone')
        view = ZoneView(True, '', self.a_objects > 0, self.b_object, not self._arm_in_b(), sum(self.c))
        return self.zone_patch(view, self.counts['zone']) if self.zone_patch else view

    def pick_target(self):
        self._call('pick_target')
        view = PickView(True, '', -0.14, -0.03, SETTINGS.cap_top_z)
        return self.pick_patch(view) if self.pick_patch else view

    def grid(self):
        self._call('grid')
        view = GridView(True, '', tuple(self.c))
        return self.grid_patch(view) if self.grid_patch else view

    def verify_place(self, slot):
        self._call('verify_place', slot)
        view = PlaceView(True, '', self.c[slot - 1], True)
        return self.place_patch(view) if self.place_patch else view

    def check_reachable(self, arm, xyz):
        self._call('check_reachable', arm, xyz)
        if (arm, xyz[:2]) in self.unreachable:
            raise TaskFault(f'{arm} cannot reach {xyz}')

    def move_home(self, arm):
        self._call('move_home', arm)
        self.position[arm] = None
        self._after_motion()

    def move_to(self, arm, xyz, contact=False):
        self._call('move_to', arm, xyz, contact)
        self.position[arm] = (xyz[0], xyz[1])
        self._after_motion()

    def at_home(self, arm):
        return self.position[arm] is None

    def suction(self, arm, operation):
        self._call('suction', arm, operation)
        location = self.position[arm]
        if operation == 'grasp':
            if location == SETTINGS.b_place:
                self.b_object = False
            else:
                self.a_objects -= 1
        elif location == SETTINGS.b_place:
            self.b_object = True
        else:
            self.c[SETTINGS.c_slots.index(location)] = True

    def attach(self, arm):
        self._call('attach', arm)

    def detach(self, arm):
        self._call('detach', arm)

    def scene_reset(self):
        self._call('scene_reset')

    def scene_add_b_object(self):
        self._call('scene_add_b_object')

    def scene_remove_b_object(self):
        self._call('scene_remove_b_object')

    def scene_add_slot_object(self, slot):
        self._call('scene_add_slot_object', slot)


class Base(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.time = 0.0
        self.path = Path(self.folder.name) / 'journal.json'
        self.open_journals = []
        self.addCleanup(self.close_all)
        self.make()

    def close_all(self):
        for journal in self.open_journals:
            journal.close()
        self.open_journals = []

    def make(self, fingerprint=FINGERPRINT):
        self.close_all()
        self.journal = Journal(self.path, fingerprint)
        self.open_journals.append(self.journal)
        self.gate = TokenGate(60.0, clock=lambda: self.time)
        if not hasattr(self, 'world'):
            self.world = World(self.path)
        self.transfer = Transfer(self.world, SETTINGS, self.journal, self.gate)

    @property
    def state(self):
        return self.journal.data

    def assert_faulted(self, text='', limit=1):
        with self.assertRaises(TaskFault) as caught:
            self.transfer.run(limit)
        self.assertIn(text, str(caught.exception))
        self.assertEqual(self.state['state'], 'FAULT')

    def calls_named(self, name):
        return [call for call in self.world.calls if call[0] == name]

    def token(self):
        return self.gate.current[0]


class HappyPath(Base):
    def test_one_object_reaches_slot_one(self):
        self.assertEqual(self.transfer.run(1), 'SUCCEEDED')
        self.assertEqual(self.world.c, [True] + [False] * 7)
        self.assertFalse(self.world.b_object)
        self.assertEqual(self.world.a_objects, 7)
        data = self.state
        self.assertEqual((data['b_owner'], data['slot'], data['completed']), ('', 0, 1))
        self.assertEqual(data['occupied'], [True] + [False] * 7)
        self.assertIsNone(self.transfer.zone.owner)

    def test_heights_follow_configuration(self):
        self.transfer.run(1)
        heights = {call[2][2] for call in self.calls_named('move_to')}
        self.assertEqual(heights, {SETTINGS.approach_z, SETTINGS.contact_z, SETTINGS.release_z})

    def test_eight_objects_fill_in_order_then_full(self):
        self.assertEqual(self.transfer.run(8), 'FULL')
        self.assertEqual(self.world.c, [True] * 8)
        self.assertEqual([call[1] for call in self.calls_named('verify_place')], list(range(1, 9)))
        with self.assertRaises(TaskFault):
            self.transfer.run(1)

    def test_object_already_in_b_goes_straight_to_c(self):
        self.world.b_object = True
        self.world.position['arm1'] = None
        self.assertEqual(self.transfer.run(1), 'SUCCEEDED')
        self.assertFalse([call for call in self.calls_named('move_to') if call[1] == 'arm1'])
        self.assertTrue(self.world.c[0])

    def test_limit_is_validated(self):
        for limit in (0, 9, True, 1.0):
            with self.assertRaises(ValueError):
                self.transfer.run(limit)


class Persistence(Base):
    def test_holding_is_unknown_on_disk_during_suction(self):
        self.transfer.run(1)
        for call, snapshot in zip(self.world.calls, self.world.snapshots):
            if call[0] == 'suction':
                self.assertEqual(snapshot['holding'][call[1]], 'unknown')

    def test_b_owner_is_on_disk_before_entering_b(self):
        self.transfer.run(1)
        for call, snapshot in zip(self.world.calls, self.world.snapshots):
            if call[0] == 'move_to' and call[2][:2] == SETTINGS.b_place:
                self.assertEqual(snapshot['b_owner'], call[1])

    def test_each_motion_runs_under_its_own_recorded_state(self):
        self.transfer.run(1)
        states = [snapshot['state'] for call, snapshot in zip(self.world.calls, self.world.snapshots)
                  if call[0] == 'move_to']
        for expected in ('ARM1:DESCEND_A', 'ARM1:DESCEND_B', 'ARM2:DESCEND_B', 'ARM2:DESCEND_C'):
            self.assertIn(expected, states)

    def test_preflight_runs_before_arm_enters_any_target(self):
        self.transfer.run(1)
        names = [call[0] for call in self.world.calls]
        first_check, first_move = names.index('check_reachable'), names.index('move_to')
        self.assertLess(first_check, first_move)


class Cancellation(unittest.TestCase):
    def test_cancel_after_every_motion_stops_and_faults(self):
        with tempfile.TemporaryDirectory() as folder:
            total = self.motion_count(Path(folder) / 'count.json')
            self.assertGreater(total, 10)
            for index in range(1, total):
                with self.subTest(after_motion=index):
                    self.cancel_once(Path(folder) / f'run{index}.json', index)

    def motion_count(self, path):
        journal = Journal(path, FINGERPRINT)
        world = World(path)
        Transfer(world, SETTINGS, journal, TokenGate(60.0)).run(1)
        journal.close()
        return sum(1 for call in world.calls if call[0] in MOTIONS)

    def cancel_once(self, path, index):
        journal = Journal(path, FINGERPRINT)
        self.addCleanup(journal.close)
        world = World(path)
        world.cancel_after = index
        gate = TokenGate(60.0)
        with self.assertRaises(TaskCancelled):
            Transfer(world, SETTINGS, journal, gate).run(1)
        self.assertEqual(sum(1 for call in world.calls if call[0] in MOTIONS), index)
        self.assertEqual(journal.data['state'], 'FAULT')
        self.assertEqual(gate.current[1], RECOVERY)


class SuctionFailures(Base):
    def test_grasp_failure_leaves_tool_unknown_and_stops(self):
        self.world.fail['suction'] = 1
        self.assert_faulted('injected suction')
        self.assertEqual(self.state['holding']['arm1'], 'unknown')
        self.assertFalse(self.calls_named('attach'))

    def test_release_failure_in_b_keeps_ownership(self):
        self.world.fail['suction'] = 2
        self.assert_faulted('injected suction')
        data = self.state
        self.assertEqual(data['holding']['arm1'], 'unknown')
        self.assertEqual(data['b_owner'], 'arm1')
        self.assertTrue(self.transfer.zone.faulted)

    def test_release_failure_in_c_commits_nothing(self):
        self.world.fail['suction'] = 4
        self.assert_faulted('injected suction')
        data = self.state
        self.assertEqual(data['holding']['arm2'], 'unknown')
        self.assertEqual(data['occupied'], [False] * 8)
        self.assertEqual(data['slot'], 1)
        self.assertEqual(self.transfer.slots.reserved, 1)


class VisionFailures(Base):
    def assert_no_arm_motion_to_target(self):
        self.assertFalse(self.calls_named('move_to'))

    def test_invalid_zone_observation(self):
        self.world.zone_patch = lambda view, _: replace(view, success=False, message='stale')
        self.assert_faulted('Zone observation invalid: stale')
        self.assert_no_arm_motion_to_target()

    def test_zone_a_empty(self):
        self.world.a_objects = 0
        self.assert_faulted('Zone A has no object')

    def test_invalid_pick_targets(self):
        cases = {'unsuccessful': dict(success=False, message='no target'),
                 'not finite': dict(x=float('nan')),
                 'outside x': dict(x=0.5),
                 'outside y': dict(y=0.3),
                 'wrong height': dict(z=SETTINGS.cap_top_z + 0.01)}
        for name, change in cases.items():
            with self.subTest(name):
                self.world = World(self.path)
                self.path.unlink(missing_ok=True)
                self.make()
                self.world.pick_patch = lambda view: replace(view, **change)
                self.assert_faulted()
                self.assert_no_arm_motion_to_target()

    def test_grid_invalid(self):
        self.world.grid_patch = lambda view: replace(view, success=False, message='no holes')
        self.assert_faulted('Grid observation invalid')
        self.assert_no_arm_motion_to_target()

    def test_grid_differs_from_record(self):
        self.world.grid_patch = lambda view: replace(view, occupied=(True,) + (False,) * 7)
        self.assert_faulted('differs from the record')
        self.assert_no_arm_motion_to_target()

    def test_c_count_differs_from_record(self):
        self.world.zone_patch = lambda view, _: replace(view, c_object_count=1)
        self.assert_faulted('differs from the record')
        self.assert_no_arm_motion_to_target()

    def test_preflight_failure_prevents_entering_any_target(self):
        self.world.fail['check_reachable'] = 1
        self.assert_faulted('injected check_reachable')
        self.assert_no_arm_motion_to_target()


class SlotPreflight(Base):
    def test_unreachable_next_slot_stops_before_taking_an_object(self):
        self.world.unreachable.add(('arm2', SETTINGS.c_slots[0]))
        self.assert_faulted('cannot reach')
        self.assertFalse(self.calls_named('move_to'))
        self.assertEqual(self.world.a_objects, 8)
        self.assertFalse(self.world.b_object)

    def test_later_unreachable_slot_stops_that_cycle_only(self):
        self.world.unreachable.add(('arm2', SETTINGS.c_slots[1]))
        with self.assertRaises(TaskFault):
            self.transfer.run(2)
        self.assertEqual(self.world.c[:2], [True, False])
        self.assertEqual(self.world.a_objects, 7)
        self.assertFalse(self.world.b_object)


class ZoneBFailures(Base):
    def test_b_not_clear_at_cycle_start(self):
        self.world.zone_patch = lambda view, _: replace(view, b_arm_clear=False)
        self.assert_faulted('not clear')
        self.assertFalse(self.calls_named('move_to'))

    def test_b_held_by_other_owner_is_refused(self):
        self.transfer.zone.acquire('arm2', observation_clear=True)
        self.assert_faulted('B zone unavailable')
        self.assertFalse([call for call in self.calls_named('move_to') if call[2][:2] == SETTINGS.b_place])

    def test_b_becomes_occupied_before_arm1_reservation(self):
        def patch(view, count):
            return replace(view, b_has_object=True) if count == 3 else view
        self.world.zone_patch = patch
        self.assert_faulted('before reservation')
        self.assertEqual(self.state['b_owner'], '')

    def test_arm1_placement_unverified_keeps_b(self):
        def patch(view, count):
            return replace(view, b_has_object=False) if count == 4 else view
        self.world.zone_patch = patch
        self.assert_faulted('unverified')
        self.assertEqual(self.state['b_owner'], 'arm1')

    def test_b_still_occupied_after_arm2_pickup_keeps_b(self):
        def patch(view, count):
            return replace(view, b_has_object=True) if count == 6 else view
        self.world.zone_patch = patch
        self.assert_faulted('after pickup')
        self.assertEqual(self.state['b_owner'], 'arm2')
        self.assertFalse([call for call in self.calls_named('move_to')
                          if call[2][:2] == SETTINGS.c_slots[0]])


class SlotVerification(Base):
    def test_unverified_placement_is_not_committed(self):
        for name, change in {'not placed': dict(placed=False), 'order': dict(order_ok=False),
                             'invalid': dict(success=False)}.items():
            with self.subTest(name):
                self.world = World(self.path)
                self.path.unlink(missing_ok=True)
                self.make()
                self.world.place_patch = lambda view: replace(view, **change)
                self.assert_faulted()
                self.assertEqual(self.state['occupied'], [False] * 8)
                self.assertFalse(self.calls_named('scene_add_slot_object'))

    def test_c_count_must_increase_by_one(self):
        def patch(view, count):
            return replace(view, c_object_count=0) if count == 7 else view
        self.world.zone_patch = patch
        self.assert_faulted('did not increase')
        self.assertEqual(self.state['occupied'], [False] * 8)


class Restart(Base):
    def test_incomplete_run_requires_recovery(self):
        self.world.fail['suction'] = 2
        self.assert_faulted()
        self.make()
        self.assertEqual(self.state['state'], 'FAULT')
        self.assertEqual(self.state['b_owner'], 'arm1')
        self.assertEqual(self.transfer.zone.owner, 'arm1')
        self.assertTrue(self.transfer.zone.faulted)
        self.assertEqual(self.gate.current[1], RECOVERY)
        count = len(self.world.calls)
        with self.assertRaises(TaskFault):
            self.transfer.run(1)
        self.assertEqual(len(self.world.calls), count)

    def test_interrupted_state_is_treated_as_incomplete(self):
        self.journal.update(state='ARM1:DESCEND_A', holding={'arm1': 'empty', 'arm2': 'empty'})
        self.make()
        self.assertEqual(self.state['state'], 'FAULT')

    def test_changed_configuration_requires_recovery(self):
        self.transfer.run(1)
        self.make('fingerprint-b')
        self.assertEqual(self.state['state'], 'FAULT')
        self.assertIn('changed', self.state['message'])

    def test_clean_run_restarts_without_recovery(self):
        self.transfer.run(1)
        self.make()
        self.assertEqual(self.state['state'], 'SUCCEEDED')
        self.assertEqual(self.transfer.run(1), 'SUCCEEDED')
        self.assertEqual(self.world.c[:2], [True, True])

    def test_full_state_requires_recovery_after_restart(self):
        self.transfer.run(8)
        self.make()
        self.assertEqual(self.gate.current[1], RECOVERY)
        with self.assertRaises(TaskFault):
            self.transfer.run(1)


class Recovery(Base):
    def fault_in_b(self):
        self.world.fail['suction'] = 2
        self.assert_faulted()
        # A person empties the tool, removes the object and moves the arm home.
        self.world.fail.clear()
        self.world.position['arm1'] = None
        self.world.b_object = False

    def test_successful_recovery_allows_a_new_run(self):
        self.fault_in_b()
        self.transfer.recover(self.token(), True)
        data = self.state
        self.assertEqual((data['state'], data['b_owner'], data['holding']['arm1']), ('IDLE', '', 'empty'))
        self.assertIsNone(self.transfer.zone.owner)
        self.assertEqual(self.transfer.run(1), 'SUCCEEDED')

    def test_recovery_clears_the_scene_and_restores_slots(self):
        self.fault_in_b()
        self.world.c = [True, True] + [False] * 6
        self.transfer.recover(self.token(), True)
        names = [call[0] for call in self.world.calls]
        self.assertLess(names.index('scene_reset'), names.index('scene_add_slot_object'))
        self.assertEqual([call[1] for call in self.calls_named('scene_add_slot_object')], [1, 2])

    def test_refused_recovery_leaves_the_scene_alone(self):
        self.fault_in_b()
        self.world.b_object = True
        with self.assertRaises(TaskFault):
            self.transfer.recover(self.token(), True)
        self.assertFalse(self.calls_named('scene_reset'))

    def test_scene_failure_keeps_the_fault(self):
        self.fault_in_b()
        self.world.fail['scene_reset'] = 1
        token = self.token()
        with self.assertRaises(TaskFault):
            self.transfer.recover(token, True)
        self.assertEqual(self.state['state'], 'FAULT')
        self.assertNotEqual(self.token(), token)

    def test_refused_when_not_confirmed(self):
        self.fault_in_b()
        token = self.token()
        with self.assertRaises(TaskFault):
            self.transfer.recover(token, False)
        self.assertEqual(self.state['state'], 'FAULT')
        self.assertNotEqual(self.token(), token)

    def test_refused_when_arm_not_home(self):
        self.fault_in_b()
        self.world.position['arm2'] = (0.0, 0.0)
        with self.assertRaises(TaskFault) as caught:
            self.transfer.recover(self.token(), True)
        self.assertIn('arm2 is not at HOME', str(caught.exception))

    def test_refused_when_b_occupied(self):
        self.fault_in_b()
        self.world.b_object = True
        with self.assertRaises(TaskFault):
            self.transfer.recover(self.token(), True)
        self.assertEqual(self.state['b_owner'], 'arm1')

    def test_refused_when_slots_are_not_contiguous(self):
        self.fault_in_b()
        self.world.c = [False, True] + [False] * 6
        with self.assertRaises(TaskFault) as caught:
            self.transfer.recover(self.token(), True)
        self.assertIn('contiguously', str(caught.exception))

    def test_refused_when_count_disagrees_with_grid(self):
        self.fault_in_b()
        self.world.zone_patch = lambda view, _: replace(view, c_object_count=3)
        with self.assertRaises(TaskFault):
            self.transfer.recover(self.token(), True)

    def test_recovery_adopts_observed_slots(self):
        self.fault_in_b()
        self.world.c = [True, True] + [False] * 6
        self.transfer.recover(self.token(), True)
        self.assertEqual(self.state['occupied'], [True, True] + [False] * 6)
        self.assertEqual(self.transfer.slots.committed, 2)

    def test_recovers_after_restart_with_retained_b(self):
        self.fault_in_b()
        self.make()
        self.transfer.recover(self.token(), True)
        self.assertEqual(self.state['state'], 'IDLE')
        self.assertIsNone(self.transfer.zone.owner)

    def test_recovery_records_new_fingerprint(self):
        self.transfer.run(1)
        self.make('fingerprint-b')
        self.transfer.recover(self.token(), True)
        self.assertEqual(self.state['config_fingerprint'], 'fingerprint-b')
        self.make('fingerprint-b')
        self.assertEqual(self.state['state'], 'IDLE')

    def test_nothing_to_recover(self):
        with self.assertRaises(TaskFault):
            self.transfer.recover('anything', True)

    def test_wrong_token_is_refused(self):
        self.fault_in_b()
        with self.assertRaises(TokenError):
            self.transfer.recover('wrong', True)
        self.assertEqual(self.state['state'], 'FAULT')


class Tokens(unittest.TestCase):
    def setUp(self):
        self.time = 0.0
        self.gate = TokenGate(10.0, clock=lambda: self.time)

    def test_token_is_single_use(self):
        token = self.gate.issue('grasp')
        self.gate.consume(token, 'grasp')
        with self.assertRaises(TokenError):
            self.gate.consume(token, 'grasp')

    def test_token_expires(self):
        token = self.gate.issue('grasp')
        self.time = 10.5
        with self.assertRaises(TokenError) as caught:
            self.gate.consume(token, 'grasp')
        self.assertIn('expired', str(caught.exception))

    def test_token_cannot_confirm_another_operation(self):
        token = self.gate.issue('grasp')
        with self.assertRaises(TokenError):
            self.gate.consume(token, 'release')

    def test_new_token_invalidates_previous(self):
        old = self.gate.issue('grasp')
        self.gate.issue('grasp')
        with self.assertRaises(TokenError):
            self.gate.consume(old, 'grasp')

    def test_ttl_must_be_positive(self):
        with self.assertRaises(ValueError):
            TokenGate(0)


class JournalFile(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / 'nested' / 'journal.json'

    def test_second_owner_is_refused(self):
        journal = Journal(self.path, FINGERPRINT)
        self.addCleanup(journal.close)
        with self.assertRaises(JournalError):
            Journal(self.path, FINGERPRINT)

    def test_corrupt_file_is_refused(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text('{not json', encoding='utf-8')
        with self.assertRaises(JournalError):
            Journal(self.path, FINGERPRINT)

    def test_invalid_contents_are_refused(self):
        journal = Journal(self.path, FINGERPRINT)
        data = journal.data
        journal.close()
        for change in (dict(occupied=[True]), dict(holding={'arm1': 'lost', 'arm2': 'empty'}), dict(b_owner='arm3')):
            with self.subTest(change):
                self.path.write_text(json.dumps({**data, **change}), encoding='utf-8')
                with self.assertRaises(JournalError):
                    Journal(self.path, FINGERPRINT)

    def test_update_rejects_invalid_values_and_keeps_record(self):
        journal = Journal(self.path, FINGERPRINT)
        self.addCleanup(journal.close)
        with self.assertRaises(JournalError):
            journal.update(b_owner='arm3')
        with self.assertRaises(JournalError):
            journal.update(unknown=1)
        self.assertEqual(json.loads(self.path.read_text(encoding='utf-8'))['b_owner'], '')

    def test_fingerprint_depends_on_config_and_model(self):
        base = config_fingerprint({'a': 1}, 'urdf')
        self.assertEqual(base, config_fingerprint({'a': 1}, 'urdf'))
        self.assertNotEqual(base, config_fingerprint({'a': 2}, 'urdf'))
        self.assertNotEqual(base, config_fingerprint({'a': 1}, 'other'))


class Isolation(unittest.TestCase):
    def test_task_logic_does_not_import_ros(self):
        code = ('import sys, dual_arm_coordinator.workflow.transfer, dual_arm_coordinator.journal, '
                'dual_arm_coordinator.confirmation; sys.exit(int("rclpy" in sys.modules))')
        result = subprocess.run([sys.executable, '-c', code], cwd=PACKAGE, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


class GoHome(Base):
    def fault_in_b(self):
        self.world.fail['suction'] = 2
        self.assert_faulted()
        self.world.fail.clear()

    def test_arm_owning_b_leaves_first(self):
        self.fault_in_b()
        self.assertEqual(self.state['b_owner'], 'arm1')
        self.world.position['arm2'] = (0.0, 0.0)
        self.world.calls.clear()
        self.assertEqual(self.transfer.go_home(), ['arm1', 'arm2'])
        self.assertEqual([call[1] for call in self.calls_named('move_home')], ['arm1', 'arm2'])
        self.assertTrue(self.world.at_home('arm1') and self.world.at_home('arm2'))
        # HOME does not recover: the fault and its token stay until /dual_arm/recover.
        self.assertEqual(self.state['state'], 'FAULT')
        self.assertEqual(self.gate.current[1], RECOVERY)

    def test_arm2_first_when_it_owns_b(self):
        self.journal.update(b_owner='arm2')
        self.world.position.update(arm1=(0.0, 0.0), arm2=SETTINGS.b_place)
        self.assertEqual(self.transfer.go_home(), ['arm2', 'arm1'])
        self.assertEqual([call[1] for call in self.calls_named('move_home')], ['arm2', 'arm1'])

    def test_arm_already_home_is_not_moved(self):
        self.world.position['arm2'] = (0.0, 0.0)
        self.transfer.go_home()
        self.assertEqual([call[1] for call in self.calls_named('move_home')], ['arm2'])
        self.assertEqual(self.state['active_arm'], '')

    def test_failed_move_faults_the_task(self):
        self.world.position['arm1'] = (0.0, 0.0)
        self.world.fail['move_home'] = 1
        with self.assertRaises(TaskFault):
            self.transfer.go_home()
        self.assertEqual(self.state['state'], 'FAULT')
        self.assertIn('injected move_home', self.state['message'])
        self.assertEqual(self.gate.current[1], RECOVERY)

    def test_stop_during_home_faults_and_moves_nothing_further(self):
        self.world.position.update(arm1=(0.0, 0.0), arm2=(0.0, 0.0))
        self.world.cancel_after = 1
        with self.assertRaises(TaskCancelled):
            self.transfer.go_home()
        self.assertEqual(len(self.calls_named('move_home')), 1)
        self.assertEqual(self.state['state'], 'FAULT')

    def test_needs_the_operator_confirmation(self):
        self.assertIn('did not confirm', self.transfer.home_problem(False, simulation=True))
        self.assertIsNone(self.transfer.home_problem(True, simulation=True))

    def test_simulation_refuses_while_an_arm_may_hold_an_object(self):
        for value in ('held', 'unknown'):
            with self.subTest(value):
                holding = {'arm1': 'empty', 'arm2': value}
                self.journal.update(holding=holding)
                self.assertIn('reset the simulation', self.transfer.home_problem(True, simulation=True))
                # On hardware a person can take the object off, which the confirmation states.
                self.assertIsNone(self.transfer.home_problem(True, simulation=False))


if __name__ == '__main__':
    unittest.main()
