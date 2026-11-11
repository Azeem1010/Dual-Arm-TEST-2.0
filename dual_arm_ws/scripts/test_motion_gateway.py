"""Drive MotionGateway against the MoveIt mock launch; no Gazebo, no hardware.

Usage: test_motion_gateway.py REPORT.json
Requires `scripts/start_sim.sh mock` in the same ROS domain with a fresh scene.
"""
import json
from pathlib import Path
import sys
import threading
import time
import traceback

from ament_index_python.packages import get_package_share_directory as share
from geometry_msgs.msg import Pose
from moveit_msgs.msg import CollisionObject, PlanningScene, PlanningSceneComponents
from moveit_msgs.srv import ApplyPlanningScene, GetPlanningScene
import rclpy
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from shape_msgs.msg import SolidPrimitive

from dual_arm_coordinator.gateways.motion import MotionGateway
from dual_arm_coordinator.homes import load_homes
from dual_arm_coordinator.task_config import load
from dual_arm_coordinator.workflow.ports import TaskCancelled, TaskFault

A_XY = (-0.14, -0.03)
SLOT_3 = 3


class Harness:
    def __init__(self, report_path):
        self.report_path = Path(report_path)
        self.report = {'status': 'FAIL', 'scope': 'MotionGateway on MoveIt mock_components; no physics, no hardware',
                       'steps': [], 'checks': {}}
        package = Path(share('dual_arm_coordinator')) / 'config' / 'sim'
        self.config = load(package / 'coordinator.yaml')
        urdf = (Path(share('dual_arm_description')) / 'urdf' / 'dual_arm_cad.urdf.xacro').read_text(encoding='utf-8')
        self.node = Node('motion_gateway_test')
        self.group = ReentrantCallbackGroup()
        self.executor = MultiThreadedExecutor(num_threads=4)
        self.executor.add_node(self.node)
        threading.Thread(target=self.executor.spin, daemon=True).start()
        self.cancelled = threading.Event()
        self.gateway = MotionGateway(self.node, self.config, urdf, load_homes(self.config, runtime_path=package / 'runtime.json'),
                                     self.guard, self.group)
        self.apply_client = self.node.create_client(ApplyPlanningScene, '/apply_planning_scene', callback_group=self.group)
        self.scene_client = self.node.create_client(GetPlanningScene, '/get_planning_scene', callback_group=self.group)

    def guard(self):
        if self.cancelled.is_set():
            raise TaskCancelled('test cancel')

    def save(self):
        self.report_path.write_text(json.dumps(self.report, indent=2) + '\n', encoding='utf-8')

    def wait_ready(self):
        self.gateway._cfg = {**self.gateway._cfg, 'goal_submit_s': 60.0}
        self.gateway.current('arm1')
        self.gateway._cfg = self.config['motion']

    def call(self, client, request):
        if not client.wait_for_service(timeout_sec=30):
            raise RuntimeError(f'{client.srv_name} unavailable')
        future = client.call_async(request)
        deadline = time.monotonic() + 30
        while not future.done():
            if time.monotonic() > deadline:
                raise RuntimeError(f'{client.srv_name} timed out')
            time.sleep(0.01)
        return future.result()

    def scene(self):
        components = PlanningSceneComponents(components=PlanningSceneComponents.WORLD_OBJECT_NAMES
                                             | PlanningSceneComponents.ROBOT_STATE_ATTACHED_OBJECTS)
        scene = self.call(self.scene_client, GetPlanningScene.Request(components=components)).scene
        return {'world': sorted(item.id for item in scene.world.collision_objects),
                'attached': sorted(item.object.id for item in scene.robot_state.attached_collision_objects)}

    def check(self, name, passed, detail=None):
        self.report['checks'][name] = {'status': 'PASS' if passed else 'FAIL', 'detail': detail}
        print(name, self.report['checks'][name], flush=True)
        self.save()

    def step(self, label, arm, action, target=None):
        action()
        tcp = self.gateway.tcp_report(arm)
        target = list(target) if target is not None else self.gateway.home_tcp(arm)
        error = sum((a - b) ** 2 for a, b in zip(tcp['tcp_m'], target)) ** 0.5
        entry = {'label': label, 'arm': arm, 'target_m': target, **tcp, 'position_error_m': error}
        self.report['steps'].append(entry)
        print(json.dumps(entry), flush=True)
        self.save()

    def to(self, label, arm, xyz, contact=False):
        self.step(label, arm, lambda: self.gateway.move_to(arm, xyz, contact=contact), xyz)

    def home(self, label, arm):
        self.step(label, arm, lambda: self.gateway.move_home(arm))

    def expect_refused(self, name, function, required=''):
        try:
            function()
        except TaskFault as error:
            self.check(name, required in str(error), str(error))
        else:
            self.check(name, False, 'was accepted')

    def transfer(self):
        gw, heights, zones = self.gateway, self.config['heights'], self.config['zones']
        approach, contact, release = heights['approach_z_m'], heights['contact_z_m'], heights['release_z_m']
        b, slot = zones['b_place_xy_m'], zones['c_slots_xy_m'][SLOT_3 - 1]
        self.home('arm1 initial home', 'arm1')
        self.home('arm2 initial home', 'arm2')
        self.check('at_home_after_home', gw.at_home('arm1') and gw.at_home('arm2'))
        gw.check_reachable('arm1', (*A_XY, approach))
        self.to('arm1 above A', 'arm1', (*A_XY, approach))
        self.to('arm1 descend A', 'arm1', (*A_XY, contact), contact=True)
        gw.attach('arm1')
        self.check('attach_visible_in_scene', self.scene()['attached'] == ['arm1_carried_cap'], self.scene())
        self.to('arm1 lift A', 'arm1', (*A_XY, approach), contact=True)
        self.home('arm1 home holding', 'arm1')
        self.to('arm1 above B', 'arm1', (*b, approach))
        self.to('arm1 descend B', 'arm1', (*b, contact), contact=True)
        gw.detach('arm1')
        gw.scene_add_b_object()
        scene = self.scene()
        self.check('detach_leaves_only_recorded_object', scene == {'world': ['cap_in_b'], 'attached': []}, scene)
        self.to('arm1 lift B', 'arm1', (*b, approach), contact=True)
        self.home('arm1 home empty', 'arm1')
        gw.scene_remove_b_object()
        gw.scene_remove_b_object()
        self.check('removing_absent_b_object_is_harmless', self.scene()['world'] == [], self.scene())
        self.to('arm2 above B', 'arm2', (*b, approach))
        self.to('arm2 descend B', 'arm2', (*b, contact), contact=True)
        gw.attach('arm2')
        self.to('arm2 lift B', 'arm2', (*b, approach), contact=True)
        self.home('arm2 home holding', 'arm2')
        self.to('arm2 above slot 3', 'arm2', (*slot, approach))
        self.to('arm2 descend slot 3', 'arm2', (*slot, release), contact=True)
        gw.detach('arm2')
        gw.scene_add_slot_object(SLOT_3)
        self.to('arm2 lift slot 3', 'arm2', (*slot, approach), contact=True)
        self.home('arm2 home empty', 'arm2')
        self.check('slot_object_recorded', self.scene() == {'world': ['cap_in_slot_3'], 'attached': []}, self.scene())

    def refusals(self):
        gw, heights, zones = self.gateway, self.config['heights'], self.config['zones']
        # Slot 8, farthest from the arms, has no downward-suction solution (ik_validation.json).
        slot_8 = zones['c_slots_xy_m'][7]
        self.expect_refused('known_unreachable_slot_8_refused',
                            lambda: gw.check_reachable('arm2', (*slot_8, heights['contact_z_m'] + 0.03)))
        self.expect_refused('far_target_refused', lambda: gw.check_reachable('arm1', (0.6, 0.0, 0.05)))
        approach, contact = (*A_XY, heights['approach_z_m']), (*A_XY, heights['contact_z_m'])
        self.set_blocker([0.08, 0.08, 0.12], 0.07)
        self.expect_refused('collision_target_refused', lambda: gw.check_reachable('arm1', approach),
                            required='state is invalid')
        self.remove_blocker()
        # Start directly above the target, so only the blocker can refuse the descent.
        gw.move_to('arm1', approach)
        self.set_blocker([0.03, 0.03, 0.02], 0.03)
        before = gw.current('arm1')
        self.expect_refused('collision_contact_path_refused_before_motion',
                            lambda: gw.move_to('arm1', contact, contact=True), required='state is invalid')
        moved = max(abs(a - b) for a, b in zip(before, gw.current('arm1')))
        self.check('refused_contact_path_did_not_move', moved < 1e-6, {'max_joint_motion_rad': moved})
        self.remove_blocker()

    def set_blocker(self, size, z):
        blocker = CollisionObject(id='blocker', operation=CollisionObject.ADD)
        blocker.header.frame_id = 'world'
        blocker.primitives = [SolidPrimitive(type=SolidPrimitive.BOX, dimensions=size)]
        pose = Pose()
        pose.position.x, pose.position.y, pose.position.z, pose.orientation.w = A_XY[0], A_XY[1], z, 1.0
        blocker.primitive_poses = [pose]
        scene = PlanningScene(is_diff=True)
        scene.world.collision_objects = [blocker]
        self.call(self.apply_client, ApplyPlanningScene.Request(scene=scene))

    def remove_blocker(self):
        scene = PlanningScene(is_diff=True)
        scene.world.collision_objects = [CollisionObject(id='blocker', operation=CollisionObject.REMOVE)]
        self.call(self.apply_client, ApplyPlanningScene.Request(scene=scene))

    def cancellation(self):
        gw, heights = self.gateway, self.config['heights']
        gw.move_home('arm1')
        self.cancelled.clear()
        timer = threading.Timer(0.6, self.cancelled.set)
        timer.start()
        stopped = False
        try:
            gw.move_to('arm1', (*A_XY, heights['approach_z_m']))
        except TaskCancelled:
            stopped = True
        timer.join()
        self.check('cancel_raises_task_cancelled', stopped)
        self.cancelled.clear()
        time.sleep(1.0)
        first = gw.current('arm1')
        time.sleep(1.5)
        second = gw.current('arm1')
        drift = max(abs(a - b) for a, b in zip(first, second))
        self.check('arm_stays_stopped_after_cancel', drift < 1e-3, {'max_joint_drift_rad': drift})
        self.check('cancel_interrupted_the_move', not gw.at_home('arm1') and
                   gw.tcp_report('arm1')['tcp_m'][2] > heights['approach_z_m'] + 1e-3, gw.tcp_report('arm1'))
        gw.move_home('arm1')

    def run(self):
        self.wait_ready()
        self.transfer()
        self.refusals()
        self.cancellation()
        worst = max(step['position_error_m'] for step in self.report['steps'])
        limit = self.config['motion']['tcp_error_limit_m']
        self.check('all_steps_within_tcp_limit', worst <= limit, {'worst_position_error_m': worst, 'limit_m': limit})
        contact_steps = [step for step in self.report['steps'] if 'descend' in step['label'] or 'lift' in step['label']]
        tilt = max(step['tool_tilt_deg'] for step in contact_steps)
        self.check('tool_down_on_contact_moves', tilt < 0.5, {'worst_tilt_deg': tilt})
        passed = all(item['status'] == 'PASS' for item in self.report['checks'].values())
        self.report['status'] = 'PASS' if passed else 'FAIL'
        self.save()
        return passed


def main():
    rclpy.init()
    harness = Harness(sys.argv[1])
    try:
        passed = harness.run()
    except Exception as error:
        harness.report['error'] = f'{error}\n{traceback.format_exc()}'
        harness.save()
        print(harness.report['error'], flush=True)
        passed = False
    harness.executor.shutdown(timeout_sec=2)
    print(harness.report['status'], flush=True)
    return 0 if passed else 1


if __name__ == '__main__':
    sys.exit(main())
