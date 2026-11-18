import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest

import yaml

from dual_arm_coordinator import task_config
from dual_arm_coordinator.task_config import TaskConfigError

CONFIG = Path(__file__).resolve().parents[1] / 'config'
SIM = CONFIG / 'sim' / 'coordinator.yaml'
HARDWARE = CONFIG / 'hardware' / 'coordinator.yaml'


def sim_doc():
    return yaml.safe_load(SIM.read_text(encoding='utf-8'))


def filled_hardware_doc():
    """Test fixture only: shows the template is refused because of its nulls."""
    doc = sim_doc()
    doc.update(mode='hardware', evidence_kind='physical', home_source='calibration')
    doc['gripper'].update(backend='manual_token', auto_confirm=False)
    return doc


def prototype_doc():
    doc = sim_doc()
    doc.update(mode='prototype', evidence_kind='prototype_estimate', home_source='calibration')
    doc['gripper'].update(backend='esp32', auto_confirm=True)
    return doc


class ShippedFiles(unittest.TestCase):
    def test_simulation_file_loads(self):
        self.assertEqual(task_config.load(SIM)['mode'], 'simulation')

    def test_hardware_template_cannot_load(self):
        with self.assertRaises(TaskConfigError) as caught:
            task_config.load(HARDWARE)
        self.assertIn('speeds.transport_scale is not measured', str(caught.exception))
        self.assertIn('zones.c_slots_xy_m is not measured', str(caught.exception))

    def test_simulation_mirrors_runtime_json(self):
        runtime = json.loads((CONFIG / 'sim' / 'runtime.json').read_text(encoding='utf-8'))
        doc = sim_doc()
        self.assertEqual(doc['speeds']['transport_scale'], runtime['transport_speed_scale'])
        self.assertEqual(doc['speeds']['contact_scale'], runtime['contact_speed_scale'])
        self.assertEqual(doc['speeds']['acceleration_scale'], runtime['acceleration_scale'])
        self.assertEqual(doc['heights']['surface_z_m'], runtime['surface_z_m'])
        self.assertEqual(doc['heights']['cap_height_m'], runtime['cap_height_m'])

    def test_simulation_slots_match_world_formula(self):
        # Measured 2026-11-11: odd column x 0.135 next to B, rows 75..180 mm from the axis line y 0.125.
        expected = [[0.135 + col * 0.035, 0.05 - row * 0.035] for row in range(4) for col in range(2)]
        for actual, wanted in zip(sim_doc()['zones']['c_slots_xy_m'], expected):
            self.assertAlmostEqual(actual[0], wanted[0])
            self.assertAlmostEqual(actual[1], wanted[1])


class Validation(unittest.TestCase):
    def assert_refused(self, doc, text):
        with self.assertRaises(TaskConfigError) as caught:
            task_config.validate(doc)
        self.assertIn(text, str(caught.exception))

    def test_filled_hardware_document_is_accepted(self):
        self.assertEqual(task_config.validate(filled_hardware_doc())['mode'], 'hardware')

    def test_null_and_non_finite_are_not_measured(self):
        doc = sim_doc()
        doc['heights']['contact_z_m'] = None
        self.assert_refused(doc, 'heights.contact_z_m is not measured')
        doc = sim_doc()
        doc['zones']['b_place_xy_m'] = [0.0, float('nan')]
        self.assert_refused(doc, 'zones.b_place_xy_m.1 is not measured')

    def test_missing_and_unknown_keys(self):
        doc = sim_doc()
        del doc['motion']['motion_s']
        self.assert_refused(doc, 'motion.motion_s is missing')
        doc = sim_doc()
        doc['speeds']['transport_scael'] = 0.1
        self.assert_refused(doc, 'speeds.transport_scael is not a known setting')

    def test_document_must_be_a_mapping(self):
        self.assert_refused([], 'document must be a mapping')

    def test_hardware_cannot_use_simulation_home(self):
        doc = filled_hardware_doc()
        doc['home_source'] = 'runtime_json'
        self.assert_refused(doc, 'hardware requires home_source=calibration')

    def test_hardware_requires_physical_evidence(self):
        doc = filled_hardware_doc()
        doc['evidence_kind'] = 'simulation_assumed'
        self.assert_refused(doc, 'hardware requires evidence_kind=physical')

    def test_hardware_refuses_gazebo_gripper(self):
        doc = filled_hardware_doc()
        doc['gripper']['backend'] = 'gazebo'
        self.assert_refused(doc, 'does not allow gripper backend gazebo')

    def test_hardware_refuses_auto_confirm(self):
        doc = filled_hardware_doc()
        doc['gripper']['auto_confirm'] = True
        self.assert_refused(doc, 'auto_confirm is simulation only')

    def test_prototype_document_is_accepted(self):
        self.assertEqual(task_config.validate(prototype_doc())['mode'], 'prototype')

    def test_prototype_requires_prototype_evidence(self):
        doc = prototype_doc()
        doc['evidence_kind'] = 'physical'
        self.assert_refused(doc, 'prototype requires evidence_kind=prototype_estimate')

    def test_prototype_refuses_gazebo_gripper(self):
        doc = prototype_doc()
        doc['gripper']['backend'] = 'gazebo'
        self.assert_refused(doc, 'prototype does not allow gripper backend gazebo')

    def test_prototype_cannot_use_runtime_json_home(self):
        doc = prototype_doc()
        doc['home_source'] = 'runtime_json'
        self.assert_refused(doc, 'prototype requires home_source=calibration')

    def test_unknown_mode(self):
        doc = sim_doc()
        doc['mode'] = 'demo'
        self.assert_refused(doc, 'mode must be one of')

    def test_speed_range(self):
        for value in (0, 1.5, True):
            doc = sim_doc()
            doc['speeds']['contact_scale'] = value
            self.assert_refused(doc, 'speeds.contact_scale must be within')

    def test_height_order(self):
        doc = sim_doc()
        doc['heights']['release_z_m'] = doc['heights']['contact_z_m']
        self.assert_refused(doc, 'heights must satisfy')
        doc = sim_doc()
        doc['heights']['contact_z_m'] = 0.02
        self.assert_refused(doc, 'heights must satisfy')

    def test_zone_bounds_and_slots(self):
        doc = sim_doc()
        doc['zones']['a_max_xy_m'] = doc['zones']['a_min_xy_m']
        self.assert_refused(doc, 'a_min_xy_m must be below')
        doc = sim_doc()
        doc['zones']['c_slots_xy_m'].pop()
        self.assert_refused(doc, 'must list 8')
        doc = sim_doc()
        doc['zones']['c_slots_xy_m'][1] = copy.copy(doc['zones']['c_slots_xy_m'][0])
        self.assert_refused(doc, 'must be distinct')

    def test_b_pick_tolerance_must_be_positive(self):
        doc = sim_doc()
        doc['zones']['b_pick_tolerance_m'] = 0.0
        self.assert_refused(doc, 'zones.b_pick_tolerance_m must be positive')
        doc = sim_doc()
        del doc['zones']['b_pick_tolerance_m']
        self.assert_refused(doc, 'b_pick_tolerance_m')

    def test_tool_tilt_range(self):
        doc = sim_doc()
        doc['motion']['max_tool_tilt_deg'] = 0
        self.assertEqual(task_config.validate(doc)['motion']['max_tool_tilt_deg'], 0)
        for value in (-1, 90, True):
            doc = sim_doc()
            doc['motion']['max_tool_tilt_deg'] = value
            self.assert_refused(doc, 'max_tool_tilt_deg must be within')

    def test_planning_attempts_must_be_integer(self):
        doc = sim_doc()
        doc['motion']['planning_attempts'] = 1.5
        self.assert_refused(doc, 'planning_attempts must be an integer')


def slot_teach():
    return {'arm': 'arm2', 'source': 'test', 'raw': [[512, 600, 700, 600 + slot] for slot in range(8)],
            'release_lift_m': 0.0, 'arrival_tolerance_raw': 4, 'max_line_drift_m': 0.003}


class SlotTeach(unittest.TestCase):
    def assert_refused(self, doc, text):
        with self.assertRaises(TaskConfigError) as caught:
            task_config.validate(doc)
        self.assertIn(text, str(caught.exception))

    def with_teach(self, doc=None, **change):
        doc = doc or prototype_doc()
        doc['c_slot_teach'] = {**slot_teach(), **change}
        return doc

    def test_prototype_accepts_taught_slots(self):
        self.assertIn('c_slot_teach', task_config.validate(self.with_teach()))

    def test_documents_without_teach_still_load(self):
        self.assertNotIn('c_slot_teach', task_config.validate(prototype_doc()))

    def test_only_prototype_may_teach(self):
        self.assert_refused(self.with_teach(sim_doc()), "c_slot_teach is only allowed in ('prototype',)")

    def test_only_arm2_places_in_c(self):
        self.assert_refused(self.with_teach(arm='arm1'), 'c_slot_teach.arm must be arm2')

    def test_shape_and_unknown_keys(self):
        doc = self.with_teach()
        del doc['c_slot_teach']['source']
        doc['c_slot_teach']['extra'] = 1
        self.assert_refused(doc, 'c_slot_teach.source is missing')
        self.assert_refused(doc, 'c_slot_teach.extra is not a known setting')

    def test_null_is_not_measured(self):
        self.assert_refused(self.with_teach(release_lift_m=None), 'c_slot_teach.release_lift_m is not measured')

    def test_raw_poses(self):
        raw = slot_teach()['raw']
        self.assert_refused(self.with_teach(raw=raw[:7]), 'must list 8 poses of four counts')
        self.assert_refused(self.with_teach(raw=raw[:7] + [[1, 2, 3]]), 'must list 8 poses of four counts')
        for bad in (1024, -1, 512.0, True):
            with self.subTest(bad=bad):
                self.assert_refused(self.with_teach(raw=raw[:7] + [[bad, 2, 3, 4]]),
                                    'counts must be integers in 0..1023')

    def test_number_ranges(self):
        self.assert_refused(self.with_teach(release_lift_m=0.03), 'release_lift_m must be within [0, 0.02]')
        self.assert_refused(self.with_teach(arrival_tolerance_raw=0), 'arrival_tolerance_raw must be an integer')
        self.assert_refused(self.with_teach(arrival_tolerance_raw=2.5), 'arrival_tolerance_raw must be an integer')

    def test_slot_above_arrival_tolerance_is_optional_and_bounded(self):
        task_config.validate(self.with_teach(above_arrival_tolerance_raw=6))
        self.assert_refused(self.with_teach(above_arrival_tolerance_raw=21),
                            'c_slot_teach.above_arrival_tolerance_raw must be an integer in 1..20')
        self.assert_refused(self.with_teach(above_arrival_tolerance_raw=3), 'must not be below arrival_tolerance_raw')
        self.assert_refused(self.with_teach(max_line_drift_m=0), 'max_line_drift_m must be within (0, 0.01]')


def b_teach():
    return {'source': 'test', 'raw': {'arm1': [350, 731, 702, 697], 'arm2': [396, 703, 756, 700]},
            'contact_lift_m': 0.0, 'arrival_tolerance_raw': 4, 'max_line_drift_m': 0.003}


class BReleaseLift(unittest.TestCase):
    def assert_refused(self, doc, text):
        with self.assertRaises(TaskConfigError) as caught:
            task_config.validate(doc)
        self.assertIn(text, str(caught.exception))

    def with_lift(self, value, doc=None, teach=True):
        doc = doc or prototype_doc()
        if teach:
            doc['b_teach'] = b_teach()
        doc['b_release_lift_extra_m'] = value
        return doc

    def test_prototype_accepts_it(self):
        self.assertEqual(task_config.validate(self.with_lift(0.005))['b_release_lift_extra_m'], 0.005)

    def test_needs_a_taught_b(self):
        self.assert_refused(self.with_lift(0.005, teach=False), 'b_release_lift_extra_m needs b_teach')

    def test_value_is_bounded(self):
        for value in (-0.001, 0.031, 'x', None):
            with self.subTest(value):
                self.assert_refused(self.with_lift(value), 'b_release_lift_extra_m must be within')


class APress(unittest.TestCase):
    def assert_refused(self, doc, text):
        with self.assertRaises(TaskConfigError) as caught:
            task_config.validate(doc)
        self.assertIn(text, str(caught.exception))

    def with_press(self, value, doc=None):
        doc = doc or prototype_doc()
        doc['a_press_m'] = value
        return doc

    def test_prototype_accepts_it(self):
        self.assertEqual(task_config.validate(self.with_press(0.003))['a_press_m'], 0.003)

    def test_only_prototype(self):
        self.assert_refused(self.with_press(0.003, sim_doc()), "a_press_m is only allowed in ('prototype',)")

    def test_value_is_bounded(self):
        for value in (0.0, -0.001, 0.009, 'x', None):
            with self.subTest(value):
                self.assert_refused(self.with_press(value), 'a_press_m must be within')


class DirectTransfer(unittest.TestCase):
    def assert_refused(self, doc, text):
        with self.assertRaises(TaskConfigError) as caught:
            task_config.validate(doc)
        self.assertIn(text, str(caught.exception))

    def with_direct(self, value, doc=None):
        doc = doc or prototype_doc()
        doc['direct_transfer'] = value
        return doc

    def test_prototype_accepts_it(self):
        self.assertIs(task_config.validate(self.with_direct(True))['direct_transfer'], True)

    def test_only_prototype(self):
        self.assert_refused(self.with_direct(True, sim_doc()), "direct_transfer is only allowed in ('prototype',)")

    def test_must_be_a_boolean(self):
        for value in (1, 'yes', None):
            with self.subTest(value):
                self.assert_refused(self.with_direct(value), 'direct_transfer must be true or false')


class FixedTransits(unittest.TestCase):
    def assert_refused(self, doc, text):
        with self.assertRaises(TaskConfigError) as caught:
            task_config.validate(doc)
        self.assertIn(text, str(caught.exception))

    def with_fixed(self, value, doc=None):
        doc = doc or prototype_doc()
        doc['fixed_transits'] = value
        return doc

    def test_prototype_accepts_it(self):
        self.assertIs(task_config.validate(self.with_fixed(True))['fixed_transits'], True)

    def test_only_prototype(self):
        self.assert_refused(self.with_fixed(True, sim_doc()), "fixed_transits is only allowed in ('prototype',)")

    def test_must_be_a_boolean(self):
        for value in (1, 'yes', None):
            with self.subTest(value):
                self.assert_refused(self.with_fixed(value), 'fixed_transits must be true or false')


class GraspSettle(unittest.TestCase):
    def assert_refused(self, doc, text):
        with self.assertRaises(TaskConfigError) as caught:
            task_config.validate(doc)
        self.assertIn(text, str(caught.exception))

    def with_grasp(self, value, doc=None):
        doc = doc or prototype_doc()
        doc['gripper']['vacuum_settle_s'] = 2.0  # the prototype file's value; the fixture comes from simulation
        doc['grasp_settle_s'] = value
        return doc

    def test_prototype_accepts_it(self):
        self.assertEqual(task_config.validate(self.with_grasp(1.2))['grasp_settle_s'], 1.2)

    def test_only_prototype(self):
        self.assert_refused(self.with_grasp(1.2, sim_doc()), "grasp_settle_s is only allowed in ('prototype',)")

    def test_not_below_one_second_nor_above_the_release_wait(self):
        for value in (0.9, 2.1, 'x', None):
            with self.subTest(value):
                self.assert_refused(self.with_grasp(value), 'grasp_settle_s must be within')


class DescentCorrection(unittest.TestCase):
    def assert_refused(self, doc, text):
        with self.assertRaises(TaskConfigError) as caught:
            task_config.validate(doc)
        self.assertIn(text, str(caught.exception))

    def with_descent(self, doc=None, **change):
        doc = doc or prototype_doc()
        doc['descent_correction'] = {**{'tolerance_m': 0.002, 'max_extra_m': 0.005, 'attempts': 2}, **change}
        return doc

    def test_prototype_accepts_it(self):
        self.assertIn('descent_correction', task_config.validate(self.with_descent()))

    def test_only_prototype(self):
        self.assert_refused(self.with_descent(sim_doc()), "descent_correction is only allowed in ('prototype',)")

    def test_values_are_bounded(self):
        for change, text in (({'max_extra_m': 0.02}, 'max_extra_m must be within'),
                             ({'tolerance_m': 0.0}, 'tolerance_m must be within'),
                             ({'attempts': 4}, 'attempts must be an integer'),
                             ({'attempts': 1.0}, 'attempts must be an integer'),
                             ({'extra': 1}, 'descent_correction.extra is not a known setting')):
            with self.subTest(change):
                self.assert_refused(self.with_descent(**change), text)


class APickOffset(unittest.TestCase):
    def assert_refused(self, doc, text):
        with self.assertRaises(TaskConfigError) as caught:
            task_config.validate(doc)
        self.assertIn(text, str(caught.exception))

    def with_offset(self, value, doc=None):
        doc = doc or prototype_doc()
        doc['a_pick_offset_xy_m'] = value
        return doc

    def test_prototype_accepts_a_small_offset(self):
        self.assertEqual(task_config.validate(self.with_offset([0.002, -0.001]))['a_pick_offset_xy_m'], [0.002, -0.001])

    def test_only_prototype_may_offset(self):
        self.assert_refused(self.with_offset([0.002, 0.0], sim_doc()), "a_pick_offset_xy_m is only allowed in ('prototype',)")

    def test_offset_is_bounded(self):
        for value in ([0.021, 0.0], [0.0, -0.03], [0.002], 'x', [None, 0.0]):
            with self.subTest(value):
                self.assert_refused(self.with_offset(value), 'a_pick_offset_xy_m must be [x, y]')


class AutoResume(unittest.TestCase):
    def assert_refused(self, doc, text):
        with self.assertRaises(TaskConfigError) as caught:
            task_config.validate(doc)
        self.assertIn(text, str(caught.exception))

    def with_resume(self, doc=None, node=None):
        doc = doc or prototype_doc()
        doc['auto_resume'] = {'max_resumes': 3} if node is None else node
        return doc

    def test_prototype_may_resume(self):
        doc = task_config.validate(self.with_resume())
        self.assertEqual(task_config.max_resumes(doc), 3)

    def test_absent_means_no_resume(self):
        self.assertEqual(task_config.max_resumes(task_config.validate(prototype_doc())), 0)

    def test_only_prototype_may_resume(self):
        self.assert_refused(self.with_resume(sim_doc()), "auto_resume is only allowed in ('prototype',)")

    def test_count_is_bounded(self):
        for value in (0, 6, 1.0, True, None):
            with self.subTest(value):
                self.assert_refused(self.with_resume(node={'max_resumes': value}), 'auto_resume.max_resumes must be')

    def test_shape_is_checked(self):
        self.assert_refused(self.with_resume(node={'max_resumes': 1, 'extra': 1}), 'auto_resume.extra is not a known setting')
        self.assert_refused(self.with_resume(node=[]), 'auto_resume must be a mapping')


class Overlap(unittest.TestCase):
    def assert_refused(self, doc, text):
        with self.assertRaises(TaskConfigError) as caught:
            task_config.validate(doc)
        self.assertIn(text, str(caught.exception))

    def with_overlap(self, doc=None, node=None):
        doc = doc or prototype_doc()
        doc['overlap'] = {'clearance_m': 0.025, 'wait_s': 240.0} if node is None else node
        return doc

    def test_prototype_may_overlap(self):
        task_config.validate(self.with_overlap())

    def test_overlap_and_direct_transfer_cannot_both_be_on(self):
        doc = self.with_overlap()
        doc['direct_transfer'] = True
        self.assert_refused(doc, 'overlap and direct_transfer cannot both be on')
        doc['direct_transfer'] = False
        task_config.validate(doc)

    def test_shipped_prototype_keeps_overlap_off(self):
        doc = task_config.load(CONFIG / 'prototype' / 'coordinator.yaml')
        self.assertNotIn('overlap', doc)
        self.assertIs(doc['direct_transfer'], True)

    def test_only_prototype_may_overlap(self):
        self.assert_refused(self.with_overlap(sim_doc()), "overlap is only allowed in ('prototype',)")

    def test_needs_automatic_suction_confirmation(self):
        doc = self.with_overlap()
        doc['gripper']['auto_confirm'] = False
        self.assert_refused(doc, 'overlap needs gripper.auto_confirm')

    def test_values_are_bounded(self):
        for key, value in (('clearance_m', 0.005), ('clearance_m', 0.2), ('clearance_m', None),
                           ('wait_s', 0.5), ('wait_s', 700.0), ('wait_s', 'x')):
            with self.subTest(key=key, value=value):
                node = {'clearance_m': 0.025, 'wait_s': 240.0, key: value}
                self.assert_refused(self.with_overlap(node=node), f'overlap.{key}')

    def test_shape_is_checked(self):
        self.assert_refused(self.with_overlap(node={'clearance_m': 0.02}), 'overlap.wait_s is missing')
        self.assert_refused(self.with_overlap(node=[]), 'overlap must be a mapping')


class BTeach(unittest.TestCase):
    def assert_refused(self, doc, text):
        with self.assertRaises(TaskConfigError) as caught:
            task_config.validate(doc)
        self.assertIn(text, str(caught.exception))

    def with_teach(self, doc=None, **change):
        doc = doc or prototype_doc()
        doc['b_teach'] = {**b_teach(), **change}
        return doc

    def test_prototype_accepts_a_taught_b_with_or_without_taught_slots(self):
        self.assertIn('b_teach', task_config.validate(self.with_teach()))
        doc = self.with_teach()
        doc['c_slot_teach'] = slot_teach()
        self.assertEqual({'b_teach', 'c_slot_teach'} & set(task_config.validate(doc)), {'b_teach', 'c_slot_teach'})

    def test_only_prototype_may_teach(self):
        self.assert_refused(self.with_teach(sim_doc()), "b_teach is only allowed in ('prototype',)")

    def test_shape_and_unknown_keys(self):
        doc = self.with_teach()
        del doc['b_teach']['source']
        doc['b_teach']['extra'] = 1
        self.assert_refused(doc, 'b_teach.source is missing')
        self.assert_refused(doc, 'b_teach.extra is not a known setting')

    def test_null_is_not_measured(self):
        self.assert_refused(self.with_teach(contact_lift_m=None), 'b_teach.contact_lift_m is not measured')

    def test_raw_needs_both_arms_with_four_counts(self):
        self.assert_refused(self.with_teach(raw={'arm1': [1, 2, 3, 4]}), 'b_teach.raw must give arm1 and arm2')
        self.assert_refused(self.with_teach(raw=[[1, 2, 3, 4], [1, 2, 3, 4]]), 'b_teach.raw must give arm1 and arm2')
        for bad in ([1, 2, 3], [1024, 2, 3, 4], [1.0, 2, 3, 4], [True, 2, 3, 4]):
            with self.subTest(bad=bad):
                self.assert_refused(self.with_teach(raw={'arm1': [1, 2, 3, 4], 'arm2': bad}),
                                    'b_teach.raw.arm2 must be four integer counts in 0..1023')

    def test_number_ranges(self):
        self.assert_refused(self.with_teach(contact_lift_m=0.03), 'b_teach.contact_lift_m must be within [0, 0.02]')
        self.assert_refused(self.with_teach(arrival_tolerance_raw=21), 'b_teach.arrival_tolerance_raw must be')
        self.assert_refused(self.with_teach(max_line_drift_m=0.02), 'b_teach.max_line_drift_m must be within')

    def test_above_arrival_tolerance_is_optional_and_bounded(self):
        task_config.validate(self.with_teach(above_arrival_tolerance_raw=6))
        self.assert_refused(self.with_teach(above_arrival_tolerance_raw=21),
                            'b_teach.above_arrival_tolerance_raw must be an integer in 1..20')
        self.assert_refused(self.with_teach(above_arrival_tolerance_raw=6.0),
                            'b_teach.above_arrival_tolerance_raw must be an integer in 1..20')
        self.assert_refused(self.with_teach(above_arrival_tolerance_raw=3),
                            'must not be below arrival_tolerance_raw')


class CommandLine(unittest.TestCase):
    def run_main(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = task_config.main([str(arg) for arg in args])
        return code, output.getvalue()

    def test_reports_pass_and_fail(self):
        code, text = self.run_main(SIM)
        self.assertEqual(code, 0)
        self.assertTrue(text.startswith('PASS'))
        code, text = self.run_main(HARDWARE)
        self.assertEqual(code, 1)
        self.assertTrue(text.startswith('FAIL'))

    def test_invalid_yaml_and_missing_file(self):
        with tempfile.TemporaryDirectory() as folder:
            bad = Path(folder) / 'bad.yaml'
            bad.write_text('a: [', encoding='utf-8')
            self.assertEqual(self.run_main(bad)[0], 1)
            self.assertEqual(self.run_main(Path(folder) / 'absent.yaml')[0], 1)


if __name__ == '__main__':
    unittest.main()
