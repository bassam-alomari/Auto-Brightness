"""Explicit multi-display coordination and non-persistent, review-only learning evidence."""

import time
from .quality import MultiDisplays, PreferenceEvidence
from .experience import effective_curve


class ReviewEngine:
    def init_review(self):
        self.secondary_displays = MultiDisplays()
        self.preference_evidence = PreferenceEvidence()

    @property
    def multi_active(self):
        return self.preferences.get("multi_display_enabled", False) and any(
            identity != self.preferences["display_target"]
            for identity in self.preferences.get("multi_display_targets", [])
        )

    def update_secondaries(self, reading):
        self.secondary_displays.process(reading, self.preferences, self.power_mode, self.cancel)

    def handle_error(self, operation, error):
        super().handle_error(operation, error)
        if not self.running and not self.resume_pending and not self.pause_reasons:
            if self.busy and self.operation == "restore":
                self.root.after(100, self.restore_after_error)
            else:
                self.restore_after_error()

    def restore_after_error(self):
        if (
            self.running
            or self.resume_pending
            or self.pause_reasons
            or not self.secondary_displays.states
        ):
            return
        if self.busy:
            self.root.after(100, self.restore_after_error)
            return
        self.restore_secondary_displays()

    def restore_secondary_displays(self, done=lambda _: None):
        def completed(results):
            if "restore_failed" in results.values():
                self.health_events.append(
                    dict(time=time.monotonic(), category="secondary_restore_failed")
                )
            done(results)

        enabled = self.restore.get()
        self.work(lambda: self.secondary_displays.restore(enabled), completed, "restore_multi")

    def finish_stop(self):
        if self.busy:
            return
        if hasattr(self, "secondary_displays") and self.secondary_displays.states:

            def done(results):
                if "restore_failed" in results.values():
                    self.health_events.append(
                        dict(time=time.monotonic(), category="secondary_restore_failed")
                    )
                self.finish_stop()

            self.work(
                lambda: self.secondary_displays.restore(self.restore.get()), done, "restore_multi"
            )
            return
        super().finish_stop()

    def capture_preference(self, value):
        meter = self.last_meter
        if (
            self.trial_original is not None
            or not self.preferences["preference_suggestions"]
            or not meter
            or not self.history
        ):
            return
        self.refresh_power()
        now = time.monotonic()
        if (
            now - self.history[-1][0] > 60
            or meter.get("quality", 0) < 0.35
            or meter.get("reason") in ("exposure_settling", "possible_cover", "uncertain")
        ):
            return
        context = (self.camera_id, self.preferences["display_target"], self.power_mode)
        self.preference_evidence.observe(meter["level"], int(value), context, now)

    def suggested_curve(self):
        self.refresh_power()
        curve = effective_curve(self.preferences, self.power_mode)
        if curve["curve"] != "custom":
            return None
        context = (self.camera_id, self.preferences["display_target"], self.power_mode)
        return self.preference_evidence.proposal(curve["points"], context, time.monotonic())
