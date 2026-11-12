"""The prototype settings load, stay labelled as estimates, and leave the strict files untouched."""
import json
from pathlib import Path
import unittest

import yaml

from dual_arm_coordinator import task_config
from dual_arm_coordinator.homes import JOINT_SUFFIXES, load_homes
from dual_arm_coordinator.task_config import TaskConfigError

SRC = Path(__file__).resolve().parents[2]
PROTOTYPE_CONFIG = SRC / 'dual_arm_coordinator' / 'config' / 'prototype' / 'coordinator.yaml'
PROTOTYPE_CALIBRATION = SRC / 'cm530_hardware' / 'config' / 'calibration_prototype.yaml'
PROTOTYPE_CONTROLLERS = SRC / 'dual_arm_controllers' / 'config' / 'controllers_prototype.yaml'
RUNTIME = SRC / 'dual_arm_coordinator' / 'config' / 'sim' / 'runtime.json'
STRICT_CALIBRATION = SRC / 'cm530_hardware' / 'config' / 'calibration.yaml'
STRICT_CONFIG = SRC / 'dual_arm_coordinator' / 'config' / 'hardware' / 'coordinator.yaml'
HEADER = '# PROTOTYPE ESTIMATE (2026-11-13): not measured, not calibration evidence.'
ARMS = ('arm1', 'arm2')


def calibration():
    return yaml.safe_load(PROTOTYPE_CALIBRATION.read_text(encoding='utf-8'))


class PrototypeFiles(unittest.TestCase):
    def test_prototype_coordinator_loads(self):
        doc = task_config.load(PROTOTYPE_CONFIG)
        self.assertEqual(doc['mode'], 'prototype')
        self.assertEqual(doc['gripper']['backend'], 'esp32')
        self.assertTrue(doc['gripper']['auto_confirm'])

    def test_prototype_calibration_gives_homes(self):
        homes = load_homes({'home_source': 'calibration', 'mode': 'prototype'},
                           calibration_path=str(PROTOTYPE_CALIBRATION))
        self.assertEqual(sorted(homes), list(ARMS))
        data = calibration()
        for arm in ARMS:
            self.assertEqual(len(homes[arm]), 4)
            for raw, suffix in zip(data['expected_home'][arm], JOINT_SUFFIXES):
                joint = data['joints'][f'{arm}_{suffix}']
                self.assertLessEqual(joint['min_raw'], raw, f'{arm} {suffix}')
                self.assertLessEqual(raw, joint['max_raw'], f'{arm} {suffix}')

    def test_prototype_calibration_matches_runtime_json(self):
        runtime = json.loads(RUNTIME.read_text(encoding='utf-8'))['home']
        data = calibration()
        for arm in ARMS:
            for index, suffix in enumerate(JOINT_SUFFIXES):
                joint = data['joints'][f'{arm}_{suffix}']
                self.assertEqual(joint['zero_raw'], runtime[arm]['raw_at_cad_zero'][index])
                self.assertEqual(joint['direction'], runtime[arm]['direction'][index])

    def test_prototype_files_are_labelled(self):
        for path in (PROTOTYPE_CONFIG, PROTOTYPE_CALIBRATION, PROTOTYPE_CONTROLLERS):
            with self.subTest(path.name):
                self.assertEqual(path.read_text(encoding='utf-8').splitlines()[0], HEADER)

    def test_strict_files_unchanged(self):
        self.assertEqual(yaml.safe_load(STRICT_CALIBRATION.read_text(encoding='utf-8'))['status'], 'NOT_RUN')
        with self.assertRaises(TaskConfigError):
            task_config.load(STRICT_CONFIG)


if __name__ == '__main__':
    unittest.main()
