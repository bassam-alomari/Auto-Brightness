"""Exposure settling, bounded preference evidence and explicit secondary display sessions."""

import copy
import math
import time
from collections import deque


def number(value):
    return type(value) in (float, int) and math.isfinite(value)


class ExposureGate:
    def __init__(self):
        self.previous = None
        self.settling = False
        self.stable = 0

    def allow(self, reading):
        exposure = reading.get("exposure")
        gain = reading.get("gain")
        current = (exposure if number(exposure) else None, gain if number(gain) else None)
        unstable = reading.get("exposure_unstable") is True
        if self.previous:
            a, b = self.previous
            unstable |= number(exposure) and number(a) and abs(exposure - a) > 0.25
            unstable |= number(gain) and number(b) and abs(gain - b) > max(2, abs(b) * 0.1)
        self.previous = current
        if unstable:
            self.settling = True
            self.stable = 0
            return False
        if self.settling:
            # Missing metadata cannot count as evidence that exposure settled.
            if current == (None, None):
                return False
            self.stable += 1
            if self.stable < 2:
                return False
            self.settling = False
        return True


class PreferenceEvidence:
    def __init__(self):
        self.samples = deque(maxlen=60)
        self.last_context = None
        self.last_time = -math.inf

    def observe(self, level, value, context, now):
        if (
            not number(level)
            or not 12 < level < 254
            or type(value) is not int
            or not 0 <= value <= 100
        ):
            return
        # Repeated callbacks for one adjustment do not become independent evidence.
        if any(row[3] == context and 0 <= now - row[0] < 30 for row in self.samples):
            return
        self.samples.append((now, level, value, context))
        self.last_context, self.last_time = context, now

    def proposal(self, points, context, now):
        from .comfort import learned_points, target
        import statistics

        recent = [row for row in self.samples if row[3] == context and 0 <= now - row[0] <= 86400]
        if len(recent) < 3:
            return None
        anchor = recent[-1][1]
        cluster = [row for row in recent if abs(row[1] - anchor) <= 1.5]
        if len(cluster) < 3:
            return None
        level = statistics.median(row[1] for row in cluster)
        values = [row[2] for row in cluster]
        if max(values) - min(values) > 12:
            return None
        wanted = round(statistics.median(values))
        if abs(target(level, 0, 100, points) - wanted) < 3:
            return None
        try:
            return learned_points(points, level, wanted)
        except ValueError:
            return None


class DisplayControl:
    def __init__(self, identity):
        self.identity = identity

    def read(self):
        from .brightness import brightness

        return brightness(display=self.identity)

    def write(self, value):
        from .brightness import brightness

        actual = brightness(value, display=self.identity)
        if self.identity == "internal" and actual != value:
            raise RuntimeError("Brightness readback mismatch.")
        return actual

    def verify(self):
        old = self.read()
        try:
            self.write(old + 5 if old <= 95 else old - 5)
        finally:
            self.write(old)
        return old

    def smooth(self, current, wanted, cancel, progress, duration):
        from .brightness import smooth_to

        return smooth_to(current, wanted, cancel, progress, duration, display=self.identity)


class MultiDisplays:
    def __init__(self):
        self.states = {}
        self.status = {}

    def process(self, reading, preferences, power, cancel, now=None, factory=DisplayControl):
        from .adaptive import AdaptiveController
        from .experience import effective_curve
        from .tuning import transition_duration
        from .settings import validate

        now = time.monotonic() if now is None else now
        targets = (
            preferences["multi_display_targets"] if preferences["multi_display_enabled"] else []
        )
        for identity in targets:
            if identity == preferences["display_target"] or cancel.is_set():
                continue
            record = self.states.setdefault(identity, dict(controller=None, original=None, retry=0))
            if now < record["retry"]:
                continue
            control = factory(identity)
            try:
                current = control.read()
                if record["controller"] is None:
                    record["original"] = control.verify()
                    record["controller"] = AdaptiveController(mapping="image", expected=current)
                profile = copy.deepcopy(preferences)
                profile.update(preferences["display_profiles"].get(identity, {}))
                profile = validate(profile)
                curve = effective_curve(profile, power)
                controller = record["controller"]
                controller.low, controller.high = (
                    profile[power + "_limits"]
                    if profile["power_profiles"]
                    else (profile["low"], profile["high"])
                )
                controller.options = profile
                controller.options["custom_points"] = curve["points"]
                controller.image_curve = curve["curve"]
                wanted = controller.update(reading, current, now)
                if now < controller.hold_until:
                    record["original"] = current
                if wanted != current and not cancel.is_set():
                    current, manual = control.smooth(
                        current,
                        wanted,
                        cancel,
                        controller.committed,
                        transition_duration(profile, current, wanted),
                    )
                    if manual:
                        controller.observe(current, time.monotonic())
                        record["original"] = current
                    else:
                        controller.committed(current)
                self.status[identity] = dict(
                    state="manual_hold"
                    if now < controller.hold_until
                    else controller.reason or "following",
                    current=current,
                    target=wanted,
                )
            except Exception as error:
                from .recovery import error_category

                category = error_category("control", error)
                record["retry"] = (
                    math.inf
                    if category
                    in (
                        "permission_denied",
                        "brightness_verification_failed",
                        "brightness_restore_failed",
                    )
                    else now + 10
                )
                self.status[identity] = dict(state=category)

    def restore(self, enabled, cancel=None, factory=DisplayControl):
        results = {}
        for identity, record in list(self.states.items()):
            if (
                record["original"] is None
                and self.status.get(identity, {}).get("state") == "brightness_verification_failed"
            ):
                results[identity] = "restore_failed"
                continue
            if not enabled or record["original"] is None:
                continue
            try:
                control = factory(identity)
                current = control.read()
                controller = record["controller"]
                if controller and controller.observe(current, time.monotonic()):
                    results[identity] = "manual_preserved"
                else:
                    control.write(record["original"])
                    results[identity] = "restored"
            except Exception:
                results[identity] = "restore_failed"
        self.states.clear()
        self.status = {identity: dict(state=state) for identity, state in results.items()}
        return results
