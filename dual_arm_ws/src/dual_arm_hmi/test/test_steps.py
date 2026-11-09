from pathlib import Path
import re

import pytest

from dual_arm_hmi.model.steps import SEGMENTS, ProgressTracker, SegmentState, describe, segment_of
from dual_arm_hmi.sources.fake_source import WORK_SEQUENCE

WORKFLOW = Path(__file__).resolve().parents[2] / 'dual_arm_coordinator' / 'dual_arm_coordinator' / 'workflow'


def published_states():
    """Every step name the coordinator can publish, read from its own source."""
    found = set()
    for name, arm in (('arm1_workflow.py', 'ARM1'), ('arm2_workflow.py', 'ARM2')):
        found |= {f'{arm}:{step}' for step in re.findall(r"step\(ARM, '([A-Z0-9_]+)'", (WORKFLOW / name).read_text(encoding='utf-8'))}
    return found | {'ARM1:INITIAL_HOME', 'ARM2:INITIAL_HOME'}


def test_every_published_step_has_a_segment_and_wording():
    states = published_states()
    assert len(states) > 30
    for state in states:
        assert segment_of(state) is not None, state
        assert describe(state) != state, state


def test_demonstration_sequence_only_moves_forward():
    segments = [segment_of(state) for state in WORK_SEQUENCE]
    assert None not in segments
    assert segments == sorted(segments)
    assert set(segments) == set(range(len(SEGMENTS)))


def test_progress_while_running():
    progress = ProgressTracker().update('ARM2:APPROACH_C')
    assert progress.segments[:6] == (SegmentState.DONE,) * 6
    assert progress.segments[6] is SegmentState.CURRENT
    assert progress.segments[7] is SegmentState.PENDING


def test_fault_marks_the_step_that_failed():
    tracker = ProgressTracker()
    tracker.update('ARM1:APPROACH_B')
    progress = tracker.update('FAULT')
    assert progress.segments[2] is SegmentState.FAILED
    assert progress.segments[:2] == (SegmentState.DONE,) * 2


def test_fault_after_restart_marks_nothing_as_failed():
    assert set(ProgressTracker().update('FAULT').segments) == {SegmentState.PENDING}


@pytest.mark.parametrize('state', ('SUCCEEDED', 'FULL'))
def test_terminal_success_fills_the_bar(state):
    assert set(ProgressTracker().update(state).segments) == {SegmentState.DONE}


def test_idle_clears_previous_progress():
    tracker = ProgressTracker()
    tracker.update('ARM1:VERIFY_B')
    assert set(tracker.update('IDLE').segments) == {SegmentState.PENDING}


def test_unknown_state_is_shown_as_published():
    assert describe('ARM3:SOMETHING') == 'ARM3:SOMETHING'
    assert segment_of('ARM3:SOMETHING') is None
    assert ProgressTracker().update('NEW_STATE').text == 'NEW_STATE'
