from dataclasses import replace

import pytest

from dual_arm_hmi.model.state import (HARDWARE_MOTION_BLOCKED, Action, CameraStatus, Level, Mode, Phase, SafetyStatus,
                                      Snapshot, TaskStatus, ZoneView, b_interlock, banner, calibration_label, camera_placeholder,
                                      evaluate_actions, next_slot, status_cells)
from dual_arm_hmi.sources.fake_source import FakeSource

SCENARIOS = tuple(key for key, _ in FakeSource().scenarios())


def ready(**changes):
    base = Snapshot(mode=Mode.SIMULATION, phase=Phase.READY, ros_connected=True, task=TaskStatus(), safety=SafetyStatus(),
                    controllers_active=True, decision_source='truth', joint_age_s=0.01)
    return replace(base, **changes)


def fault(**changes):
    return ready(task=TaskStatus(state='FAULT', message='x'), **changes)


def latched(**changes):
    return ready(safety=SafetyStatus(latched=True, reason='Operator software stop', **changes))


@pytest.mark.parametrize('scenario', SCENARIOS)
@pytest.mark.parametrize('cleared', (False, True))
def test_stop_can_always_be_pressed(scenario, cleared):
    assert evaluate_actions(FakeSource(scenario).snapshot(), cleared)[Action.STOP].enabled


@pytest.mark.parametrize('scenario', SCENARIOS)
def test_a_disabled_button_always_says_why(scenario):
    for action, state in evaluate_actions(FakeSource(scenario).snapshot()).items():
        if not state.enabled:
            assert state.reason, action


@pytest.mark.parametrize('snapshot,reason', (
    (ready(task=None), '任務節點未啟動'),
    (ready(phase=Phase.STARTING), '系統尚未就緒'),
    (latched(), '安全鎖定中'),
    (ready(task=TaskStatus(busy=True)), '任務執行中'),
    (fault(), '請先完成復歸'),
    (ready(task=TaskStatus(state='FULL')), 'C 區已滿，請先復歸'),
    (ready(controllers_active=False), '控制器未啟用'),
    (ready(task=TaskStatus(state='ARM1:LIFT_A')), '任務狀態為 ARM1:LIFT_A'),
))
def test_start_task_refusals(snapshot, reason):
    state = evaluate_actions(snapshot)[Action.START_TASK]
    assert not state.enabled and state.reason == reason


@pytest.mark.parametrize('state', ('IDLE', 'SUCCEEDED'))
def test_start_task_allowed_from_clean_states(state):
    assert evaluate_actions(ready(task=TaskStatus(state=state)))[Action.START_TASK].enabled


@pytest.mark.parametrize('mode', (Mode.HARDWARE_READ_ONLY, Mode.HARDWARE_MOTION))
def test_hardware_transfer_is_blocked_unless_a_source_clears_it(mode):
    state = evaluate_actions(ready(mode=mode))[Action.START_TASK]
    assert not state.enabled and state.reason == HARDWARE_MOTION_BLOCKED


def test_prototype_is_hardware_but_not_blocked():
    assert Mode.HARDWARE_PROTOTYPE.is_hardware and Mode.HARDWARE_PROTOTYPE.has_torque_step
    snapshot = ready(mode=Mode.HARDWARE_PROTOTYPE)
    assert evaluate_actions(snapshot)[Action.START_TASK].enabled
    assert evaluate_actions(replace(fault(arms_at_home=False), mode=Mode.HARDWARE_PROTOTYPE), True)[Action.GO_HOME].enabled
    assert banner(snapshot).title == '實機 PROTOTYPE' and 'CM-530' in banner(snapshot).next_step
    cell = status_cells(snapshot)[0]
    assert cell.value == '實機 Prototype' and cell.level is Level.HARDWARE


def test_go_home_needs_confirmation_and_is_refused_on_hardware():
    snapshot = fault(arms_at_home=False)
    assert evaluate_actions(snapshot, False)[Action.GO_HOME].reason == '請先勾選已清空'
    assert evaluate_actions(snapshot, True)[Action.GO_HOME].enabled
    hardware = replace(snapshot, mode=Mode.HARDWARE_MOTION)
    assert evaluate_actions(hardware, True)[Action.GO_HOME].reason == '實機需等 H5 通過'


def test_go_home_refused_while_latched_or_running():
    assert not evaluate_actions(latched(), True)[Action.GO_HOME].enabled
    assert not evaluate_actions(ready(task=TaskStatus(busy=True), arms_at_home=False), True)[Action.GO_HOME].enabled


def test_recover_order():
    away = fault(arms_at_home=False)
    assert evaluate_actions(away, True)[Action.RECOVER].reason == '兩臂需先回 HOME'
    home = fault()
    assert evaluate_actions(home, False)[Action.RECOVER].reason == '請先勾選已清空'
    assert evaluate_actions(home, True)[Action.RECOVER].enabled
    assert evaluate_actions(ready(), True)[Action.RECOVER].reason == '目前不需要復歸'


def test_safety_reset_waits_for_the_cause():
    assert evaluate_actions(latched())[Action.SAFETY_RESET].enabled
    assert not evaluate_actions(latched(blocking_problem='Emergency-stop heartbeat is stale'))[Action.SAFETY_RESET].enabled
    assert not evaluate_actions(ready())[Action.SAFETY_RESET].enabled
    assert not evaluate_actions(ready(safety=None))[Action.SAFETY_RESET].enabled


def test_torque_needs_motion_mode_and_passing_calibration():
    read_only = ready(mode=Mode.HARDWARE_READ_ONLY, phase=Phase.READ_ONLY, calibration_pass=True)
    assert evaluate_actions(read_only)[Action.TORQUE_ON].reason == '唯讀模式不能上扭力'
    motion = ready(mode=Mode.HARDWARE_MOTION, phase=Phase.READ_ONLY)
    assert evaluate_actions(motion)[Action.TORQUE_ON].reason == '馬達校正尚未通過'
    assert evaluate_actions(replace(motion, calibration_pass=True))[Action.TORQUE_ON].enabled
    assert not evaluate_actions(ready())[Action.TORQUE_ON].visible


def test_shutdown_refused_while_working():
    assert evaluate_actions(ready(task=TaskStatus(busy=True)))[Action.SHUTDOWN].reason == '任務執行中，請先停止'
    assert evaluate_actions(ready())[Action.SHUTDOWN].enabled


def test_residual_gazebo_blocks_start():
    state = evaluate_actions(Snapshot(residual_processes=True))[Action.START_SYSTEM]
    assert not state.enabled and 'Gazebo' in state.reason


def test_suction_buttons_need_a_token():
    assert not evaluate_actions(ready(mode=Mode.HARDWARE_MOTION))[Action.SUCTION_OK].enabled
    assert not evaluate_actions(ready())[Action.SUCTION_OK].visible
    assert evaluate_actions(ready(task=TaskStatus(suction_token='t')))[Action.SUCTION_OK].enabled


def test_banner_priority():
    fault_and_latched = latched()
    fault_and_latched = replace(fault_and_latched, task=TaskStatus(state='FAULT', message='x'))
    assert banner(fault_and_latched).title == '安全鎖定'
    assert banner(fault()).title == '任務故障'
    assert banner(ready(task=TaskStatus(suction_token='t', busy=True))).title == '等待吸盤確認'


def test_banner_names_the_next_step():
    assert '回 HOME' in banner(fault(arms_at_home=False)).next_step
    assert '復歸' in banner(fault()).next_step
    assert '先排除' in banner(latched(blocking_problem='Emergency-stop heartbeat is stale')).next_step


def test_stale_data_and_lost_camera_are_announced():
    assert banner(ready(joint_age_s=2.0)).title == '馬達資料過期'
    assert banner(ready(joint_age_s=None)).title == '馬達資料過期'
    lost = ready(cameras={'env': CameraStatus(age_s=1.5)})
    assert banner(lost).level is Level.WARN and banner(lost).title == '相機無訊號'


def test_status_cells_mark_hardware_and_fake_data():
    cells = status_cells(ready(mode=Mode.HARDWARE_MOTION, is_fake=True))
    assert cells[0].level is Level.HARDWARE and '假資料' in cells[0].title
    assert status_cells(latched())[3].level is Level.DANGER


def test_only_a_lost_camera_is_a_warning():
    assert camera_placeholder(Snapshot(phase=Phase.STOPPED), 'env') == ('未啟動', Level.NEUTRAL)
    assert camera_placeholder(Snapshot(phase=Phase.STARTING), 'env') == ('等待影像', Level.NEUTRAL)
    assert camera_placeholder(ready(), 'env') == ('此模式沒有相機', Level.NEUTRAL)
    assert camera_placeholder(ready(cameras={'env': CameraStatus()}), 'env') == ('無訊號', Level.WARN)


@pytest.mark.parametrize('phase', (Phase.STOPPED, Phase.STARTING))
def test_missing_supervisor_is_not_a_warning_before_the_system_is_up(phase):
    assert status_cells(Snapshot(phase=phase))[3].level is Level.NEUTRAL


def test_missing_supervisor_is_a_warning_once_running():
    assert status_cells(ready(safety=None))[3].level is Level.WARN


def interlock(task, zones=ZoneView(), **changes):
    return b_interlock(ready(task=task, zones=zones, **changes))


def test_interlock_owner_blocks_the_other_arm():
    view = interlock(TaskStatus(state='ARM1:APPROACH_B', busy=True, b_owner='arm1'))
    assert view.center == 'Arm1 佔用' and view.owner == 'arm1'
    assert view.arm1.owned and view.arm1.may_enter
    assert view.arm2.state == '禁止進入' and not view.arm2.may_enter


def test_interlock_stays_locked_after_a_fault_until_recovery():
    view = interlock(TaskStatus(state='FAULT', b_owner='arm2'))
    assert view.center == '故障鎖定' and view.center_level is Level.DANGER
    assert not view.arm1.may_enter and not view.arm2.may_enter and not view.arm2.owned


def test_interlock_needs_the_arm_withdrawn():
    view = interlock(TaskStatus(), ZoneView(b_arm_clear=False))
    assert view.center == '手臂未離開' and not view.arm1.may_enter and not view.arm2.may_enter


def test_interlock_follows_which_arm_needs_the_zone():
    empty = interlock(TaskStatus(), ZoneView(b_has_object=False))
    assert empty.center == '可預約' and empty.arm1.may_enter and not empty.arm2.may_enter
    loaded = interlock(TaskStatus(), ZoneView(b_has_object=True))
    assert not loaded.arm1.may_enter and loaded.arm2.may_enter


@pytest.mark.parametrize('view', (
    interlock(TaskStatus(state='FAULT')),
    b_interlock(replace(latched(), zones=ZoneView())),
))
def test_interlock_closes_both_gates_when_stopped(view):
    assert view.center == '暫停' and not view.arm1.may_enter and not view.arm2.may_enter


def test_interlock_without_observation_or_task_grants_nothing():
    assert not interlock(TaskStatus(), None).arm1.may_enter
    view = b_interlock(ready(task=None))
    assert view.center == '—' and not view.arm1.may_enter


def test_monitor_only_refuses_every_action_including_stop():
    for action, state in evaluate_actions(ready(monitor_only=True), True).items():
        assert not state.enabled and state.reason, action


def test_monitor_banner_never_points_at_a_button():
    for snapshot in (ready(monitor_only=True), latched(), fault(), Snapshot(monitor_only=True)):
        result = banner(replace(snapshot, monitor_only=True))
        assert '按「' not in result.next_step


def test_monitor_status_title():
    assert '唯讀' in status_cells(ready(monitor_only=True))[0].title


def test_interlock_does_not_grant_entry_from_a_source_the_task_ignores():
    view = interlock(TaskStatus(), ZoneView(), zones_authoritative=False)
    assert view.center == '未佔用' and view.arm1.gate_unknown and not view.arm1.may_enter


def test_interlock_owner_is_shown_even_when_zones_are_only_for_reference():
    view = interlock(TaskStatus(b_owner='arm2', busy=True), ZoneView(), zones_authoritative=False)
    assert view.owner == 'arm2' and view.arm1.state == '禁止進入'


def test_lost_contact_does_not_keep_the_system_green():
    cells = status_cells(ready(ros_connected=False, safety=None))
    assert cells[1].level is Level.DANGER and cells[2].level is Level.WARN and cells[2].value == '狀態未知'
    assert cells[3].level is Level.NEUTRAL


def test_camera_staleness_can_be_widened_for_a_slow_simulation():
    assert not CameraStatus(age_s=2.0).has_signal
    assert CameraStatus(age_s=2.0, stale_after_s=4.0).has_signal


@pytest.mark.parametrize('phase', (Phase.STARTING, Phase.STOPPING))
def test_missing_ros_while_starting_or_stopping_is_not_a_failure(phase):
    snapshot = Snapshot(phase=phase, ros_connected=False)
    assert banner(snapshot).level is Level.INFO
    assert status_cells(snapshot)[1].level is Level.NEUTRAL and status_cells(snapshot)[2].level is Level.BUSY


def test_wired_actions_limit_what_is_enabled():
    snapshot = Snapshot(wired_actions=frozenset({Action.START_SYSTEM}))
    actions = evaluate_actions(snapshot)
    assert actions[Action.START_SYSTEM].enabled
    assert not actions[Action.STOP].enabled and actions[Action.STOP].reason == '尚未接通'


def test_banner_never_names_a_button_that_is_not_wired():
    snapshot = replace(latched(), wired_actions=frozenset({Action.START_SYSTEM}))
    assert '解除鎖定' not in banner(snapshot).next_step
    ready_live = ready(wired_actions=frozenset({Action.START_SYSTEM, Action.SHUTDOWN}))
    assert '開始工作' not in banner(ready_live).next_step


def test_launch_failure_outranks_lost_contact():
    snapshot = ready(ros_connected=False, launch_problem='系統意外結束')
    assert banner(snapshot).title == '系統啟動失敗' and status_cells(snapshot)[2].value == '啟動失敗'


def test_next_slot():
    assert next_slot(TaskStatus(occupied=(True, True) + (False,) * 6)) == 3
    assert next_slot(TaskStatus(slot=5)) == 5
    assert next_slot(TaskStatus(occupied=(True,) * 8)) == 0


def test_simulated_fault_while_holding_points_to_reset_simulation():
    task = TaskStatus(state='FAULT', message='Task canceled', holding=(('arm1', 'held'), ('arm2', 'empty')))
    held = Snapshot(mode=Mode.SIMULATION, phase=Phase.READY, ros_connected=True, task=task, arms_at_home=False)
    assert '重置模擬' in banner(held).next_step
    empty = replace(held, task=replace(task, holding=(('arm1', 'empty'), ('arm2', 'empty'))))
    assert '回 HOME' in banner(empty).next_step


def test_placeholder_rotation():
    for rotation, expected in (('off', ('輪流中，鏡頭關閉', Level.NEUTRAL)), ('switching', ('切換中', Level.NEUTRAL)),
                               ('error', ('鏡頭切換失敗', Level.WARN))):
        snapshot = ready(cameras={'arm2': CameraStatus(rotation=rotation)})
        assert camera_placeholder(snapshot, 'arm2') == expected, rotation


def test_rotated_off_camera_is_not_lost():
    quiet = ready(cameras={'arm1': CameraStatus(age_s=0.1, rotation='on'), 'arm2': CameraStatus(rotation='off')})
    assert banner(quiet).title != '相機無訊號'
    switching = ready(cameras={'arm1': CameraStatus(rotation='switching'), 'arm2': CameraStatus(rotation='switching')})
    assert banner(switching).title != '相機無訊號'
    failed = ready(cameras={'arm2': CameraStatus(rotation='error')})
    assert banner(failed).title == '相機無訊號'


def test_monitor_only_calibration_label():
    assert calibration_label(CameraStatus(rotation='off')) == '僅監控'
    assert calibration_label(CameraStatus(calibration='PASS')) == '校正 PASS'
    assert calibration_label(None) == '校正 NOT_RUN'
