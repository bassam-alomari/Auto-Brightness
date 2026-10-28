"""Session-only trials, active-power curve selection and reviewed problem reports."""

import copy
import time


def effective_curve(preferences, power):
    if preferences.get("separate_power_curves"):
        return preferences["power_curves"][power]
    return {"curve": preferences["brightness_curve"], "points": preferences["custom_points"]}


class Experience:
    trial_original = None
    trial_transition = False
    trial_ending = False
    trial_deadline = None
    trial_timer = None

    def refresh_power(self):
        import ctypes
        from .ui import Power

        power = Power()
        try:
            if ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(power)):
                self.power_mode = "ac" if power.ac == 1 else "battery"
        except AttributeError:
            pass

    def target_for_level(self, level):
        from .adaptive import image_target
        from .comfort import target

        if not self.running:
            self.refresh_power()
        curve = effective_curve(self.preferences, self.power_mode)
        low, high = (
            self.preferences[self.power_mode + "_limits"]
            if self.preferences["power_profiles"]
            else (self.low.get(), self.high.get())
        )
        return (
            target(level, low, high, curve["points"])
            if curve["curve"] == "custom"
            else image_target(level, low, high, curve["curve"])
        )

    def begin_trial(self, candidate):
        if (
            self.trial_original is not None
            or self.running
            or self.busy
            or self.resume_pending
            or self.pause_reasons
        ):
            raise ValueError("Stop automatic mode before changing settings.")
        original = copy.deepcopy(self.preferences)
        self.trial_transition = True
        try:
            self.apply_preferences(candidate)
        finally:
            self.trial_transition = False
        self.trial_original = original
        self.trial_deadline = time.monotonic() + 60
        self.trial_timer = self.root.after(1000, self.trial_tick)

    def trial_remaining(self):
        import math

        return max(0, math.ceil((self.trial_deadline or 0) - time.monotonic()))

    def trial_tick(self):
        self.trial_timer = None
        if self.trial_original is None or self.trial_ending:
            return
        if self.trial_remaining() == 0:
            self.end_trial(False)
        else:
            self.trial_timer = self.root.after(1000, self.trial_tick)

    def end_trial(self, keep):
        if self.trial_original is None or self.trial_ending:
            return
        self.trial_ending = True
        original = copy.deepcopy(self.trial_original)
        proposed = copy.deepcopy(self.preferences)
        if self.trial_timer is not None:
            self.root.after_cancel(self.trial_timer)
            self.trial_timer = None
        self.stop()

        def finish():
            if self.busy:
                self.root.after(100, finish)
                return
            self.trial_original = None
            self.trial_deadline = None
            pending_controller = self.controller if self.original is not None else None
            proposed["resume_was_running"] = False
            if keep:
                try:
                    self.apply_preferences(proposed)
                    if self.original is not None:
                        self.controller = pending_controller
                    self.trial_ending = False
                    return
                except ValueError:
                    self.error_details = (
                        "Trial settings could not be saved. Previous settings restored."
                    )
            self.trial_transition = True
            try:
                self.apply_preferences(original)
                if self.original is not None:
                    self.controller = pending_controller
            finally:
                self.trial_transition = False
                self.trial_ending = False

        finish()

    def close(self):
        if self.trial_original is not None:
            self.exit_running_intent = False
            self.end_trial(False)

            def finish():
                if self.trial_original is not None or self.busy:
                    self.root.after(100, finish)
                else:
                    super(Experience, self).close()

            self.root.after(100, finish)
            return
        super().close()

    def decision_values(self):
        from .adaptive import image_target
        from .comfort import target

        meter = self.last_meter
        if not meter:
            return None
        curve = effective_curve(self.preferences, self.power_mode)
        low, high = (
            (self.controller.low, self.controller.high)
            if self.controller
            else (self.low.get(), self.high.get())
        )
        level = meter["level"]
        raw = (
            target(level, low, high, curve["points"])
            if curve["curve"] == "custom"
            else image_target(level, low, high, curve["curve"])
        )
        return dict(
            image=round(level, 1), raw=raw, target=meter["target"], current=self.display_value.get()
        )


def problem_bundle(engine, version):
    from .recovery import diagnostic_report

    report = diagnostic_report(engine, version)
    report["power_mode"] = (
        engine.power_mode if engine.power_mode in ("ac", "battery") else "unknown"
    )
    report["trial_active"] = engine.trial_original is not None
    report["device_health"] = {
        "selected_camera_in_last_discovery": engine.selected_device() is not None,
        "display_type": "internal"
        if engine.preferences["display_target"] == "internal"
        else "external",
        "waiting_for_device": "device" in engine.pause_reasons,
        "camera_retry": engine.diagnostic == "camera_retry",
    }
    report["features"] = {
        key: engine.preferences[key]
        for key in (
            "cover_guard",
            "separate_power_curves",
            "directional_response",
            "spatial_protection",
            "reduce_motion",
        )
    }
    return report
