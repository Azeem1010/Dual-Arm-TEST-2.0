"""Joint numbers as shown to the operator."""
from dataclasses import dataclass
import math
from typing import Optional, Tuple

# Same constant and formula as cm530_hardware/src/calibration.cpp.
RADIANS_PER_COUNT = math.radians(300.0) / 1023.0
NEAR_LIMIT_RAD = math.radians(5.0)
# Target minus actual above this is highlighted; the arms only move one joint step at a time.
LARGE_ERROR_DEG = 2.0
# AX/HOME/POS values are AX-12A raw positions 0..1023 (v17 interface spec 1.3).
PROTOCOL_RAW_RANGE = (0, 1023)

JOINT_LABELS = ('j1 底座', 'j2 肩', 'j3 肘', 'j4 腕')
_JOINT_SUFFIXES = ('shoulder_pan', 'shoulder_lift', 'elbow_flex', 'wrist_flex')
ARMS = ('arm1', 'arm2')
JOINT_NAMES = tuple(f'{arm}_arm_{suffix}_joint' for arm in ARMS for suffix in _JOINT_SUFFIXES)
# Motor IDs per joint, v17 interface spec 1.2; also in cm530_hardware/config/calibration.yaml.
MOTOR_IDS = dict(zip(JOINT_NAMES, (17, 3, 2, 15, 12, 1, 8, 16)))
EMPTY = '—'


@dataclass(frozen=True)
class JointSample:
    name: str
    position: float
    velocity: float
    lower: Optional[float]
    upper: Optional[float]
    command: Optional[float] = None
    # AX-12A counts only as the CM-530 firmware reported them; never derived from an angle.
    raw: Optional[int] = None
    raw_target: Optional[int] = None
    raw_limits: Optional[Tuple[int, int]] = None


@dataclass(frozen=True)
class JointRow:
    motor_id: str
    degrees: str
    target_degrees: str
    error_degrees: str
    large_error: bool
    raw: str
    raw_target: str
    raw_outside: bool
    raw_target_outside: bool
    margin: str
    near_limit: bool
    detail: str


def firmware_count(value):
    """A count from the driver, or None unless it is a whole number inside the protocol range.

    raw_target is NaN until the firmware has acknowledged an AX, so NaN means no value.
    """
    if value is None or not math.isfinite(value) or value != int(value):
        return None
    count = int(value)
    return count if PROTOCOL_RAW_RANGE[0] <= count <= PROTOCOL_RAW_RANGE[1] else None


def _outside(count, limits):
    return count is not None and limits is not None and not limits[0] <= count <= limits[1]


def joint_row(sample):
    margin_text, near_limit = EMPTY, False
    if sample.lower is not None and sample.upper is not None and sample.upper > sample.lower:
        margin = min(sample.position - sample.lower, sample.upper - sample.position)
        margin_text, near_limit = f'{math.degrees(margin):.1f}', margin < NEAR_LIMIT_RAD
    if sample.command is None:
        target, error, large = EMPTY, EMPTY, False
    else:
        error_deg = math.degrees(sample.command - sample.position)
        target, error, large = f'{math.degrees(sample.command):+.1f}', f'{error_deg:+.1f}', abs(error_deg) > LARGE_ERROR_DEG
    detail = f'{sample.position:+.3f} rad，速度（估）{sample.velocity:+.2f} rad/s'
    if sample.raw_limits is not None:
        detail += f'\n校正計數範圍 {sample.raw_limits[0]}–{sample.raw_limits[1]}'
    motor_id = MOTOR_IDS.get(sample.name)
    return JointRow(
        motor_id=EMPTY if motor_id is None else str(motor_id), degrees=f'{math.degrees(sample.position):+.1f}',
        target_degrees=target, error_degrees=error, large_error=large,
        raw=EMPTY if sample.raw is None else str(sample.raw),
        raw_target=EMPTY if sample.raw_target is None else str(sample.raw_target),
        raw_outside=_outside(sample.raw, sample.raw_limits), raw_target_outside=_outside(sample.raw_target, sample.raw_limits),
        margin=margin_text, near_limit=near_limit, detail=detail)
