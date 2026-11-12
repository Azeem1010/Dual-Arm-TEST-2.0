"""Sends the operator's commands. Kept apart from RosSource so the monitor stays read-only.

Every call is asynchronous: send() returns at once and the replies are collected with
results(). A service with no server, or one that does not answer in time, is reported as
a refusal rather than waited on.
"""
from dataclasses import dataclass
import threading
import time

import rclpy
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.context import Context
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from controller_manager_msgs.srv import SetHardwareComponentState
from lifecycle_msgs.msg import State
from std_srvs.srv import Trigger

from dual_arm_interfaces.srv import ConfirmStep

# Service name, type, and how long its reply may take. /safety/reset waits up to 10 s for the controllers.
SERVICES = {
    '/safety/trigger_stop': (Trigger, 3.0),
    '/safety/reset': (Trigger, 15.0),
    '/dual_arm/start': (Trigger, 5.0),
    '/dual_arm/cancel': (Trigger, 3.0),
    '/dual_arm/go_home': (ConfirmStep, 5.0),
    '/dual_arm/recover': (ConfirmStep, 15.0),
    # Torque on: the CM-530 component goes active (prototype only; strict hardware keeps the CLI step).
    '/controller_manager/set_hardware_component_state': (SetHardwareComponentState, 10.0),
}
HARDWARE_COMPONENT = 'DualArmSystem'
UNAVAILABLE = '服務不存在'
TIMED_OUT = '沒有回覆'


@dataclass(frozen=True)
class Reply:
    service: str
    ok: bool
    message: str


def request_for(service, token='', confirmed=False):
    kind, _ = SERVICES[service]
    if kind is Trigger:
        return Trigger.Request()
    if kind is SetHardwareComponentState:
        return SetHardwareComponentState.Request(
            name=HARDWARE_COMPONENT, target_state=State(id=State.PRIMARY_STATE_ACTIVE, label='active'))
    return ConfirmStep.Request(token=token, success=bool(confirmed), message='operator interface')


def reply_from(service, response):
    """Trigger answers with success, ConfirmStep with accepted."""
    if isinstance(response, SetHardwareComponentState.Response):
        return Reply(service, bool(response.ok), f'DualArmSystem {response.state.label or "?"}')
    ok = response.success if isinstance(response, Trigger.Response) else response.accepted
    return Reply(service, bool(ok), response.message)


class RosCommander:
    def __init__(self, domain_id=None, clock=time.monotonic):
        self._clock = clock
        self._lock = threading.Lock()
        self._pending = []  # (batch, service, future, deadline)
        self._done = []     # (batch, Reply)
        self._context = Context()
        rclpy.init(context=self._context, domain_id=domain_id)
        self._node = Node('dual_arm_hmi_command', context=self._context)
        group = ReentrantCallbackGroup()
        self._clients = {name: self._node.create_client(kind, name, callback_group=group)
                         for name, (kind, _) in SERVICES.items()}
        self._executor = MultiThreadedExecutor(num_threads=2, context=self._context)
        self._executor.add_node(self._node)
        self._thread = threading.Thread(target=self._executor.spin, daemon=True)
        self._thread.start()

    def available(self, service):
        return self._clients[service].service_is_ready()

    def send(self, batch, calls):
        """calls: (service, request) pairs sent together under one batch key."""
        now = self._clock()
        with self._lock:
            for service, request in calls:
                client = self._clients[service]
                if not client.service_is_ready():
                    self._done.append((batch, Reply(service, False, UNAVAILABLE)))
                    continue
                self._pending.append((batch, service, client.call_async(request), now + SERVICES[service][1]))

    def results(self):
        """Replies that arrived or timed out since the last call, as (batch, Reply)."""
        now = self._clock()
        with self._lock:
            still = []
            for batch, service, future, deadline in self._pending:
                if future.done():
                    result = future.result()
                    self._done.append((batch, Reply(service, False, TIMED_OUT) if result is None
                                       else reply_from(service, result)))
                elif now > deadline:
                    future.cancel()
                    self._done.append((batch, Reply(service, False, TIMED_OUT)))
                else:
                    still.append((batch, service, future, deadline))
            self._pending = still
            done, self._done = self._done, []
        return done

    def waiting(self, batch):
        with self._lock:
            return any(item[0] == batch for item in self._pending)

    def close(self):
        self._executor.shutdown(timeout_sec=2.0)
        self._node.destroy_node()
        rclpy.shutdown(context=self._context)
