"""Decides when motion must stop. Free of ROS for unit testing.

This is a software interlock. It does not replace a physical emergency stop.
"""
import threading
import time

# The operator interface translates this text; keep both in step.
OPERATOR_STOP = 'Operator software stop'


class SafetyMonitor:
    """Latches on the first unsafe input and stays latched until an explicit reset."""

    def __init__(self, estop_max_age_s, permit_max_age_s, require_estop=True, clock=time.monotonic):
        if estop_max_age_s <= 0 or permit_max_age_s <= 0:
            raise ValueError('Input ages must be positive')
        self._estop_max_age, self._permit_max_age = estop_max_age_s, permit_max_age_s
        self._require_estop, self._clock = require_estop, clock
        self._lock = threading.Lock()
        self._estop, self._estop_received = None, 0.0
        self._permit_received = None
        self._reason = None

    def on_estop(self, asserted):
        with self._lock:
            self._estop, self._estop_received = asserted, self._clock()

    def on_permit(self):
        with self._lock:
            self._permit_received = self._clock()

    def _problem(self):
        now = self._clock()
        if self._estop is True:
            return 'Emergency stop is asserted'
        if self._require_estop:
            if self._estop is None:
                return 'Emergency-stop heartbeat has not been received'
            if now - self._estop_received > self._estop_max_age:
                return 'Emergency-stop heartbeat is stale'
        # A coordinator that never started has not sent any motion to stop.
        if self._permit_received is not None and now - self._permit_received > self._permit_max_age:
            return 'Coordinator stopped responding'
        return None

    def update(self):
        """Evaluate the inputs; returns True only on the call that latches."""
        with self._lock:
            if self._reason is not None:
                return False
            self._reason = self._problem()
            return self._reason is not None

    def trigger(self, reason):
        """Latch on request, e.g. the operator's stop button. Returns True if this call latched.

        Unlike a missing heartbeat, nothing has to be fixed afterwards, so reset clears it.
        """
        with self._lock:
            if self._reason is not None:
                return False
            self._reason = reason
            return True

    @property
    def reason(self):
        with self._lock:
            return self._reason

    def problem_blocking_reset(self):
        with self._lock:
            return self._problem()

    def reset(self):
        """Clear the latch if every input is healthy now; returns the refusal or None."""
        with self._lock:
            problem = self._problem()
            if problem is None:
                self._reason = None
            return problem
