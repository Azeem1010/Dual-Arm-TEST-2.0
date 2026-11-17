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
    # Prototype: real arms with estimated values (2026-11-13 user decision); never counts as calibration evidence.
    'prototype': {'evidence_kind': 'prototype_estimate', 'home_source': 'calibration',
                  'backends': ('manual_token', 'esp32')},
}
# Suction results may be confirmed automatically only where nobody claims real accuracy.
AUTO_CONFIRM_MODES = ('simulation', 'prototype')
# Optional: C slots as taught joint positions instead of xy (prototype only, user decision 2026-11-13).
SLOT_TEACH_KEY = 'c_slot_teach'
SLOT_TEACH_MODES = ('prototype',)
_SLOT_TEACH_SHAPE = dict.fromkeys(('arm', 'source', 'raw', 'release_lift_m', 'arrival_tolerance_raw',
                                   'max_line_drift_m'))
# Optional: the B hand-over as taught joint positions of both arms instead of b_place_xy_m
# (prototype only, user decision 2026-11-15).
B_TEACH_KEY = 'b_teach'
_B_TEACH_SHAPE = dict.fromkeys(('source', 'raw', 'contact_lift_m', 'arrival_tolerance_raw', 'max_line_drift_m'))
# Optional: after a fault, go HOME, recover and continue by itself, at most max_resumes times per start
# (prototype only, user decision 2026-11-17).
AUTO_RESUME_KEY = 'auto_resume'
_AUTO_RESUME_SHAPE = dict.fromkeys(('max_resumes',))
MAX_RESUMES_LIMIT = 5
# Optional: a fixed xy correction added to the observed zone A object before arm 1 picks it
# (prototype only, user decision 2026-11-17: the cup missed the cap sideways).
A_OFFSET_KEY = 'a_pick_offset_xy_m'
MAX_A_OFFSET_M = 0.02
# Optional: re-aim a contact descent that stopped short by more than tolerance_m, at most
# max_extra_m below the target and attempts times (prototype only, user decision 2026-11-17).
DESCENT_KEY = 'descent_correction'
_DESCENT_SHAPE = dict.fromkeys(('tolerance_m', 'max_extra_m', 'attempts'))
MAX_DESCENT_EXTRA_M = 0.01
# Optional: arm 1 aims this much below contact_z_m when it picks in zone A (prototype only,
# user decision 2026-11-17: the joints reached the target but the cup stayed above the cap).
A_PRESS_KEY = 'a_press_m'
MAX_A_PRESS_M = 0.008
# Optional: after releasing in a taught B, arm 1 lifts straight up from where its cup is to
# approach_z_m plus this (prototype only, user decision 2026-11-17: the taught joint-line lift
# turned j1 back while the cup still touched the object and pushed it).
B_LIFT_KEY = 'b_release_lift_extra_m'
MAX_B_LIFT_EXTRA_M = 0.03
# Optional: arm 1 goes from A straight to B and arm 2 from B straight to C, without HOME in
# between (prototype only, user decision 2026-11-17: the video showed about 25 s of detour).
DIRECT_KEY = 'direct_transfer'
# Optional: wait this long after a grasp instead of gripper.vacuum_settle_s; the release keeps the
# full wait (prototype only, user decision 2026-11-17: E0 held a cap in about 1 s).
GRASP_SETTLE_KEY = 'grasp_settle_s'
MIN_GRASP_SETTLE_S = 1.0
# Optional: non-contact moves run the joint line to their target, every waypoint checked and the
# tool never below the lower end, before falling back to a MoveIt plan (prototype only, user
# decision 2026-11-17: no planning time and the same path every time).
FIXED_KEY = 'fixed_transits'
# Optional: overlapped transfer (prototype only, user decision 2026-11-17): arm 1 picks the next
# object while arm 2 carries the previous one to C, and puts it in B once arm 2 has left B. Both
# arms may then move at once; every trajectory first reserves the x range the arm's joints sweep
# (padded by clearance_m on each side), and an arm waits up to wait_s for the other's range.
OVERLAP_KEY = 'overlap'
_OVERLAP_SHAPE = dict.fromkeys(('clearance_m', 'wait_s'))
OVERLAP_CLEARANCE_RANGE_M = (0.01, 0.10)
OVERLAP_WAIT_RANGE_S = (1.0, 600.0)
OPTIONAL_KEYS = (SLOT_TEACH_KEY, B_TEACH_KEY, AUTO_RESUME_KEY, A_OFFSET_KEY, DESCENT_KEY, A_PRESS_KEY, B_LIFT_KEY,
                 DIRECT_KEY, GRASP_SETTLE_KEY, FIXED_KEY, OVERLAP_KEY)


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
    elif gripper['auto_confirm'] and doc['mode'] not in AUTO_CONFIRM_MODES:
        errors.append('gripper.auto_confirm is simulation only (or prototype)')
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


def _check_slot_teach(doc):
    """The taught C-slot joints: arm 2, eight poses of four integer AX-12 counts."""
    teach = doc[SLOT_TEACH_KEY]
    errors = _shape_errors(teach, _SLOT_TEACH_SHAPE, f'{SLOT_TEACH_KEY}.')
    if errors:
        return errors
    errors = _unmeasured(teach, f'{SLOT_TEACH_KEY}.')
    if errors:
        return errors
    if doc['mode'] not in SLOT_TEACH_MODES:
        errors.append(f'{SLOT_TEACH_KEY} is only allowed in {SLOT_TEACH_MODES}')
    if teach['arm'] != 'arm2':
        errors.append(f'{SLOT_TEACH_KEY}.arm must be arm2, which places into C')
    if not isinstance(teach['source'], str) or not teach['source'].strip():
        errors.append(f'{SLOT_TEACH_KEY}.source must name where the readings come from')
    raw = teach['raw']
    if (not isinstance(raw, list) or len(raw) != SLOT_COUNT
            or not all(isinstance(pose, list) and len(pose) == 4 for pose in raw)):
        errors.append(f'{SLOT_TEACH_KEY}.raw must list {SLOT_COUNT} poses of four counts')
    elif not all(type(count) is int and 0 <= count <= 1023 for pose in raw for count in pose):
        errors.append(f'{SLOT_TEACH_KEY}.raw counts must be integers in 0..1023')
    return errors + _check_teach_limits(teach, SLOT_TEACH_KEY, 'release_lift_m')


def _check_teach_limits(teach, key, lift_key):
    errors = []
    lift = teach[lift_key]
    if not _is_number(lift) or not 0 <= lift <= 0.02:
        errors.append(f'{key}.{lift_key} must be within [0, 0.02]')
    tolerance = teach['arrival_tolerance_raw']
    if type(tolerance) is not int or not 1 <= tolerance <= 20:
        errors.append(f'{key}.arrival_tolerance_raw must be an integer in 1..20')
    drift = teach['max_line_drift_m']
    if not _is_number(drift) or not 0 < drift <= 0.01:
        errors.append(f'{key}.max_line_drift_m must be within (0, 0.01]')
    return errors


def _check_b_teach(doc):
    """The taught B hand-over: one pose of four integer AX-12 counts for each arm."""
    teach = doc[B_TEACH_KEY]
    errors = _shape_errors(teach, _B_TEACH_SHAPE, f'{B_TEACH_KEY}.')
    if errors:
        return errors
    errors = _unmeasured(teach, f'{B_TEACH_KEY}.')
    if errors:
        return errors
    if doc['mode'] not in SLOT_TEACH_MODES:
        errors.append(f'{B_TEACH_KEY} is only allowed in {SLOT_TEACH_MODES}')
    if not isinstance(teach['source'], str) or not teach['source'].strip():
        errors.append(f'{B_TEACH_KEY}.source must name where the readings come from')
    raw = teach['raw']
    if not isinstance(raw, dict) or set(raw) != {'arm1', 'arm2'}:
        errors.append(f'{B_TEACH_KEY}.raw must give arm1 and arm2')
    else:
        for arm in ('arm1', 'arm2'):
            pose = raw[arm]
            if not (isinstance(pose, list) and len(pose) == 4
                    and all(type(count) is int and 0 <= count <= 1023 for count in pose)):
                errors.append(f'{B_TEACH_KEY}.raw.{arm} must be four integer counts in 0..1023')
    return errors + _check_teach_limits(teach, B_TEACH_KEY, 'contact_lift_m')


def _check_auto_resume(doc):
    node = doc[AUTO_RESUME_KEY]
    if not isinstance(node, dict):
        return [f'{AUTO_RESUME_KEY} must be a mapping']
    errors = _shape_errors(node, _AUTO_RESUME_SHAPE, f'{AUTO_RESUME_KEY}.')
    if errors:
        return errors
    if doc['mode'] not in SLOT_TEACH_MODES:
        errors.append(f'{AUTO_RESUME_KEY} is only allowed in {SLOT_TEACH_MODES}')
    count = node['max_resumes']
    if type(count) is not int or not 1 <= count <= MAX_RESUMES_LIMIT:
        errors.append(f'{AUTO_RESUME_KEY}.max_resumes must be an integer in 1..{MAX_RESUMES_LIMIT}')
    return errors


def _check_a_offset(doc):
    value = doc[A_OFFSET_KEY]
    errors = []
    if doc['mode'] not in SLOT_TEACH_MODES:
        errors.append(f'{A_OFFSET_KEY} is only allowed in {SLOT_TEACH_MODES}')
    if not _is_xy(value) or not all(abs(item) <= MAX_A_OFFSET_M for item in value):
        errors.append(f'{A_OFFSET_KEY} must be [x, y] with each within +-{MAX_A_OFFSET_M} m')
    return errors


def _check_descent(doc):
    node = doc[DESCENT_KEY]
    if not isinstance(node, dict):
        return [f'{DESCENT_KEY} must be a mapping']
    errors = _shape_errors(node, _DESCENT_SHAPE, f'{DESCENT_KEY}.')
    if errors:
        return errors
    if doc['mode'] not in SLOT_TEACH_MODES:
        errors.append(f'{DESCENT_KEY} is only allowed in {SLOT_TEACH_MODES}')
    for key in ('tolerance_m', 'max_extra_m'):
        if not _is_number(node[key]) or not 0 < node[key] <= MAX_DESCENT_EXTRA_M:
            errors.append(f'{DESCENT_KEY}.{key} must be within (0, {MAX_DESCENT_EXTRA_M}]')
    if type(node['attempts']) is not int or not 1 <= node['attempts'] <= 3:
        errors.append(f'{DESCENT_KEY}.attempts must be an integer in 1..3')
    return errors


def _check_a_press(doc):
    errors = []
    if doc['mode'] not in SLOT_TEACH_MODES:
        errors.append(f'{A_PRESS_KEY} is only allowed in {SLOT_TEACH_MODES}')
    if not _is_number(doc[A_PRESS_KEY]) or not 0 < doc[A_PRESS_KEY] <= MAX_A_PRESS_M:
        errors.append(f'{A_PRESS_KEY} must be within (0, {MAX_A_PRESS_M}] m')
    return errors


def _check_b_lift(doc):
    errors = []
    if doc['mode'] not in SLOT_TEACH_MODES:
        errors.append(f'{B_LIFT_KEY} is only allowed in {SLOT_TEACH_MODES}')
    if B_TEACH_KEY not in doc:
        errors.append(f'{B_LIFT_KEY} needs {B_TEACH_KEY}')
    if not _is_number(doc[B_LIFT_KEY]) or not 0 <= doc[B_LIFT_KEY] <= MAX_B_LIFT_EXTRA_M:
        errors.append(f'{B_LIFT_KEY} must be within [0, {MAX_B_LIFT_EXTRA_M}] m')
    return errors


def _check_switch(doc, key):
    errors = []
    if doc['mode'] not in SLOT_TEACH_MODES:
        errors.append(f'{key} is only allowed in {SLOT_TEACH_MODES}')
    if type(doc[key]) is not bool:
        errors.append(f'{key} must be true or false')
    return errors


def _check_direct(doc):
    return _check_switch(doc, DIRECT_KEY)


def _check_grasp_settle(doc):
    errors = []
    if doc['mode'] not in SLOT_TEACH_MODES:
        errors.append(f'{GRASP_SETTLE_KEY} is only allowed in {SLOT_TEACH_MODES}')
    value, high = doc[GRASP_SETTLE_KEY], doc['gripper']['vacuum_settle_s']
    if not _is_number(value) or not _is_number(high) or not MIN_GRASP_SETTLE_S <= value <= high:
        errors.append(f'{GRASP_SETTLE_KEY} must be within [{MIN_GRASP_SETTLE_S}, gripper.vacuum_settle_s] s')
    return errors


def _check_overlap(doc):
    node = doc[OVERLAP_KEY]
    if not isinstance(node, dict):
        return [f'{OVERLAP_KEY} must be a mapping']
    errors = _shape_errors(node, _OVERLAP_SHAPE, f'{OVERLAP_KEY}.')
    if errors:
        return errors
    if doc['mode'] not in SLOT_TEACH_MODES:
        errors.append(f'{OVERLAP_KEY} is only allowed in {SLOT_TEACH_MODES}')
    if doc['gripper']['auto_confirm'] is not True:
        # One operator confirmation at a time; two arms could ask at once.
        errors.append(f'{OVERLAP_KEY} needs gripper.auto_confirm')
    low, high = OVERLAP_CLEARANCE_RANGE_M
    if not _is_number(node['clearance_m']) or not low <= node['clearance_m'] <= high:
        errors.append(f'{OVERLAP_KEY}.clearance_m must be within [{low}, {high}] m')
    low, high = OVERLAP_WAIT_RANGE_S
    if not _is_number(node['wait_s']) or not low <= node['wait_s'] <= high:
        errors.append(f'{OVERLAP_KEY}.wait_s must be within [{low}, {high}] s')
    if doc.get(DIRECT_KEY) is True:
        # Overlap waits HOME for zone B; direct transfer takes B before the pick and keeps it until
        # arm 2 is HOME again, so together arm 1 could not take B or arm 2 would block it.
        errors.append(f'{OVERLAP_KEY} and {DIRECT_KEY} cannot both be on')
    return errors


def max_resumes(doc):
    """How often a run may resume itself after a fault; 0 when the configuration does not allow it."""
    return doc[AUTO_RESUME_KEY]['max_resumes'] if AUTO_RESUME_KEY in doc else 0


def validate(doc):
    """Return doc unchanged when valid; otherwise raise listing every problem found."""
    present = [key for key in OPTIONAL_KEYS if isinstance(doc, dict) and key in doc]
    required = {key: value for key, value in doc.items() if key not in present} if present else doc
    errors = _shape_errors(required, _SHAPE, '')
    if not errors:
        errors = _unmeasured(required)
    if not errors:
        if doc['schema_version'] != 1:
            errors.append('schema_version must be 1')
        errors += _check_rules(doc) + _check_numbers(doc) + _check_zones(doc)
        if SLOT_TEACH_KEY in present:
            errors += _check_slot_teach(doc)
        if B_TEACH_KEY in present:
            errors += _check_b_teach(doc)
        if AUTO_RESUME_KEY in present:
            errors += _check_auto_resume(doc)
        if A_OFFSET_KEY in present:
            errors += _check_a_offset(doc)
        if DESCENT_KEY in present:
            errors += _check_descent(doc)
        if A_PRESS_KEY in present:
            errors += _check_a_press(doc)
        if B_LIFT_KEY in present:
            errors += _check_b_lift(doc)
        if DIRECT_KEY in present:
            errors += _check_direct(doc)
        if GRASP_SETTLE_KEY in present:
            errors += _check_grasp_settle(doc)
        if FIXED_KEY in present:
            errors += _check_switch(doc, FIXED_KEY)
        if OVERLAP_KEY in present:
            errors += _check_overlap(doc)
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
