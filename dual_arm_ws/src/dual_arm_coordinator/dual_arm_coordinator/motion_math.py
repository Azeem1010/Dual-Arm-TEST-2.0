"""Straight-line joint paths with a downward tool. Free of ROS for unit testing."""
import math

import numpy as np


def line_points(start, end, step):
    """Evenly spaced points after start, ending exactly at end."""
    start, end = np.asarray(start, dtype=float), np.asarray(end, dtype=float)
    if step <= 0:
        raise ValueError('step must be positive')
    distance = float(np.linalg.norm(end - start))
    if distance == 0.0:
        return []
    count = max(1, math.ceil(distance / step))
    return [start + (end - start) * index / count for index in range(1, count + 1)]


def solve_line(model, start_q, points, max_jump):
    """Solve downward IK along points; a large joint jump means a branch change."""
    path = [list(start_q)]
    for point in points:
        q = model.solve(point, path[-1])
        if max(abs(a - b) for a, b in zip(q, path[-1])) > max_jump:
            raise ValueError(f'Joint jump above {max_jump} rad at {np.round(point, 4).tolist()}')
        path.append(list(q))
    return path


def joint_line(start_q, end_q, max_step):
    """Joint-space straight line from start to end, no joint moving more than max_step per step."""
    start, end = np.asarray(start_q, dtype=float), np.asarray(end_q, dtype=float)
    if max_step <= 0:
        raise ValueError('max_step must be positive')
    count = max(1, math.ceil(float(np.max(np.abs(end - start))) / max_step))
    return [(start + (end - start) * index / count).tolist() for index in range(count + 1)]


def line_drift(model, path):
    """Largest distance of the TCP along path from the straight segment between its ends."""
    points = [tcp_position(model, q) for q in path]
    first, last = points[0], points[-1]
    span = last - first
    length = float(np.dot(span, span))
    drift = 0.0
    for point in points:
        share = 0.0 if length == 0.0 else min(1.0, max(0.0, float(np.dot(point - first, span)) / length))
        drift = max(drift, float(np.linalg.norm(point - (first + share * span))))
    return drift


# A taught slot's approach pose must clear its release pose by at least this much: the
# held cap (10 mm) plus margin over the caps in neighbouring slots.
MIN_SLOT_CLEARANCE_M = 0.02
# Where approach_z has no solution within the tilt limit, try this much lower each time.
SLOT_APPROACH_STEP_M = 0.002


def _slot_above(model, x, y, release, release_z, approach_z):
    """Joints straight above the release pose: at approach_z, or the highest height below
    it (in SLOT_APPROACH_STEP_M steps) the model reaches within its tilt limit."""
    floor = release_z + MIN_SLOT_CLEARANCE_M
    if approach_z < floor:
        raise ValueError(f'approach height {approach_z} m is less than {MIN_SLOT_CLEARANCE_M} m '
                         f'above the release height {release_z:.4f} m')
    height, error = approach_z, None
    while height >= floor - 1e-9:
        try:
            return list(model.solve((x, y, height), release)), height
        except ValueError as failure:
            error = failure
        height -= SLOT_APPROACH_STEP_M
    raise ValueError(f'no approach pose between {floor:.4f} and {approach_z} m: {error}')


def prepare_slot_poses(model, taught, teach, approach_z):
    """Release and approach joints for each taught slot.

    The release pose is the taught one (raised by teach['release_lift_m'] when
    set). The approach pose is straight above it, see _slot_above; a vertical
    move keeps the horizontal radius, so j1 stays at the taught count.
    """
    poses = []
    for slot, q in enumerate(taught, start=1):
        release = list(q)
        x, y, z = (float(value) for value in tcp_position(model, release))
        lift = teach['release_lift_m']
        try:
            if lift > 0:
                release = list(model.solve((x, y, z + lift), release))
                z += lift
            above, above_z = _slot_above(model, x, y, release, z, approach_z)
        except ValueError as error:
            raise ValueError(f'Taught slot {slot}: {error}') from error
        poses.append({'release': release, 'above': above, 'xy': (x, y), 'release_z': z, 'above_z': above_z})
    return poses


def prepare_b_poses(models, taught, contact_lift, approach_z):
    """Contact and approach joints of each arm's taught B pose, as prepare_slot_poses.

    The contact pose (stored as 'release') is where arm 1 lets go and arm 2 grasps.
    """
    poses = {}
    for arm, q in taught.items():
        try:
            poses[arm] = prepare_slot_poses(models[arm], [q], {'release_lift_m': contact_lift}, approach_z)[0]
        except ValueError as error:
            raise ValueError(str(error).replace('Taught slot 1', f'Taught B {arm}')) from error
    return poses


def trapezoid_times(path, velocity, acceleration):
    """Time stamps along a joint path; the fastest joint follows a trapezoid profile."""
    if velocity <= 0 or acceleration <= 0:
        raise ValueError('velocity and acceleration must be positive')
    steps = [max(abs(a - b) for a, b in zip(first, second)) for first, second in zip(path, path[1:])]
    total = sum(steps)
    if total == 0.0:
        return []
    ramp = velocity * velocity / (2.0 * acceleration)
    if total < 2.0 * ramp:
        ramp = total / 2.0
        velocity = math.sqrt(acceleration * total)
    ramp_time = velocity / acceleration
    cruise = total - 2.0 * ramp

    def at(distance):
        if distance <= ramp:
            return math.sqrt(2.0 * distance / acceleration)
        if distance <= ramp + cruise:
            return ramp_time + (distance - ramp) / velocity
        remaining = max(0.0, total - distance)
        return 2.0 * ramp_time + cruise / velocity - math.sqrt(2.0 * remaining / acceleration)

    times, travelled = [0.0], 0.0
    for step in steps:
        travelled += step
        # Repeated points would otherwise yield an invalid non-increasing time.
        times.append(max(at(travelled), times[-1] + 1e-3))
    return times


def tcp_position(model, q):
    return model.forward(q)[:3, 3]


def tcp_error(model, q, target):
    return float(np.linalg.norm(tcp_position(model, q) - np.asarray(target, dtype=float)))


def tool_tilt_deg(model, q):
    """Angle between the suction axis and straight down."""
    axis = model.forward(q)[:3, 2]
    return math.degrees(math.acos(float(np.clip(np.dot(axis, [0.0, 0.0, -1.0]), -1.0, 1.0))))
