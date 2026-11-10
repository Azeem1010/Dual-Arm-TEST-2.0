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
        expected = [[0.1675 - col * 0.035, -0.09 + row * 0.035] for row in range(4) for col in range(2)]
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

    def test_planning_attempts_must_be_integer(self):
        doc = sim_doc()
        doc['motion']['planning_attempts'] = 1.5
        self.assert_refused(doc, 'planning_attempts must be an integer')


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
