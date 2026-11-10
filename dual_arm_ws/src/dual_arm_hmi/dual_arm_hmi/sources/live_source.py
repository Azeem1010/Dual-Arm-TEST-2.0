"""Live data plus starting and stopping the system. Task actions arrive in stage 3."""
from dataclasses import replace
import os
import time

from ..launcher.profiles import build_plan, domain_for, journal_settings, new_journal_path
from ..launcher.process import gazebo_processes
from ..model.state import Action, CommandFeedback, EventRecord, Level, Mode, Phase
from .base import DataSource

WIRED_ACTIONS = frozenset({Action.START_SYSTEM, Action.SHUTDOWN, Action.RESET_SIMULATION})
_RESIDUAL_CHECK_S = 2.0


class LiveSource(DataSource):
    def __init__(self, ros, launcher, profiles, workspace, settings_store, clock=time.time, reconnect=None):
        """ros watches ROS_DOMAIN_ID. reconnect(domain) gives a new monitor on another domain; without it the
        monitor never moves, which is only right when every mode shares one domain."""
        self._ros, self._launcher, self._profiles = ros, launcher, profiles
        self._reconnect, self._domain = reconnect, str(os.environ.get('ROS_DOMAIN_ID', '')).strip()
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
        self._note(Level.NEUTRAL, f'監看 ROS domain {domain}（{mode.value}）')

    # --- DataSource ---

    def close(self):
        # The system keeps running; a restarted interface adopts it.
        self._ros.close()

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
        self._events.insert(0, EventRecord(time.strftime('%H:%M:%S'), level, message))

    def invoke(self, action):
        if action not in WIRED_ACTIONS:
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
        events = tuple(self._events) + base.events
        return replace(base, phase=phase, mode=mode, monitor_only=False, wired_actions=WIRED_ACTIONS,
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
