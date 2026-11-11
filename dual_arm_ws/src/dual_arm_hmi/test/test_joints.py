import math

import pytest

from dual_arm_hmi.model.joints import EMPTY, JOINT_NAMES, MOTOR_IDS, RADIANS_PER_COUNT, JointSample, firmware_count, joint_row


def sample(position, **changes):
    return JointSample(**{'name': 'arm1_arm_shoulder_pan_joint', 'position': position, 'velocity': 0.0,
                          'lower': -1.0, 'upper': 1.0, **changes})


def test_joint_names_match_the_controllers():
    assert len(JOINT_NAMES) == 8
    assert JOINT_NAMES[0] == 'arm1_arm_shoulder_pan_joint'
    assert JOINT_NAMES[7] == 'arm2_arm_wrist_flex_joint'


def test_motor_ids_follow_the_v17_interface_spec():
    assert [MOTOR_IDS[name] for name in JOINT_NAMES] == [17, 3, 2, 15, 12, 1, 8, 16]


def test_full_range_is_300_degrees_over_1023_counts():
    assert math.degrees(RADIANS_PER_COUNT * 1023) == pytest.approx(300.0)


def test_angles_are_shown_in_degrees_with_target_and_difference():
    row = joint_row(sample(0.5, velocity=-0.25, command=0.51, raw=600, raw_target=602))
    assert row.motor_id == '17'
    assert row.degrees == '+28.6' and row.target_degrees == '+29.2' and row.error_degrees == '+0.6'
    assert row.raw == '600' and row.raw_target == '602'
    assert not row.large_error
    assert '+0.500 rad' in row.detail and '-0.25' in row.detail


def test_large_difference_is_flagged():
    assert joint_row(sample(0.0, command=math.radians(2.5))).large_error
    assert not joint_row(sample(0.0, command=math.radians(1.5))).large_error


def test_missing_counts_and_command_show_a_dash():
    row = joint_row(sample(0.0))
    assert row.raw == EMPTY and row.raw_target == EMPTY
    assert row.target_degrees == EMPTY and row.error_degrees == EMPTY
    assert not row.raw_outside and not row.raw_target_outside


@pytest.mark.parametrize('value,expected', (
    (0.0, 0), (1023.0, 1023), (512.0, 512),
    (None, None), (float('nan'), None), (float('inf'), None), (512.4, None), (-1.0, None), (1024.0, None),
))
def test_only_whole_protocol_counts_are_accepted(value, expected):
    assert firmware_count(value) == expected


def test_counts_outside_the_calibrated_range_are_flagged():
    row = joint_row(sample(0.0, raw=99, raw_target=700, raw_limits=(100, 700)))
    assert row.raw_outside and not row.raw_target_outside
    assert '100–700' in row.detail
    assert not joint_row(sample(0.0, raw=99)).raw_outside


def test_margin_to_the_nearer_limit():
    assert joint_row(sample(0.0)).margin == f'{math.degrees(1.0):.1f}'


def test_no_limits_gives_no_margin():
    row = joint_row(sample(0.5, lower=None, upper=None))
    assert row.margin == EMPTY and not row.near_limit


def test_near_limit_threshold_is_five_degrees():
    assert joint_row(sample(1.0 - math.radians(4.9))).near_limit
    assert not joint_row(sample(1.0 - math.radians(5.1))).near_limit
    assert joint_row(sample(-1.0 + math.radians(1.0))).near_limit
