from pathlib import Path
import copy
import math
import unittest

import yaml

from dual_arm_coordinator.kinematics import CadKinematics
from dual_arm_coordinator.motion_math import tcp_position, tool_tilt_deg
from dual_arm_coordinator.tools.calibration_sheet import COUNTS_PER_RADIAN, JOINT_SUFFIXES, SheetError, check_sheet, fit_joint
from dual_arm_coordinator.tools.cm530_probe import ALLOWED_COMMANDS, Probe, ProbeError, run_probe
from dual_arm_coordinator.tools.manual_xy import manual_move
from dual_arm_coordinator.tools.operator_console import ConsoleError, confirmation_token, parse_arguments, recovery_token
from dual_arm_coordinator.workflow.ports import TaskFault

PACKAGE = Path(__file__).resolve().parents[1]
URDF = (PACKAGE.parent / 'dual_arm_description' / 'urdf' / 'dual_arm_cad.urdf.xacro').read_text(encoding='utf-8')
TEMPLATE = PACKAGE / 'config' / 'hardware' / 'calibration_worksheet.template.yaml'
CONFIG = yaml.safe_load((PACKAGE / 'config' / 'sim' / 'coordinator.yaml').read_text(encoding='utf-8'))
REPLIES = {'VERSION': 'VERSION,5', 'PING': 'PONG', 'GET_HOME,arm1': 'HOME,arm1,90,567,712,825',
           'GET_HOME,arm2': 'HOME,arm2,590,567,712,825', 'READ,arm1': 'POS,arm1,500,501,502,503', 'READ,arm2': 'POS,arm2,510,511,512,513'}


class FakePort:
    def __init__(self, replies=None, boot=b''):
        self.replies, self.rx, self.written, self.now = dict(replies or REPLIES), boot, [], 0.0

    def write(self, data):
        self.written.append(data)
        if not data.startswith(b'\x7f'):
            reply = self.replies.get(data.decode().strip())
            if reply is not None:
                self.rx += reply.encode() + b'\r\n'

    def read(self, timeout):
        data, self.rx = self.rx, b''
        if not data:
            self.now += timeout
        return data

    def commands(self):
        return [item.decode().strip() for item in self.written if not item.startswith(b'\x7f')]


class CM530Probe(unittest.TestCase):
    def run_with(self, port):
        probe_report = None
        original = Probe.__init__

        def patched(instance, device, timeout, clock=None):
            original(instance, device, timeout, lambda: port.now)
        Probe.__init__ = patched
        try:
            probe_report = run_probe(port, 1.0)
        finally:
            Probe.__init__ = original
        return probe_report

    def test_reads_version_home_and_position(self):
        report = self.run_with(FakePort())
        self.assertEqual(report['status'], 'PASS')
        self.assertEqual(report['home']['arm1'], [90, 567, 712, 825])
        self.assertEqual(report['position']['arm2'], [510, 511, 512, 513])

    def test_only_read_only_commands_are_written(self):
        port = FakePort()
        self.run_with(port)
        self.assertTrue(set(port.commands()) <= set(ALLOWED_COMMANDS))
        for forbidden in ('AX', 'HOLD', 'TORQUE', 'LED'):
            self.assertFalse(any(command.startswith(forbidden) for command in port.commands()))
        self.assertFalse(any(command.startswith('HOME') for command in port.commands()))

    def test_first_write_clears_the_firmware_line(self):
        port = FakePort()
        self.run_with(port)
        self.assertEqual(port.written[0], b'\x7f' * 96)

    def test_other_commands_are_refused_before_writing(self):
        port = FakePort()
        probe = Probe(port, 1.0, clock=lambda: port.now)
        for command in ('AX,arm1,1,2,3,4', 'HOME,arm1', 'HOLD,arm1', 'TORQUE,arm1,1'):
            with self.assertRaises(ProbeError):
                probe.send(command)
        self.assertEqual(port.written, [])

    def test_timeout_stops_without_retry(self):
        replies = dict(REPLIES)
        del replies['PING']
        port = FakePort(replies)
        report = self.run_with(port)
        self.assertEqual(report['status'], 'FAIL')
        self.assertIn('No reply to PING', report['error'])
        self.assertEqual(port.commands(), ['VERSION', 'PING'])

    def test_error_reply_stops_the_probe(self):
        replies = {**REPLIES, 'READ,arm1': 'ERR,DXL_TIMEOUT,arm1,15'}
        port = FakePort(replies)
        report = self.run_with(port)
        self.assertEqual(report['status'], 'FAIL')
        self.assertIn('DXL_TIMEOUT', report['error'])
        self.assertEqual(port.commands()[-1], 'READ,arm1')

    def test_wrong_version_stops(self):
        self.assertEqual(self.run_with(FakePort({**REPLIES, 'VERSION': 'VERSION,4'}))['status'], 'FAIL')

    def test_boot_message_is_tolerated(self):
        self.assertEqual(self.run_with(FakePort(boot=b'READY,5\r\n'))['status'], 'PASS')

    def test_unexpected_startup_line_stops(self):
        report = self.run_with(FakePort(boot=b'OK,AX,arm1\r\n'))
        self.assertEqual(report['status'], 'FAIL')
        self.assertFalse(report['exchanges'])


LIMITS = {'max_fit_ticks': 2.0, 'min_span_rad': 0.2, 'max_position_error_m': 0.005, 'max_tilt_error_deg': 3.0}
ZERO, DIRECTION = 500.0, -1


def raw_for(q):
    return ZERO + DIRECTION * q * COUNTS_PER_RADIAN


def good_sheet():
    model = CadKinematics(URDF, 'arm1')
    joints = {f'arm1_{suffix}': {'samples': [{'angle_rad': angle, 'raw': raw_for(angle)} for angle in (-0.3, 0.0, 0.3)]}
              for suffix in JOINT_SUFFIXES}
    poses = [[0.0, 0.0, 0.0, 0.0], [0.2, -0.3, 0.4, 0.5], [-0.2, 0.3, 0.2, 1.0]]
    verification = [{'raw': [raw_for(q) for q in pose], 'tcp_m': tcp_position(model, pose).tolist(), 'tilt_deg': tool_tilt_deg(model, pose)}
                    for pose in poses]
    return {'acceptance': dict(LIMITS), 'arms': ['arm1'], 'joints': joints, 'verification': {'arm1': verification}}


class CalibrationSheet(unittest.TestCase):
    def test_recovers_zero_and_direction(self):
        report = check_sheet(good_sheet(), URDF)
        self.assertEqual(report['status'], 'PASS', report['problems'])
        joint = report['joints']['arm1_arm_elbow_flex_joint']
        self.assertAlmostEqual(joint['zero_raw'], ZERO, places=6)
        self.assertEqual(joint['direction'], DIRECTION)

    def test_never_claims_to_write_calibration(self):
        self.assertIs(check_sheet(good_sheet(), URDF)['written_to_calibration'], False)

    def test_fit_chooses_the_matching_sign(self):
        samples = [(angle, 512 + angle * COUNTS_PER_RADIAN) for angle in (-0.2, 0.0, 0.2)]
        self.assertEqual(fit_joint(samples)[1], 1)

    def test_shipped_template_is_refused(self):
        with self.assertRaises(SheetError):
            check_sheet(yaml.safe_load(TEMPLATE.read_text(encoding='utf-8')), URDF)

    def test_limits_have_no_defaults(self):
        for name in LIMITS:
            sheet = good_sheet()
            sheet['acceptance'][name] = None
            with self.subTest(name), self.assertRaises(SheetError):
                check_sheet(sheet, URDF)

    def test_too_few_samples_are_refused(self):
        sheet = good_sheet()
        sheet['joints']['arm1_arm_wrist_flex_joint']['samples'].pop()
        with self.assertRaises(SheetError):
            check_sheet(sheet, URDF)

    def test_missing_joint_and_verification_are_refused(self):
        sheet = good_sheet()
        del sheet['joints']['arm1_arm_elbow_flex_joint']
        with self.assertRaises(SheetError):
            check_sheet(sheet, URDF)
        sheet = good_sheet()
        sheet['verification']['arm1'].pop()
        with self.assertRaises(SheetError):
            check_sheet(sheet, URDF)

    def test_small_span_fails(self):
        sheet = good_sheet()
        sheet['joints']['arm1_arm_shoulder_pan_joint']['samples'] = [
            {'angle_rad': angle, 'raw': raw_for(angle)} for angle in (0.0, 0.05, 0.1)]
        self.assertEqual(check_sheet(sheet, URDF)['status'], 'FAIL')

    def test_inconsistent_samples_fail(self):
        sheet = good_sheet()
        sheet['joints']['arm1_arm_shoulder_lift_joint']['samples'][1]['raw'] += 12.0
        report = check_sheet(sheet, URDF)
        self.assertEqual(report['status'], 'FAIL')
        self.assertIn('residual', ' '.join(report['problems']))

    def test_wrong_measured_position_fails(self):
        sheet = good_sheet()
        sheet['verification']['arm1'][1]['tcp_m'][0] += 0.02
        report = check_sheet(sheet, URDF)
        self.assertEqual(report['status'], 'FAIL')
        self.assertIn('position error', ' '.join(report['problems']))

    def test_wrong_measured_tilt_fails(self):
        sheet = good_sheet()
        sheet['verification']['arm1'][0]['tilt_deg'] += 10.0
        self.assertIn('tilt error', ' '.join(check_sheet(sheet, URDF)['problems']))

    def test_non_finite_values_are_refused(self):
        sheet = copy.deepcopy(good_sheet())
        sheet['joints']['arm1_arm_elbow_flex_joint']['samples'][0]['raw'] = math.nan
        with self.assertRaises(SheetError):
            check_sheet(sheet, URDF)


class FakeMotion:
    def __init__(self, reachable=True):
        self.reachable, self.moves, self.checks = reachable, [], []

    def check_reachable(self, arm, xyz):
        self.checks.append((arm, xyz))
        if not self.reachable:
            raise TaskFault('cannot reach')

    def move_to(self, arm, xyz):
        self.moves.append((arm, xyz))

    def tcp_report(self, _arm):
        return {'tcp_m': [0.0, 0.0, 0.0]}


class ManualMove(unittest.TestCase):
    world = staticmethod(lambda _arm, x, y: (x + 1.0, y + 2.0))

    def run_move(self, motion, x=0.1, y=0.2, execute=False, status=None, arm='arm1'):
        return manual_move(motion, CONFIG, arm, x, y, execute, self.world, status)

    def test_plans_only_by_default(self):
        motion = FakeMotion()
        report = self.run_move(motion)
        self.assertEqual(motion.moves, [])
        self.assertEqual(len(motion.checks), 1)
        self.assertFalse(report['executed'])

    def test_execute_moves_at_travel_height_after_conversion(self):
        motion = FakeMotion()
        report = self.run_move(motion, execute=True)
        self.assertEqual(motion.moves, [('arm1', (1.1, 2.2, CONFIG['heights']['approach_z_m']))])
        self.assertTrue(report['executed'])

    def test_refused_while_a_task_is_running(self):
        motion = FakeMotion()
        with self.assertRaises(TaskFault):
            self.run_move(motion, execute=True, status={'busy': True})
        self.assertEqual(motion.checks, [])

    def test_idle_status_allows_planning(self):
        self.run_move(FakeMotion(), status={'busy': False})

    def test_unreachable_target_never_moves(self):
        motion = FakeMotion(reachable=False)
        with self.assertRaises(TaskFault):
            self.run_move(motion, execute=True)
        self.assertEqual(motion.moves, [])

    def test_non_finite_and_unknown_arm_are_refused(self):
        for kwargs in (dict(x=math.nan), dict(y=math.inf), dict(arm='arm3')):
            with self.subTest(kwargs), self.assertRaises(TaskFault):
                self.run_move(FakeMotion(), **kwargs)


class OperatorArguments(unittest.TestCase):
    def assert_rejected(self, *arguments):
        with self.assertRaises(SystemExit):
            parse_arguments(list(arguments))

    def test_confirm_needs_exactly_one_result(self):
        self.assert_rejected('confirm')
        self.assert_rejected('confirm', '--success', '--failed')
        self.assertTrue(parse_arguments(['confirm', '--success']).success)
        self.assertTrue(parse_arguments(['confirm', '--failed', '--message', 'cap fell']).failed)

    def test_recover_needs_the_cleared_flag(self):
        self.assert_rejected('recover')
        self.assertTrue(parse_arguments(['recover', '--cleared']).cleared)

    def test_unknown_command_is_rejected(self):
        self.assert_rejected('home')

    def test_tokens_come_from_status(self):
        self.assertEqual(confirmation_token({'suction_token': 'abc'}), 'abc')
        self.assertEqual(recovery_token({'recovery_token': 'def'}), 'def')

    def test_missing_tokens_are_reported(self):
        for function in (confirmation_token, recovery_token):
            for status in ({}, None, {'suction_token': '', 'recovery_token': ''}):
                with self.subTest(status), self.assertRaises(ConsoleError):
                    function(status)


if __name__ == '__main__':
    unittest.main()
