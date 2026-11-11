"""Drive the real coordinator node through its services in Gazebo.

Usage: test_coordinator_sim.py WORK_DIR REPORT.json
Requires `scripts/start_sim.sh headless` in the same ROS domain with a fresh scene.
Objects are located from Gazebo ground truth; no cameras or hardware are involved.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import traceback

from ament_index_python.packages import get_package_prefix, get_package_share_directory as share
import rclpy
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile
from std_msgs.msg import String
from std_srvs.srv import Trigger

from dual_arm_coordinator.gateways.motion import MotionGateway
from dual_arm_coordinator.gateways.truth import TruthObserver, wire_truth
from dual_arm_coordinator.homes import load_homes
from dual_arm_coordinator.task_config import load
from dual_arm_interfaces.srv import ConfirmStep

# The 2026-11-11 measured layout reaches slot 1, so runs start from an empty C.
PREFILLED = 0


class Harness:
    def __init__(self, work_dir, report_path):
        self.work_dir, self.report_path = Path(work_dir), Path(report_path)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.journal = self.work_dir / 'journal.json'
        for path in (self.journal, self.journal.with_suffix('.lock')):
            path.unlink(missing_ok=True)
        self.report = {'status': 'FAIL', 'scope': 'Coordinator node in Gazebo with ground truth; no cameras, no hardware',
                       'checks': {}, 'observations': {}}
        self.process, self.launches = None, 0
        self.status, self.received = None, 0.0
        self.lock = threading.Lock()
        self.node = Node('coordinator_sim_test')
        group = ReentrantCallbackGroup()
        self.executor = MultiThreadedExecutor(num_threads=4)
        self.executor.add_node(self.node)
        self.spinner = threading.Thread(target=self.executor.spin, daemon=True)
        self.spinner.start()
        qos = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.node.create_subscription(String, '/dual_arm/status', self.on_status, qos, callback_group=group)
        self.clients = {name: self.node.create_client(Trigger, f'/dual_arm/{name}', callback_group=group)
                        for name in ('start', 'cancel')}
        self.recover_client = self.node.create_client(ConfirmStep, '/dual_arm/recover', callback_group=group)
        package = Path(share('dual_arm_coordinator')) / 'config' / 'sim'
        self.config = load(package / 'coordinator.yaml')
        urdf = (Path(share('dual_arm_description')) / 'urdf' / 'dual_arm_cad.urdf.xacro').read_text(encoding='utf-8')
        # Stands in for the operator who moves the arm home during recovery.
        self.operator = MotionGateway(self.node, self.config, urdf,
                                      load_homes(self.config, runtime_path=package / 'runtime.json'),
                                      lambda: None, group)
        self.truth = TruthObserver(self.config, lambda arm: self.operator.tcp_report(arm)['tcp_m'],
                                   self.operator.check_reachable, self.operator.home_tcp)
        wire_truth(self.node, self.truth, group)

    def on_status(self, message):
        with self.lock:
            self.status, self.received = json.loads(message.data), time.monotonic()

    def latest(self):
        with self.lock:
            return self.status

    def save(self):
        self.report_path.write_text(json.dumps(self.report, indent=2) + '\n', encoding='utf-8')

    def check(self, name, passed, detail=None):
        self.report['checks'][name] = {'status': 'PASS' if passed else 'FAIL', 'detail': detail}
        print(name, self.report['checks'][name], flush=True)
        self.save()

    def observe(self, name, value):
        self.report['observations'][name] = value
        print('observation', name, value, flush=True)
        self.save()

    def start_coordinator(self, cycles=1, prefilled=PREFILLED, journal=None, extra=()):
        with self.lock:
            self.status = None
        self.launches += 1
        executable = Path(get_package_prefix('dual_arm_coordinator')) / 'lib' / 'dual_arm_coordinator' / 'coordinator_node'
        log = (self.work_dir / f'coordinator_{self.launches}.log').open('w')
        parameters = [f'cycles:={cycles}', f'simulation_prefilled_slots:={prefilled}',
                      f'journal_path:={journal or self.journal}', *extra]
        arguments = [str(executable), '--ros-args']
        for parameter in parameters:
            arguments += ['-p', parameter]
        self.process = subprocess.Popen(arguments, stdout=log, stderr=subprocess.STDOUT)
        return self.wait_status(lambda s: True, 60, 'first status')

    def kill_coordinator(self):
        self.process.kill()
        self.process.wait(timeout=10)

    def wait_status(self, predicate, timeout, label):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status = self.latest()
            if status is not None and predicate(status):
                return status
            if self.process.poll() is not None:
                raise RuntimeError(f'Coordinator exited while waiting for {label}')
            time.sleep(0.02)
        raise RuntimeError(f'Timed out waiting for {label}; last status {self.latest()}')

    def wait_state(self, text, timeout):
        return self.wait_status(lambda s: text in s['state'], timeout, text)

    def call(self, client, request):
        if not client.wait_for_service(timeout_sec=60):
            raise RuntimeError(f'{client.srv_name} unavailable')
        future = client.call_async(request)
        deadline = time.monotonic() + 120
        while not future.done():
            if time.monotonic() > deadline:
                raise RuntimeError(f'{client.srv_name} timed out')
            time.sleep(0.01)
        return future.result()

    def trigger(self, name):
        return self.call(self.clients[name], Trigger.Request())

    def recover(self, token, cleared=True):
        return self.call(self.recover_client, ConfirmStep.Request(token=token, success=cleared, message='test'))

    def idle_after_start(self):
        status = self.start_coordinator()
        self.check('fresh_journal_is_idle_with_empty_c',
                   status['state'] == 'IDLE' and status['occupied'] == [False] * 8, status['state'])

    def wait_arm_moving(self, arm, timeout):
        """Planning takes time, so a cancel only tests motion once the TCP has left HOME."""
        home = self.operator.home_tcp(arm)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            tcp = self.operator.tcp_report(arm)['tcp_m']
            if sum((a - b) ** 2 for a, b in zip(tcp, home)) ** 0.5 > 0.005:
                return
            time.sleep(0.02)
        raise RuntimeError(f'{arm} did not leave HOME')

    def wait_arm_moving_from(self, arm, start, timeout):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if max(abs(a - b) for a, b in zip(self.operator.current(arm), start)) > 0.005:
                return
            time.sleep(0.02)
        raise RuntimeError(f'{arm} did not start moving')

    def wait_arm_still(self, arm, timeout, window=3.0):
        """MoveIt refuses a new trajectory until the running one has ended."""
        deadline, reference, since = time.monotonic() + timeout, self.operator.current(arm), time.monotonic()
        while time.monotonic() < deadline:
            current = self.operator.current(arm)
            if max(abs(a - b) for a, b in zip(current, reference)) > 1e-4:
                reference, since = current, time.monotonic()
            elif time.monotonic() - since >= window:
                return
            time.sleep(0.05)
        raise RuntimeError(f'{arm} did not stop moving')

    def cancel_during_motion(self):
        response = self.trigger('start')
        self.check('start_accepted', response.success, response.message)
        second = self.trigger('start')
        self.check('second_start_refused_while_busy', not second.success, second.message)
        self.wait_state('ARM1:APPROACH_A', 180)
        self.wait_arm_moving('arm1', 60)
        cancelled = self.trigger('cancel')
        self.check('cancel_accepted', cancelled.success, cancelled.message)
        status = self.wait_status(lambda s: s['state'] == 'FAULT' and not s['busy'], 30, 'FAULT after cancel')
        self.check('cancel_ends_in_fault_with_recovery_token', bool(status['recovery_token']), status['message'])
        time.sleep(3.0)
        first = self.operator.current('arm1')
        time.sleep(2.0)
        second_sample = self.operator.current('arm1')
        drift = max(abs(a - b) for a, b in zip(first, second_sample))
        self.check('arm_stays_stopped_after_cancel', drift < 0.01, {'max_joint_drift_rad': drift})
        self.check('cancel_interrupted_motion_before_target', not self.operator.at_home('arm1') and
                   self.operator.tcp_report('arm1')['tcp_m'][2] > self.config['heights']['approach_z_m'] + 0.005,
                   self.operator.tcp_report('arm1'))
        return status

    def refusals_in_fault(self, status):
        response = self.trigger('start')
        self.check('start_refused_in_fault', not response.success, response.message)
        wrong = self.recover('wrong-token')
        self.check('wrong_recovery_token_refused', not wrong.accepted, wrong.message)
        token = status['recovery_token']
        refused = self.recover(token)
        self.check('recovery_refused_while_arm_is_not_home', not refused.accepted and 'not at HOME' in refused.message,
                   refused.message)
        status = self.wait_status(lambda s: s['recovery_token'] and s['recovery_token'] != token, 10, 'new token')
        self.check('refused_recovery_issues_a_new_token', True)
        return status

    def restart_keeps_fault(self, status):
        old_token = status['recovery_token']
        self.kill_coordinator()
        status = self.start_coordinator()
        self.check('fault_survives_restart', status['state'] == 'FAULT', status['message'])
        refused = self.recover(old_token)
        self.check('token_from_previous_process_refused', not refused.accepted, refused.message)
        self.operator.move_home('arm1')
        status = self.wait_status(lambda s: bool(s['recovery_token']), 10, 'recovery token')
        accepted = self.recover(status['recovery_token'])
        self.check('recovery_accepted_after_arm_is_home', accepted.accepted, accepted.message)
        self.wait_status(lambda s: s['state'] == 'IDLE' and not s['busy'], 10, 'IDLE after recovery')

    def kill_during_run(self):
        response = self.trigger('start')
        self.check('second_run_accepted', response.success, response.message)
        self.wait_state('ARM1:DESCEND_A', 240)
        self.wait_arm_moving_from('arm1', self.operator.current('arm1'), 60)
        before = self.operator.current('arm1')
        killed_at = time.monotonic()
        self.kill_coordinator()
        self.wait_arm_still('arm1', 120)
        after = self.operator.current('arm1')
        # Known gap until WP9: a dead coordinator does not stop the running trajectory.
        self.observe('joint_motion_after_coordinator_killed_rad', max(abs(a - b) for a, b in zip(before, after)))
        self.observe('seconds_until_arm_stopped_after_kill', time.monotonic() - killed_at)
        status = self.start_coordinator()
        self.check('interrupted_run_requires_recovery', status['state'] == 'FAULT' and 'did not finish' in status['message'],
                   status['message'])
        response = self.trigger('start')
        self.check('start_refused_after_interrupted_run', not response.success, response.message)
        self.operator.move_home('arm1')
        status = self.wait_status(lambda s: bool(s['recovery_token']), 10, 'recovery token')
        accepted = self.recover(status['recovery_token'])
        self.check('recovery_after_interrupted_run', accepted.accepted, accepted.message)
        self.wait_status(lambda s: s['state'] == 'IDLE' and not s['busy'], 10, 'IDLE after second recovery')

    def full_cycle(self):
        response = self.trigger('start')
        self.check('final_run_accepted', response.success, response.message)
        status = self.wait_status(lambda s: s['state'] in ('SUCCEEDED', 'FAULT') and not s['busy'], 900, 'end of run')
        self.check('full_cycle_succeeded', status['state'] == 'SUCCEEDED', status['message'])
        self.check('record_shows_slot_1_and_no_owner',
                   status['occupied'] == [True] + [False] * 7 and status['b_owner'] == '' and
                   status['completed'] == 1 and set(status['holding'].values()) == {'empty'},
                   {key: status[key] for key in ('occupied', 'b_owner', 'completed', 'holding')})
        grid = self.truth.grid()
        self.check('ground_truth_has_a_cap_in_slot_1', grid.success and grid.occupied[0], list(grid.occupied))

    def run(self):
        self.idle_after_start()
        status = self.cancel_during_motion()
        status = self.refusals_in_fault(status)
        self.restart_keeps_fault(status)
        self.kill_during_run()
        self.full_cycle()
        passed = all(item['status'] == 'PASS' for item in self.report['checks'].values())
        self.report['status'] = 'PASS' if passed else 'FAIL'
        self.save()
        return passed

    def close(self):
        if self.process is not None and self.process.poll() is None:
            self.kill_coordinator()
        self.executor.shutdown(timeout_sec=5)
        self.spinner.join(timeout=5)


def main():
    rclpy.init()
    harness = Harness(sys.argv[1], sys.argv[2])
    try:
        passed = harness.run()
    except Exception as error:
        harness.report['error'] = f'{error}\n{traceback.format_exc()}'
        harness.save()
        print(harness.report['error'], flush=True)
        passed = False
    harness.close()
    print(harness.report['status'], flush=True)
    # The report is saved; skip interpreter teardown, which can abort in the ROS client library.
    os._exit(0 if passed else 1)


if __name__ == '__main__':
    main()
