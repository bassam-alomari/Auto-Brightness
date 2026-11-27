"""Run brightness decisions against injected device operations."""

import time
from dataclasses import dataclass
from threading import Lock


@dataclass(frozen=True)
class Decision:
    current: int
    target: int
    reason: str
    applied: bool = False


def evaluate_target(controller, reading, current, now):
    target = controller.update(reading, current, now)
    return Decision(current, target, controller.reason)


class ControlSession:
    def __init__(self, controller, read, write, monitor=False):
        self.controller = controller
        self.read = read
        self.write = write
        self.monitor = monitor
        self._lock = Lock()
        self._generation = 0

    def cancel(self):
        with self._lock:
            self._generation += 1

    def generation(self):
        with self._lock:
            return self._generation

    def evaluate(self, reading, generation, cancelled=lambda: False):
        current = self.read()
        with self._lock:
            if generation != self._generation or cancelled():
                return Decision(current, current, "cancelled")
            decision = evaluate_target(self.controller, reading, current, time.monotonic())
        if self.monitor or decision.target == current:
            return decision
        fresh = self.read()
        with self._lock:
            if generation != self._generation or cancelled():
                return Decision(fresh, fresh, "cancelled")
            if self.controller.observe(fresh, time.monotonic()):
                return Decision(fresh, fresh, "manual_hold")
            actual = self.write(decision.target)
            self.controller.committed(actual)
        return Decision(actual, decision.target, decision.reason, True)
