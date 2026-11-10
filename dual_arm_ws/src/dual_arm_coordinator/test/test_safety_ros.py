"""SafetySupervisor against a stand-in controller manager, over real ROS services."""
import json
import threading
import time
import unittest

from controller_manager_msgs.msg import ControllerState
from controller_manager_msgs.srv import ListControllers, SwitchController
import rclpy
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.context import Context
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile
from std_msgs.msg import Bool, String
from std_srvs.srv import Trigger

from dual_arm_coordinator.safety_supervisor import SafetySupervisor

DOMAIN_ID = 94
TIMEOUT_S = 10.0
ARMS = ('arm1_controller', 'arm2_controller')


class FakeControllerManager(Node):
    def __init__(self, context):
        super().__init__('fake_controller_manager', context=context)
        self.states = dict.fromkeys(ARMS, 'inactive')
        self.refuse_stop, self.activate_then_fail = False, False
        self.lister = self.create_service(ListControllers, '/controller_manager/list_controllers', self.list_controllers)
        self.create_service(SwitchController, '/controller_manager/switch_controller', self.switch)

    def list_controllers(self, _request, response):
        response.controller = [ControllerState(name=name, state=state) for name, state in self.states.items()]
        return response

    def switch(self, request, response):
        if request.deactivate_controllers and self.refuse_stop:
            response.ok = False
            return response
        for name in request.deactivate_controllers:
            self.states[name] = 'inactive'
        for name in request.activate_controllers:
            self.states[name] = 'active'
        response.ok = not (request.activate_controllers and self.activate_then_fail)
        return response


class Supervisor(unittest.TestCase):
    def setUp(self):
        self.context = Context()
        rclpy.init(context=self.context, domain_id=DOMAIN_ID)
        self.manager = FakeControllerManager(self.context)
        self.supervisor = SafetySupervisor(context=self.context)
        self.node = Node('safety_ros_test', context=self.context)
        self.status = None
        group = ReentrantCallbackGroup()
        qos = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.node.create_subscription(String, '/safety/status', self.on_status, qos, callback_group=group)
        self.estop = self.node.create_publisher(Bool, '/safety/estop', 10)
        self.reset_client = self.node.create_client(Trigger, '/safety/reset', callback_group=group)
        self.stop_client = self.node.create_client(Trigger, '/safety/trigger_stop', callback_group=group)
        self.executor = MultiThreadedExecutor(num_threads=6, context=self.context)
        for node in (self.manager, self.supervisor, self.node):
            self.executor.add_node(node)
        self.spinner = threading.Thread(target=self.executor.spin, daemon=True)
        self.spinner.start()
        self.heartbeat = threading.Event()
        self.heartbeat_stop = threading.Event()
        self.heartbeat_thread = threading.Thread(target=self.beat, daemon=True)
        self.heartbeat_thread.start()
        self.wait_for(self.stopped_and_latched, 'the initial stop')

    def tearDown(self):
        self.heartbeat_stop.set()
        self.heartbeat_thread.join(timeout=2)
        self.executor.shutdown(timeout_sec=5)
        self.spinner.join(timeout=5)
        for node in (self.manager, self.supervisor, self.node):
            node.destroy_node()
        rclpy.shutdown(context=self.context)

    def on_status(self, message):
        self.status = json.loads(message.data)

    def beat(self):
        while not self.heartbeat_stop.wait(0.05):
            if self.heartbeat.is_set():
                self.estop.publish(Bool(data=False))

    def wait_for(self, predicate, label):
        deadline = time.monotonic() + TIMEOUT_S
        while not predicate():
            if time.monotonic() > deadline:
                self.fail(f'Timed out waiting for {label}; status {self.status}, states {self.manager.states}')
            time.sleep(0.01)

    def stopped_and_latched(self):
        return bool(self.status and self.status['latched'] and self.status['controllers_stopped'])

    def all_states(self, state):
        return set(self.manager.states.values()) == {state}

    def reset(self):
        self.assertTrue(self.reset_client.wait_for_service(timeout_sec=TIMEOUT_S))
        future = self.reset_client.call_async(Trigger.Request())
        self.wait_for(future.done, 'the reset reply')
        return future.result()

    def prepare_reset(self):
        self.heartbeat.set()
        time.sleep(0.5)

    def test_controller_activated_by_hand_is_stopped_again(self):
        self.manager.states['arm1_controller'] = 'active'
        self.wait_for(lambda: self.all_states('inactive'), 'the controller to be stopped again')
        self.wait_for(self.stopped_and_latched, 'the status to recover')

    def test_status_is_not_stopped_while_a_controller_stays_active(self):
        self.manager.refuse_stop = True
        self.manager.states['arm1_controller'] = 'active'
        self.wait_for(lambda: self.status['controllers_stopped'] is False, 'the status to change')
        time.sleep(1.0)
        self.assertFalse(self.status['controllers_stopped'])
        self.assertTrue(self.status['latched'])

    def test_unverifiable_controllers_are_not_reported_stopped(self):
        self.manager.destroy_service(self.manager.lister)
        self.wait_for(lambda: self.status['controllers_stopped'] is False, 'the status to change')

    def test_reset_leaves_controllers_active(self):
        self.prepare_reset()
        response = self.reset()
        self.assertTrue(response.success, response.message)
        self.wait_for(lambda: self.status['latched'] is False, 'the latch to clear')
        time.sleep(1.0)  # Several verification periods.
        self.assertTrue(self.all_states('active'))

    def test_failed_reset_stops_partly_activated_controllers(self):
        self.prepare_reset()
        self.manager.activate_then_fail = True
        response = self.reset()
        self.assertFalse(response.success)
        self.assertIn('refused', response.message)
        self.wait_for(lambda: self.all_states('inactive'), 'the controllers to be stopped')
        self.wait_for(self.stopped_and_latched, 'the status to recover')

    def test_reset_is_refused_without_heartbeat_and_nothing_activates(self):
        response = self.reset()
        self.assertFalse(response.success)
        self.assertTrue(self.all_states('inactive'))

    def call(self, client):
        self.assertTrue(client.wait_for_service(timeout_sec=TIMEOUT_S))
        future = client.call_async(Trigger.Request())
        self.wait_for(future.done, 'the reply')
        return future.result()

    def test_operator_stop_deactivates_after_a_reset(self):
        self.prepare_reset()
        self.assertTrue(self.reset().success)
        self.wait_for(lambda: self.all_states('active') and self.status['latched'] is False, 'the reset')
        response = self.call(self.stop_client)
        self.assertTrue(response.success, response.message)
        self.wait_for(lambda: self.all_states('inactive'), 'the controllers to stop')
        self.wait_for(lambda: self.stopped_and_latched() and self.status['reason'] == 'Operator software stop',
                      'the status to show the operator stop')
        # Nothing has to be fixed after an operator stop, so a reset brings the controllers back.
        self.assertTrue(self.reset().success)
        self.wait_for(lambda: self.all_states('active'), 'the controllers to be active again')

    def test_operator_stop_while_latched_keeps_the_first_reason(self):
        response = self.call(self.stop_client)
        self.assertTrue(response.success)
        self.assertIn('Already latched', response.message)
        self.assertNotEqual(self.status['reason'], 'Operator software stop')


if __name__ == '__main__':
    unittest.main()
