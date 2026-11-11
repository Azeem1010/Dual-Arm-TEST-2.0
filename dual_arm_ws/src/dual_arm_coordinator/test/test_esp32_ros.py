"""Checks the ESP32 topic wiring against a stand-in that behaves like the firmware."""
import threading
import time
import unittest

import rclpy
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.context import Context
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from std_msgs.msg import Int32

from dual_arm_coordinator.confirmation import TokenGate
from dual_arm_coordinator.gateways.gripper import create_gripper
from dual_arm_coordinator.workflow.ports import TaskFault

DOMAIN = 93
CONFIG = {'mode': 'hardware', 'gripper': {'backend': 'esp32', 'auto_confirm': False, 'reply_timeout_s': 10.0,
                                          'esp32_echo_timeout_s': 15.0, 'vacuum_settle_s': 0.05,
                                          'esp32_modules': {'arm1': 1, 'arm2': 2}}}


class FirmwareStandIn(Node):
    """Echoes after acting, delays releases like the firmware, and answers 0 to unknown values."""

    def __init__(self, context, respond=True):
        super().__init__('suction_controller_node', context=context)
        self.commands, self.respond = [], respond
        self.status = self.create_publisher(Int32, 'suction_status', 10)
        self.create_subscription(Int32, 'suction_command', self.on_command, 10)

    def on_command(self, message):
        self.commands.append(message.data)
        if message.data in (2, 4):
            time.sleep(0.55)
        if self.respond:
            self.status.publish(Int32(data=message.data if 0 <= message.data <= 4 else 0))


class Esp32Topics(unittest.TestCase):
    def setUp(self):
        self.context = Context()
        rclpy.init(context=self.context, domain_id=DOMAIN)
        self.addCleanup(rclpy.shutdown, context=self.context)
        self.node = Node('coordinator_under_test', context=self.context)
        self.executor = MultiThreadedExecutor(num_threads=3, context=self.context)
        self.executor.add_node(self.node)
        self.addCleanup(self.executor.shutdown)
        self.gate = TokenGate(30.0)
        self.confirm_with = True
        self.backend = create_gripper(self.node, CONFIG, lambda: None, gate=self.gate, announce=self.announce,
                                      callback_group=ReentrantCallbackGroup())

    def announce(self, _arm, _operation, token):
        threading.Timer(0.02, self.backend.confirm, args=(token, self.confirm_with, 'test')).start()

    def start(self, respond=True):
        self.firmware = FirmwareStandIn(self.context, respond)
        self.executor.add_node(self.firmware)
        threading.Thread(target=self.executor.spin, daemon=True).start()

    def test_commands_and_echoes_cross_real_topics(self):
        self.start()
        self.backend.suction('arm1', 'grasp')
        self.backend.suction('arm1', 'release')
        self.backend.suction('arm2', 'grasp')
        self.backend.suction('arm2', 'release')
        self.assertEqual(self.firmware.commands, [1, 2, 3, 4])

    def test_operator_failure_is_reported_after_a_good_echo(self):
        self.start()
        self.confirm_with = False
        with self.assertRaises(TaskFault) as caught:
            self.backend.suction('arm1', 'grasp')
        self.assertIn('Operator reported', str(caught.exception))
        self.assertEqual(self.firmware.commands, [1])


if __name__ == '__main__':
    unittest.main()
