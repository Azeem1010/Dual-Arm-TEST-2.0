"""MoveIt motion and PlanningScene gateway.

The planning group uses position-only KDL, which does not hold the suction axis,
so targets are solved here with CadKinematics and sent as joint values. All
targets are in the URDF world frame; other frames are converted by the caller.
"""
import collections
import math
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

from .. import timing
from ..kinematics import CadKinematics
from ..motion_math import (joint_line, line_drift, line_points, prepare_b_poses, prepare_slot_poses, solve_line,
                           solve_line_holding_tool, tcp_error,
                           tcp_position, tool_tilt_deg, trapezoid_times)
from ..workflow.ports import TaskFault

ARMS = ('arm1', 'arm2')
_GOAL_JOINT_TOLERANCE = 1e-5
_B_OBJECT = 'cap_in_b'
# CadKinematics accepts straight-down solutions within about 0.26 deg.
_STRAIGHT_DOWN_DEG = 0.5
# AX-12A: 300 degrees over 1023 counts, as in home_pose.py and cm530_hardware.
_RAD_PER_COUNT = math.radians(300.0) / 1023.0
# An arm counts as still when the average of every joint over one settle_s window differs from
# the previous window's by at most this. Averages, because a holding AX-12 hunts: at rest the
# arm2 elbow swung 4 counts and arm 1's elbow and wrist 2 (field 2026-11-17), and a range test
# never passed. A sag still moves the average from one window to the next.
_STILL_RAD = 1.0 * _RAD_PER_COUNT
# Readings each window needs before already-received readings may prove the arm still.
_STILL_MIN_READINGS = 3
# A descent correction never aims the tool closer than this to the board surface.
_SURFACE_CLEARANCE_M = 0.001
# A trajectory starts from the joints read just before it is sent; a larger change since the
# path was computed means the arm moved on its own, so it is refused.
_FRESH_START_LIMIT_RAD = 10 * _RAD_PER_COUNT
# Joint-line sampling for taught slot moves; small enough that the drift check sees the path.
_JOINT_LINE_STEP_RAD = 0.01


def _duration(seconds):
    whole = int(seconds)
    return Duration(sec=whole, nanosec=int((seconds - whole) * 1e9))


class MotionGateway:
    def __init__(self, node, config, urdf_text, homes, guard, callback_group=None, slot_joints=None, b_joints=None):
        if config['target_frame'] != 'world':
            raise ValueError('MotionGateway targets must be in the world frame')
        self._node, self._guard = node, guard
        self._cfg, self._heights, self._zones = config['motion'], config['heights'], config['zones']
        self._speeds, self._arms = config['speeds'], config['arms']
        self._homes = homes
        self._models = {arm: CadKinematics(urdf_text, arm, self._cfg['max_tool_tilt_deg']) for arm in ARMS}
        # Taught C slots (prototype): joint targets instead of xy, see homes.load_slot_joints.
        self._teach, self._slot_arm, self._slot_poses = config.get('c_slot_teach'), None, None
        if slot_joints is not None:
            self._slot_arm = slot_joints['arm']
            self._slot_poses = prepare_slot_poses(self._models[self._slot_arm], slot_joints['release'], self._teach,
                                                  self._heights['approach_z_m'])
        # Taught B hand-over (prototype): both arms go to their taught joints, see homes.load_b_joints.
        # Prototype: re-aim a contact descent that stopped short (see _correct_descent).
        self._descent = config.get('descent_correction')
        self._b_teach, self._b_poses = config.get('b_teach'), None
        if b_joints is not None:
            self._b_poses = prepare_b_poses(self._models, b_joints, self._b_teach['contact_lift_m'],
                                            self._heights['approach_z_m'])
        self._lock = threading.Lock()
        self._joints, self._sequence, self._received = {}, 0, 0.0
        self._history = {arm: collections.deque() for arm in ARMS}
        self._attached = dict.fromkeys(ARMS, False)
        # Tool orientation when each arm attached its cap (the cap was lying flat then).
        self._held_tool = dict.fromkeys(ARMS)
        # Extra height of the last empty contact move, and of the pick that holds the cap.
        self._contact_lift, self._held_gap = dict.fromkeys(ARMS, 0.0), dict.fromkeys(ARMS, 0.0)
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
        now = time.monotonic()
        with self._lock:
            self._joints.update(zip(message.name, message.position))
            self._sequence += 1
            self._received = now
            # Kept for _wait_still: two settle_s windows plus a margin.
            keep = 2.0 * (self._cfg['settle_s'] or 0.0) + 0.5
            for arm, names in ((arm, self._models[arm].names) for arm in ARMS):
                if all(name in self._joints for name in names):
                    history = self._history[arm]
                    history.append((now, [self._joints[name] for name in names]))
                    while history and history[0][0] < now - keep:
                        history.popleft()

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

    @timing.timed('arrive')
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

    @timing.timed('still')
    def _wait_still(self, arm, label):
        """Wait until every joint of arm has stayed within _STILL_RAD for settle_s.

        A loaded AX-12 keeps sagging after the controller reports the goal reached; a move
        planned from that state is refused once the arm has drifted 0.01 rad from its start
        (field runs 2026-11-17: shoulder and wrist of arm 1 holding a cap).
        """
        window = self._cfg['settle_s']
        if not window:
            return
        if self._still_already(arm, window):
            return
        timeout = self._cfg['arrival_timeout_s']
        deadline = time.monotonic() + timeout
        previous, samples, started, seen = None, [], time.monotonic(), -1
        while time.monotonic() < deadline:
            self._guard()
            q, sequence, age = self._sample(arm)
            if q is not None and sequence != seen and age <= self._cfg['joint_state_max_age_s']:
                seen = sequence
                samples.append(q)
            now = time.monotonic()
            if now - started >= window:
                if samples:
                    mean = [sum(column) / len(samples) for column in zip(*samples)]
                    if previous is not None and max(abs(a - b) for a, b in zip(mean, previous)) <= _STILL_RAD:
                        return
                    previous = mean
                samples, started = [], now
            time.sleep(0.005)
        raise TaskFault(f'{label}: {arm} did not stop moving within {timeout} s')

    def _still_already(self, arm, window):
        """The same test as _wait_still on the readings of the last two windows, already received.

        Before a move the arm has often stood for seconds (vacuum, camera, validity checks); then
        the two windows that ended now show it still and the move need not wait for two more
        (speed-up 2026-11-17). Too few or old readings: wait as before.
        """
        now = time.monotonic()
        with self._lock:
            history = list(getattr(self, '_history', {}).get(arm, ()))
        if not history or now - history[-1][0] > self._cfg['joint_state_max_age_s']:
            return False
        older = [q for stamp, q in history if now - 2.0 * window <= stamp < now - window]
        recent = [q for stamp, q in history if now - window <= stamp <= now]
        if len(older) < _STILL_MIN_READINGS or len(recent) < _STILL_MIN_READINGS:
            return False
        means = [[sum(column) / len(samples) for column in zip(*samples)] for samples in (older, recent)]
        return max(abs(a - b) for a, b in zip(*means)) <= _STILL_RAD

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

    @timing.timed('move')
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
        # MoveGroup reports how long it planned; move it from 'move' to 'plan'.
        planning = getattr(outcome.result, 'planning_time', None)
        if isinstance(planning, float) and planning > 0.0:
            timing.add('plan', planning)
            timing.add('move', -planning)

    # --- validity ---

    def _validity_request(self, arm, q):
        request = GetStateValidity.Request()
        request.group_name = self._arms[arm]['planning_group']
        request.robot_state = RobotState(is_diff=True, joint_state=JointState(
            name=list(self._models[arm].names), position=[float(value) for value in q]))
        return request

    @staticmethod
    def _raise_invalid(response, label):
        if not response.valid:
            pairs = sorted({f'{c.contact_body_1}/{c.contact_body_2}' for c in response.contacts})
            raise TaskFault(f'{label}: state is invalid {pairs}')

    @timing.timed('check')
    def _require_valid(self, arm, q, label):
        self._raise_invalid(self._call(self._validity, self._validity_request(arm, q), 'State validity'), label)

    @timing.timed('check')
    def _require_valid_all(self, arm, path, label):
        """Check every joint state of path; all requests are sent before the first answer is awaited.

        One call at a time took about a second for a contact line (2026-11-17); the checks
        themselves are unchanged, and the first invalid state in path order faults.
        """
        if not path:
            return
        if not self._validity.wait_for_service(timeout_sec=self._cfg['goal_submit_s']):
            raise TaskFault('State validity service is unavailable')
        futures = [self._validity.call_async(self._validity_request(arm, q)) for q in path]
        for future in futures:
            self._raise_invalid(self._wait(future, self._cfg['goal_submit_s'], 'State validity'), label)

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
        self._wait_still(arm, label)
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
            xyz = self._contact_target(arm, xyz)
            descending = xyz[2] < self._tcp(arm)[2]
            commanded = self._move_straight(arm, xyz, label)
            self._confirm_arrival(arm, xyz, label)
            if descending and self._descent:
                commanded = self._correct_descent(arm, xyz, label) or commanded
            self._report_arrival(arm, xyz, commanded, label)
        else:
            q = self._solve(arm, xyz, self.current(arm))
            self._require_valid(arm, q, label)
            self._plan_and_move(arm, q, label)
            self._confirm_arrival(arm, xyz, label)

    def lift_vertical(self, arm, z):
        """Straight up from where the tool is now to height z; xy is held, not corrected."""
        label = f'{arm} vertical lift to z {z:.4f}'
        self._wait_still(arm, label)
        start = self.current(arm)
        x, y, now_z = (float(value) for value in tcp_position(self._models[arm], start))
        if z <= now_z:
            raise TaskFault(f'{label}: the tool is already at z {now_z:.4f}')
        xyz = (x, y, float(z))
        points = line_points((x, y, now_z), xyz, self._cfg['waypoint_step_m'])
        try:
            # Keep the cup's orientation: the taught B pose is tilted, and a downward solve
            # would flip the wrist at the first step.
            path = solve_line_holding_tool(self._models[arm], start, points, self._cfg['waypoint_joint_jump_rad'])
        except ValueError as error:
            raise TaskFault(f'{label}: {error}') from error
        commanded = self._execute_path(arm, path, label)
        self._confirm_arrival(arm, xyz, label)
        self._report_arrival(arm, xyz, commanded, label)

    def _tcp(self, arm):
        return [float(value) for value in tcp_position(self._models[arm], self.current(arm))]

    def _correct_descent(self, arm, xyz, label):
        """Descend again while the measured tool stays above the target (prototype).

        A warm or loaded AX-12 stops short of its goal, and the 1 cm arrival check lets a cup
        that never reached the cap pass (field runs 2026-11-17). The joint readings show the
        shortfall, so the line is re-aimed lower by it, at most max_extra_m below the target.
        A shortfall the readings cannot see (calibration error) is not corrected.
        Returns the last commanded joints, or None when no correction was needed.
        """
        cfg, logger = self._descent, self._node.get_logger()
        extra, commanded = 0.0, None
        for attempt in range(cfg['attempts'] + 1):
            self._wait_still(arm, label)
            short = self._tcp(arm)[2] - xyz[2]
            if short <= cfg['tolerance_m']:
                return commanded
            # Never aim into the board: with a deep zone A press, the cap itself may hold the cup up.
            floor_extra = xyz[2] - (self._heights['surface_z_m'] + _SURFACE_CLEARANCE_M)
            limit = min(cfg['max_extra_m'], max(0.0, floor_extra))
            if attempt == cfg['attempts'] or extra >= limit:
                raise TaskFault(f'{label}: {arm} stopped {short * 1000:.1f} mm above the target '
                                f'after {extra * 1000:.1f} mm of extra descent')
            extra = min(limit, extra + short)
            aim = (xyz[0], xyz[1], xyz[2] - extra)
            logger.warning(f'{label}: {arm} stopped {short * 1000:.1f} mm above the target; '
                           f'descending again to {extra * 1000:.1f} mm below it')
            commanded = self._move_straight(arm, aim, f'{label} correction')
        return commanded

    def _fresh_start(self, arm, path, label):
        """Replace the first point by the joints read now.

        Checking every waypoint takes about a second, and a loaded joint can creep by more than
        the controller's 0.01 rad start tolerance meanwhile (field run 2026-11-17: arm 1 elbow
        lifting a cap in A), which aborts the trajectory.
        """
        now = self.current(arm)
        moved = max(abs(a - b) for a, b in zip(now, path[0]))
        if moved > _FRESH_START_LIMIT_RAD:
            raise TaskFault(f'{label}: {arm} moved {moved / _RAD_PER_COUNT:.1f} counts while its path was checked')
        return [list(now)] + [list(q) for q in path[1:]]

    def _report_arrival(self, arm, xyz, commanded, label):
        """Log where a contact move ended: target and measured TCP, and each joint's error."""
        q = self.current(arm)
        tcp = [float(value) for value in tcp_position(self._models[arm], q)]
        joints = ('n/a' if commanded is None else
                  '[' + ', '.join(f'{(a - b) / _RAD_PER_COUNT:+.1f}' for a, b in zip(q, commanded)) + ']')
        self._node.get_logger().info(
            f'{label}: arrived z {tcp[2] * 1000:.1f} mm for target {xyz[2] * 1000:.1f} mm '
            f'(dz {(tcp[2] - xyz[2]) * 1000:+.1f}), xy error '
            f'{math.hypot(tcp[0] - xyz[0], tcp[1] - xyz[1]) * 1000:.1f} mm, joint error counts {joints}')

    def _contact_target(self, arm, xyz):
        """Raise a tilted contact target so the lowest rim just meets what is below.

        Empty, the rim is the cup's: a cup tilted by t is cup_radius * sin(t) lower
        at its rim than at its centre. Holding, it is the cap's: the cap was flat when
        attached, so it tilts by however much the tool has turned since, and its rim
        drops cap_radius * sin(that). Otherwise the rim stops on the cap or the board
        before the centre arrives (Gazebo, slot 8 and cap 8, 2026-11-12). A cap picked
        from a raised cup also hangs that much further from the cup, so the pick lift
        is added again when it is put down. Straight-down moves with a flat cap that
        was picked straight down are unchanged.
        """
        x, y, z = (float(value) for value in xyz)
        held = self._held_tool[arm] is not None
        gap = self._held_gap[arm] if held else 0.0
        lift = gap
        for _ in range(3):  # the tilt changes slightly with height; three passes settle it
            tilt, radius = self._rim_tilt(arm, self._solve(arm, (x, y, z + lift), self.current(arm)))
            lift = gap + (radius * math.sin(math.radians(tilt)) if tilt > _STRAIGHT_DOWN_DEG else 0.0)
        if not held:
            self._contact_lift[arm] = lift
        return (x, y, z + lift)

    def _rim_tilt(self, arm, q):
        """Tilt in degrees of the lowest part (cup or held cap) at q, and its radius."""
        model, held = self._models[arm], self._held_tool[arm]
        if held is None:
            return tool_tilt_deg(model, q), self._heights['cup_radius_m']
        cap_axis = model.forward(q)[:3, :3] @ held.T @ [0.0, 0.0, 1.0]
        tilt = math.degrees(math.acos(max(-1.0, min(1.0, float(cap_axis[2])))))
        return tilt, self._heights['cap_radius_m']

    def _move_straight(self, arm, xyz, label):
        """Contact moves stay on a sampled vertical line; the tool stays downward, or within
        max_tool_tilt_deg where straight down has no solution."""
        self._wait_still(arm, label)
        model, start = self._models[arm], self.current(arm)
        points = line_points(tcp_position(model, start), xyz, self._cfg['waypoint_step_m'])
        try:
            path = solve_line(model, start, points, self._cfg['waypoint_joint_jump_rad'])
        except ValueError as error:
            raise TaskFault(f'{label}: {error}') from error
        return self._execute_path(arm, path, label)

    def _execute_path(self, arm, path, label):
        """Check every waypoint, start from the joints read now, and run the path at contact speed."""
        model = self._models[arm]
        self._require_valid_all(arm, path[1:], label)
        path = self._fresh_start(arm, path, label)
        times = trapezoid_times(path, self._cfg['max_velocity_rad_s'] * self._speeds['contact_scale'],
                                self._cfg['max_acceleration_rad_s2'] * self._speeds['acceleration_scale'])
        if not times:
            return path[-1]
        trajectory = JointTrajectory(joint_names=list(model.names), points=[
            JointTrajectoryPoint(positions=[float(value) for value in q], time_from_start=_duration(stamp))
            for q, stamp in zip(path, times)])
        goal = ExecuteTrajectory.Goal(trajectory=RobotTrajectory(joint_trajectory=trajectory),
                                      controller_names=[self._arms[arm]['controller']])
        self._run_action(self._execute, goal, label)
        return path[-1]

    # --- taught C slots (prototype) ---

    def _slot(self, arm, slot):
        if self._slot_poses is None:
            raise TaskFault('No taught slot joints are configured')
        if arm != self._slot_arm:
            raise TaskFault(f'Slots were taught with {self._slot_arm}, not {arm}')
        if not 1 <= slot <= len(self._slot_poses):
            raise TaskFault(f'Slot {slot} is out of range')
        return self._slot_poses[slot - 1]

    def slot_xy(self, slot):
        """Where a cap in this slot sits: the taught pose when slots are taught, else the configured xy."""
        if self._slot_poses is not None:
            return self._slot_poses[slot - 1]['xy']
        return tuple(self._zones['c_slots_xy_m'][slot - 1])

    def check_slot(self, arm, slot):
        poses = self._slot(arm, slot)
        for name in ('above', 'release'):
            self._require_valid(arm, poses[name], f'{arm} slot {slot} {name}')

    def move_slot(self, arm, slot, pose, contact=False):
        """pose 'above' or 'release'. A contact move is a joint-space line from the current
        joints, refused when the tool would leave the straight TCP segment by more than
        max_line_drift_m; otherwise MoveIt plans to the joints."""
        self._move_taught(arm, self._slot(arm, slot)[pose], f'{arm} slot {slot} {pose}', contact, self._teach)

    # --- taught B hand-over (prototype) ---

    def _b(self, arm):
        if self._b_poses is None:
            raise TaskFault('No taught B joints are configured')
        return self._b_poses[arm]

    def b_xy(self):
        """Where arm 1 puts the object down in B: its taught pose when B is taught, else the configured xy."""
        if self._b_poses is not None:
            return self._b_poses['arm1']['xy']
        return tuple(self._zones['b_place_xy_m'])

    def b_grasp_xy(self, arm):
        """Where arm's tool meets the object at its taught contact pose (model world xy)."""
        return tuple(float(value) for value in self._b(arm)['xy'])

    def check_b(self, arm):
        poses = self._b(arm)
        for name in ('above', 'release'):
            self._require_valid(arm, poses[name], f'{arm} B {name}')

    def move_b(self, arm, pose, contact=False):
        """pose 'above' or 'contact' (the taught pose: arm 1 releases, arm 2 grasps there); moves as move_slot."""
        if pose not in ('above', 'contact'):
            raise TaskFault(f'Unknown B pose {pose}')
        target = self._b(arm)['release' if pose == 'contact' else 'above']
        self._move_taught(arm, target, f'{arm} B {pose}', contact, self._b_teach)
        if contact:
            # Taught poses carry no extra lift, so a later held move starts from the cap top.
            self._contact_lift[arm] = 0.0

    def _move_taught(self, arm, target, label, contact, teach):
        if contact:
            self._move_joint_line(arm, target, label, teach['max_line_drift_m'])
        else:
            self._require_valid(arm, target, label)
            self._plan_and_move(arm, target, label)
        self._confirm_joints(arm, target, label, teach['arrival_tolerance_raw'])
        if contact:
            xyz = tcp_position(self._models[arm], target)
            self._report_arrival(arm, [float(value) for value in xyz], target, label)

    def _move_joint_line(self, arm, target, label, limit):
        self._wait_still(arm, label)
        model = self._models[arm]
        path = joint_line(self.current(arm), target, _JOINT_LINE_STEP_RAD)
        drift = line_drift(model, path)
        if drift > limit:
            raise TaskFault(f'{label}: the joint line leaves the straight path by {drift:.4f} m (limit {limit} m)')
        self._require_valid_all(arm, path[1:], label)
        path = self._fresh_start(arm, path, label)
        times = trapezoid_times(path, self._cfg['max_velocity_rad_s'] * self._speeds['contact_scale'],
                                self._cfg['max_acceleration_rad_s2'] * self._speeds['acceleration_scale'])
        if not times:
            return path[-1]
        trajectory = JointTrajectory(joint_names=list(model.names), points=[
            JointTrajectoryPoint(positions=[float(value) for value in q], time_from_start=_duration(stamp))
            for q, stamp in zip(path, times)])
        goal = ExecuteTrajectory.Goal(trajectory=RobotTrajectory(joint_trajectory=trajectory),
                                      controller_names=[self._arms[arm]['controller']])
        self._run_action(self._execute, goal, label)
        return path[-1]

    def _confirm_joints(self, arm, target, label, tolerance_raw):
        """Like _confirm_arrival, but every joint within tolerance_raw counts of the taught pose."""
        needed = self._cfg['arrival_samples']
        limit = tolerance_raw * _RAD_PER_COUNT
        stable, seen, error = 0, -1, float('inf')
        deadline = time.monotonic() + self._cfg['arrival_timeout_s']
        while time.monotonic() < deadline:
            self._guard()
            q, sequence, _ = self._sample(arm)
            if q is not None and sequence != seen:
                seen = sequence
                error = max(abs(a - b) for a, b in zip(q, target))
                stable = stable + 1 if error <= limit else 0
                if stable >= needed:
                    return
            time.sleep(0.005)
        raise TaskFault(f'{label}: {arm} did not settle within {tolerance_raw} counts, '
                        f'last error {error / _RAD_PER_COUNT:.1f} counts')

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
        self._held_tool[arm] = self._models[arm].forward(self.current(arm))[:3, :3]
        self._held_gap[arm] = self._contact_lift[arm]

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
        self._held_tool[arm] = None
        self._held_gap[arm] = 0.0

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
        self._held_tool = dict.fromkeys(ARMS)
        self._contact_lift, self._held_gap = dict.fromkeys(ARMS, 0.0), dict.fromkeys(ARMS, 0.0)
        self._b_object_present = False

    def _apply_world(self, objects, label):
        scene = PlanningScene(is_diff=True)
        scene.world.collision_objects = objects
        self._apply(scene, label)

    def scene_add_b_object(self):
        self._apply_world([self._world_cap(_B_OBJECT, self.b_xy())], 'add B object')
        self._b_object_present = True

    def scene_remove_b_object(self):
        # An object found in B by vision was never added here, so there is nothing to remove.
        if not self._b_object_present:
            return
        self._apply_world([CollisionObject(id=_B_OBJECT, operation=CollisionObject.REMOVE)], 'remove B object')
        self._b_object_present = False

    def scene_add_slot_object(self, slot):
        self._apply_world([self._world_cap(f'cap_in_slot_{slot}', self.slot_xy(slot))], f'add slot {slot} object')
