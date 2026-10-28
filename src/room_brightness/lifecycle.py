"""Opt-in session continuation, exact-device recovery and reversible preferences."""

import copy
import time
from collections import deque

CAMERA_KEYS = ("custom_points", "brightness_curve", "meter_region", "spatial_protection")


class Lifecycle:
    def init_lifecycle(self, discover):
        from .updater import UpdateClient

        self.update_client = UpdateClient(self.directory)
        self.settings_undo = deque(maxlen=20)
        self.previous_options = self.option_snapshot(self.preferences)
        self.undoing = False
        self.exiting = False
        self.run_requested = False
        self.last_resume_discovery = 0
        self.pause_until_ac = False
        self.device_retry_timer = None
        self.startup_resume_pending = (
            discover
            and self.preferences["resume_automatic"]
            and self.preferences["resume_was_running"]
        )
        if discover:
            self.lifecycle_timer = self.root.after(2000, self.lifecycle_tick)

    def option_snapshot(self, options):
        from .extras import PORTABLE_KEYS

        return {key: copy.deepcopy(options[key]) for key in PORTABLE_KEYS}

    def record_options(self, options):
        current = self.option_snapshot(options)
        if current != self.previous_options:
            if not self.undoing:
                self.settings_undo.append(copy.deepcopy(self.previous_options))
            self.previous_options = current

    def undo_options(self):
        if not self.settings_undo:
            return False
        candidate = copy.deepcopy(self.preferences)
        candidate.update(copy.deepcopy(self.settings_undo[-1]))
        self.undoing = True
        try:
            self.apply_preferences(candidate)
        finally:
            self.undoing = False
        self.settings_undo.pop()
        return True

    def save_camera_options(self):
        if self.camera_id:
            profiles = self.preferences["camera_profiles"]
            profiles[self.camera_id] = {
                key: copy.deepcopy(self.preferences[key]) for key in CAMERA_KEYS
            }
            while len(profiles) > 20:
                del profiles[next(iter(profiles))]

    def choose_device(self, device):
        from .settings import DEFAULTS

        if device["id"] != self.camera_id:
            self.save_camera_options()
            profile = self.preferences["camera_profiles"].get(device["id"], {})
            # A camera with no saved profile inherits the current choices on its first use.
            if profile:
                for key in CAMERA_KEYS:
                    self.preferences[key] = copy.deepcopy(profile.get(key, DEFAULTS[key]))
            self.last_meter = None
            self.history.clear()
        super().choose_device(device)

    def pause_until(self, when):
        from datetime import datetime, timedelta

        if not self.running and "timed" not in self.pause_reasons:
            return
        now = datetime.now()
        deadline = now.replace(hour=when.hour(), minute=when.minute(), second=0, microsecond=0)
        if deadline <= now:
            deadline += timedelta(days=1)
        self.clear_pause_timer()
        self.pause_until_ac = False
        self.pause_deadline = time.monotonic() + (deadline - now).total_seconds()
        self.session_pause("timed", True)
        self.pause_tick()

    def pause_until_charger(self):
        if not self.running and "timed" not in self.pause_reasons:
            return
        self.clear_pause_timer()
        self.pause_deadline = None
        self.pause_until_ac = True
        self.session_pause("timed", True)

    def wait_for_devices(self):
        self.session_pause("device", True)
        self.diagnostic = "device_wait"
        self.render_status()
        self.schedule_device_retry()

    def schedule_device_retry(self):
        if self.device_retry_timer is None and self.run_requested:
            self.device_retry_timer = self.root.after(10000, self.recover_devices)

    def recover_devices(self):
        from . import ui, monitors

        self.device_retry_timer = None
        if not self.run_requested or "device" not in self.pause_reasons:
            return
        if self.busy:
            self.schedule_device_retry()
            return

        def inspect():
            try:
                cameras = ui.list_devices()
                if not any(d["id"] == self.camera_id for d in cameras):
                    return None
                target = self.preferences["display_target"]
                if target != "internal" and not any(
                    d["id"] == target for d in monitors.list_displays()
                ):
                    return None
                ui.brightness()  # Read only; no switch to a different display.
                return cameras
            except Exception:
                return None

        def done(cameras):
            if not self.run_requested:
                return
            if cameras:
                self.devices = cameras
                selected = next(d for d in cameras if d["id"] == self.camera_id)
                self.choose_device(selected)
                self.session_pause("device", False)
            else:
                self.schedule_device_retry()

        self.work(inspect, done, "device_recovery")

    def lifecycle_tick(self):
        from . import __version__, ui
        import ctypes

        if self.exiting:
            return
        if self.pause_until_ac:
            power = ui.Power()
            if ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(power)) and power.ac == 1:
                self.resume_now()
        if (
            self.startup_resume_pending
            and not self.busy
            and self.selected_device()
            and self.preferences["onboarding_done"]
        ):
            self.startup_resume_pending = False
            self.start()
        elif (
            self.startup_resume_pending
            and not self.busy
            and time.monotonic() - self.last_resume_discovery >= 10
        ):
            self.last_resume_discovery = time.monotonic()
            self.refresh_cameras()
        client = self.update_client
        if self.preferences["update_checks"] and (
            client.last_attempt is None or time.monotonic() - client.last_attempt >= 86400
        ):
            client.check(__version__, self.preferences["auto_download_updates"])
        self.lifecycle_timer = self.root.after(2000, self.lifecycle_tick)

    def close(self):
        self.exiting = True
        self.startup_resume_pending = False
        self.preferences["resume_was_running"] = bool(
            getattr(self, "exit_running_intent", self.running or self.resume_pending)
        )
        self.update_client.closed = True
        self.update_client.cancel.set()
        super().close()
