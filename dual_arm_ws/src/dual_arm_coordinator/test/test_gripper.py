import re
import threading
import time
import unittest

from dual_arm_coordinator.confirmation import TokenError, TokenGate
from dual_arm_coordinator.gateways.gripper import Esp32Suction, GazeboSuction, ManualTokenSuction, create_gripper
from dual_arm_coordinator.workflow.ports import TaskCancelled, TaskFault

ATTACH_FORMAT = re.compile(r'[1-9][0-9]*,attach,cap_[1-8]\Z')
RELEASE_FORMAT = re.compile(r'[1-9][0-9]*,release\Z')
TIMEOUT = 20.0


class FakeTime:
    def __init__(self):
        self.now = 0.0
        self.hook = None

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds
        if self.hook:
            self.hook()


class GazeboCase(unittest.TestCase):
    def setUp(self):
        self.time = FakeTime()
        self.sent = []
        self.reply = lambda sequence, text: f'{sequence},attached:cap_3' if 'attach' in text else f'{sequence},released'
        self.cap = 'cap_3'
        self.guard_error = None
        self.backend = self.make()

    def guard(self):
        if self.guard_error:
            raise self.guard_error

    def locator(self, _arm):
        if isinstance(self.cap, Exception):
            raise self.cap
        return self.cap

    def publish(self, arm, text):
        self.sent.append((arm, text))
        if self.reply:
            answer = self.reply(int(text.split(',')[0]), text)
            if answer:
                self.backend.on_state(arm, answer)

    def make(self):
        return GazeboSuction(self.publish, self.locator, TIMEOUT, self.guard, self.time.clock, self.time.sleep)

    def assert_faults(self, text, arm='arm1', operation='grasp'):
        with self.assertRaises(TaskFault) as caught:
            self.backend.suction(arm, operation)
        self.assertIn(text, str(caught.exception))


class GazeboProtocol(GazeboCase):
    def test_commands_match_what_the_plugin_accepts(self):
        self.backend.suction('arm1', 'grasp')
        self.backend.suction('arm1', 'release')
        self.assertRegex(self.sent[0][1], ATTACH_FORMAT)
        self.assertRegex(self.sent[1][1], RELEASE_FORMAT)
        self.assertLessEqual(max(len(text) for _, text in self.sent), 64)

    def test_sequences_increase_across_arms(self):
        self.backend.suction('arm1', 'release')
        self.backend.suction('arm2', 'release')
        self.backend.suction('arm1', 'release')
        sequences = [int(text.split(',')[0]) for _, text in self.sent]
        self.assertEqual(sequences, sorted(set(sequences)))
        self.assertGreater(sequences[0], 0)

    def test_new_backend_continues_above_previous_sequences(self):
        self.backend.suction('arm1', 'release')
        first = int(self.sent[-1][1].split(',')[0])
        time.sleep(0.002)
        self.backend = self.make()
        self.backend.suction('arm1', 'release')
        self.assertGreater(int(self.sent[-1][1].split(',')[0]), first)

    def test_uses_the_requesting_arm_topic(self):
        self.backend.suction('arm2', 'release')
        self.assertEqual(self.sent[0][0], 'arm2')


class GazeboFailures(GazeboCase):
    def test_fault_reply_stops(self):
        for reason in ('no_contact', 'already_attached', 'missing_entity'):
            with self.subTest(reason):
                self.reply = lambda sequence, _text, r=reason: f'{sequence},fault:{r}'
                self.assert_faults(f'fault:{reason}')

    def test_wrong_object_reply_stops(self):
        self.reply = lambda sequence, _text: f'{sequence},attached:cap_4'
        self.assert_faults('attached:cap_4')

    def test_no_reply_times_out(self):
        self.reply = None
        self.assert_faults('no suction reply')
        self.assertGreaterEqual(self.time.now, TIMEOUT)

    def test_reply_to_an_older_command_is_ignored(self):
        self.reply = lambda sequence, _text: f'{sequence - 1},released'
        self.assert_faults('no suction reply', operation='release')

    def test_reply_arriving_while_waiting_is_accepted(self):
        self.reply = None
        def later():
            if self.time.now >= 1.0 and self.sent:
                sequence = self.sent[-1][1].split(',')[0]
                self.backend.on_state('arm1', f'{sequence},released')
        self.time.hook = later
        self.backend.suction('arm1', 'release')

    def test_cancel_interrupts_waiting(self):
        self.reply = None
        def cancel():
            if self.time.now >= 1.0:
                self.guard_error = TaskCancelled('stop')
        self.time.hook = cancel
        with self.assertRaises(TaskCancelled):
            self.backend.suction('arm1', 'grasp')
        self.assertLess(self.time.now, TIMEOUT)

    def test_canceled_before_sending_publishes_nothing(self):
        self.guard_error = TaskCancelled('stop')
        with self.assertRaises(TaskCancelled):
            self.backend.suction('arm1', 'grasp')
        self.assertFalse(self.sent)

    def test_publish_failure_propagates(self):
        def refuse(_arm, _text):
            raise TaskFault('topics are not connected')
        self.backend._publish = refuse
        self.assert_faults('not connected')


class GazeboObjects(GazeboCase):
    def test_locator_failure_sends_nothing(self):
        self.cap = RuntimeError('stale pose')
        self.assert_faults('no object identified')
        self.assertFalse(self.sent)

    def test_invalid_names_are_not_sent(self):
        for name in ('cap_9', 'cap_1,extra', '../cap_1', None):
            with self.subTest(name):
                self.cap = name
                self.assert_faults('invalid object name')
        self.assertFalse(self.sent)

    def test_same_object_cannot_be_held_twice(self):
        self.backend.suction('arm1', 'grasp')
        self.assert_faults('already held', arm='arm2')

    def test_object_can_be_grasped_again_after_release(self):
        self.backend.suction('arm1', 'grasp')
        self.backend.suction('arm1', 'release')
        self.backend.suction('arm2', 'grasp')

    def test_failed_grasp_does_not_record_object(self):
        self.reply = lambda sequence, _text: f'{sequence},fault:no_contact'
        self.assert_faults('no_contact')
        self.reply = lambda sequence, _text: f'{sequence},attached:cap_3'
        self.backend.suction('arm2', 'grasp')

    def test_invalid_requests_are_refused(self):
        self.assert_faults('Invalid suction request', operation='hold')
        self.assert_faults('Invalid suction request', arm='arm3')


class ManualCase(unittest.TestCase):
    def setUp(self):
        self.time = FakeTime()
        self.gate = TokenGate(TIMEOUT * 2, clock=self.time.clock)
        self.announced = []
        self.on_announce = None
        self.guard_error = None
        self.backend = self.make()

    def make(self, auto_confirm=False):
        return ManualTokenSuction(self.gate, self.announce, TIMEOUT, self.guard, auto_confirm,
                                  self.time.clock, self.time.sleep)

    def guard(self):
        if self.guard_error:
            raise self.guard_error

    def announce(self, arm, operation, token):
        self.announced.append((arm, operation, token))
        if self.on_announce:
            self.on_announce(token)


class ManualConfirmation(ManualCase):
    def test_confirmed_step_returns(self):
        self.on_announce = lambda token: self.backend.confirm(token, True)
        self.backend.suction('arm1', 'grasp')
        self.assertEqual(self.announced[0][:2], ('arm1', 'grasp'))

    def test_confirmation_from_another_thread(self):
        backend = ManualTokenSuction(self.gate_real(), self.announce_thread, 5.0, self.guard)
        self.thread_backend = backend
        backend.suction('arm1', 'release')

    def gate_real(self):
        return TokenGate(5.0)

    def announce_thread(self, _arm, _operation, token):
        threading.Timer(0.02, self.thread_backend.confirm, args=(token, True)).start()

    def test_operator_failure_stops(self):
        self.on_announce = lambda token: self.backend.confirm(token, False, 'cap fell')
        with self.assertRaises(TaskFault) as caught:
            self.backend.suction('arm1', 'grasp')
        self.assertIn('cap fell', str(caught.exception))

    def test_only_true_counts_as_success(self):
        self.on_announce = lambda token: self.backend.confirm(token, 1)
        with self.assertRaises(TaskFault):
            self.backend.suction('arm1', 'grasp')

    def test_no_confirmation_times_out(self):
        with self.assertRaises(TaskFault) as caught:
            self.backend.suction('arm1', 'grasp')
        self.assertIn('not confirmed', str(caught.exception))

    def test_late_confirmation_is_refused(self):
        with self.assertRaises(TaskFault):
            self.backend.suction('arm1', 'grasp')
        with self.assertRaises(TokenError):
            self.backend.confirm(self.announced[0][2], True)

    def test_token_is_revoked_after_timeout(self):
        with self.assertRaises(TaskFault):
            self.backend.suction('arm1', 'grasp')
        self.assertIsNone(self.gate.current[0])

    def test_wrong_token_is_refused_and_step_keeps_waiting(self):
        def wrong_then_right(token):
            with self.assertRaises(TokenError):
                self.backend.confirm('wrong', True)
            self.backend.confirm(token, True)
        self.on_announce = wrong_then_right
        self.backend.suction('arm1', 'grasp')

    def test_token_from_previous_step_cannot_confirm_next(self):
        self.on_announce = lambda token: self.backend.confirm(token, True)
        self.backend.suction('arm1', 'grasp')
        previous = self.announced[0][2]
        def stale(_token):
            with self.assertRaises(TokenError):
                self.backend.confirm(previous, True)
        self.on_announce = stale
        with self.assertRaises(TaskFault):
            self.backend.suction('arm1', 'release')

    def test_confirm_without_waiting_step_is_refused(self):
        with self.assertRaises(TokenError):
            self.backend.confirm('anything', True)

    def test_cancel_revokes_the_token(self):
        def cancel():
            if self.time.now >= 1.0:
                self.guard_error = TaskCancelled('stop')
        self.time.hook = cancel
        with self.assertRaises(TaskCancelled):
            self.backend.suction('arm1', 'grasp')
        self.assertIsNone(self.gate.current[0])

    def test_invalid_request_announces_nothing(self):
        with self.assertRaises(TaskFault):
            self.backend.suction('arm1', 'hold')
        self.assertFalse(self.announced)

    def test_auto_confirm_does_not_wait(self):
        self.backend = self.make(auto_confirm=True)
        self.backend.suction('arm1', 'grasp')
        self.assertEqual(self.time.now, 0.0)
        self.assertEqual(len(self.announced), 1)


class Esp32Case(unittest.TestCase):
    ECHO_TIMEOUT, SETTLE = 2.0, 0.5

    def setUp(self):
        self.time = FakeTime()
        self.sent, self.confirmed, self.guard_error = [], [], None
        self.confirm_error = None
        self.answer = lambda command: command
        self.backend = self.make({'arm1': 1, 'arm2': 2})

    def make(self, modules):
        return Esp32Suction(self.publish, modules, self.ECHO_TIMEOUT, self.SETTLE, self, self.guard, self.time.clock, self.time.sleep)

    def guard(self):
        if self.guard_error:
            raise self.guard_error

    def publish(self, arm, command):
        self.sent.append((arm, command))
        reply = self.answer(command)
        if reply is not None:
            self.backend.on_status(reply)

    def suction(self, arm, operation):
        self.confirmed.append((arm, operation, self.time.now))
        if self.confirm_error:
            raise self.confirm_error


class Esp32Commands(Esp32Case):
    def test_commands_match_the_firmware(self):
        for arm, operation, command in (('arm1', 'grasp', 1), ('arm1', 'release', 2), ('arm2', 'grasp', 3), ('arm2', 'release', 4)):
            with self.subTest(arm=arm, operation=operation):
                self.sent.clear()
                self.backend.suction(arm, operation)
                self.assertEqual(self.sent, [(arm, command)])

    def test_module_assignment_can_be_swapped(self):
        self.backend = self.make({'arm1': 2, 'arm2': 1})
        self.backend.suction('arm1', 'grasp')
        self.assertEqual(self.sent, [('arm1', 3)])

    def test_never_sends_the_all_off_command(self):
        self.backend.suction('arm1', 'release')
        self.assertNotIn(0, [command for _, command in self.sent])


class Esp32Failures(Esp32Case):
    def assert_faults(self, text, operation='grasp'):
        with self.assertRaises(TaskFault) as caught:
            self.backend.suction('arm1', operation)
        self.assertIn(text, str(caught.exception))
        self.assertEqual(self.confirmed, [])

    def test_zero_echo_is_a_fault(self):
        self.answer = lambda _command: 0
        self.assert_faults('answered 0')

    def test_different_echo_is_a_fault(self):
        self.answer = lambda _command: 3
        self.assert_faults('answered 3')

    def test_no_echo_times_out(self):
        self.answer = lambda _command: None
        self.assert_faults('no suction controller reply')
        self.assertGreaterEqual(self.time.now, self.ECHO_TIMEOUT)

    def test_echo_from_an_earlier_command_is_not_accepted(self):
        self.backend.on_status(1)
        self.answer = lambda _command: None
        self.assert_faults('no suction controller reply')

    def test_cancel_while_waiting_for_echo(self):
        self.answer = lambda _command: None
        def cancel():
            self.guard_error = TaskCancelled('stop')
        self.time.hook = cancel
        with self.assertRaises(TaskCancelled):
            self.backend.suction('arm1', 'grasp')
        self.assertEqual(self.confirmed, [])

    def test_canceled_before_sending_publishes_nothing(self):
        self.guard_error = TaskCancelled('stop')
        with self.assertRaises(TaskCancelled):
            self.backend.suction('arm1', 'grasp')
        self.assertEqual(self.sent, [])

    def test_invalid_requests_are_refused(self):
        with self.assertRaises(TaskFault):
            self.backend.suction('arm3', 'grasp')
        with self.assertRaises(TaskFault):
            self.backend.suction('arm1', 'hold')
        self.assertEqual(self.sent, [])


class Esp32Confirmation(Esp32Case):
    def test_echo_alone_does_not_finish_the_step(self):
        self.backend.suction('arm1', 'grasp')
        self.assertEqual([item[:2] for item in self.confirmed], [('arm1', 'grasp')])

    def test_operator_failure_stops_the_step(self):
        self.confirm_error = TaskFault('cap fell')
        with self.assertRaises(TaskFault):
            self.backend.suction('arm1', 'grasp')

    def test_grasp_waits_for_vacuum_before_asking(self):
        self.backend.suction('arm1', 'grasp')
        self.assertGreaterEqual(self.confirmed[0][2], self.SETTLE)

    def test_release_does_not_wait_for_vacuum(self):
        self.backend.suction('arm1', 'release')
        self.assertLess(self.confirmed[0][2], self.SETTLE)

    def test_cancel_during_vacuum_wait(self):
        def cancel():
            if self.time.now >= 0.1:
                self.guard_error = TaskCancelled('stop')
        self.time.hook = cancel
        with self.assertRaises(TaskCancelled):
            self.backend.suction('arm1', 'grasp')
        self.assertEqual(self.confirmed, [])

    def test_confirm_reaches_the_operator_backend(self):
        received = []
        self.confirm = lambda *arguments: received.append(arguments)
        self.backend.confirm('token', True, 'ok')
        self.assertEqual(received, [('token', True, 'ok')])


class TokenRevocation(unittest.TestCase):
    def test_revoke_only_affects_the_given_token(self):
        gate = TokenGate(10.0)
        old = gate.issue('a')
        new = gate.issue('b')
        gate.revoke(old)
        gate.consume(new, 'b')

    def test_revoked_token_cannot_be_used(self):
        gate = TokenGate(10.0)
        token = gate.issue('a')
        gate.revoke(token)
        with self.assertRaises(TokenError):
            gate.consume(token, 'a')


def config(mode, backend, auto_confirm=False):
    return {'mode': mode, 'gripper': {'backend': backend, 'auto_confirm': auto_confirm, 'reply_timeout_s': 1.0}}


class Factory(unittest.TestCase):
    def guard(self):
        pass

    def assert_refused(self, doc, text, **kwargs):
        with self.assertRaises(ValueError) as caught:
            create_gripper(None, doc, self.guard, **kwargs)
        self.assertIn(text, str(caught.exception))

    def test_hardware_refuses_auto_confirm(self):
        self.assert_refused(config('hardware', 'manual_token', True), 'simulation only',
                            gate=TokenGate(1.0), announce=print)

    def test_hardware_refuses_gazebo(self):
        self.assert_refused(config('hardware', 'gazebo'), 'simulation only', locator=lambda _: 'cap_1')

    def test_gazebo_needs_locator(self):
        self.assert_refused(config('simulation', 'gazebo'), 'object locator')

    def test_manual_needs_gate_and_announce(self):
        self.assert_refused(config('hardware', 'manual_token'), 'token gate')

    def test_esp32_needs_operator_confirmation(self):
        self.assert_refused(config('hardware', 'esp32'), 'token gate')

    def test_esp32_refuses_auto_confirm(self):
        self.assert_refused(config('hardware', 'esp32', True), 'simulation only', gate=TokenGate(1.0), announce=print)

    def test_prototype_allows_auto_confirm(self):
        backend = create_gripper(None, config('prototype', 'manual_token', True), self.guard,
                                 gate=TokenGate(1.0), announce=lambda *_: None)
        self.assertTrue(backend._auto_confirm)

    def test_prototype_refuses_gazebo(self):
        self.assert_refused(config('prototype', 'gazebo'), 'simulation only', locator=lambda _: 'cap_1')

    def test_unknown_backend_is_not_available(self):
        self.assert_refused(config('hardware', 'pneumatic'), 'not available')

    def test_hardware_manual_never_auto_confirms(self):
        backend = create_gripper(None, config('hardware', 'manual_token'), self.guard,
                                 gate=TokenGate(1.0), announce=lambda *_: None)
        self.assertFalse(backend._auto_confirm)


if __name__ == '__main__':
    unittest.main()
