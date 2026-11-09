"""Stops the arm controllers when the emergency-stop heartbeat or the coordinator is lost.

MoveIt keeps executing a sent trajectory if its client dies, so stopping must
happen at the controllers. While latched, the controllers are checked repeatedly, so
one activated by hand is stopped again. This is a software interlock, not a physical stop.
"""
import json
import threading
import time

from controller_manager_msgs.srv import ListControllers, SwitchController
import rclpy
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile
from std_msgs.msg import Bool, String
from std_srvs.srv import Trigger

from .safety_monitor import SafetyMonitor

_RESEND_PERIOD_S = 0.5
_VERIFY_PERIOD_S = 0.2
_CALL_TIMEOUT_S = 2.0
_RESET_TIMEOUT_S = 10.0


class SafetySupervisor(Node):
    def __init__(self, context=None):
        super().__init__('safety_supervisor', context=context)
        declare = lambda name, value: self.declare_parameter(name, value).value
        self.controllers = declare('controllers', ['arm1_controller', 'arm2_controller'])
        self.monitor = SafetyMonitor(declare('estop_max_age_s', 2.0), declare('permit_max_age_s', 1.0),
                                     declare('require_estop', True))
        self.group = ReentrantCallbackGroup()
        self.lock = threading.Lock()
        self.applied, self.pending, self.last_sent = False, None, 0.0
        self.listing, self.last_listed, self.resetting = None, 0.0, False
        self.switch = self.create_client(SwitchController, '/controller_manager/switch_controller', callback_group=self.group)
        self.lister = self.create_client(ListControllers, '/controller_manager/list_controllers', callback_group=self.group)
        qos = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.status = self.create_publisher(String, '/safety/status', qos)
        self.create_subscription(Bool, '/safety/estop', lambda message: self.monitor.on_estop(message.data), 10, callback_group=self.group)
        self.create_subscription(Bool, '/dual_arm/permit', lambda _message: self.monitor.on_permit(), 10, callback_group=self.group)
        self.create_service(Trigger, '/safety/reset', self._reset, callback_group=self.group)
        self.create_timer(0.05, self._tick, callback_group=self.group)
        self.create_timer(0.2, self._publish, callback_group=self.group)

    def _request(self, *, activate=False):
        request = SwitchController.Request()
        if activate:
            request.activate_controllers = list(self.controllers)
        else:
            request.deactivate_controllers = list(self.controllers)
        request.strictness = SwitchController.Request.BEST_EFFORT
        return request

    def _tick(self):
        if self.monitor.update():
            self.get_logger().error(f'Stopping the arm controllers: {self.monitor.reason}')
            with self.lock:
                self.applied, self.listing = False, None
        with self.lock:
            # A reset activates the controllers before it clears the latch.
            if self.monitor.reason is None or self.resetting:
                return
            now = time.monotonic()
            if self.applied:
                self._verify_stopped(now)
            if not self.applied:
                self._send_stop(now)

    def _verify_stopped(self, now):
        """Withdraw the stopped state if a controller is active or cannot be checked."""
        if self.listing is not None:
            if self.listing.done():
                result, self.listing = self.listing.result(), None
                active = [] if result is None else [item.name for item in result.controller
                                                    if item.name in self.controllers and item.state == 'active']
                if result is None or active:
                    self.get_logger().error(f'Controllers must stay stopped while latched; found active: {active}')
                    self.applied = False
            elif now - self.last_listed >= _CALL_TIMEOUT_S:
                self.listing, self.applied = None, False
            return
        if not self.lister.service_is_ready():
            self.applied = False
        elif now - self.last_listed >= _VERIFY_PERIOD_S:
            self.last_listed = now
            self.listing = self.lister.call_async(ListControllers.Request())

    def _send_stop(self, now):
        if self.pending is not None:
            if not self.pending.done():
                if now - self.last_sent >= _CALL_TIMEOUT_S:
                    self.pending = None
                return
            result, self.pending = self.pending.result(), None
            if result is not None and result.ok:
                self.applied = True
                self._log_applied()
                return
        # Keep trying: a failed stop must not be forgotten.
        if now - self.last_sent >= _RESEND_PERIOD_S and self.switch.service_is_ready():
            self.last_sent = now
            self.pending = self.switch.call_async(self._request())

    def _log_applied(self):
        self.get_logger().error('Arm controllers are deactivated; /safety/reset is required')

    def _publish(self):
        with self.lock:
            applied = self.applied
        reason = self.monitor.reason
        self.status.publish(String(data=json.dumps({'latched': reason is not None, 'reason': reason or '', 'controllers_stopped': applied})))

    def _reset(self, _request, response):
        if self.monitor.reason is None:
            response.success, response.message = False, 'Nothing to reset'
            return response
        problem = self.monitor.problem_blocking_reset()
        if problem is not None:
            response.success, response.message = False, problem
            return response
        if not self.switch.wait_for_service(timeout_sec=_RESET_TIMEOUT_S):
            response.success, response.message = False, 'Controller manager is unavailable'
            return response
        with self.lock:
            if self.pending is not None and not self.pending.done():
                response.success, response.message = False, 'A controller stop is still in progress'
                return response
            # From here the controllers may be active; any failure below stops them again.
            self.resetting, self.applied, self.pending, self.listing = True, False, None, None
        try:
            return self._activate_and_clear(response)
        finally:
            with self.lock:
                self.resetting = False

    def _activate_and_clear(self, response):
        future = self.switch.call_async(self._request(activate=True))
        deadline = time.monotonic() + _RESET_TIMEOUT_S
        while not future.done():
            if time.monotonic() >= deadline:
                response.success, response.message = False, 'Controller activation timed out'
                return response
            time.sleep(0.01)
        result = future.result()
        if result is None or not result.ok:
            response.success, response.message = False, 'Controller activation was refused'
            return response
        # Inputs may have changed while the controllers were being activated.
        problem = self.monitor.reset()
        if problem is not None:
            response.success, response.message = False, problem
            return response
        response.success, response.message = True, 'Latch cleared and arm controllers activated'
        return response


def main(args=None):
    rclpy.init(args=args)
    node = SafetySupervisor()
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        executor.shutdown()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
