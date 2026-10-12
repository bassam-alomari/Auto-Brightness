"""Qt timer adapter for the established serialized brightness engine."""

import queue
import threading
import time
import ctypes
from collections import deque

from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QMessageBox

from . import ui, startup
from .paths import DATA_DIR
from .settings import load_settings, resolve_language, resolve_theme
from .widgets import PALETTES


class Value:
    def __init__(self, value=None):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class Scheduler(QObject):
    qt_native = True

    def __init__(self):
        super().__init__()
        self.alive = True
        self.timers = {}
        self.sequence = 0

    def after(self, milliseconds, callback):
        self.sequence += 1
        key = self.sequence
        timer = QTimer(self)
        timer.setSingleShot(True)

        def invoke():
            self.timers.pop(key, None)
            timer.deleteLater()
            if self.alive:
                callback()

        timer.timeout.connect(invoke)
        self.timers[key] = timer
        timer.start(max(1, milliseconds))
        return key

    def after_cancel(self, key):
        timer = self.timers.pop(key, None)
        if timer:
            timer.stop()
            timer.deleteLater()

    def winfo_exists(self):
        return self.alive

    def destroy(self):
        self.alive = False
        for key in list(self.timers):
            self.after_cancel(key)


class Engine(ui.App):
    """Share tested control methods without creating a Tcl/Tk interpreter."""

    def __init__(self, scheduler, discover=True, directory=None):
        self.root = scheduler
        self.directory = directory or DATA_DIR
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.busy = self.running = self.verified = False
        self.operation = ""
        self.original = self.controller = self.timer = self.save_timer = None
        self.screen_timer = self.discovery_timer = None
        self.preferences = load_settings(self.directory)
        self.language = resolve_language(self.preferences["language"])
        self.theme = resolve_theme(self.preferences["theme"])
        self.palette = PALETTES[self.theme]
        self.view = "home"
        self.tray_icon = None
        self.last_meter = None
        self.history = deque(maxlen=180)
        self.pause_reasons = set()
        self.resume_pending = False
        self.diagnostic = ""
        self.power_mode = "ac"
        self.preview_enabled = False
        self.error_details = ""
        self.devices = []
        self.camera_id = self.preferences["camera_id"]
        self.calibration_id = self.preferences["calibration_id"]
        self.dark = self.preferences["dark"]
        self.light = self.preferences["bright"]
        self.camera = Value(self.preferences["camera_index"])
        self.camera_label = Value(self.t("finding"))
        self.display_value = Value("—")
        self.manual_value = Value(50)
        self.low = Value(self.preferences["low"])
        self.high = Value(self.preferences["high"])
        self.interval_ac = Value(self.preferences["interval_ac"])
        self.interval_battery = Value(self.preferences["interval_battery"])
        self.restore = Value(self.preferences["restore"])
        startup_error = None
        if discover and self.preferences.get("startup_defaults_revision") != 1:
            try:
                startup.set_enabled(True)
                self.preferences["startup_defaults_revision"] = 1
            except OSError as exc:
                startup_error = str(exc)
        self.startup_choice = Value(startup.is_enabled())
        self.preferences["startup"] = self.startup_choice.get()
        self.language_mode = Value(self.preferences["language"])
        self.status_title = Value("")
        self.status = Value("")
        self.status_state = ("auto_ready", "auto_welcome", {})
        self.render_status()
        self.poll_timer = scheduler.after(80, self.poll)
        self.environment_timer = scheduler.after(1500, self.sync_environment)
        if discover:
            self.persist()
            if startup_error:
                self.error_details = startup_error
                self.set_status("error", "startup_error")
            self.discovery_timer = scheduler.after(100, self.refresh_cameras)

    def work(self, function, done, operation):
        def completed(result):
            done(result)
            if operation == "test" and hasattr(self, "resume_original"):
                self.original = self.resume_original
                del self.resume_original

        return super().work(function, completed, operation)

    def persist(self):
        from .settings import save_settings

        device = self.selected_device()
        self.preferences.update(
            low=self.low.get(),
            high=self.high.get(),
            restore=self.restore.get(),
            interval_ac=self.interval_ac.get(),
            interval_battery=self.interval_battery.get(),
            camera_id=self.camera_id,
            camera_index=self.camera.get(),
            camera_name=device["name"] if device else self.preferences["camera_name"],
        )
        try:
            save_settings(self.directory, self.preferences)
            return True
        except OSError as exc:
            self.error_details = str(exc)
            self.set_status("error", "error_settings")
            return False

    def build(self):
        self.render_status()

    def update_controls(self):
        pass

    def update_meter(self):
        if self.last_meter:
            self.history.append(
                (
                    time.monotonic(),
                    self.last_meter["level"],
                    self.last_meter["target"],
                    self.last_meter["current"],
                )
            )
            self.diagnostic = self.last_meter.get("reason", "image_curve")

    def begin_pair_cycle(self):
        if self.pause_reasons or not self.running:
            return
        power = ui.Power()
        try:
            ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(power))
            self.power_mode = "ac" if power.ac == 1 else "battery"
        except AttributeError:
            self.power_mode = "ac"
        if self.controller:
            self.controller.options = dict(self.preferences)
            if self.preferences["power_profiles"]:
                self.controller.low, self.controller.high = self.preferences[
                    self.power_mode + "_limits"
                ]
            else:
                self.controller.low, self.controller.high = self.low.get(), self.high.get()
        super().begin_pair_cycle()

    def session_pause(self, reason, paused):
        if paused:
            self.pause_reasons.add(reason)
            self.resume_pending = self.resume_pending or self.running
            self.running = False
            self.cancel.set()
            for key in ("timer", "screen_timer"):
                timer = getattr(self, key, None)
                if timer is not None:
                    self.root.after_cancel(timer)
                    setattr(self, key, None)
            self.diagnostic = "paused"
            self.status_title.set(self.t("stopped"))
            self.status.set(
                "الكاميرا متوقفة أثناء القفل أو السكون"
                if self.language == "ar"
                else "Camera paused while locked or sleeping"
            )
        else:
            self.pause_reasons.discard(reason)
            self.try_resume()
            if not self.pause_reasons and not self.resume_pending and not self.running:
                self.finish_stop()

    def try_resume(self):
        if self.pause_reasons or not self.resume_pending:
            return
        if self.busy:
            self.root.after(200, self.try_resume)
            return
        self.resume_pending = False
        self.cancel.clear()
        # Re-verify the display and camera after resume; preserve the initial restore value.
        old = self.original
        self.verify(start_after=True)
        self.resume_original = old

    def start(self):
        if not self.pause_reasons:
            super().start()

    def stop(self):
        self.resume_pending = False
        super().stop()

    def finish_stop(self):
        if self.pause_reasons or self.resume_pending:
            return
        super().finish_stop()

    def learn_current(self):
        from .comfort import learned_points

        if (
            not self.last_meter
            or self.last_meter.get("quality", 0) < 0.35
            or time.monotonic() - (self.history[-1][0] if self.history else 0) > 60
        ):
            raise ValueError("Take a fresh light reading first.")
        if self.busy:
            raise ValueError("Wait for the current operation to finish.")
        points = learned_points(
            self.preferences["custom_points"],
            self.last_meter["level"],
            int(self.display_value.get()),
        )
        self.preferences["custom_points"] = points
        self.preferences["brightness_curve"] = "custom"
        if self.controller:
            self.controller.image_curve = "custom"
        self.persist()

    def handle_error(self, operation, error):
        self.diagnostic = "camera_error" if "camera" in str(error).lower() else "display_error"
        super().handle_error(operation, error)

    def update_readings(self):
        pass

    def draw_curve(self):
        pass

    def render_status(self):
        title, description, values = self.status_state
        self.status_title.set(self.t(title))
        self.status.set(self.t(description, **values))

    def show_details(self):
        QMessageBox.information(None, self.t("details"), self.error_details)

    def refresh_cameras(self):
        self.discovery_timer = None
        if self.busy or self.running:
            return
        self.cancel.clear()
        self.error_details = ""
        self.camera_label.set(self.t("finding"))

        def done(devices):
            self.devices = devices
            if self.cancel.is_set():
                self.finish_stop()
                return
            if not devices:
                self.camera_label.set(self.t("no_camera"))
                self.set_status("no_camera", "no_camera_help")
                return
            device = next((d for d in devices if d["id"] == self.camera_id), devices[0])
            self.choose_device(device)
            self.set_status("auto_ready", "auto_welcome")

        self.work(ui.list_devices, done, "devices")

    def apply_manual(self):
        if self.running or self.busy:
            return
        value = max(10, min(100, round(self.manual_value.get())))
        self.work(
            lambda: ui.set_checked(value),
            lambda actual: self.display_value.set(str(actual)),
            "control",
        )
