import math

import pytest

from dual_arm_hmi.model.joints import EMPTY, JOINT_NAMES, RADIANS_PER_COUNT, JointSample, joint_row, rad_to_raw


def sample(position, **changes):
    return JointSample(**{'name': 'j', 'position': position, 'velocity': 0.0, 'lower': -1.0, 'upper': 1.0, **changes})


def test_joint_names_match_the_controllers():
    assert len(JOINT_NAMES) == 8
    assert JOINT_NAMES[0] == 'arm1_arm_shoulder_pan_joint'
    assert JOINT_NAMES[7] == 'arm2_arm_wrist_flex_joint'


@pytest.mark.parametrize('zero,direction,radians,expected', (
    (512, 1, 0.0, 512),
    (512, 1, RADIANS_PER_COUNT * 10, 522),
    (512, -1, RADIANS_PER_COUNT * 10, 502),
))
def test_raw_conversion_matches_the_driver_formula(zero, direction, radians, expected):
    assert rad_to_raw(radians, zero, direction) == expected


def test_full_range_is_300_degrees_over_1023_counts():
    assert math.degrees(RADIANS_PER_COUNT * 1023) == pytest.approx(300.0)


def test_values_are_formatted():
    row = joint_row(sample(0.5, velocity=-0.25, command=0.51, raw=600))
    assert row.degrees == '+28.6' and row.radians == '+0.500' and row.raw == '600'
    assert row.velocity == '-0.25' and row.error == '+0.010'


def test_missing_raw_and_command_show_a_dash():
    row = joint_row(sample(0.0))
    assert row.raw == EMPTY and row.error == EMPTY


def test_position_fraction_is_clamped():
    assert joint_row(sample(0.0)).fraction == pytest.approx(0.5)
    assert joint_row(sample(5.0)).fraction == 1.0
    assert joint_row(sample(-5.0)).fraction == 0.0


def test_unknown_limits_show_no_position_or_warning():
    row = joint_row(sample(0.5, lower=None, upper=None))
    assert row.fraction is None and row.margin == EMPTY and not row.near_limit


def test_near_limit_is_within_five_degrees():
    assert joint_row(sample(1.0 - math.radians(4.9))).near_limit
    assert not joint_row(sample(1.0 - math.radians(5.1))).near_limit
    assert joint_row(sample(-1.0 + math.radians(1.0))).near_limit
