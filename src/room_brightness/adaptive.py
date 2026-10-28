"""Relative automatic adaptation with manual override priority and artifact guards."""

from dataclasses import dataclass, field
from collections import deque
import math
import statistics


def curve_target(shift, preferred, low, high, sensitivity=1.0):
    """Asymmetric smooth curve spanning the user's entire comfort range."""
    preferred = max(low, min(high, preferred))
    span = high - preferred if shift >= 0 else preferred - low
    response = math.tanh(abs(shift) * sensitivity / 0.7)
    return round(preferred + (span * response if shift >= 0 else -span * response))


def scene_target(score, low, high, sensitivity=1.0):
    """Approximate exposure-normalized scene curve; not a lux calibration."""
    position = max(0.0, min(1.0, (score + 3.5) / 5.0))
    smooth = position * position * (3 - 2 * position)
    return round(low + (high - low) * smooth ** (1 / sensitivity))


CURVES = {
    "custom": ("Your curve", "كيرفك", [(12, 0), (15, 50), (20, 70), (25, 90), (27, 100)]),
    "linear": ("Linear", "خطي", [(12, 0), (40, 100)]),
    "smooth": ("Smooth", "ناعم", [(12, 0), (24, 50), (40, 100)]),
    "gentle": ("Gentle", "هادئ", [(12, 0), (21, 30), (28, 50), (45, 100)]),
    "responsive": ("Responsive", "سريع الاستجابة", [(12, 0), (18, 55), (24, 80), (30, 100)]),
    "night": ("Night comfort", "راحة ليلية", [(12, 0), (21, 20), (28, 35), (40, 60), (65, 100)]),
    "day": ("Daylight", "نهاري", [(12, 0), (18, 60), (25, 85), (30, 100)]),
    "balanced": ("Balanced", "متوازن", [(12, 0), (21, 40), (28, 65), (36, 100)]),
    "contrast": ("High contrast", "تباين عالٍ", [(12, 0), (19, 20), (24, 75), (30, 100)]),
    "power": ("Battery saver", "توفير بطارية", [(12, 0), (21, 25), (30, 45), (50, 75), (80, 100)]),
}


def image_target(level, low, high, curve="custom"):
    """User-defined image curve with smooth interpolation through exact knots."""
    source = CURVES.get(curve, CURVES["custom"])[2]
    if curve != "custom":
        scale = min(0.5, 18 / (source[-1][0] - 12))
        source = [(12 + (x - 12) * scale, y) for x, y in source]
    knots = list(source)
    knots[0] = (knots[0][0], low)
    if level <= 12:
        return low
    if level >= knots[-1][0]:
        return high
    for (x0, y0), (x1, y1) in zip(knots, knots[1:]):
        if level <= x1:
            t = (level - x0) / (x1 - x0)
            smooth = t * t * (3 - 2 * t)
            return max(low, min(high, round(y0 + (y1 - y0) * smooth)))
    return high


@dataclass
class AdaptiveController:
    low: int = 25
    high: int = 80
    sensitivity: float = 1.0
    mapping: str = "relative"
    image_curve: str = "custom"
    protect_dim: bool = True
    options: dict | None = None
    stability: object = None
    reason: str = ""
    reference_signature: list = field(default_factory=list)
    absolute_bias: int = 0
    manual_reference: bool = False
    expected: int | None = None
    anchor: float | None = None
    preferred: int = 50
    filtered: float | None = None
    hold_until: float = 0
    image_recovery: bool = False
    bright_samples: int = 0
    dark_samples: int = 0
    covered_samples: int = 0
    confirmations: int = 0
    direction: int = 0
    needs_anchor: bool = True
    anchor_zones: list = field(default_factory=list)
    scores: deque = field(default_factory=lambda: deque(maxlen=3))

    def __post_init__(self):
        if not 0 <= self.low < self.high <= 100:
            raise ValueError("Invalid brightness limits.")

    def observe(self, current, now):
        if self.expected is not None and current != self.expected:
            self.expected = current
            self.preferred = current
            self.manual_reference = True
            self.image_recovery = False
            self.bright_samples = 0
            self.hold_until = now + 180
            self.needs_anchor = True
            self.confirmations = 0
            self.scores.clear()
            self.reference_signature = []
            if self.stability is not None:
                self.stability.pending, self.stability.count = None, 0
            return True
        self.expected = current
        return False

    def update(self, measurement, current, now):
        self.reason = ""
        manual = self.observe(current, now)
        if manual or now < self.hold_until:
            self.dark_samples = 0
            return current
        self.covered_samples = (
            self.covered_samples + 1 if measurement.get("possibly_covered") is True else 0
        )
        if self.covered_samples and (self.options or {}).get("cover_guard", True):
            self.reason = "possible_cover" if self.covered_samples >= 2 else "uncertain"
            if self.stability is not None:
                self.stability.pending, self.stability.count = None, 0
            return current
        if self.mapping == "image":
            level = measurement.get("level")
            if (
                type(level) not in (int, float)
                or not math.isfinite(level)
                or not 0 <= level <= 255
                or measurement.get("confidence", 0) < 0.25
            ):
                self.reason = "uncertain"
                if self.stability is not None:
                    self.stability.pending, self.stability.count = None, 0
                return current
            self.reason = "image_curve"
            wanted = image_target(level, self.low, self.high, self.image_curve)
            if self.options is not None:
                from .comfort import Stability, target

                if self.image_curve == "custom":
                    wanted = target(level, self.low, self.high, self.options["custom_points"])
                if self.stability is None:
                    self.stability = Stability()
                wanted = self.stability.decide(
                    measurement,
                    wanted,
                    current,
                    self.options["stability_guard"],
                    self.options["deadband"],
                    (self.low, self.high),
                )
                self.reason = self.stability.reason or "image_curve"
            return wanted
        score = measurement["score"]
        if not math.isfinite(score) or measurement["confidence"] + 1e-6 < 0.25:
            self.reason = "uncertain"
            self.dark_samples = 0
            self.confirmations = 0
            return current
        # Explicit low-image rule requested by the user, independent of the
        # relative anchor. This is image darkness, not a calibrated lux reading.
        level = measurement.get("level")
        dark = (
            type(level) in (int, float)
            and math.isfinite(level)
            and 0 <= level <= 10
            and measurement["confidence"] >= 0.75
        )
        self.dark_samples = self.dark_samples + 1 if dark else 0
        if dark:
            self.bright_samples = 0
            self.reason = "confirming_dim" if self.dark_samples < 2 else "dark_floor"
            if self.dark_samples >= 2:
                self.confirmations = 0
                self.image_recovery = True
                # Re-anchor to confirmed darkness, so subsequent light increases
                # are compared to the dark room rather than the old bright scene.
                self.anchor = self.filtered = score
                self.preferred = self.low
                self.anchor_zones = measurement.get("zones", [])[:]
                self.reference_signature = measurement.get("scene_signature", [])[:]
                self.needs_anchor = False
                self.scores.clear()
                self.scores.append(score)
                return self.low
            return current

        recovery = self.image_recovery or current <= self.low
        if recovery and type(level) in (int, float) and math.isfinite(level):
            if level >= 16 and measurement["confidence"] >= 0.75:
                self.bright_samples += 1
                self.image_recovery = True
                if self.bright_samples < 2:
                    self.reason = "confirming_light"
                    return current
                # Exposure metadata may remain fixed or disagree with image
                # changes. Recover from darkness using the visible image curve.
                position = max(0.0, min(1.0, (level - 10) / 30))
                response = position * position * (3 - 2 * position)
                self.reason = "light_recovery"
                return round(self.low + (self.high - self.low) * response)
            self.bright_samples = 0
            self.reason = "uncertain"
            return current

        from .vision import scene_distance

        signature = measurement.get("scene_signature", [])
        zones = measurement.get("zones", [])
        uniform_change = False
        if self.anchor is not None and len(zones) == len(self.anchor_zones) and zones:
            raw_direction = 1 if score > self.anchor else -1
            uniform_change = abs(score - self.anchor) >= 0.4 and sum(
                (new - old) * raw_direction > 0.15 for new, old in zip(zones, self.anchor_zones)
            ) >= math.ceil(0.75 * len(zones))
        if (
            not self.needs_anchor
            and self.reference_signature
            and signature
            and not uniform_change
            and scene_distance(self.reference_signature, signature) > 0.35
        ):
            self.reason = "scene_changed"
            self.confirmations = 0
            return current
        zones = measurement.get("zones", [])
        if self.needs_anchor:
            self.anchor = self.filtered = score
            self.preferred = current if self.manual_reference else max(current, self.low)
            self.reference_signature = signature[:]
            self.anchor_zones = zones[:]
            if self.manual_reference and measurement.get("exposure_corrected"):
                self.absolute_bias = current - scene_target(
                    score, self.low, self.high, self.sensitivity
                )
                self.manual_reference = False
            self.needs_anchor = False
            self.scores.clear()
            self.scores.append(score)
            return max(current, self.preferred) if self.protect_dim else current
        self.scores.append(score)
        median = statistics.median(self.scores)
        self.filtered = 0.65 * median + 0.35 * self.filtered
        shift = self.filtered - self.anchor
        raw_shift = score - self.anchor
        desired = curve_target(shift, self.preferred, self.low, self.high, self.sensitivity)
        absolute = self.mapping == "scene" and measurement.get("exposure_corrected", False)
        if absolute:
            desired = max(
                self.low,
                min(
                    self.high,
                    scene_target(self.filtered, self.low, self.high, self.sensitivity)
                    + self.absolute_bias,
                ),
            )
        # The configured floor prevents unreadable brightness, while allowing
        # confirmed room darkening to lower an initially bright screen.
        desired = max(self.low, min(self.high, desired))
        delta = desired - current
        direction = 1 if delta > 0 else -1
        coherent = True
        if len(zones) == len(self.anchor_zones) and zones:
            changes = [new - old for new, old in zip(zones, self.anchor_zones)]
            coherent = sum(change * direction > 0.03 for change in changes) >= math.ceil(
                0.5 * len(changes)
            )
        eligible = (
            abs(delta) >= 2
            if absolute
            else (
                abs(delta) >= 2
                and abs(raw_shift) >= 0.10
                and raw_shift * direction > 0
                and coherent
            )
        )
        self.confirmations = (
            self.confirmations + 1 if eligible and direction == self.direction else int(eligible)
        )
        self.direction = direction
        required = 3 if self.protect_dim and direction < 0 else 2
        if self.confirmations < required:
            if eligible and direction < 0:
                self.reason = "confirming_dim"
            return current
        return desired

    def committed(self, actual):
        self.expected = actual
