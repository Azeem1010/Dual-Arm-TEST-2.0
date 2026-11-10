"""Fit a j1 rotation axis from ruler-marked points; opens no port and writes no calibration.

A pointer fixed to the rotating base is turned by hand, torque off, to several j1
angles. At each angle the tester marks the pointer tip on paper and measures it on
the table reference lines (F toward the user, L along the arm-side edge toward
B/C, see docs/HARDWARE_TEST_GUIDE.md section 3.1), optionally with the j1 READ.

The points lie on a circle about the axis. The fit reports the axis position and
its standard error from the point scatter. With READ values it also reports the
j1 direction and the raw count at which the pointer faces +F (the field), using
yaw = atan2(L - L0, F - F0), positive toward +L (the arm's left). That count is the
arm facing the field only if the pointer was fixed along the arm's forward direction;
otherwise it is off by the pointer's mounting angle, while the direction still holds.

The output is a measurement report for a person to review. It has no acceptance
limits (those are D6) and never writes calibration.yaml.

Usage: ros2 run dual_arm_coordinator fit_axis_circle SHEET.yaml [REPORT.json]
"""
import json
import math
from pathlib import Path
import sys

import numpy as np
import yaml

COUNTS_PER_RADIAN = 1023.0 / math.radians(300.0)
MIN_POINTS = 3


class SheetError(ValueError):
    """The point sheet is incomplete or cannot define a circle."""


def _finite(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise SheetError(f'{name} must be a measured finite number')
    return float(value)


def fit_circle(points):
    """Least-squares circle through (f, l) points: returns centre, radius, residuals, covariance or None."""
    xy = np.asarray(points, dtype=float)
    if xy.ndim != 2 or xy.shape[1] != 2 or len(xy) < MIN_POINTS:
        raise SheetError(f'at least {MIN_POINTS} points are required')
    scale = float(np.ptp(xy, axis=0).max())
    if scale <= 0.0:
        raise SheetError('points are all identical')
    # Algebraic start (Kasa), then Gauss-Newton on the geometric distance.
    design = np.column_stack([xy, np.ones(len(xy))])
    solution, *_ = np.linalg.lstsq(design, (xy ** 2).sum(axis=1), rcond=None)
    centre = solution[:2] / 2.0
    radius_sq = solution[2] + centre @ centre
    if not math.isfinite(radius_sq) or radius_sq <= 0.0:
        raise SheetError('points are collinear and do not define a circle')
    params = np.array([centre[0], centre[1], math.sqrt(radius_sq)])
    for _ in range(50):
        delta = xy - params[:2]
        distance = np.hypot(delta[:, 0], delta[:, 1])
        if np.any(distance == 0.0):
            raise SheetError('a point coincides with the fitted centre')
        jacobian = np.column_stack([-delta[:, 0] / distance, -delta[:, 1] / distance, -np.ones(len(xy))])
        step, *_ = np.linalg.lstsq(jacobian, -(distance - params[2]), rcond=None)
        params = params + step
        if np.abs(step).max() < 1e-12 * max(scale, 1.0):
            break
    delta = xy - params[:2]
    distance = np.hypot(delta[:, 0], delta[:, 1])
    residuals = distance - params[2]
    jacobian = np.column_stack([-delta[:, 0] / distance, -delta[:, 1] / distance, -np.ones(len(xy))])
    normal = jacobian.T @ jacobian
    if np.linalg.cond(normal) > 1e12 or params[2] > 1e3 * scale:
        raise SheetError('points are nearly collinear; spread them over a wider j1 range')
    covariance = None
    if len(xy) > 3:
        # Residual variance with three fitted parameters.
        covariance = np.linalg.inv(normal) * float(residuals @ residuals) / (len(xy) - 3)
    return params[:2], float(params[2]), residuals, covariance


def _wrap(angle):
    return (angle + math.pi) % (2.0 * math.pi) - math.pi


def fit_direction(yaws, raws):
    """Direction (+1/-1) and raw count at yaw 0 for the AX-12 scale; returns (direction, zero_raw, residual counts)."""
    yaws, raws = np.asarray(yaws, dtype=float), np.asarray(raws, dtype=float)
    best = None
    for direction in (1, -1):
        # direction * yaw = (raw - zero) / counts_per_radian, compared modulo a full turn.
        phase = direction * yaws - raws / COUNTS_PER_RADIAN
        offset = math.atan2(np.sin(phase).mean(), np.cos(phase).mean())
        residual = np.array([_wrap(p - offset) for p in phase]) * COUNTS_PER_RADIAN
        zero = -offset * COUNTS_PER_RADIAN
        turn = 2.0 * math.pi * COUNTS_PER_RADIAN
        zero += turn * round((raws.mean() - zero) / turn)
        worst = float(np.abs(residual).max())
        if best is None or worst < best[2]:
            best = (direction, float(zero), worst, residual)
    return best[0], best[1], best[3]


def analyse(sheet):
    points = sheet.get('points') if isinstance(sheet, dict) else None
    if not isinstance(points, list) or len(points) < MIN_POINTS:
        raise SheetError(f'points must list at least {MIN_POINTS} measured marks')
    unit = sheet.get('unit')
    if unit not in ('mm', 'm'):
        raise SheetError('unit must be mm or m')
    fl, raws = [], []
    for index, point in enumerate(points):
        if not isinstance(point, dict):
            raise SheetError(f'points[{index}] must be a mapping with f and l')
        fl.append((_finite(point.get('f'), f'points[{index}].f'), _finite(point.get('l'), f'points[{index}].l')))
        if point.get('raw') is not None:
            raws.append(_finite(point['raw'], f'points[{index}].raw'))
    if raws and len(raws) != len(points):
        raise SheetError('give raw for every point or for none')
    centre, radius, residuals, covariance = fit_circle(fl)
    yaws = [math.atan2(l - centre[1], f - centre[0]) for f, l in fl]
    unwrapped = np.unwrap(yaws)
    report = {
        'unit': unit,
        'points': len(fl),
        'axis_f': float(centre[0]), 'axis_l': float(centre[1]), 'radius': radius,
        'axis_standard_error': None if covariance is None else
        [float(math.sqrt(max(covariance[0, 0], 0.0))), float(math.sqrt(max(covariance[1, 1], 0.0)))],
        'radial_residual_rms': float(math.sqrt(np.mean(residuals ** 2))),
        'radial_residual_max': float(np.abs(residuals).max()),
        'angular_span_deg': float(math.degrees(np.ptp(unwrapped))),
        'yaw_deg': [float(math.degrees(y)) for y in yaws],
        'note': 'status PASS only means the sheet was complete and the fit ran. '
                'Measurement report only: no acceptance limits (D6), nothing is written to calibration.yaml. '
                'Three points fit exactly, so they give no error estimate; use at least five.',
    }
    if raws:
        direction, zero, raw_residual = fit_direction(yaws, raws)
        report.update({'j1_direction': direction, 'raw_facing_field': zero,
                       'raw_residual_counts': [float(r) for r in raw_residual],
                       'raw_residual_max_counts': float(np.abs(raw_residual).max())})
    return report


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) not in (1, 2):
        print('Usage: fit_axis_circle SHEET.yaml [REPORT.json]', file=sys.stderr)
        return 2
    try:
        report = analyse(yaml.safe_load(Path(argv[0]).read_text(encoding='utf-8')))
    except (OSError, yaml.YAMLError, SheetError) as error:
        print(json.dumps({'status': 'FAIL', 'error': str(error)}, indent=2))
        return 1
    report = {'status': 'PASS', **report}
    text = json.dumps(report, indent=2)
    if len(argv) == 2:
        Path(argv[1]).write_text(text + '\n', encoding='utf-8')
    print(text)
    return 0


if __name__ == '__main__':
    sys.exit(main())
