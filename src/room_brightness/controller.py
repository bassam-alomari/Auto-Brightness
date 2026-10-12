"""Hardware-independent filtering and brightness decisions."""

from dataclasses import dataclass
import math


def target(light: float, dark: float, bright: float, low: int, high: int) -> int:
    """Map a relative camera measurement into user-selected brightness limits."""
    if not all(math.isfinite(v) for v in (light, dark, bright)):
        raise ValueError("Light measurements must be finite.")
    if not 0 <= dark < bright <= 255 or bright - dark < 8:
        raise ValueError("Calibration needs at least 8 points of light separation.")
    if not 0 <= low < high <= 100:
        raise ValueError("Brightness limits must satisfy 0 <= minimum < maximum <= 100.")
    fraction = max(0.0, min(1.0, (light - dark) / (bright - dark)))
    return round(low + (high - low) * fraction)


@dataclass
class BrightnessController:
    """Require persistent changes and apply no more than five points per sample."""

    dark: float
    bright: float
    low: int = 25
    high: int = 80
    filtered: float | None = None
    direction: int = 0
    confirmations: int = 0

    def __post_init__(self):
        target(self.dark, self.dark, self.bright, self.low, self.high)

    def update(self, measurement: float, current: int) -> int:
        if not math.isfinite(measurement) or not 0 <= measurement <= 255:
            raise ValueError("Camera light level must be between 0 and 255.")
        if not 0 <= current <= 100:
            raise ValueError("Set screen brightness to at least 10% and verify again.")
        self.filtered = (
            measurement if self.filtered is None else 0.3 * measurement + 0.7 * self.filtered
        )
        desired = target(self.filtered, self.dark, self.bright, self.low, self.high)
        delta = desired - current
        direction = 1 if delta > 0 else -1
        raw_delta = target(measurement, self.dark, self.bright, self.low, self.high) - current
        raw_direction = 1 if raw_delta > 0 else -1
        if abs(delta) < 6 or abs(raw_delta) < 6 or raw_direction != direction:
            self.confirmations = 0
        else:
            self.confirmations = self.confirmations + 1 if direction == self.direction else 1
        self.direction = direction
        if self.confirmations < 2:
            return current
        return current + max(-5, min(5, delta))
