"""Overlapped transfer (prototype): keep the two arms in separate ranges of world x.

arm1 stands at x -0.10 and works zone A (-x), arm2 at +0.10 and works zone C (+x); only zone B
lies between them. Before an arm moves it reserves the x range every joint of its trajectory
sweeps, padded by the clearance on each side. The reservation is granted only while it stays
clear of the other arm, which is either the other arm's own reservation while it moves or the
range its joints occupy where it stands. Checking and reserving happen under one lock, so two
arms can never both be granted overlapping ranges.

This compares x only: it is conservative in y and z, and it knows nothing about the link
shapes beyond the clearance. It is the model's view, so it cannot see calibration error.
"""
import threading
import time

from .workflow.ports import TaskFault

ARMS = ('arm1', 'arm2')
_POLL_S = 0.05


def overlaps(first, second):
    return first[0] < second[1] and second[0] < first[1]


class XLanes:
    def __init__(self, standing, clearance_m, wait_s, clock=time.monotonic):
        """standing(arm) returns the unpadded (low, high) x range of arm's joints where it is now."""
        self._standing, self._clearance, self._wait = standing, float(clearance_m), float(wait_s)
        self._clock = clock
        self._moving = {}
        self._condition = threading.Condition()

    def padded(self, low, high):
        return (low - self._clearance, high + self._clearance)

    def _other_range(self, arm):
        other = next(name for name in ARMS if name != arm)
        if other in self._moving:
            return other, self._moving[other]
        return other, self.padded(*self._standing(other))

    def reserve(self, arm, low, high, guard, label):
        """Block until arm may sweep [low, high] (unpadded), then hold it until finish(arm)."""
        wanted = self.padded(low, high)
        deadline = self._clock() + self._wait
        with self._condition:
            if arm in self._moving:
                raise TaskFault(f'{label}: {arm} already holds a lane')
            while True:
                other, held = self._other_range(arm)
                if not overlaps(wanted, held):
                    self._moving[arm] = wanted
                    return wanted
                if self._clock() >= deadline:
                    raise TaskFault(f'{label}: {arm} waited {self._wait:.0f} s for {other} to clear x '
                                    f'{wanted[0]:.3f}..{wanted[1]:.3f} (it holds {held[0]:.3f}..{held[1]:.3f})')
                # guard() may raise a cancel; it never waits, so the lock is held only briefly.
                guard()
                self._condition.wait(_POLL_S)

    def finish(self, arm):
        with self._condition:
            self._moving.pop(arm, None)
            self._condition.notify_all()

    def moving(self, arm):
        with self._condition:
            return self._moving.get(arm)
