"""Exercise the safety supervisor against the MoveIt mock; no Gazebo, no hardware.

Usage: test_safety_supervisor.py WORK_DIR REPORT.json
Requires `scripts/start_sim.sh mock` in the same ROS domain.
"""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import traceback

from ament_index_python.packages import get_package_prefix, get_package_share_directory as share
from controller_manager_msgs.srv import ListControllers, SwitchController
import rclpy
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile
from std_msgs.msg import Bool, String
from std_srvs.srv import Trigger

from dual_arm_coordinator.gateways.motion import MotionGateway
from dual_arm_coordinator.homes import load_homes
from dual_arm_coordinator.task_config import load
from dual_arm_coordinator.workflow.ports import TaskFault

A_APPROACH = (-0.14, -0.03, 0.054)
SLOW_SCALE = 0.15
ARM = 'arm1'


class Harness:
    def __init__(self, work_dir, report_path):
        self.work, self.report_path = Path(work_dir), Path(report_path)
        self.work.mkdir(parents=True, exist_ok=True)
        self.journal = self.work / 'journal.json'
        for path in (self.journal, self.journal.with_suffix('.lock')):
            path.unlink(missing_ok=True)
        self.report = {'status': 'FAIL', 'scope': 'Safety supervisor on MoveIt mock_components; no physics, no hardware',
                       'checks': {}, 'observations': {}}
        self.node = Node('safety_supervisor_test')
        group = ReentrantCallbackGroup()
        self.executor = MultiThreadedExecutor(num_threads=4)
        self.executor.add_node(self.node)
        self.spinner = threading.Thread(target=self.executor.spin, daemon=True)
        self.spinner.start()
        self.safety_status = None
        qos = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.node.create_subscription(String, '/safety/status', self.on_status, qos, callback_group=group)
        self.estop = self.node.create_publisher(Bool, '/safety/estop', 10)
        self.reset_client = self.node.create_client(Trigger, '/safety/reset', callback_group=group)
        self.list_client = self.node.create_client(ListControllers, '/controller_manager/list_controllers', callback_group=group)
        self.switch_client = self.node.create_client(SwitchController, '/controller_manager/switch_controller', callback_group=group)
        self.heartbeat_value, self.heartbeat_on = False, threading.Event()
        threading.Thread(target=self.heartbeat, daemon=True).start()
        package = Path(share('dual_arm_coordinator')) / 'config' / 'sim'
        config = copy.deepcopy(load(package / 'coordinator.yaml'))
        config['speeds']['transport_scale'] = SLOW_SCALE
        urdf = (Path(share('dual_arm_description')) / 'urdf' / 'dual_arm_cad.urdf.xacro').read_text(encoding='utf-8')
        self.gateway = MotionGateway(self.node, config, urdf, load_homes(config, runtime_path=package / 'runtime.json'), lambda: None, group)
        self.coordinator, self.supervisor, self.launches = None, None, 0

    def on_status(self, message):
        self.safety_status = json.loads(message.data)

    def heartbeat(self):
        while True:
            if self.heartbeat_on.is_set():
                self.estop.publish(Bool(data=self.heartbeat_value))
            time.sleep(0.1)

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

    def spawn(self, executable, *arguments):
        self.launches += 1
        path = Path(get_package_prefix('dual_arm_coordinator')) / 'lib' / 'dual_arm_coordinator' / executable
        log = (self.work / f'{executable}_{self.launches}.log').open('w')
        return subprocess.Popen([str(path), '--ros-args', *arguments], stdout=log, stderr=subprocess.STDOUT)

    def start_coordinator(self):
        self.coordinator = self.spawn('coordinator_node', '-p', f'journal_path:={self.journal}')

    def wait_for(self, predicate, timeout, label):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return True
            time.sleep(0.02)
        raise RuntimeError(f'Timed out waiting for {label}; status {self.safety_status}')

    def call(self, client, request):
        if not client.wait_for_service(timeout_sec=60):
            raise RuntimeError(f'{client.srv_name} unavailable')
        future = client.call_async(request)
        deadline = time.monotonic() + 30
        while not future.done():
            if time.monotonic() > deadline:
                raise RuntimeError(f'{client.srv_name} timed out')
            time.sleep(0.01)
        return future.result()

    def reset(self):
        return self.call(self.reset_client, Trigger.Request())

    def controller_states(self):
        controllers = self.call(self.list_client, ListControllers.Request()).controller
        return {item.name: item.state for item in controllers if item.name.endswith('_controller')}

    def latched(self, text):
        return lambda: bool(self.safety_status and self.safety_status['latched'] and text in self.safety_status['reason']
                            and self.safety_status['controllers_stopped'])

    def begin_slow_move(self):
        """Start a long move; returns a holder that records how the move ended."""
        result = {'error': None, 'done': threading.Event()}
        start = self.gateway.current(ARM)

        def run():
            try:
                self.gateway.move_to(ARM, A_APPROACH)
            except Exception as error:
                result['error'] = str(error)
            result['done'].set()
        threading.Thread(target=run, daemon=True).start()
        self.wait_for(lambda: max(abs(a - b) for a, b in zip(self.gateway.current(ARM), start)) > 0.01, 60, 'arm motion')
        return result

    def wait_still(self, timeout, window=1.0):
        deadline, reference, since = time.monotonic() + timeout, self.gateway.current(ARM), time.monotonic()
        while time.monotonic() < deadline:
            current = self.gateway.current(ARM)
            if max(abs(a - b) for a, b in zip(current, reference)) > 1e-4:
                reference, since = current, time.monotonic()
            elif time.monotonic() - since >= window:
                return time.monotonic() - window
            time.sleep(0.01)
        raise RuntimeError('Arm did not stop')

    def verify_stopped(self, prefix, started_at, move):
        stopped_at = self.wait_still(30)
        self.observe(f'{prefix}_seconds_until_arm_stopped', stopped_at - started_at)
        self.check(f'{prefix}_controllers_inactive', set(self.controller_states().values()) == {'inactive'}, self.controller_states())
        self.check(f'{prefix}_move_reported_failure', move['done'].wait(30) and move['error'] is not None, move['error'])
        self.check(f'{prefix}_interrupted_before_target', self.gateway.tcp_report(ARM)['tcp_m'][2] > A_APPROACH[2] + 0.005, self.gateway.tcp_report(ARM))
        return stopped_at - started_at

    def restart_clean(self):
        """Clear the latch and return the arm home for the next scenario."""
        response = self.reset()
        self.check(f'reset_accepted_{self.launches}_{len(self.report["checks"])}', response.success, response.message)
        self.wait_for(lambda: self.safety_status and not self.safety_status['latched'], 10, 'latch cleared')
        self.gateway.move_home(ARM)

    def startup(self):
        self.heartbeat_on.set()
        time.sleep(1.0)
        self.start_coordinator()
        self.supervisor = self.spawn('safety_supervisor')
        self.wait_for(lambda: self.safety_status is not None, 60, 'first status')
        self.observe('status_at_startup', self.safety_status)
        time.sleep(3.0)
        if self.safety_status['latched']:
            response = self.reset()
            self.check('startup_reset_after_inputs_arrive', response.success, response.message)
        self.wait_for(lambda: not self.safety_status['latched'], 10, 'clear status')
        self.check('controllers_active_when_healthy', set(self.controller_states().values()) == {'active'}, self.controller_states())
        self.gateway.move_home(ARM)
        self.check('motion_allowed_when_healthy', self.gateway.at_home(ARM))

    def heartbeat_loss(self):
        move = self.begin_slow_move()
        lost_at = time.monotonic()
        self.heartbeat_on.clear()
        self.wait_for(self.latched('heartbeat'), 15, 'heartbeat trip')
        self.check('heartbeat_loss_latches', True, self.safety_status)
        self.observe('heartbeat_seconds_until_controllers_stopped', time.monotonic() - lost_at)
        self.verify_stopped('heartbeat', lost_at, move)
        try:
            self.gateway.move_home(ARM)
            self.check('motion_refused_while_latched', False, 'motion was accepted')
        except TaskFault as error:
            self.check('motion_refused_while_latched', True, str(error))
        refused = self.reset()
        self.check('reset_refused_without_heartbeat', not refused.success and 'heartbeat' in refused.message, refused.message)
        self.check('still_latched_after_refused_reset', self.safety_status['latched'])
        self.heartbeat_on.set()
        time.sleep(1.0)
        self.check('latch_survives_heartbeat_return', self.safety_status['latched'])
        self.check('controllers_stay_inactive_until_reset', set(self.controller_states().values()) == {'inactive'})
        self.manual_activation_while_latched()
        self.restart_clean()

    def manual_activation_while_latched(self):
        """Conflict C32: a person activating the controllers must not get past the latch."""
        request = SwitchController.Request(activate_controllers=['arm1_controller', 'arm2_controller'],
                                           strictness=SwitchController.Request.BEST_EFFORT)
        activated_at = time.monotonic()
        self.check('manual_activation_is_accepted_by_controller_manager', self.call(self.switch_client, request).ok)
        self.wait_for(lambda: set(self.controller_states().values()) == {'inactive'}, 10, 'controllers stopped again')
        self.observe('manual_activation_seconds_until_stopped', time.monotonic() - activated_at)
        self.wait_for(lambda: self.safety_status['latched'] and self.safety_status['controllers_stopped'], 10, 'status recovered')
        self.check('manual_activation_is_stopped_again', True, self.safety_status)
        time.sleep(1.0)
        self.check('controllers_still_inactive_after_manual_activation', set(self.controller_states().values()) == {'inactive'}, self.controller_states())

    def coordinator_death(self):
        move = self.begin_slow_move()
        killed_at = time.monotonic()
        self.coordinator.kill()
        self.coordinator.wait(timeout=10)
        self.wait_for(self.latched('Coordinator'), 15, 'coordinator trip')
        self.check('coordinator_death_latches', True, self.safety_status)
        seconds = self.verify_stopped('coordinator', killed_at, move)
        self.check('arm_stops_soon_after_coordinator_death', seconds < 5.0, {'seconds': seconds, 'before_wp9_seconds': 22.2})
        refused = self.reset()
        self.check('reset_refused_while_coordinator_is_dead', not refused.success and 'Coordinator' in refused.message, refused.message)
        self.start_coordinator()
        self.wait_for_permit(60)
        self.restart_clean()

    def wait_for_permit(self, timeout):
        """A restarted coordinator needs time to load; until it reports in, reset is correctly refused."""
        self.permits = 0
        subscription = self.node.create_subscription(Bool, '/dual_arm/permit', self.count_permit, 10)
        try:
            self.wait_for(lambda: self.permits >= 3, timeout, 'coordinator permit')
        finally:
            self.node.destroy_subscription(subscription)

    def count_permit(self, _message):
        self.permits += 1

    def asserted_estop(self):
        move = self.begin_slow_move()
        asserted_at = time.monotonic()
        self.heartbeat_value = True
        self.wait_for(self.latched('asserted'), 15, 'estop trip')
        self.check('asserted_estop_latches', True, self.safety_status)
        self.verify_stopped('estop', asserted_at, move)
        refused = self.reset()
        self.check('reset_refused_while_estop_is_asserted', not refused.success and 'asserted' in refused.message, refused.message)
        self.heartbeat_value = False
        time.sleep(1.0)
        self.restart_clean()
        self.gateway.move_to(ARM, A_APPROACH)
        self.check('motion_works_after_final_reset', True, self.gateway.tcp_report(ARM))

    def run(self):
        self.startup()
        self.heartbeat_loss()
        self.coordinator_death()
        self.asserted_estop()

    def close(self):
        for process in (self.coordinator, self.supervisor):
            if process is not None and process.poll() is None:
                process.kill()
                process.wait(timeout=10)
        self.executor.shutdown(timeout_sec=5)
        self.spinner.join(timeout=5)


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
    harness.close()
    print(harness.report['status'], flush=True)
    os._exit(0 if passed else 1)


if __name__ == '__main__':
    main()
