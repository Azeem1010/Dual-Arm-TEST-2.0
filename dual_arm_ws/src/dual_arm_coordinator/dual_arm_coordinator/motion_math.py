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
