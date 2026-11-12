"""Turns the coordinator state string into an eight-segment progress display."""
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple

SEGMENTS = ('回 HOME', 'Arm1\n取料', 'Arm1\n放到 B', '確認\nB 區', 'Arm2\n取料', '確認\nB 清空', 'Arm2\n放到 C', '確認\nC 區')

_ARM1_SEGMENTS = {
    **dict.fromkeys(('CHECK_ZONES', 'QUERY_TARGET', 'PREFLIGHT', 'APPROACH_A', 'DESCEND_A', 'GRASP_A', 'ATTACH',
                     'LIFT_A', 'HOME_HOLDING'), 1),
    **dict.fromkeys(('RESERVE_B', 'APPROACH_B', 'DESCEND_B', 'RELEASE_B', 'DETACH', 'LIFT_B', 'HOME_EMPTY'), 2),
    'VERIFY_B': 3,
}
_ARM2_SEGMENTS = {
    **dict.fromkeys(('CHECK_ZONES', 'QUERY_B_TARGET', 'RESERVE_SLOT', 'PREFLIGHT', 'RESERVE_B', 'APPROACH_B', 'DESCEND_B', 'GRASP_B',
                     'ATTACH', 'LIFT_B', 'HOME_HOLDING'), 4),
    'VERIFY_B_EMPTY': 5,
    **dict.fromkeys(('APPROACH_C', 'DESCEND_C', 'RELEASE_C', 'DETACH', 'LIFT_C', 'HOME_EMPTY'), 6),
    'VERIFY_C': 7,
}

_STEP_TEXT = {
    'INITIAL_HOME': '回到 HOME', 'CHECK_ZONES': '檢查區域狀態', 'QUERY_TARGET': '查詢取料點', 'QUERY_B_TARGET': '查詢 B 區取料點', 'RESERVE_SLOT': '預約 C 區格位',
    'PREFLIGHT': '動作前檢查', 'APPROACH_A': '移到 A 區上方', 'DESCEND_A': '下降到 A 區', 'GRASP_A': '在 A 區吸取',
    'ATTACH': '確認吸附', 'LIFT_A': '從 A 區抬升', 'HOME_HOLDING': '持物回 HOME', 'RESERVE_B': '預約 B 區',
    'APPROACH_B': '移到 B 區上方', 'DESCEND_B': '下降到 B 區', 'RELEASE_B': '在 B 區釋放', 'GRASP_B': '在 B 區吸取',
    'DETACH': '確認釋放', 'LIFT_B': '從 B 區抬升', 'HOME_EMPTY': '空手回 HOME', 'VERIFY_B': '確認 B 區有物件',
    'VERIFY_B_EMPTY': '確認 B 區已清空', 'APPROACH_C': '移到 C 區上方', 'DESCEND_C': '下降到 C 區', 'RELEASE_C': '在 C 區釋放',
    'LIFT_C': '從 C 區抬升', 'VERIFY_C': '確認 C 區放置結果',
}
_STATE_TEXT = {'IDLE': '待命', 'STARTING': '開始任務', 'SUCCEEDED': '任務完成', 'FULL': 'C 區已滿', 'FAULT': '任務故障'}


class SegmentState(Enum):
    PENDING = '未開始'
    CURRENT = '進行中'
    DONE = '完成'
    FAILED = '故障'


@dataclass(frozen=True)
class Progress:
    segments: Tuple[SegmentState, ...]
    text: str


def segment_of(state):
    """The segment for a coordinator state, or None for terminal and unknown states."""
    if state == 'STARTING':
        return 0
    arm, separator, step = state.partition(':')
    if not separator:
        return None
    if step == 'INITIAL_HOME' and arm in ('ARM1', 'ARM2'):
        return 0
    return {'ARM1': _ARM1_SEGMENTS, 'ARM2': _ARM2_SEGMENTS}.get(arm, {}).get(step)


def describe(state):
    """Operator wording for a state; an unknown state is shown as published."""
    if state in _STATE_TEXT:
        return _STATE_TEXT[state]
    arm, separator, step = state.partition(':')
    if separator and step in _STEP_TEXT:
        return f'{arm.capitalize()}：{_STEP_TEXT[step]}'
    return state


class ProgressTracker:
    """The published state becomes FAULT when a step fails, so the failing step must be remembered."""

    def __init__(self):
        self._last: Optional[int] = None

    def update(self, state):
        count = len(SEGMENTS)
        segment = segment_of(state)
        if segment is not None:
            self._last = segment
        elif state == 'IDLE':
            self._last = None
        elif state in ('SUCCEEDED', 'FULL'):
            self._last = None
            return Progress((SegmentState.DONE,) * count, describe(state))
        if self._last is None:
            return Progress((SegmentState.PENDING,) * count, describe(state))
        active = SegmentState.FAILED if state == 'FAULT' else SegmentState.CURRENT
        segments = (SegmentState.DONE,) * self._last + (active,) + (SegmentState.PENDING,) * (count - self._last - 1)
        return Progress(segments, describe(state))
