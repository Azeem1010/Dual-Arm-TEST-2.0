"""Joint numbers as shown to the operator."""
from dataclasses import dataclass
import math
from typing import Optional

# Same constant and formula as cm530_hardware/src/calibration.cpp.
RADIANS_PER_COUNT = math.radians(300.0) / 1023.0
NEAR_LIMIT_RAD = math.radians(5.0)

JOINT_LABELS = ('j1 底座', 'j2 肩', 'j3 肘', 'j4 腕')
_JOINT_SUFFIXES = ('shoulder_pan', 'shoulder_lift', 'elbow_flex', 'wrist_flex')
ARMS = ('arm1', 'arm2')
JOINT_NAMES = tuple(f'{arm}_arm_{suffix}_joint' for arm in ARMS for suffix in _JOINT_SUFFIXES)
EMPTY = '—'


@dataclass(frozen=True)
class JointSample:
    name: str
    position: float
    velocity: float
    lower: Optional[float]
    upper: Optional[float]
    command: Optional[float] = None
    raw: Optional[int] = None


@dataclass(frozen=True)
class JointRow:
    degrees: str
    radians: str
    raw: str
    velocity: str
    error: str
    fraction: Optional[float]
    margin: str
    near_limit: bool


def rad_to_raw(radians, zero_raw, direction):
    """Motor counts for a joint angle, matching Calibration::rad_to_raw without its range check."""
    return round(zero_raw + direction * radians / RADIANS_PER_COUNT)


def joint_row(sample):
    fraction, margin_text, near_limit = None, EMPTY, False
    if sample.lower is not None and sample.upper is not None and sample.upper > sample.lower:
        fraction = min(1.0, max(0.0, (sample.position - sample.lower) / (sample.upper - sample.lower)))
        margin = min(sample.position - sample.lower, sample.upper - sample.position)
        margin_text, near_limit = f'{math.degrees(margin):.1f}', margin < NEAR_LIMIT_RAD
    error = EMPTY if sample.command is None else f'{sample.command - sample.position:+.3f}'
    return JointRow(degrees=f'{math.degrees(sample.position):+.1f}', radians=f'{sample.position:+.3f}',
                    raw=EMPTY if sample.raw is None else str(sample.raw), velocity=f'{sample.velocity:+.2f}',
                    error=error, fraction=fraction, margin=margin_text, near_limit=near_limit)
