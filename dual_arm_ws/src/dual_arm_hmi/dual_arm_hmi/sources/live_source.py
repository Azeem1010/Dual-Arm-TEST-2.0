"""Live data, starting and stopping the system, and the task commands (stage 3).

Task commands go through a separate command node, so the monitor itself never commands.
Each command is followed in three steps: sent, accepted or refused by the service, and the
outcome seen on /dual_arm/status or /safety/status.
"""
from dataclasses import dataclass, replace
import os
import time

from ..launcher.profiles import build_plan, domain_for, journal_settings, new_journal_path
from ..launcher.process import gazebo_processes
from ..model.state import Action, CommandFeedback, EventRecord, Level, Mode, Phase
from .base import DataSource

LAUNCH_ACTIONS = frozenset({Action.START_SYSTEM, Action.SHUTDOWN, Action.RESET_SIMULATION})
# The services each command calls. The stop button cancels the task and latches the supervisor.
TASK_ACTIONS = {
    Action.STOP: ('/safety/trigger_stop', '/dual_arm/cancel'),
    Action.SAFETY_RESET: ('/safety/reset',),
    Action.START_TASK: ('/dual_arm/start',),
    Action.CANCEL_TASK: ('/dual_arm/cancel',),
    Action.GO_HOME: ('/dual_arm/go_home',),
    Action.RECOVER: ('/dual_arm/recover',),
}
# These services finish the work before they answer; the others report it on /dual_arm/status.
_FINISHED_BY_REPLY = frozenset({Action.SAFETY_RESET, Action.RECOVER, Action.TORQUE_ON})
# Hardware gets only the stop until the stepwise hardware start (stage 5) exists.
_HARDWARE_TASK_ACTIONS = frozenset({Action.STOP})
# The prototype also turns the torque on from the interface (2026-11-13).
_TORQUE = {Action.TORQUE_ON: ('/controller_manager/set_hardware_component_state',)}
_RESIDUAL_CHECK_S = 2.0
EVENT_LIMIT = 200
# How long a command may stay accepted without the task ever showing busy before it counts as settled.
_SETTLE_S = 1.5
_SERVICE_TEXT = {'/safety/trigger_stop': '安全監控', '/safety/reset': '安全監控', '/dual_arm/start': '任務',
                 '/dual_arm/cancel': '任務', '/dual_arm/go_home': '任務', '/dual_arm/recover': '任務',
                 '/controller_manager/set_hardware_component_state': '馬達扭力'}


@dataclass
class _Command:
    action: Action
    batch: int
    expected: int
    replies: list
    accepted_at: float = 0.0
    seen_busy: bool = False


class LiveSource(DataSource):
    def __init__(self, ros, launcher, profiles, workspace, settings_store, clock=time.time, reconnect=None,
                 commander=None):
        """ros watches ROS_DOMAIN_ID. reconnect(domain) gives a new monitor on another domain; without it the
        monitor never moves, which is only right when every mode shares one domain.

        commander(domain) gives a command node on that domain (None = ROS_DOMAIN_ID). Without it the task
        commands stay unwired.
        """
        self._ros, self._launcher, self._profiles = ros, launcher, profiles
        self._reconnect, self._domain = reconnect, str(os.environ.get('ROS_DOMAIN_ID', '')).strip()
        self._make_commander = commander
        self._commander = commander(None) if commander is not None else None
        self._command, self._batch, self._base = None, 0, None
        self._workspace, self._store, self._clock = workspace, settings_store, clock
        self._settings = settings_store.load()
        self._selected = Mode(self._settings.get('mode', Mode.SIMULATION.value))
        self._cycles = int(self._settings.get('cycles', 1))
        self._feedback, self._events = None, []
        self._restart_mode, self._shutdown_requested = None, False
        self._residual, self._residual_checked = False, -1e9
        self._last_state = None
        # A system adopted from an earlier interface is watched on its own domain.
        status = launcher.status()
        adopted = _mode_named(status.mode) if status.state in ('running', 'stopping') else None
        self._watch(adopted or self._selected)

    def _watch(self, mode):
        """Move the monitor to the domain this mode runs on."""
        if self._reconnect is None or mode is None:
            return
        domain = domain_for(mode, self._profiles)
        if not domain.isdigit() or domain == self._domain:
            return
        self._ros.close()
        self._ros, self._domain = self._reconnect(int(domain)), domain
        if self._commander is not None:
            # Commands must reach the same system the monitor shows.
            self._commander.close()
            self._commander, self._command = self._make_commander(int(domain)), None
        self._note(Level.NEUTRAL, f'監看 ROS domain {domain}（{mode.value}）')

    # --- DataSource ---

    def close(self):
        # The system keeps running; a restarted interface adopts it.
        self._ros.close()
        if self._commander is not None:
            self._commander.close()

    def frame(self, camera, annotated):
        return self._ros.frame(camera, annotated)

    def select_mode(self, mode):
        self._selected = mode
        self._remember(mode=mode.value)
        # While a system runs the monitor stays with it; the panel only offers a choice when stopped.
        if self._launcher.status().state not in ('running', 'stopping'):
            self._watch(mode)

    def set_cycles(self, cycles):
        self._cycles = cycles
        self._remember(cycles=cycles)

    def cycles(self):
        return self._cycles

    def _remember(self, **values):
        self._settings.update(values)
        self._store.save(self._settings)

    def _note(self, level, message):
        self._events.insert(0, EventRecord(time.strftime('%H:%M:%S'), level, message, time.time()))
        del self._events[EVENT_LIMIT:]

    def _wired(self, mode):
        if self._commander is None:
            return LAUNCH_ACTIONS
        if mode.hardware_locked:
            return LAUNCH_ACTIONS | _HARDWARE_TASK_ACTIONS
        return LAUNCH_ACTIONS | frozenset(TASK_ACTIONS) | (frozenset(_TORQUE) if mode.allows_hardware_tasks else frozenset())

    def invoke(self, action, cleared=False):
        """cleared: the operator ticked that the tools and zone B are clear (HOME and recovery)."""
        if action in TASK_ACTIONS or action in _TORQUE:
            self._send(action, cleared)
            return
        if action not in LAUNCH_ACTIONS:
            self._feedback = CommandFeedback(action, '已拒絕', '這個操作尚未接通')
            self._note(Level.WARN, f'{action.value}：尚未接通')
            return
        self._feedback = CommandFeedback(action, '已送出')
        if action is Action.START_SYSTEM:
            self._start(self._selected)
        elif action is Action.SHUTDOWN:
            self._shutdown()
        elif action is Action.RESET_SIMULATION:
            self._remember(journal_path=new_journal_path(time.strftime('%Y%m%d_%H%M%S')))
            self._restart_mode = Mode.SIMULATION
            self._shutdown()

    # --- task commands ---

    def _send(self, action, cleared):
        mode = self._base.mode if self._base is not None else self._selected
        if action not in self._wired(mode):
            reason = '實機操作在階段 5 開放' if self._commander is not None and mode.hardware_locked else '這個操作尚未接通'
            self._feedback = CommandFeedback(action, '已拒絕', reason)
            self._note(Level.WARN, f'{action.value}：{reason}')
            return
        from .ros_command import request_for
        task = self._base.task if self._base is not None else None
        token = task.recovery_token if action is Action.RECOVER and task is not None else ''
        services = {**TASK_ACTIONS, **_TORQUE}[action]
        if action is Action.STOP:
            # Stop whatever exists; a missing coordinator or supervisor is no reason to stop nothing.
            services = tuple(name for name in services if self._commander.available(name))
            if not services:
                self._feedback = CommandFeedback(action, '已拒絕', '沒有可停止的節點；危險時請按實體急停')
                self._note(Level.WARN, f'{action.value}：沒有可停止的節點')
                return
        self._batch += 1
        self._command = _Command(action, self._batch, len(services), [])
        self._commander.send(self._batch, [(name, request_for(name, token, cleared)) for name in services])
        self._feedback = CommandFeedback(action, '已送出')
        self._note(Level.NEUTRAL, f'操作：{action.value}')

    def _collect_replies(self):
        if self._commander is None:
            return
        for batch, reply in self._commander.results():
            command = self._command
            if command is None or batch != command.batch:
                continue
            command.replies.append(reply)
            verdict = '接受' if reply.ok else '拒絕'
            self._note(Level.OK if reply.ok else Level.DANGER,
                       f'{command.action.value}：{_SERVICE_TEXT.get(reply.service, reply.service)}{verdict}｜{reply.message}')
        command = self._command
        if command is None or command.accepted_at or len(command.replies) < command.expected:
            return
        accepted = [reply for reply in command.replies if reply.ok]
        # The stop counts once anything stopped; every other command needs all of its services.
        refused = not accepted if command.action is Action.STOP else len(accepted) < len(command.replies)
        message = '；'.join(reply.message for reply in command.replies if reply.ok is not refused)
        if refused:
            self._feedback, self._command = CommandFeedback(command.action, '已拒絕', message), None
        elif command.action in _FINISHED_BY_REPLY:
            self._feedback, self._command = CommandFeedback(command.action, '完成', message), None
        else:
            command.accepted_at = self._clock()
            self._feedback = CommandFeedback(command.action, '已接受', '等待系統回報結果')

    def _follow_command(self, base):
        """Turn an accepted command into its outcome once the task has settled."""
        command = self._command
        if command is None or not command.accepted_at or not base.ros_connected:
            return
        if base.busy:
            command.seen_busy = True
            return
        if not command.seen_busy and self._clock() - command.accepted_at < _SETTLE_S:
            return
        task = base.task
        action, phase, message = command.action, '完成', ''
        if action is Action.STOP:
            message = '已鎖定，控制器停用' if base.latched else '任務已停止'
        elif action is Action.START_TASK and task is not None:
            message = f'任務結果：{task.state}' + (f'｜{task.message}' if task.message else '')
            if task.state == 'FAULT':
                phase = '失敗'
        elif action is Action.GO_HOME:
            if base.arms_at_home:
                message = '兩臂已在 HOME'
            else:
                phase, message = '失敗', (task.message if task is not None and task.message else '兩臂未回到 HOME')
        self._feedback, self._command = CommandFeedback(action, phase, message), None
        self._note(Level.OK if phase == '完成' else Level.DANGER,
                   f'{action.value}：{phase}' + (f'｜{message}' if message else ''))

    def _start(self, mode):
        plan = build_plan(mode, self._profiles, self._workspace, journal_settings(self._settings), self._cycles)
        if plan.problem:
            self._feedback = CommandFeedback(Action.START_SYSTEM, '已拒絕', plan.problem)
            self._note(Level.DANGER, f'無法啟動：{plan.problem}')
            return
        self._watch(mode)
        if plan.notice:
            self._note(Level.WARN, plan.notice)
        error = self._launcher.start(mode.value, plan.command, dict(plan.environment))
        if error:
            self._feedback = CommandFeedback(Action.START_SYSTEM, '已拒絕', error)
            self._note(Level.DANGER, f'無法啟動：{error}')
            return
        self._ros.expect_disconnect(False)
        self._feedback = CommandFeedback(Action.START_SYSTEM, '已接受', '等待控制器就緒')
        self._note(Level.BUSY, f'啟動系統：{mode.value}')

    def _shutdown(self):
        self._ros.expect_disconnect(True)
        if self._launcher.stop_async():
            self._shutdown_requested = True
            self._feedback = CommandFeedback(self._feedback.action, '已接受', '正在關閉')
            self._note(Level.NEUTRAL, '關閉系統')
        else:
            self._restart_mode = None
            self._feedback = CommandFeedback(self._feedback.action, '已拒絕', '沒有由介面啟動的系統')

    # --- state ---

    def _residual_gazebo(self, managed_running):
        now = time.monotonic()
        if now - self._residual_checked >= _RESIDUAL_CHECK_S:
            self._residual_checked = now
            self._residual = not managed_running and bool(gazebo_processes())
        return self._residual

    def _follow_launch(self, status, phase):
        if status.state != self._last_state:
            if status.state == 'failed':
                self._note(Level.DANGER, f'{status.message}，紀錄檔：{status.log_path}')
            elif status.adopted and status.state == 'running':
                self._note(Level.NEUTRAL, f'接回先前啟動的系統：{status.mode}')
            self._last_state = status.state
        # Checked on every refresh, so a stop that finished between two refreshes is not missed.
        if self._shutdown_requested and status.state in ('idle', 'failed'):
            self._shutdown_requested = False
            self._note(Level.OK, '系統已關閉' + (f'；{status.message}' if status.message else ''))
            if self._feedback is not None:
                self._feedback = CommandFeedback(self._feedback.action, '完成')
            if self._restart_mode is not None:
                mode, self._restart_mode = self._restart_mode, None
                self._start(mode)
        if self._feedback is not None and self._feedback.action is Action.START_SYSTEM and self._feedback.phase == '已接受' and phase is Phase.READY:
            self._feedback = CommandFeedback(Action.START_SYSTEM, '完成')
            self._note(Level.OK, '系統就緒')

    def snapshot(self):
        base = self._ros.snapshot()
        self._base = base
        self._collect_replies()
        self._follow_command(base)
        status = self._launcher.status()
        running = status.state == 'running'
        managed = running or status.state == 'stopping'
        phase, mode = base.phase, base.mode
        problem, warning = '', ''
        if status.state == 'stopping':
            phase = Phase.STOPPING
        elif not managed and not base.ros_connected:
            phase = Phase.STOPPED
        elif running and not base.ros_connected:
            phase = Phase.STARTING
        if status.state == 'failed':
            problem = f'{status.message}。紀錄檔：{status.log_path}'
        limit = float(self._profiles.get('startup_warning_s', 240))
        if running and phase is Phase.STARTING and self._clock() - status.started_at > limit:
            warning = f'啟動超過 {int(limit)} 秒仍未就緒。紀錄檔：{status.log_path}'
        if mode is Mode.UNKNOWN:
            mode = Mode(status.mode) if managed and status.mode else self._selected
        if phase is Phase.STOPPED:
            mode = self._selected
        self._follow_launch(status, phase)
        # Newest first across both lists; sorted() keeps the order of events with the same stamp.
        events = tuple(sorted(self._events + list(base.events), key=lambda event: event.stamp, reverse=True))[:EVENT_LIMIT]
        return replace(base, phase=phase, mode=mode, monitor_only=False, wired_actions=self._wired(mode),
                       launch_managed=managed or not base.ros_connected, launch_problem=problem, launch_warning=warning,
                       residual_processes=self._residual_gazebo(managed), feedback=self._feedback or base.feedback,
                       events=events, cycles=self._cycles)


def _mode_named(value):
    try:
        return Mode(value)
    except ValueError:
        return None


class SettingsStore:
    """Small JSON file for the operator's last choices, kept with the session state."""

    def __init__(self, path):
        self._path = path

    def load(self):
        import json
        try:
            with open(self._path, encoding='utf-8') as handle:
                data = json.load(handle)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def save(self, data):
        import json
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        with open(self._path, 'w', encoding='utf-8') as handle:
            json.dump(data, handle)
