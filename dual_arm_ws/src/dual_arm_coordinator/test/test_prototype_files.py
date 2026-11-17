"""The prototype settings load, stay labelled as estimates, and leave the strict files untouched."""
import json
import math
from pathlib import Path
import unittest

import yaml

from dual_arm_coordinator import task_config
from dual_arm_coordinator.homes import JOINT_SUFFIXES, load_b_joints, load_homes, load_slot_joints
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

    # User decision 2026-11-17: arm2 j1 read 90 at B where 2026-11-11 read 396, so its zero moved by -306.
    ZERO_EXCEPTIONS = {('arm2', 'arm_shoulder_pan_joint'): 206}

    def test_prototype_calibration_matches_runtime_json(self):
        runtime = json.loads(RUNTIME.read_text(encoding='utf-8'))['home']
        data = calibration()
        for arm in ARMS:
            for index, suffix in enumerate(JOINT_SUFFIXES):
                joint = data['joints'][f'{arm}_{suffix}']
                expected = self.ZERO_EXCEPTIONS.get((arm, suffix), runtime[arm]['raw_at_cad_zero'][index])
                self.assertEqual(joint['zero_raw'], expected)
                self.assertEqual(joint['direction'], runtime[arm]['direction'][index])

    def test_taught_slots_round_trip_to_the_taught_counts(self):
        """The driver turns the radians back into counts with the same file, so nothing moves."""
        config = task_config.load(PROTOTYPE_CONFIG)
        joints = load_slot_joints(config, calibration_path=str(PROTOTYPE_CALIBRATION))
        self.assertEqual(joints['arm'], 'arm2')
        data = calibration()
        for raw, q in zip(config['c_slot_teach']['raw'], joints['release']):
            counts = []
            for value, suffix in zip(q, JOINT_SUFFIXES):
                joint = data['joints'][f'arm2_{suffix}']
                counts.append(round(joint['zero_raw'] + joint['direction'] * value * 1023 / math.radians(300)))
            self.assertEqual(counts, raw)

    def test_taught_slots_must_be_inside_the_calibration_limits(self):
        config = task_config.load(PROTOTYPE_CONFIG)
        config['c_slot_teach']['raw'][0] = [1000, 630, 926, 602]
        with self.assertRaisesRegex(ValueError, 'Slot 1 arm_shoulder_pan_joint count 1000 is outside'):
            load_slot_joints(config, calibration_path=str(PROTOTYPE_CALIBRATION))

    def test_taught_slots_need_the_driver_calibration(self):
        with self.assertRaisesRegex(ValueError, 'need the calibration file'):
            load_slot_joints(task_config.load(PROTOTYPE_CONFIG))
        self.assertIsNone(load_slot_joints({}, calibration_path=str(PROTOTYPE_CALIBRATION)))

    def test_taught_b_round_trips_to_the_taught_counts(self):
        config = task_config.load(PROTOTYPE_CONFIG)
        joints = load_b_joints(config, calibration_path=str(PROTOTYPE_CALIBRATION))
        data = calibration()
        for arm in ARMS:
            counts = []
            for value, suffix in zip(joints[arm], JOINT_SUFFIXES):
                joint = data['joints'][f'{arm}_{suffix}']
                counts.append(round(joint['zero_raw'] + joint['direction'] * value * 1023 / math.radians(300)))
            self.assertEqual(counts, config['b_teach']['raw'][arm], arm)

    def test_taught_b_uses_the_accepted_arm1_redo(self):
        self.assertEqual(task_config.load(PROTOTYPE_CONFIG)['b_teach']['raw']['arm1'], [350, 731, 702, 697])

    def test_taught_b_must_be_inside_the_calibration_limits_and_needs_it(self):
        config = task_config.load(PROTOTYPE_CONFIG)
        # The rejected first arm1 file (j1 634) lies outside arm1's j1 limits 0..486.
        config['b_teach']['raw']['arm1'] = [634, 717, 742, 699]
        with self.assertRaisesRegex(ValueError, 'B arm1 arm_shoulder_pan_joint count 634 is outside'):
            load_b_joints(config, calibration_path=str(PROTOTYPE_CALIBRATION))
        with self.assertRaisesRegex(ValueError, 'need the calibration file'):
            load_b_joints(task_config.load(PROTOTYPE_CONFIG))
        self.assertIsNone(load_b_joints({}, calibration_path=str(PROTOTYPE_CALIBRATION)))

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
