"""Sends the operator's commands. Kept apart from RosSource so the monitor stays read-only.

Every call is asynchronous: send() returns at once and the replies are collected with
results(). A service with no server, or one that does not answer in time, is reported as
a refusal rather than waited on.

The ESP32 suction board is a topic, not a service: "all off" is published on /suction_command
and counts as answered once the board echoes 0 on /suction_status.
"""
from dataclasses import dataclass
import threading
import time

import rclpy
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.context import Context
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.task import Future
from controller_manager_msgs.srv import SetHardwareComponentState, SwitchController
from lifecycle_msgs.msg import State
from std_msgs.msg import Int32
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
    # Then the arm controllers: the prototype has no e-stop heartbeat, so the supervisor never latches and
    # /safety/reset (which otherwise activates them) is refused with 'Nothing to reset'.
    '/controller_manager/switch_controller': (SwitchController, 10.0),
    # ESP32 suction: 0 turns both pumps and valves off. E0 2026-11-13: longest echo 563 ms.
    '/suction_command': (Int32, 2.0),
}
SUCTION_OFF = '/suction_command'
SUCTION_STATUS = '/suction_status'
HARDWARE_COMPONENT = 'DualArmSystem'
ARM_CONTROLLERS = ('arm1_controller', 'arm2_controller')
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
    if kind is SwitchController:
        return SwitchController.Request(activate_controllers=list(ARM_CONTROLLERS),
                                        strictness=SwitchController.Request.STRICT)
    if kind is Int32:
        return Int32(data=0)
    return ConfirmStep.Request(token=token, success=bool(confirmed), message='operator interface')


def reply_from(service, response):
    """Trigger answers with success, ConfirmStep with accepted; the suction board with its echo."""
    if service == SUCTION_OFF:
        return Reply(service, response == 0, '吸盤泵、閥全關' if response == 0 else f'吸盤回音 {response}，不是 0')
    if isinstance(response, SetHardwareComponentState.Response):
        return Reply(service, bool(response.ok), f'DualArmSystem {response.state.label or "?"}')
    if isinstance(response, SwitchController.Response):
        return Reply(service, bool(response.ok), ('已啟用 ' if response.ok else '無法啟用 ') + '、'.join(ARM_CONTROLLERS))
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
                         for name, (kind, _) in SERVICES.items() if kind is not Int32}
        self._suction = self._node.create_publisher(Int32, SUCTION_OFF, 10)
        self._echoes = []   # futures waiting for the suction board to echo 0
        self._node.create_subscription(Int32, SUCTION_STATUS, self._on_echo, 10, callback_group=group)
        self._executor = MultiThreadedExecutor(num_threads=2, context=self._context)
        self._executor.add_node(self._node)
        self._thread = threading.Thread(target=self._executor.spin, daemon=True)
        self._thread.start()

    def available(self, service):
        if service == SUCTION_OFF:
            # The micro-ROS agent bridges the board: it subscribes the command and publishes the echo.
            return bool(self._node.count_subscribers(SUCTION_OFF) and self._node.count_publishers(SUCTION_STATUS))
        return self._clients[service].service_is_ready()

    def _on_echo(self, message):
        # Only 0 answers "all off"; an echo of an earlier coordinator command is not the answer.
        if message.data != 0:
            return
        with self._lock:
            waiting, self._echoes = self._echoes, []
        for future in waiting:
            if not future.done():
                future.set_result(0)

    def _publish_suction(self, request):
        future = Future()
        self._echoes.append(future)
        self._suction.publish(request)
        return future

    def send(self, batch, calls):
        """calls: (service, request) pairs sent together under one batch key."""
        now = self._clock()
        with self._lock:
            for service, request in calls:
                if not self.available(service):
                    self._done.append((batch, Reply(service, False, UNAVAILABLE)))
                    continue
                future = (self._publish_suction(request) if service == SUCTION_OFF
                          else self._clients[service].call_async(request))
                self._pending.append((batch, service, future, now + SERVICES[service][1]))

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
