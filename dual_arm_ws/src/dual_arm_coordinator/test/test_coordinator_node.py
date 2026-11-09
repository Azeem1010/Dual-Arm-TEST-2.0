"""Startup refusals of the real node; no MoveIt or Gazebo is needed."""
from pathlib import Path
import tempfile
import unittest

import rclpy
from rclpy.context import Context
from rclpy.parameter import Parameter
import yaml

from dual_arm_coordinator import coordinator_node
from dual_arm_coordinator.coordinator_node import CoordinatorNode
from dual_arm_coordinator.task_config import TaskConfigError

PACKAGE = Path(__file__).resolve().parents[1]
SIM = PACKAGE / 'config' / 'sim' / 'coordinator.yaml'
HARDWARE = PACKAGE / 'config' / 'hardware' / 'coordinator.yaml'
DOMAIN = 92


class Startup(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.journal = Path(self.folder.name) / 'journal.json'

    def start(self, config, *extra):
        """Build the node with overridden parameters inside an isolated context."""
        arguments = ['--ros-args', '-p', f'config_path:={config}', '-p', f'journal_path:={self.journal}']
        for item in extra:
            arguments += ['-p', item]
        context = Context()
        rclpy.init(args=arguments, context=context, domain_id=DOMAIN)
        self.addCleanup(rclpy.shutdown, context=context)
        return CoordinatorNode(context=context)

    def filled_hardware(self):
        doc = yaml.safe_load(SIM.read_text(encoding='utf-8'))
        doc.update(mode='hardware', evidence_kind='physical', home_source='calibration')
        doc['gripper'].update(backend='manual_token', auto_confirm=False)
        path = Path(self.folder.name) / 'hardware.yaml'
        path.write_text(yaml.safe_dump(doc), encoding='utf-8')
        return path

    def test_hardware_template_is_refused(self):
        with self.assertRaises(TaskConfigError):
            self.start(HARDWARE)

    def test_complete_hardware_config_is_still_blocked(self):
        with self.assertRaises(RuntimeError) as caught:
            self.start(self.filled_hardware())
        self.assertIn('BLOCKED', str(caught.exception))
        self.assertFalse(self.journal.exists())

    def test_cycles_must_be_in_range(self):
        for value in ('0', '9'):
            with self.subTest(value), self.assertRaises(ValueError):
                self.start(SIM, f'cycles:={value}')

    def test_prefilled_slots_must_be_in_range(self):
        with self.assertRaises(ValueError):
            self.start(SIM, 'simulation_prefilled_slots:=9')


if __name__ == '__main__':
    unittest.main()
