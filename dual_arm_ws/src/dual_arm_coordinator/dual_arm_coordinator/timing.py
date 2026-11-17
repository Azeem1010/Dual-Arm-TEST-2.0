"""Where a task run spends its time, step by step (user request 2026-11-17: speed up the prototype).

The workflow marks each step (TaskContext.step); gateways mark inside a step what they wait for
(span). A step lasts until the next step started by the same thread: the sequential run uses one
thread, so any step ends the previous one; an overlapped run has one thread per arm. The part of a
step no span covers is 'other' (workflow logic, journal writes, planning-scene updates).

Only records; nothing here changes what the task does. Outside a run (start..finish) it is idle.
"""
from contextlib import contextmanager
import csv
import functools
from pathlib import Path
import threading
import time

# plan: MoveIt planning (MoveGroup planning_time), move: action until its result, arrive: waiting for
# the joint readings to reach the target, still: waiting for the arm to stop moving, check: state
# validity calls, camera_wait: waiting for an env image after the arms settled, camera: the scene
# service call, echo: waiting for the ESP32 echo, vacuum: suction build-up or vent wait.
KINDS = ('plan', 'move', 'arrive', 'still', 'check', 'camera_wait', 'camera', 'echo', 'vacuum')


class StepTimer:
    def __init__(self, clock=time.monotonic, on_step=None):
        self._clock, self.on_step = clock, on_step
        self._lock = threading.Lock()
        self._running, self._started = False, 0.0
        self._records, self._open = [], {}

    def start(self):
        with self._lock:
            self._running, self._started = True, self._clock()
            self._records, self._open = [], {}

    def step(self, arm, state):
        if not self._running:
            return
        now = self._clock()
        thread = threading.get_ident()
        with self._lock:
            closed = self._close(thread, now)
            self._open[thread] = {'arm': arm, 'step': state, 'start': now - self._started, 'parts': {}}
        if closed is not None and self.on_step is not None:
            self.on_step(format_step(closed))

    def add(self, kind, seconds):
        """Count seconds of kind towards the step this thread is in; ignored outside a step."""
        with self._lock:
            record = self._open.get(threading.get_ident())
            if record is not None:
                record['parts'][kind] = record['parts'].get(kind, 0.0) + seconds

    @contextmanager
    def span(self, kind):
        started = self._clock()
        try:
            yield
        finally:
            self.add(kind, self._clock() - started)

    def finish(self):
        """End the run; returns every step in the order they ended."""
        if not self._running:
            return []
        now = self._clock()
        with self._lock:
            for thread in list(self._open):
                self._close(thread, now)
            self._running = False
            return list(self._records)

    def _close(self, thread, now):
        record = self._open.pop(thread, None)
        if record is not None:
            record['duration'] = now - self._started - record['start']
            self._records.append(record)
        return record


# The timer shared by the workflow and the gateways of this process.
TIMER = StepTimer()


def span(kind):
    return TIMER.span(kind)


def add(kind, seconds):
    TIMER.add(kind, seconds)


def timed(kind):
    """Decorator: the whole call counts as kind for the step the calling thread is in."""
    def wrap(function):
        @functools.wraps(function)
        def inner(*args, **kwargs):
            with TIMER.span(kind):
                return function(*args, **kwargs)
        return inner
    return wrap


def other(record):
    return record['duration'] - sum(record['parts'].values())


def _parts_text(record):
    parts = sorted(record['parts'].items(), key=lambda item: -item[1])
    if record['parts']:
        rest = other(record)
        if abs(rest) >= 0.005:
            parts.append(('other', rest))
    return ', '.join(f'{kind} {seconds:.2f}' for kind, seconds in parts)


def format_step(record):
    parts = _parts_text(record)
    line = f"TIMING {record['arm']}:{record['step']} {record['duration']:.2f} s"
    return f'{line} ({parts})' if parts else line


def summary(records, objects):
    """A few lines for the log: totals by kind and the slowest steps."""
    if not records:
        return 'TIMING SUMMARY no steps recorded'
    total = max(record['start'] + record['duration'] for record in records)
    head = f'TIMING SUMMARY {objects} object(s), {total:.2f} s'
    if objects:
        head += f', {total / objects:.2f} s per object'
    kinds = {}
    for record in records:
        for kind, seconds in record['parts'].items():
            kinds[kind] = kinds.get(kind, 0.0) + seconds
        kinds['other'] = kinds.get('other', 0.0) + other(record)
    busy = sum(kinds.values()) or 1.0
    lines = [head, 'by kind (summed over both arms): ' + ', '.join(
        f'{kind} {seconds:.2f} s ({100 * seconds / busy:.0f}%)'
        for kind, seconds in sorted(kinds.items(), key=lambda item: -item[1]))]
    steps = {}
    for record in records:
        name = f"{record['arm']}:{record['step']}"
        steps[name] = steps.get(name, 0.0) + record['duration']
    lines.append('slowest steps: ' + ', '.join(
        f'{name} {seconds:.2f} s' for name, seconds in sorted(steps.items(), key=lambda item: -item[1])[:8]))
    return '\n'.join(lines)


def write_csv(records, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(['arm', 'step', 'start', 'duration', *KINDS, 'other'])
        for record in records:
            writer.writerow([record['arm'], record['step'], f"{record['start']:.3f}", f"{record['duration']:.3f}",
                             *(f"{record['parts'].get(kind, 0.0):.3f}" for kind in KINDS),
                             f'{other(record):.3f}'])
