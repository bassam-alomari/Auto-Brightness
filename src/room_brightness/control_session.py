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

    def evaluate(self, reading, generation):
        current = self.read()
        with self._lock:
            if generation != self._generation:
                return Decision(current, current, "cancelled")
            target = self.controller.update(reading, current, time.monotonic())
            reason = self.controller.reason
        if self.monitor or target == current:
            return Decision(current, target, reason)
        fresh = self.read()
        with self._lock:
            if generation != self._generation:
                return Decision(fresh, fresh, "cancelled")
            if self.controller.observe(fresh, time.monotonic()):
                return Decision(fresh, fresh, "manual_hold")
            actual = self.write(target)
            self.controller.committed(actual)
        return Decision(actual, target, reason, True)
