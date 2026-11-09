"""Checks the real ROS topic wiring against a stand-in for the Gazebo plugin."""
import threading
import unittest

import rclpy
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.context import Context
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from std_msgs.msg import String

from dual_arm_coordinator.gateways.gripper import create_gripper
from dual_arm_coordinator.workflow.ports import TaskFault

DOMAIN = 91
CONFIG = {'mode': 'simulation', 'gripper': {'backend': 'gazebo', 'auto_confirm': False, 'reply_timeout_s': 15.0}}


class PluginStandIn(Node):
    def __init__(self, context, arm, answer):
        super().__init__('plugin_stand_in', context=context)
        self.commands, self.answer = [], answer
        self.state = self.create_publisher(String, f'/gripper/{arm}/state', 10)
        self.create_subscription(String, f'/gripper/{arm}/command', self.on_command, 10)

    def on_command(self, message):
        self.commands.append(message.data)
        sequence, _, rest = message.data.partition(',')
        reply = self.answer(sequence, rest)
        if reply:
            self.state.publish(String(data=reply))


class TopicWiring(unittest.TestCase):
    def setUp(self):
        self.context = Context()
        rclpy.init(context=self.context, domain_id=DOMAIN)
        self.addCleanup(rclpy.shutdown, context=self.context)
        self.node = Node('gripper_under_test', context=self.context)
        self.executor = MultiThreadedExecutor(num_threads=3, context=self.context)
        self.executor.add_node(self.node)
        self.addCleanup(self.executor.shutdown)
        self.backend = create_gripper(self.node, CONFIG, lambda: None, locator=lambda _arm: 'cap_2',
                                      callback_group=ReentrantCallbackGroup())

    def start(self, answer):
        self.plugin = PluginStandIn(self.context, 'arm1', answer)
        self.executor.add_node(self.plugin)
        threading.Thread(target=self.executor.spin, daemon=True).start()

    @staticmethod
    def successful(sequence, rest):
        return f'{sequence},attached:cap_2' if rest.startswith('attach') else f'{sequence},released'

    def test_commands_and_replies_cross_real_topics(self):
        self.start(self.successful)
        self.backend.suction('arm1', 'grasp')
        self.backend.suction('arm1', 'release')
        self.assertEqual([text.split(',', 1)[1] for text in self.plugin.commands], ['attach,cap_2', 'release'])

    def test_fault_reply_crosses_real_topics(self):
        self.start(lambda sequence, _rest: f'{sequence},fault:no_contact')
        with self.assertRaises(TaskFault) as caught:
            self.backend.suction('arm1', 'grasp')
        self.assertIn('fault:no_contact', str(caught.exception))


if __name__ == '__main__':
    unittest.main()
