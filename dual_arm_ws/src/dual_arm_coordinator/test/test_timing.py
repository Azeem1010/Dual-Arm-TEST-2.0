import csv
from pathlib import Path
import tempfile
import threading
import unittest

from dual_arm_coordinator import timing
from dual_arm_coordinator.timing import StepTimer


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class StepTimes(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.lines = []
        self.timer = StepTimer(clock=self.clock, on_step=self.lines.append)

    def test_nothing_is_recorded_before_start(self):
        self.timer.step('arm1', 'APPROACH_A')
        with self.timer.span('move'):
            self.clock.advance(1.0)
        self.assertEqual(self.timer.finish(), [])
        self.assertEqual(self.lines, [])

    def test_a_step_lasts_until_the_next_step_of_the_same_arm(self):
        self.timer.start()
        self.timer.step('arm1', 'APPROACH_A')
        self.clock.advance(2.0)
        self.timer.step('arm1', 'DESCEND_A')
        self.clock.advance(3.0)
        records = self.timer.finish()
        self.assertEqual([(r['arm'], r['step'], r['duration']) for r in records],
                         [('arm1', 'APPROACH_A', 2.0), ('arm1', 'DESCEND_A', 3.0)])
        self.assertEqual([r['start'] for r in records], [0.0, 2.0])

    def test_spans_split_the_step_and_the_rest_is_other(self):
        self.timer.start()
        self.timer.step('arm1', 'APPROACH_A')
        with self.timer.span('still'):
            self.clock.advance(0.5)
        with self.timer.span('move'):
            self.clock.advance(4.0)
        self.timer.add('plan', 1.0)
        self.timer.add('move', -1.0)
        self.clock.advance(0.25)
        record = self.timer.finish()[0]
        self.assertEqual(record['parts'], {'still': 0.5, 'move': 3.0, 'plan': 1.0})
        self.assertAlmostEqual(timing.other(record), 0.25)

    def test_each_closed_step_is_reported(self):
        self.timer.start()
        self.timer.step('arm1', 'APPROACH_A')
        with self.timer.span('move'):
            self.clock.advance(4.0)
        self.timer.step('arm1', 'DESCEND_A')
        self.assertEqual(self.lines, ['TIMING arm1:APPROACH_A 4.00 s (move 4.00)'])

    def test_a_span_belongs_to_the_arm_of_its_thread(self):
        self.timer.start()
        self.timer.step('arm1', 'GRASP_A')

        def arm2():
            self.timer.step('arm2', 'GRASP_B')
            self.timer.add('vacuum', 2.0)

        worker = threading.Thread(target=arm2)
        worker.start()
        worker.join()
        self.timer.add('echo', 0.1)
        self.clock.advance(3.0)
        parts = {r['arm']: r['parts'] for r in self.timer.finish()}
        self.assertEqual(parts, {'arm1': {'echo': 0.1}, 'arm2': {'vacuum': 2.0}})

    def test_a_failing_span_still_counts(self):
        self.timer.start()
        self.timer.step('arm1', 'APPROACH_A')
        with self.assertRaises(RuntimeError):
            with self.timer.span('move'):
                self.clock.advance(1.5)
                raise RuntimeError('fault')
        self.assertEqual(self.timer.finish()[0]['parts'], {'move': 1.5})

    def test_start_clears_the_previous_run(self):
        self.timer.start()
        self.timer.step('arm1', 'APPROACH_A')
        self.timer.finish()
        self.timer.start()
        self.assertEqual(self.timer.finish(), [])


class Report(unittest.TestCase):
    def records(self):
        clock = Clock()
        timer = StepTimer(clock=clock)
        timer.start()
        for arm, step, parts, rest in (('arm1', 'APPROACH_A', {'plan': 1.0, 'move': 5.0}, 0.0),
                                       ('arm1', 'GRASP_A', {'echo': 0.1, 'vacuum': 2.0}, 0.0),
                                       ('arm2', 'APPROACH_C', {'move': 6.0, 'still': 1.0}, 0.9)):
            timer.step(arm, step)
            for kind, seconds in parts.items():
                timer.add(kind, seconds)
            clock.advance(sum(parts.values()) + rest)
        return timer.finish()

    def test_summary_totals_by_kind_and_step(self):
        text = timing.summary(self.records(), objects=2)
        self.assertIn('TIMING SUMMARY 2 object(s), 16.00 s, 8.00 s per object', text)
        self.assertIn('move 11.00 s', text)
        self.assertIn('other 0.90 s', text)
        self.assertIn('arm2:APPROACH_C 7.90 s', text)
        # the slowest step comes first
        self.assertLess(text.index('arm2:APPROACH_C'), text.index('arm1:APPROACH_A'))

    def test_summary_without_objects(self):
        self.assertIn('0 object(s), 16.00 s', timing.summary(self.records(), objects=0))
        self.assertEqual(timing.summary([], objects=0), 'TIMING SUMMARY no steps recorded')

    def test_csv_has_one_row_per_step_and_a_column_per_kind(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'timing' / 'run.csv'
            timing.write_csv(self.records(), path)
            rows = list(csv.DictReader(path.open(encoding='utf-8')))
        self.assertEqual([row['step'] for row in rows], ['APPROACH_A', 'GRASP_A', 'APPROACH_C'])
        self.assertEqual(rows[2]['move'], '6.000')
        self.assertEqual(rows[2]['other'], '0.900')
        self.assertEqual(rows[0]['vacuum'], '0.000')


class Workflow(unittest.TestCase):
    """The shared timer follows the workflow steps of a real transfer."""

    def test_a_transfer_records_every_step_of_both_arms(self):
        import test_workflow
        case = test_workflow.HappyPath('test_one_object_reaches_slot_one')
        case.setUp()
        self.addCleanup(case.doCleanups)
        timing.TIMER.start()
        try:
            self.assertEqual(case.transfer.run(1), 'SUCCEEDED')
        finally:
            records = timing.TIMER.finish()
        steps = {(r['arm'], r['step']) for r in records}
        for expected in (('arm1', 'APPROACH_A'), ('arm1', 'VERIFY_B'), ('arm2', 'GRASP_B'), ('arm2', 'VERIFY_C')):
            self.assertIn(expected, steps)
