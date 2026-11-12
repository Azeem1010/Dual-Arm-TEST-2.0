"""Suction backends for the workflow TaskIO contract.

The Gazebo plugin silently drops malformed or out-of-order commands, so every
command needs a timeout. A manual confirmation is the operator's word about the
physical result, and only a matching one-time token can give it.
"""
import re
import threading
import time

from ..confirmation import TokenError
from ..task_config import AUTO_CONFIRM_MODES
from ..workflow.ports import TaskFault

ARMS = ('arm1', 'arm2')
OPERATIONS = ('grasp', 'release')
_CAP_NAME = re.compile(r'cap_[1-8]\Z')
_POLL_S = 0.005


def _check_request(arm, operation):
    if arm not in ARMS or operation not in OPERATIONS:
        raise TaskFault(f'Invalid suction request: {arm} {operation}')


class GazeboSuction:
    def __init__(self, publish, locator, timeout_s, guard, clock=time.monotonic, sleep=time.sleep):
        self._publish, self._locator, self._timeout = publish, locator, timeout_s
        self._guard, self._clock, self._sleep = guard, clock, sleep
        self._lock = threading.Lock()
        self._replies = dict.fromkeys(ARMS, '')
        self._held = dict.fromkeys(ARMS)
        # The plugin keeps its last sequence across runs of this process.
        self._sequence = time.time_ns() // 1000

    def on_state(self, arm, text):
        with self._lock:
            self._replies[arm] = text

    def _next_sequence(self):
        with self._lock:
            self._sequence += 1
            return self._sequence

    def _cap_under_tool(self, arm):
        try:
            name = self._locator(arm)
        except Exception as error:
            raise TaskFault(f'{arm}: no object identified under the tool: {error}') from error
        if not isinstance(name, str) or not _CAP_NAME.match(name):
            raise TaskFault(f'{arm}: invalid object name {name!r}')
        if name in self._held.values():
            raise TaskFault(f'{name} is already held')
        return name

    def _await_reply(self, arm, sequence):
        prefix, deadline = f'{sequence},', self._clock() + self._timeout
        while True:
            self._guard()
            with self._lock:
                reply = self._replies[arm]
            if reply.startswith(prefix):
                return reply
            if self._clock() >= deadline:
                raise TaskFault(f'{arm}: no suction reply to command {sequence}')
            self._sleep(_POLL_S)

    def suction(self, arm, operation):
        _check_request(arm, operation)
        self._guard()
        sequence = self._next_sequence()
        if operation == 'grasp':
            name = self._cap_under_tool(arm)
            command, expected = f'{sequence},attach,{name}', f'{sequence},attached:{name}'
        else:
            name = None
            command, expected = f'{sequence},release', f'{sequence},released'
        self._publish(arm, command)
        reply = self._await_reply(arm, sequence)
        if reply != expected:
            raise TaskFault(f'{arm}: suction {operation} failed: {reply}')
        self._held[arm] = name


class ManualTokenSuction:
    """A person operates the suction and confirms the result with a one-time token."""

    def __init__(self, gate, announce, timeout_s, guard, auto_confirm=False, clock=time.monotonic, sleep=time.sleep):
        self._gate, self._announce, self._timeout = gate, announce, timeout_s
        self._guard, self._auto_confirm = guard, auto_confirm
        self._clock, self._sleep = clock, sleep
        self._lock = threading.Lock()
        self._operation, self._result = None, None

    def confirm(self, token, success, message=''):
        with self._lock:
            if self._operation is None:
                raise TokenError('No suction step is waiting for confirmation')
            self._gate.consume(token, self._operation)
            self._result = (success is True, message)

    def _await_result(self, token):
        deadline = self._clock() + self._timeout
        while True:
            self._guard()
            with self._lock:
                result = self._result
            if result is not None:
                return result
            if self._clock() >= deadline:
                raise TaskFault(f'Suction step was not confirmed within {self._timeout} s')
            self._sleep(_POLL_S)

    def suction(self, arm, operation):
        _check_request(arm, operation)
        self._guard()
        step = f'{arm}:{operation}'
        with self._lock:
            token = self._gate.issue(step)
            self._operation, self._result = step, None
        try:
            self._announce(arm, operation, token)
            if self._auto_confirm:
                return
            passed, message = self._await_result(token)
        finally:
            with self._lock:
                self._operation = None
            self._gate.revoke(token)
        if not passed:
            raise TaskFault(f'Operator reported suction {operation} failed on {arm}: {message}')


class Esp32Suction:
    """Commands the suction modules; an operator confirms what actually happened.

    The firmware only echoes the command after acting. It has no vacuum sensor, so
    an echo proves the relays were driven, not that an object is held.
    """

    def __init__(self, publish, modules, echo_timeout_s, vacuum_settle_s, confirmer, guard,
                 clock=time.monotonic, sleep=time.sleep):
        self._publish, self._modules, self._echo_timeout = publish, modules, echo_timeout_s
        self._settle, self._confirmer, self._guard = vacuum_settle_s, confirmer, guard
        self._clock, self._sleep = clock, sleep
        self._lock = threading.Lock()
        self._echo = None

    def on_status(self, value):
        with self._lock:
            self._echo = value

    def confirm(self, token, success, message=''):
        self._confirmer.confirm(token, success, message)

    def _command(self, arm, operation):
        return (self._modules[arm] - 1) * 2 + (1 if operation == 'grasp' else 2)

    def _await_echo(self, arm, command):
        deadline = self._clock() + self._echo_timeout
        while True:
            self._guard()
            with self._lock:
                echo = self._echo
            if echo is not None:
                if echo != command:
                    raise TaskFault(f'{arm}: suction controller answered {echo} to command {command}')
                return
            if self._clock() >= deadline:
                raise TaskFault(f'{arm}: no suction controller reply to command {command}')
            self._sleep(_POLL_S)

    def _wait_for_vacuum(self):
        deadline = self._clock() + self._settle
        while self._clock() < deadline:
            self._guard()
            self._sleep(_POLL_S)

    def suction(self, arm, operation):
        _check_request(arm, operation)
        self._guard()
        command = self._command(arm, operation)
        with self._lock:
            self._echo = None
        self._publish(arm, command)
        self._await_echo(arm, command)
        if operation == 'grasp':
            self._wait_for_vacuum()
        self._confirmer.suction(arm, operation)


def _wire_esp32(node, settings, guard, confirmer, callback_group):
    from std_msgs.msg import Int32

    publisher = node.create_publisher(Int32, '/suction_command', 10)

    def publish(arm, command):
        deadline = time.monotonic() + settings['esp32_echo_timeout_s']
        # The agent bridges the ESP32 late; a command sent before discovery would be lost.
        while not (node.count_subscribers('/suction_command') and node.count_publishers('/suction_status')):
            guard()
            if time.monotonic() >= deadline:
                raise TaskFault(f'{arm}: the suction controller is not connected')
            time.sleep(0.01)
        publisher.publish(Int32(data=command))

    backend = Esp32Suction(publish, settings['esp32_modules'], settings['esp32_echo_timeout_s'],
                           settings['vacuum_settle_s'], confirmer, guard)
    node.create_subscription(Int32, '/suction_status', lambda message: backend.on_status(message.data),
                             10, callback_group=callback_group)
    return backend


def _wire_gazebo(node, settings, guard, locator, callback_group):
    from std_msgs.msg import String

    publishers = {arm: node.create_publisher(String, f'/gripper/{arm}/command', 10) for arm in ARMS}

    def publish(arm, text):
        command_topic, state_topic = f'/gripper/{arm}/command', f'/gripper/{arm}/state'
        deadline = time.monotonic() + settings['reply_timeout_s']
        # A command sent before discovery finishes would be lost without any reply.
        while not (node.count_subscribers(command_topic) and node.count_publishers(state_topic)):
            guard()
            if time.monotonic() >= deadline:
                raise TaskFault(f'{arm}: suction topics are not connected')
            time.sleep(0.01)
        publishers[arm].publish(String(data=text))

    backend = GazeboSuction(publish, locator, settings['reply_timeout_s'], guard)
    for arm in ARMS:
        node.create_subscription(String, f'/gripper/{arm}/state',
                                 lambda message, name=arm: backend.on_state(name, message.data),
                                 10, callback_group=callback_group)
    return backend


def create_gripper(node, config, guard, *, locator=None, gate=None, announce=None, callback_group=None):
    settings, mode = config['gripper'], config['mode']
    if settings['auto_confirm'] and mode not in AUTO_CONFIRM_MODES:
        raise ValueError('Automatic suction confirmation is simulation only (or prototype)')
    backend = settings['backend']
    if backend == 'gazebo':
        if mode != 'simulation':
            raise ValueError('The Gazebo suction backend is simulation only')
        if locator is None:
            raise ValueError('The Gazebo suction backend needs an object locator')
        return _wire_gazebo(node, settings, guard, locator, callback_group)
    if backend in ('manual_token', 'esp32'):
        if gate is None or announce is None:
            raise ValueError('Operator confirmation needs a token gate and an announce callback')
        confirmer = ManualTokenSuction(gate, announce, settings['reply_timeout_s'], guard, settings['auto_confirm'])
        return confirmer if backend == 'manual_token' else _wire_esp32(node, settings, guard, confirmer, callback_group)
    raise ValueError(f'Suction backend {backend} is not available')
