"""Overlapped transfer (prototype): arm 1 picks the next object while arm 2 carries the previous one.

Each arm runs in its own thread. Zone B keeps its single owner: arm 1 puts an object into B only
after arm 2 has taken the previous one out and left B, and arm 2 enters B only once arm 1 has
verified its placement and left. Between those hand-overs both arms may move at once; the motion
gateway keeps them in separate x lanes (lanes.py), so this module decides only the order.

When one arm stops with an error the other finishes the part it is in (arm 1 a pick from A or a
placement in B, arm 2 a whole B-to-C transfer) and then stops too. A cancel or safety stop
reaches both arms through guard() at once.
"""
import threading

from .arm1_workflow import Arm1Workflow
from .arm2_workflow import Arm2Workflow
from .ports import TaskCancelled, TaskFault

_POLL_S = 0.05


class OverlapRun:
    def __init__(self, context, preflight_slot):
        """preflight_slot(slot) checks that arm 2 can place into slot, as before a sequential cycle."""
        self.ctx, self._preflight_slot = context, preflight_slot
        self._condition = threading.Condition()
        self._b_object = False
        self._arm1_done = False
        self._errors = []
        self.a_empty_after = None

    def run(self, limit):
        """Move at most limit objects; returns how many arm 1 picked from A in this run."""
        ctx, io = self.ctx, self.ctx.io
        io.guard()
        occupied = ctx.occupied()
        free = occupied.count(False)
        if not free:
            return 0
        view = ctx.zone_view()
        if not view.b_arm_clear:
            raise TaskFault('Zone B is not clear at the start of a cycle')
        ctx.require_consistent_c(view)
        target = min(limit, free)
        # An object an earlier run left in B (auto resume) is delivered first.
        self._b_object = view.b_has_object
        to_pick = target - (1 if self._b_object else 0)

        # Checked once, with both arms HOME and no task object in B: later the other arm or the
        # object in B would make these poses look invalid.
        if to_pick:
            Arm1Workflow(ctx).check_b_poses()
        first = occupied.index(False) + 1
        if ctx.settings.b_joints:
            io.check_b('arm2')
        for slot in range(first, first + target):
            self._preflight_slot(slot)

        self._arm1_done = to_pick == 0
        picked = [0]
        workers = [threading.Thread(target=self._arm1, args=(to_pick, picked), name='overlap-arm1', daemon=True),
                   threading.Thread(target=self._arm2, name='overlap-arm2', daemon=True)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()
        if self._errors:
            cancelled = [error for error in self._errors if isinstance(error, TaskCancelled)]
            raise (cancelled or self._errors)[0]
        return picked[0]

    # --- shared state ---

    def _stop(self, error):
        with self._condition:
            self._errors.append(error)
            self._condition.notify_all()

    def _halted(self):
        with self._condition:
            return bool(self._errors)

    def _wait_for(self, ready):
        """Wait until ready() or the other arm stopped; guard() still ends the wait on a cancel."""
        with self._condition:
            while not ready() and not self._errors:
                self._condition.wait(_POLL_S)
                self.ctx.io.guard()
            return not self._errors

    def _set_b_object(self, value):
        with self._condition:
            self._b_object = value
            self._condition.notify_all()

    # --- workers ---

    def _arm1(self, to_pick, picked):
        try:
            for _ in range(to_pick):
                if self._halted():
                    return
                if not self.ctx.zone_view().a_has_object:
                    self.a_empty_after = picked[0]
                    return
                workflow = Arm1Workflow(self.ctx)
                workflow.pick_a(overlapped=True)
                picked[0] += 1
                # HOME holding the object until arm 2 has taken the previous one out of B.
                if not self._wait_for(lambda: not self._b_object):
                    return
                workflow.place_b()
                self._set_b_object(True)
        except BaseException as error:  # noqa: B036 - handed to the main thread
            self._stop(error)
        finally:
            with self._condition:
                self._arm1_done = True
                self._condition.notify_all()

    def _arm2(self):
        try:
            while True:
                if not self._wait_for(lambda: self._b_object or self._arm1_done):
                    return
                with self._condition:
                    if not self._b_object:
                        return
                Arm2Workflow(self.ctx, on_b_released=lambda: self._set_b_object(False)).run()
                journal = self.ctx.journal
                journal.update(completed=journal.data['completed'] + 1)
        except BaseException as error:  # noqa: B036 - handed to the main thread
            self._stop(error)
