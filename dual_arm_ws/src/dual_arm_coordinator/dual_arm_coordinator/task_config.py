"""Strict loader for coordinator task settings.

No value has a default. A null or non-finite entry means "not measured", so the
hardware template cannot load until every field comes from real measurements.
Joint zeros and directions stay in cm530_hardware/config/calibration.yaml.
"""
import argparse
import math
import sys
from pathlib import Path

import yaml

ARMS = ('arm1', 'arm2')
SLOT_COUNT = 8

_ARM_KEYS = ('planning_group', 'controller', 'tcp_link', 'moveit_base_frame', 'vision_base_frame')
_SHAPE = {
    'schema_version': None,
    'mode': None,
    'evidence_kind': None,
    'target_frame': None,
    'home_source': None,
    'journal_path': None,
    'arms': {arm: dict.fromkeys(_ARM_KEYS) for arm in ARMS},
    'speeds': dict.fromkeys(('transport_scale', 'contact_scale', 'acceleration_scale')),
    'heights': dict.fromkeys(('surface_z_m', 'cap_height_m', 'cap_radius_m', 'cup_radius_m', 'contact_z_m', 'release_z_m',
                              'approach_z_m', 'pick_z_tolerance_m')),
    'zones': dict.fromkeys(('a_min_xy_m', 'a_max_xy_m', 'b_place_xy_m', 'b_pick_tolerance_m', 'c_slots_xy_m')),
    'motion': dict.fromkeys(('planning_s', 'planning_attempts', 'goal_submit_s', 'motion_s',
                             'settle_s', 'tcp_error_limit_m', 'arrival_samples', 'arrival_timeout_s',
                             'joint_state_max_age_s', 'waypoint_step_m', 'waypoint_joint_jump_rad',
                             'max_velocity_rad_s', 'max_acceleration_rad_s2', 'max_tool_tilt_deg')),
    'gripper': {**dict.fromkeys(('backend', 'auto_confirm', 'reply_timeout_s', 'esp32_echo_timeout_s', 'vacuum_settle_s')),
                'esp32_modules': dict.fromkeys(ARMS)},
}
_RULES = {
    'simulation': {'evidence_kind': 'simulation_assumed', 'home_source': 'runtime_json',
                   'backends': ('gazebo', 'manual_token')},
    # SRDF named states and runtime.json are simulation values, so hardware must
    # derive HOME from the measured calibration.
    'hardware': {'evidence_kind': 'physical', 'home_source': 'calibration',
                 'backends': ('manual_token', 'esp32')},
}


class TaskConfigError(ValueError):
    """The configuration cannot authorize a task; the message lists every problem."""


def _shape_errors(node, shape, path):
    if not isinstance(node, dict):
        return [f'{path or "document"} must be a mapping']
    errors = [f'{path}{key} is missing' for key in shape if key not in node]
    errors += [f'{path}{key} is not a known setting' for key in node if key not in shape]
    for key, child in shape.items():
        if isinstance(child, dict) and key in node:
            errors += _shape_errors(node[key], child, f'{path}{key}.')
    return errors


def _unmeasured(node, path=''):
    if isinstance(node, dict):
        return [item for key, value in node.items() for item in _unmeasured(value, f'{path}{key}.')]
    if isinstance(node, list):
        return [item for index, value in enumerate(node) for item in _unmeasured(value, f'{path}{index}.')]
    if node is None or (isinstance(node, float) and not math.isfinite(node)):
        return [f'{path.rstrip(".")} is not measured']
    return []


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_xy(value):
    return isinstance(value, list) and len(value) == 2 and all(_is_number(item) for item in value)


def _check_rules(doc):
    errors = []
    rules = _RULES.get(doc['mode'])
    if rules is None:
        return [f'mode must be one of {sorted(_RULES)}']
    for key in ('evidence_kind', 'home_source'):
        if doc[key] != rules[key]:
            errors.append(f'{doc["mode"]} requires {key}={rules[key]}, got {doc[key]}')
    gripper = doc['gripper']
    if gripper['backend'] not in rules['backends']:
        errors.append(f'{doc["mode"]} does not allow gripper backend {gripper["backend"]}')
    if not isinstance(gripper['auto_confirm'], bool):
        errors.append('gripper.auto_confirm must be true or false')
    elif gripper['auto_confirm'] and doc['mode'] != 'simulation':
        errors.append('gripper.auto_confirm is simulation only')
    return errors


def _check_numbers(doc):
    errors = []
    for key, value in doc['speeds'].items():
        if not _is_number(value) or not 0 < value <= 1:
            errors.append(f'speeds.{key} must be within (0, 1]')
    heights = doc['heights']
    if not all(_is_number(value) for value in heights.values()):
        errors.append('heights must all be numbers')
    else:
        for key in ('cap_height_m', 'cap_radius_m', 'cup_radius_m', 'pick_z_tolerance_m'):
            if heights[key] <= 0:
                errors.append(f'heights.{key} must be positive')
        top = heights['surface_z_m'] + heights['cap_height_m']
        if not top <= heights['contact_z_m'] < heights['release_z_m'] < heights['approach_z_m']:
            errors.append('heights must satisfy cap top <= contact < release < approach')
    motion = doc['motion']
    for key, value in motion.items():
        if key == 'max_tool_tilt_deg':
            if not _is_number(value) or not 0 <= value < 90:
                errors.append('motion.max_tool_tilt_deg must be within [0, 90)')
        elif not _is_number(value) or value <= 0:
            errors.append(f'motion.{key} must be positive')
    for key in ('planning_attempts', 'arrival_samples'):
        if not isinstance(motion[key], int) or isinstance(motion[key], bool):
            errors.append(f'motion.{key} must be an integer')
    gripper = doc['gripper']
    for key in ('reply_timeout_s', 'esp32_echo_timeout_s'):
        if not _is_number(gripper[key]) or gripper[key] <= 0:
            errors.append(f'gripper.{key} must be positive')
    if not _is_number(gripper['vacuum_settle_s']) or gripper['vacuum_settle_s'] < 0:
        errors.append('gripper.vacuum_settle_s must not be negative')
    if sorted(map(str, gripper['esp32_modules'].values())) != ['1', '2']:
        errors.append('gripper.esp32_modules must assign modules 1 and 2 to the two arms')
    return errors


def _check_zones(doc):
    zones = doc['zones']
    errors = [f'zones.{key} must be [x, y]' for key in ('a_min_xy_m', 'a_max_xy_m', 'b_place_xy_m')
              if not _is_xy(zones[key])]
    if not errors and not all(low < high for low, high in zip(zones['a_min_xy_m'], zones['a_max_xy_m'])):
        errors.append('zones.a_min_xy_m must be below zones.a_max_xy_m')
    if not _is_number(zones['b_pick_tolerance_m']) or zones['b_pick_tolerance_m'] <= 0:
        errors.append('zones.b_pick_tolerance_m must be positive')
    slots = zones['c_slots_xy_m']
    if not isinstance(slots, list) or len(slots) != SLOT_COUNT or not all(_is_xy(slot) for slot in slots):
        errors.append(f'zones.c_slots_xy_m must list {SLOT_COUNT} [x, y] pairs')
    elif len({tuple(slot) for slot in slots}) != SLOT_COUNT:
        errors.append('zones.c_slots_xy_m must be distinct')
    return errors


def validate(doc):
    """Return doc unchanged when valid; otherwise raise listing every problem found."""
    errors = _shape_errors(doc, _SHAPE, '')
    if not errors:
        errors = _unmeasured(doc)
    if not errors:
        if doc['schema_version'] != 1:
            errors.append('schema_version must be 1')
        errors += _check_rules(doc) + _check_numbers(doc) + _check_zones(doc)
    if errors:
        raise TaskConfigError('; '.join(errors))
    return doc


def load(path):
    try:
        text = Path(path).read_text(encoding='utf-8')
    except OSError as error:
        raise TaskConfigError(f'cannot read {path}: {error}') from error
    try:
        return validate(yaml.safe_load(text))
    except yaml.YAMLError as error:
        raise TaskConfigError(f'invalid YAML in {path}: {error}') from error


def main(argv=None):
    parser = argparse.ArgumentParser(description='Validate a coordinator task configuration; moves nothing.')
    parser.add_argument('path')
    args = parser.parse_args(argv)
    try:
        doc = load(args.path)
    except TaskConfigError as error:
        print(f'FAIL {args.path}: {error}')
        return 1
    print(f'PASS {args.path}: mode={doc["mode"]}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
