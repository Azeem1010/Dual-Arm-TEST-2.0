"""WP6 regression of the coordinator node in Gazebo; ground truth, no cameras or hardware.

Usage: test_transfer_regression.py GROUP WORK_DIR REPORT.json
GROUP is two, faults or batch. Each group needs a freshly started simulation.
"""
import os
from pathlib import Path
import sys
import threading
import time
import traceback

from moveit_msgs.msg import PlanningSceneComponents
from moveit_msgs.srv import GetPlanningScene
import rclpy
from std_msgs.msg import Bool
import yaml

from dual_arm_coordinator.task_config import load
from dual_arm_interfaces.srv import ConfirmStep
from ament_index_python.packages import get_package_share_directory as share

from test_coordinator_sim import Harness

OBJECT_TIMEOUT_S = 700.0


class Regression(Harness):
    def __init__(self, work_dir, report_path):
        super().__init__(work_dir, report_path)
        self.confirm_client = self.node.create_client(ConfirmStep, '/dual_arm/confirm')
        self.scene_client = self.node.create_client(GetPlanningScene, '/get_planning_scene')
        self.estop = self.node.create_publisher(Bool, '/safety/estop', 10)
        self.heartbeat_on = threading.Event()
        threading.Thread(target=self._heartbeat, daemon=True).start()

    def _heartbeat(self):
        while True:
            if self.heartbeat_on.is_set():
                self.estop.publish(Bool(data=False))
            time.sleep(0.1)

    def fresh_journal(self, name):
        path = self.work_dir / f'{name}.json'
        for item in (path, path.with_suffix('.lock')):
            item.unlink(missing_ok=True)
        return path

    def scene(self):
        components = PlanningSceneComponents(components=PlanningSceneComponents.WORLD_OBJECT_NAMES
                                             | PlanningSceneComponents.ROBOT_STATE_ATTACHED_OBJECTS)
        scene = self.call(self.scene_client, GetPlanningScene.Request(components=components)).scene
        return {'world': sorted(item.id for item in scene.world.collision_objects),
                'attached': sorted(item.object.id for item in scene.robot_state.attached_collision_objects)}

    def confirm(self, token, success, message=''):
        return self.call(self.confirm_client, ConfirmStep.Request(token=token, success=success, message=message))

    def wait_end(self, timeout):
        return self.wait_status(lambda s: s['state'] in ('SUCCEEDED', 'FULL', 'FAULT') and not s['busy'], timeout, 'end of run')

    def physical_slots(self):
        grid = self.truth.grid()
        return list(grid.occupied) if grid.success else None

    def recover_after_home(self, arm):
        self.wait_arm_still(arm, 120)
        self.operator.move_home(arm)
        status = self.wait_status(lambda s: bool(s['recovery_token']), 10, 'recovery token')
        return self.recover(status['recovery_token'])

    # --- two objects ---

    def two_objects(self):
        self.start_coordinator(cycles=2, journal=self.fresh_journal('two'))
        self.check('start_accepted', self.trigger('start').success)
        status = self.wait_end(2 * OBJECT_TIMEOUT_S)
        self.check('two_objects_succeeded', status['state'] == 'SUCCEEDED', status['message'])
        self.check('record_has_slots_3_and_4',
                   status['occupied'] == [True] * 4 + [False] * 4 and status['completed'] == 2 and status['b_owner'] == '',
                   {key: status[key] for key in ('occupied', 'completed', 'b_owner')})
        slots = self.physical_slots()
        self.check('ground_truth_has_caps_in_slots_3_and_4', slots == [False, False, True, True] + [False] * 4, slots)
        scene = self.scene()
        self.check('scene_matches_placed_objects', scene == {'world': ['cap_in_slot_3', 'cap_in_slot_4'], 'attached': []}, scene)

    # --- batch ---

    def batch(self):
        self.start_coordinator(cycles=8, prefilled=0, journal=self.fresh_journal('from_empty'))
        self.check('from_empty_start_accepted', self.trigger('start').success)
        status = self.wait_end(180)
        self.observe('eight_objects_from_empty_c', {'status': 'FAIL' if status['state'] != 'FULL' else 'PASS',
                                                    'state': status['state'], 'message': status['message']})
        self.check('slot_1_stops_the_run_before_any_object_moves',
                   status['state'] == 'FAULT' and 'cannot reach' in status['message'] and status['b_owner'] == '' and
                   set(status['holding'].values()) == {'empty'} and self.physical_slots() == [False] * 8, status['message'])
        zone = self.truth.zone()
        self.check('no_object_left_zone_a', zone.success and zone.a_has_object and not zone.b_has_object and zone.c_object_count == 0)
        self.kill_coordinator()
        self.start_coordinator(cycles=6, journal=self.fresh_journal('six'))
        self.check('six_start_accepted', self.trigger('start').success)
        status = self.wait_end(6 * OBJECT_TIMEOUT_S)
        slots = self.physical_slots()
        self.observe('six_objects_result', {'state': status['state'], 'message': status['message'], 'occupied': status['occupied'],
                                            'completed': status['completed'], 'ground_truth_slots': slots})
        self.check('six_objects_fill_slots_3_to_8', status['state'] == 'FULL' and status['completed'] == 6, status['message'])
        self.check('ground_truth_has_caps_in_slots_3_to_8', slots == [False, False] + [True] * 6, slots)

    # --- fault scenarios ---

    def release_failure(self):
        config = load(Path(share('dual_arm_coordinator')) / 'config' / 'sim' / 'coordinator.yaml')
        config['gripper'].update(backend='manual_token', auto_confirm=False, reply_timeout_s=240.0)
        path = self.work_dir / 'manual_token.yaml'
        path.write_text(yaml.safe_dump(config), encoding='utf-8')
        self.start_coordinator(journal=self.fresh_journal('release_failure'), extra=[f'config_path:={path}'])
        self.check('manual_run_accepted', self.trigger('start').success)
        status = self.wait_status(lambda s: s['suction_step'] == 'arm1:grasp', 300, 'grasp confirmation request')
        old = status['suction_token']
        self.check('confirm_with_wrong_token_refused', not self.confirm('wrong', True).accepted)
        self.check('grasp_confirmed', self.confirm(old, True).accepted)
        self.check('used_token_refused', not self.confirm(old, True).accepted)
        status = self.wait_status(lambda s: s['suction_step'] == 'arm1:release', 300, 'release confirmation request')
        self.check('release_reported_failed', self.confirm(status['suction_token'], False, 'cap stuck').accepted)
        status = self.wait_status(lambda s: s['state'] == 'FAULT' and not s['busy'], 30, 'FAULT after failed release')
        self.check('release_failure_keeps_tool_unknown_and_b_owner',
                   'cap stuck' in status['message'] and status['holding']['arm1'] == 'unknown' and status['b_owner'] == 'arm1',
                   {key: status[key] for key in ('message', 'holding', 'b_owner')})
        scene = self.scene()
        self.check('fault_leaves_attached_object_in_scene', scene['attached'] == ['arm1_carried_cap'], scene)
        refused = self.recover(status['recovery_token'])
        self.check('recovery_refused_with_arm_in_b', not refused.accepted, refused.message)
        accepted = self.recover_after_home('arm1')
        self.check('recovery_accepted_after_home', accepted.accepted, accepted.message)
        status = self.wait_status(lambda s: s['state'] == 'IDLE' and not s['busy'], 10, 'IDLE after recovery')
        self.check('recovery_clears_tool_and_b_owner', status['holding']['arm1'] == 'empty' and status['b_owner'] == '',
                   {key: status[key] for key in ('holding', 'b_owner')})
        scene = self.scene()
        self.check('recovery_clears_attached_object', scene['attached'] == [] and 'arm1_carried_cap' not in scene['world'], scene)
        self.kill_coordinator()

    def start_when_heartbeat_arrives(self, timeout=20.0):
        """A new node correctly refuses start until its first heartbeat has been received."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            response = self.trigger('start')
            if response.success:
                return True
            if 'heartbeat' not in response.message:
                self.observe('unexpected_start_refusal', response.message)
                return False
            time.sleep(0.2)
        return False

    def estop_scenarios(self):
        self.heartbeat_on.set()
        time.sleep(0.5)
        self.start_coordinator(journal=self.fresh_journal('estop'), extra=['require_safety:=true'])
        self.check('start_accepted_with_heartbeat', self.start_when_heartbeat_arrives())
        self.wait_state('ARM1:APPROACH_A', 240)
        self.wait_arm_moving('arm1', 60)
        self.heartbeat_on.clear()
        status = self.wait_status(lambda s: s['state'] == 'FAULT' and not s['busy'], 30, 'FAULT after heartbeat loss')
        self.check('heartbeat_loss_stops_the_task', 'heartbeat' in status['message'] or 'canceled' in status['message'].lower(),
                   status['message'])
        self.wait_arm_still('arm1', 60)
        first = self.operator.current('arm1')
        time.sleep(2.0)
        drift = max(abs(a - b) for a, b in zip(first, self.operator.current('arm1')))
        self.check('arm_stays_stopped_after_heartbeat_loss', drift < 0.01, {'max_joint_drift_rad': drift})
        response = self.trigger('start')
        self.check('start_refused_after_heartbeat_loss', not response.success, response.message)
        self.heartbeat_on.set()
        accepted = self.recover_after_home('arm1')
        self.check('recovery_after_heartbeat_returns', accepted.accepted, accepted.message)
        self.wait_status(lambda s: s['state'] == 'IDLE' and not s['busy'], 10, 'IDLE')
        self.estop.publish(Bool(data=True))
        time.sleep(0.5)
        self.heartbeat_on.set()
        time.sleep(0.5)
        response = self.trigger('start')
        self.check('asserted_estop_latches_and_refuses_start', not response.success and 'latched' in response.message, response.message)
        self.heartbeat_on.clear()
        self.kill_coordinator()

    def cancel_while_holding(self):
        self.start_coordinator(journal=self.fresh_journal('cancel_holding'))
        self.check('holding_run_accepted', self.trigger('start').success)
        self.wait_state('ARM1:HOME_HOLDING', 400)
        self.wait_arm_moving_from('arm1', self.operator.current('arm1'), 60)
        self.check('cancel_while_holding_accepted', self.trigger('cancel').success)
        status = self.wait_status(lambda s: s['state'] == 'FAULT' and not s['busy'], 30, 'FAULT after cancel')
        self.check('cancel_keeps_holding_state', status['holding']['arm1'] == 'held', status['holding'])
        self.wait_arm_still('arm1', 60)
        first = self.operator.current('arm1')
        time.sleep(2.0)
        drift = max(abs(a - b) for a, b in zip(first, self.operator.current('arm1')))
        self.check('arm_stays_stopped_while_holding', drift < 0.01, {'max_joint_drift_rad': drift})

    def faults(self):
        self.release_failure()
        self.estop_scenarios()
        self.cancel_while_holding()


def main():
    rclpy.init()
    group, work_dir, report = sys.argv[1:4]
    harness = Regression(work_dir, report)
    harness.report['group'] = group
    try:
        {'two': harness.two_objects, 'batch': harness.batch, 'faults': harness.faults}[group]()
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
    # The report is saved; skip interpreter teardown, which can abort in the ROS client library.
    os._exit(0 if passed else 1)


if __name__ == '__main__':
    main()
