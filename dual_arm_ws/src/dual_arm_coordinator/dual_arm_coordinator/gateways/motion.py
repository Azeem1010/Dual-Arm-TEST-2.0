"""MoveIt motion and PlanningScene gateway.

The planning group uses position-only KDL, which does not hold the suction axis,
so targets are solved here with CadKinematics and sent as joint values. All
targets are in the URDF world frame; other frames are converted by the caller.
"""
import threading
import time

from action_msgs.msg import GoalStatus
from builtin_interfaces.msg import Duration
from geometry_msgs.msg import Pose
from moveit_msgs.action import ExecuteTrajectory, MoveGroup
from moveit_msgs.msg import (AttachedCollisionObject, CollisionObject, Constraints, JointConstraint,
                             MoveItErrorCodes, PlanningScene, PlanningSceneComponents, RobotState, RobotTrajectory)
from moveit_msgs.srv import ApplyPlanningScene, GetPlanningScene, GetStateValidity
from rclpy.action import ActionClient
from sensor_msgs.msg import JointState
from shape_msgs.msg import SolidPrimitive
from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint

from ..kinematics import CadKinematics
from ..motion_math import line_points, solve_line, tcp_error, tcp_position, tool_tilt_deg, trapezoid_times
from ..workflow.ports import TaskFault

ARMS = ('arm1', 'arm2')
_GOAL_JOINT_TOLERANCE = 1e-5
_B_OBJECT = 'cap_in_b'


def _duration(seconds):
    whole = int(seconds)
    return Duration(sec=whole, nanosec=int((seconds - whole) * 1e9))


class MotionGateway:
    def __init__(self, node, config, urdf_text, homes, guard, callback_group=None):
        if config['target_frame'] != 'world':
            raise ValueError('MotionGateway targets must be in the world frame')
        self._node, self._guard = node, guard
        self._cfg, self._heights, self._zones = config['motion'], config['heights'], config['zones']
        self._speeds, self._arms = config['speeds'], config['arms']
        self._homes = homes
        self._models = {arm: CadKinematics(urdf_text, arm) for arm in ARMS}
        self._lock = threading.Lock()
        self._joints, self._sequence, self._received = {}, 0, 0.0
        self._attached = dict.fromkeys(ARMS, False)
        self._b_object_present = False
        group = callback_group
        node.create_subscription(JointState, '/joint_states', self._on_joint_state, 10, callback_group=group)
        self._move_group = ActionClient(node, MoveGroup, '/move_action', callback_group=group)
        self._execute = ActionClient(node, ExecuteTrajectory, '/execute_trajectory', callback_group=group)
        self._scene = node.create_client(ApplyPlanningScene, '/apply_planning_scene', callback_group=group)
        self._validity = node.create_client(GetStateValidity, '/check_state_validity', callback_group=group)
        self._scene_query = node.create_client(GetPlanningScene, '/get_planning_scene', callback_group=group)

    # --- feedback ---

    def _on_joint_state(self, message):
        with self._lock:
            self._joints.update(zip(message.name, message.position))
            self._sequence += 1
            self._received = time.monotonic()

    def _sample(self, arm):
        names = self._models[arm].names
        with self._lock:
            if any(name not in self._joints for name in names):
                return None, self._sequence, float('inf')
            return [self._joints[name] for name in names], self._sequence, time.monotonic() - self._received

    def current(self, arm):
        deadline = time.monotonic() + self._cfg['goal_submit_s']
        while True:
            q, _, age = self._sample(arm)
            if q is not None and age <= self._cfg['joint_state_max_age_s']:
                return q
            if time.monotonic() >= deadline:
                raise TaskFault(f'No fresh joint state for {arm}')
            self._guard()
            time.sleep(0.01)

    def _confirm_arrival(self, arm, target, label):
        """Require consecutive new measurements within the TCP limit, not just an accepted goal."""
        model, needed = self._models[arm], self._cfg['arrival_samples']
        limit, stable, seen = self._cfg['tcp_error_limit_m'], 0, -1
        error = float('inf')
        deadline = time.monotonic() + self._cfg['arrival_timeout_s']
        while time.monotonic() < deadline:
            self._guard()
            q, sequence, _ = self._sample(arm)
            if q is not None and sequence != seen:
                seen = sequence
                error = tcp_error(model, q, target)
                stable = stable + 1 if error <= limit else 0
                if stable >= needed:
                    return
            time.sleep(0.005)
        raise TaskFault(f'{label}: {arm} did not settle within {limit} m, last error {error:.5f} m')

    def tcp_report(self, arm):
        q = self.current(arm)
        model = self._models[arm]
        return {'tcp_m': tcp_position(model, q).tolist(), 'tool_tilt_deg': tool_tilt_deg(model, q)}

    def home_tcp(self, arm):
        return tcp_position(self._models[arm], self._homes[arm]).tolist()

    def at_home(self, arm):
        q = self.current(arm)
        return tcp_error(self._models[arm], q, self.home_tcp(arm)) <= self._cfg['tcp_error_limit_m']

    def home_state(self, arm):
        """at_home for status reports: never waits, and None when the joint state is missing or old."""
        q, _, age = self._sample(arm)
        if q is None or age > self._cfg['joint_state_max_age_s']:
            return None
        return bool(tcp_error(self._models[arm], q, self.home_tcp(arm)) <= self._cfg['tcp_error_limit_m'])

    # --- ROS call helpers ---

    def _wait(self, future, timeout, label):
        deadline = time.monotonic() + timeout
        while not future.done():
            self._guard()
            if time.monotonic() >= deadline:
                raise TaskFault(f'{label} timed out')
            time.sleep(0.005)
        return future.result()

    def _call(self, client, request, label):
        if not client.wait_for_service(timeout_sec=self._cfg['goal_submit_s']):
            raise TaskFault(f'{label} service is unavailable')
        return self._wait(client.call_async(request), self._cfg['goal_submit_s'], label)

    def _cancel(self, handle, label):
        cancelled = handle.cancel_goal_async()
        deadline = time.monotonic() + self._cfg['goal_submit_s']
        while not cancelled.done():
            if time.monotonic() >= deadline:
                self._node.get_logger().error(f'{label}: cancel was not acknowledged')
                return
            time.sleep(0.005)

    def _run_action(self, client, goal, label):
        if not client.wait_for_server(timeout_sec=self._cfg['goal_submit_s']):
            raise TaskFault(f'{label} action server is unavailable')
        sent = client.send_goal_async(goal)
        try:
            handle = self._wait(sent, self._cfg['goal_submit_s'], f'{label} submission')
        except BaseException:
            # A goal accepted after this point must not keep running untracked.
            sent.add_done_callback(lambda done: done.result() and done.result().cancel_goal_async())
            raise
        if handle is None or not handle.accepted:
            raise TaskFault(f'{label} was rejected')
        try:
            outcome = self._wait(handle.get_result_async(), self._cfg['motion_s'], label)
        except BaseException:
            self._cancel(handle, label)
            raise
        code = outcome.result.error_code.val
        if outcome.status != GoalStatus.STATUS_SUCCEEDED or code != MoveItErrorCodes.SUCCESS:
            raise TaskFault(f'{label} failed: status {outcome.status}, MoveIt code {code}')

    # --- validity ---

    def _require_valid(self, arm, q, label):
        request = GetStateValidity.Request()
        request.group_name = self._arms[arm]['planning_group']
        request.robot_state = RobotState(is_diff=True, joint_state=JointState(
            name=list(self._models[arm].names), position=[float(value) for value in q]))
        response = self._call(self._validity, request, 'State validity')
        if not response.valid:
            pairs = sorted({f'{c.contact_body_1}/{c.contact_body_2}' for c in response.contacts})
            raise TaskFault(f'{label}: state is invalid {pairs}')

    def _solve(self, arm, xyz, seed):
        try:
            return self._models[arm].solve(xyz, seed)
        except ValueError as error:
            raise TaskFault(f'{arm} cannot reach {tuple(xyz)}: {error}') from error

    def check_reachable(self, arm, xyz):
        q = self._solve(arm, xyz, self.current(arm))
        self._require_valid(arm, q, f'{arm} target {tuple(xyz)}')

    # --- motion ---

    def _plan_and_move(self, arm, q, label):
        goal = MoveGroup.Goal()
        request = goal.request
        request.group_name = self._arms[arm]['planning_group']
        request.start_state.is_diff = True
        request.allowed_planning_time = float(self._cfg['planning_s'])
        request.num_planning_attempts = self._cfg['planning_attempts']
        request.max_velocity_scaling_factor = float(self._speeds['transport_scale'])
        request.max_acceleration_scaling_factor = float(self._speeds['acceleration_scale'])
        request.goal_constraints = [Constraints(joint_constraints=[
            JointConstraint(joint_name=name, position=float(value), tolerance_above=_GOAL_JOINT_TOLERANCE,
                            tolerance_below=_GOAL_JOINT_TOLERANCE, weight=1.0)
            for name, value in zip(self._models[arm].names, q)])]
        goal.planning_options.plan_only = False
        self._run_action(self._move_group, goal, label)

    def move_home(self, arm):
        label = f'{arm} home'
        self._plan_and_move(arm, self._homes[arm], label)
        self._confirm_arrival(arm, self.home_tcp(arm), label)

    def move_to(self, arm, xyz, contact=False):
        label = f'{arm} to {tuple(xyz)}'
        if contact:
            self._move_straight(arm, xyz, label)
        else:
            q = self._solve(arm, xyz, self.current(arm))
            self._require_valid(arm, q, label)
            self._plan_and_move(arm, q, label)
        self._confirm_arrival(arm, xyz, label)

    def _move_straight(self, arm, xyz, label):
        """Contact moves stay on a sampled vertical line so the tool remains downward."""
        model, start = self._models[arm], self.current(arm)
        points = line_points(tcp_position(model, start), xyz, self._cfg['waypoint_step_m'])
        try:
            path = solve_line(model, start, points, self._cfg['waypoint_joint_jump_rad'])
        except ValueError as error:
            raise TaskFault(f'{label}: {error}') from error
        for q in path[1:]:
            self._require_valid(arm, q, label)
        times = trapezoid_times(path, self._cfg['max_velocity_rad_s'] * self._speeds['contact_scale'],
                                self._cfg['max_acceleration_rad_s2'] * self._speeds['acceleration_scale'])
        if not times:
            return
        trajectory = JointTrajectory(joint_names=list(model.names), points=[
            JointTrajectoryPoint(positions=[float(value) for value in q], time_from_start=_duration(stamp))
            for q, stamp in zip(path, times)])
        goal = ExecuteTrajectory.Goal(trajectory=RobotTrajectory(joint_trajectory=trajectory),
                                      controller_names=[self._arms[arm]['controller']])
        self._run_action(self._execute, goal, label)

    # --- planning scene ---

    def _apply(self, scene, label):
        response = self._call(self._scene, ApplyPlanningScene.Request(scene=scene), label)
        if not response.success:
            raise TaskFault(f'{label}: MoveIt refused the planning scene update')

    def _cylinder(self, object_id, frame, x, y, z):
        obj = CollisionObject(id=object_id, operation=CollisionObject.ADD)
        obj.header.frame_id = frame
        obj.primitives = [SolidPrimitive(type=SolidPrimitive.CYLINDER, dimensions=[
            float(self._heights['cap_height_m']), float(self._heights['cap_radius_m'])])]
        pose = Pose()
        pose.position.x, pose.position.y, pose.position.z = float(x), float(y), float(z)
        pose.orientation.w = 1.0
        obj.primitive_poses = [pose]
        return obj

    def _world_cap(self, object_id, xy):
        z = self._heights['surface_z_m'] + self._heights['cap_height_m'] / 2.0
        return self._cylinder(object_id, 'world', xy[0], xy[1], z)

    def attach(self, arm):
        tcp = self._arms[arm]['tcp_link']
        # The TCP +Z axis points out of the cup, towards the held object.
        obj = self._cylinder(f'{arm}_carried_cap', tcp, 0.0, 0.0, self._heights['cap_height_m'] / 2.0)
        scene = PlanningScene(is_diff=True)
        scene.robot_state.is_diff = True
        scene.robot_state.attached_collision_objects = [AttachedCollisionObject(
            link_name=tcp, object=obj, touch_links=[tcp, f'{arm}_cad_link_4'])]
        self._apply(scene, f'{arm} attach')
        self._attached[arm] = True

    def detach(self, arm):
        if not self._attached[arm]:
            return
        object_id, tcp = f'{arm}_carried_cap', self._arms[arm]['tcp_link']
        scene = PlanningScene(is_diff=True)
        scene.robot_state.is_diff = True
        scene.robot_state.attached_collision_objects = [AttachedCollisionObject(
            link_name=tcp, object=CollisionObject(id=object_id, operation=CollisionObject.REMOVE))]
        self._apply(scene, f'{arm} detach')
        # MoveIt moves a detached object into the world; the task records it there itself.
        world = PlanningScene(is_diff=True)
        world.world.collision_objects = [CollisionObject(id=object_id, operation=CollisionObject.REMOVE)]
        self._apply(world, f'{arm} detach cleanup')
        self._attached[arm] = False

    def scene_reset(self):
        """Clear objects by asking MoveIt, since a restarted process has no record of them."""
        components = PlanningSceneComponents(components=PlanningSceneComponents.WORLD_OBJECT_NAMES
                                             | PlanningSceneComponents.ROBOT_STATE_ATTACHED_OBJECTS)
        scene = self._call(self._scene_query, GetPlanningScene.Request(components=components), 'Scene query').scene
        attached = [(item.link_name, item.object.id) for item in scene.robot_state.attached_collision_objects]
        if attached:
            detach = PlanningScene(is_diff=True)
            detach.robot_state.is_diff = True
            detach.robot_state.attached_collision_objects = [AttachedCollisionObject(
                link_name=link, object=CollisionObject(id=object_id, operation=CollisionObject.REMOVE))
                for link, object_id in attached]
            self._apply(detach, 'scene reset detach')
        # MoveIt moves detached objects into the world, so list the world objects afterwards.
        names = {item.id for item in scene.world.collision_objects} | {object_id for _, object_id in attached}
        if names:
            self._apply_world([CollisionObject(id=name, operation=CollisionObject.REMOVE) for name in sorted(names)],
                              'scene reset')
        self._attached = dict.fromkeys(ARMS, False)
        self._b_object_present = False

    def _apply_world(self, objects, label):
        scene = PlanningScene(is_diff=True)
        scene.world.collision_objects = objects
        self._apply(scene, label)

    def scene_add_b_object(self):
        self._apply_world([self._world_cap(_B_OBJECT, self._zones['b_place_xy_m'])], 'add B object')
        self._b_object_present = True

    def scene_remove_b_object(self):
        # An object found in B by vision was never added here, so there is nothing to remove.
        if not self._b_object_present:
            return
        self._apply_world([CollisionObject(id=_B_OBJECT, operation=CollisionObject.REMOVE)], 'remove B object')
        self._b_object_present = False

    def scene_add_slot_object(self, slot):
        self._apply_world([self._world_cap(f'cap_in_slot_{slot}', self._zones['c_slots_xy_m'][slot - 1])],
                          f'add slot {slot} object')
