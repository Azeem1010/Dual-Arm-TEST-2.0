"""Run the operator tools against mock serial and the MoveIt mock; no Gazebo, no hardware.

Usage: test_operator_tools.py WORK_DIR REPORT.json
Requires `scripts/start_sim.sh mock` and a static arm1_base transform in the same ROS domain.
"""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
import traceback

from ament_index_python.packages import get_package_prefix, get_package_share_directory as share
import rclpy
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from sensor_msgs.msg import JointState

# World point (-0.14, -0.03) expressed in arm1_base; see docs/COORDINATE_FRAMES.md.
BASE_X, BASE_Y = 0.11725, -0.04
WORLD_XY = (-0.14, -0.03)
ARM1 = [f'arm1_arm_{name}' for name in ('shoulder_pan_joint', 'shoulder_lift_joint', 'elbow_flex_joint', 'wrist_flex_joint')]
ALLOWED = {'VERSION', 'PING', 'GET_HOME,arm1', 'GET_HOME,arm2', 'READ,arm1', 'READ,arm2'}


def tool(package, name):
    return str(Path(get_package_prefix(package)) / 'lib' / package / name)


class Harness:
    def __init__(self, work_dir, report_path):
        self.work, self.report_path = Path(work_dir), Path(report_path)
        self.work.mkdir(parents=True, exist_ok=True)
        self.report = {'status': 'FAIL', 'scope': 'Operator tools on mock serial and MoveIt mock; no hardware', 'checks': {}, 'outputs': {}}
        self.node = Node('operator_tools_test')
        self.joints = {}
        self.node.create_subscription(JointState, '/joint_states', self.on_joints, 10)
        self.executor = MultiThreadedExecutor(num_threads=2)
        self.executor.add_node(self.node)
        threading.Thread(target=self.executor.spin, daemon=True).start()

    def on_joints(self, message):
        self.joints.update(zip(message.name, message.position))

    def save(self):
        self.report_path.write_text(json.dumps(self.report, indent=2) + '\n', encoding='utf-8')

    def check(self, name, passed, detail=None):
        self.report['checks'][name] = {'status': 'PASS' if passed else 'FAIL', 'detail': detail}
        print(name, self.report['checks'][name], flush=True)
        self.save()

    def run_tool(self, label, command, timeout=120):
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
        self.report['outputs'][label] = {'exit': result.returncode, 'stdout': result.stdout[-3000:], 'stderr': result.stderr[-1500:]}
        self.save()
        try:
            parsed = json.loads(result.stdout)
        except ValueError:
            parsed = {}
        return result.returncode, parsed

    def arm1(self):
        return [self.joints[name] for name in ARM1]

    def probe(self):
        port = self.work / 'mock_port'
        port.unlink(missing_ok=True)
        mock = subprocess.Popen([tool('cm530_hardware', 'cm530_mock_serial'), '--link', str(port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            deadline = time.monotonic() + 15
            while not port.exists() and time.monotonic() < deadline:
                time.sleep(0.05)
            code, report = self.run_tool('probe', [tool('dual_arm_coordinator', 'cm530_probe'), '--port', str(port)])
            self.check('probe_reads_the_board', code == 0 and report.get('status') == 'PASS', report.get('error'))
            self.check('probe_reports_firmware_home', report.get('home', {}).get('arm1') == [90, 567, 712, 825] and
                       report.get('home', {}).get('arm2') == [590, 567, 712, 825], report.get('home'))
            sent = {item['tx'] for item in report.get('exchanges', [])}
            self.check('probe_sent_only_read_only_commands', sent == ALLOWED, sorted(sent))
        finally:
            mock.send_signal(signal.SIGTERM)
            mock.wait(timeout=10)
        code, report = self.run_tool('probe_missing_port', [tool('dual_arm_coordinator', 'cm530_probe'), '--port', str(self.work / 'absent')])
        self.check('probe_reports_a_missing_port', code == 1 and report.get('status') == 'FAIL', report.get('error'))

    def sheet(self):
        template = Path(share('dual_arm_coordinator')) / 'config' / 'hardware' / 'calibration_worksheet.template.yaml'
        code, report = self.run_tool('sheet_template', [tool('dual_arm_coordinator', 'check_calibration_sheet'), str(template)])
        self.check('shipped_worksheet_template_is_refused', code == 1 and report.get('written_to_calibration') is False, report.get('error'))

    def manual(self):
        deadline = time.monotonic() + 30
        while any(name not in self.joints for name in ARM1) and time.monotonic() < deadline:
            time.sleep(0.05)
        command = [tool('dual_arm_coordinator', 'manual_xy'), '--arm', 'arm1', '--x', str(BASE_X), '--y', str(BASE_Y)]
        before = self.arm1()
        code, report = self.run_tool('manual_plan', command)
        target = report.get('target_world_m', [0, 0])
        self.check('manual_plan_converts_base_frame', code == 0 and abs(target[0] - WORLD_XY[0]) < 1e-3 and abs(target[1] - WORLD_XY[1]) < 1e-3, report)
        time.sleep(1.0)
        moved = max(abs(a - b) for a, b in zip(before, self.arm1()))
        self.check('plan_only_leaves_the_arm_still', report.get('executed') is False and moved < 1e-6, {'max_joint_motion_rad': moved})
        code, report = self.run_tool('manual_execute', [*command, '--execute'])
        tcp = report.get('tcp_after', {}).get('tcp_m', [0, 0, 0])
        self.check('execute_reaches_the_target', code == 0 and report.get('executed') is True and
                   abs(tcp[0] - WORLD_XY[0]) < 1e-3 and abs(tcp[1] - WORLD_XY[1]) < 1e-3, tcp)
        code, report = self.run_tool('manual_unreachable', [tool('dual_arm_coordinator', 'manual_xy'), '--frame', 'world', '--x', '0.6', '--y', '0.0', '--execute'])
        self.check('unreachable_target_is_refused', code == 1 and 'cannot reach' in report.get('error', ''), report.get('error'))
        hardware = Path(share('dual_arm_coordinator')) / 'config' / 'hardware' / 'coordinator.yaml'
        code, report = self.run_tool('manual_hardware_template', [*command, '--execute', '--config', str(hardware)])
        self.check('hardware_template_is_refused', code == 1 and 'not measured' in report.get('error', ''), str(report.get('error'))[:160])

    def console(self):
        console = tool('dual_arm_coordinator', 'operator_console')
        code, report = self.run_tool('console_no_coordinator', [console, 'status'])
        self.check('status_reports_a_missing_coordinator', code == 1 and 'No status' in report.get('error', ''), report)
        journal = self.work / 'journal.json'
        for path in (journal, journal.with_suffix('.lock')):
            path.unlink(missing_ok=True)
        log = (self.work / 'coordinator.log').open('w')
        coordinator = subprocess.Popen([tool('dual_arm_coordinator', 'coordinator_node'), '--ros-args', '-p', f'journal_path:={journal}'], stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 60
            report = {}
            while not report.get('state') and time.monotonic() < deadline:
                _, report = self.run_tool('console_status', [console, 'status'])
            self.check('status_shows_the_coordinator', report.get('state') == 'IDLE', report.get('state'))
            code, report = self.run_tool('console_confirm_nothing', [console, 'confirm', '--success'])
            self.check('confirm_without_a_step_is_refused', code == 1 and 'No suction step' in report.get('error', ''), report)
            code, _ = self.run_tool('console_recover_no_flag', [console, 'recover'])
            self.check('recover_requires_the_cleared_flag', code == 2)
            code, report = self.run_tool('console_recover_nothing', [console, 'recover', '--cleared'])
            self.check('recover_without_a_fault_is_refused', code == 1 and 'not waiting' in report.get('error', ''), report)
            code, report = self.run_tool('console_start', [console, 'start'])
            self.check('start_is_accepted', code == 0 and report.get('accepted') is True, report)
            deadline = time.monotonic() + 120
            report = {}
            while time.monotonic() < deadline:
                _, report = self.run_tool('console_status_after_start', [console, 'status'])
                if report.get('state') in ('FAULT', 'SUCCEEDED') and not report.get('busy'):
                    break
            # The mock has no object poses, so the run must stop at the first observation.
            self.check('run_stops_without_observations', report.get('state') == 'FAULT' and 'Ground truth' in report.get('message', ''), report.get('message'))
            code, report = self.run_tool('console_recover', [console, 'recover', '--cleared'])
            self.check('recover_is_refused_without_a_valid_scene', code == 1 and report.get('accepted') is False, report)
        finally:
            coordinator.kill()
            coordinator.wait(timeout=10)

    def run(self):
        self.probe()
        self.sheet()
        self.manual()
        self.console()


def main():
    rclpy.init()
    harness = Harness(sys.argv[1], sys.argv[2])
    try:
        harness.run()
        passed = all(item['status'] == 'PASS' for item in harness.report['checks'].values())
        harness.report['status'] = 'PASS' if passed else 'FAIL'
        harness.save()
    except Exception as error:
        harness.report['error'] = f'{error}\n{traceback.format_exc()}'
        harness.save()
        print(harness.report['error'], flush=True)
        passed = False
    print(harness.report['status'], flush=True)
    os._exit(0 if passed else 1)


if __name__ == '__main__':
    main()
