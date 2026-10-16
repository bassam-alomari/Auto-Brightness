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
from .extras import SamplingBudget, PROFILE_KEYS
import copy


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
        self.manual_offer = None
        self.last_meter = None
        self.history = deque(maxlen=180)
        self.health_events = deque(maxlen=50)
        self.pause_reasons = set()
        self.resume_pending = False
        self.pause_deadline = None
        self.pause_timer = None
        self.diagnostic = ""
        self.power_mode = "ac"
        self.sampling_budget = SamplingBudget()
        self.retry_attempt = 0
        self.displays = [{"id": "internal", "name": "Built-in display"}]
        self.wizard_eligible = discover
        from . import monitors

        monitors.select(self.preferences["display_target"])
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
            resuming = operation == "test" and hasattr(self, "resume_original")
            expected = getattr(self, "resume_expected", None)
            manual = resuming and expected is not None and result != expected
            if resuming:
                self.original = result if manual else self.resume_original
                del self.resume_original
                if hasattr(self, "resume_expected"):
                    del self.resume_expected
            done(result)
            if manual and self.running and self.controller:
                self.controller.hold_until = time.monotonic() + 180
                self.controller.preferred = result
                self.controller.manual_reference = True

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
            self.health_events.append(
                {"time": time.monotonic(), "category": "settings_write_failed"}
            )
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
            self.sampling_budget.observe(self.last_meter)
            self.retry_attempt = 0

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
        base = self.interval_ac.get() if self.power_mode == "ac" else self.interval_battery.get()
        self.cycle_seconds = self.sampling_budget.interval(
            base,
            self.preferences["max_interval_" + self.power_mode],
            self.preferences["adaptive_sampling"],
        )
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
            self.diagnostic = "timed_paused" if reason == "timed" else "paused"
            self.status_title.set(self.t("stopped"))
            self.status.set(
                (
                    "الوضع التلقائي متوقف مؤقتًا؛ السطوع محفوظ والكاميرا متوقفة."
                    if self.language == "ar"
                    else "Automatic mode paused; brightness held and camera stopped."
                )
                if reason == "timed"
                else "الكاميرا متوقفة أثناء القفل أو السكون"
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
        self.resume_expected = self.controller.expected if self.controller else None
        self.verify(start_after=True)
        self.resume_original = old

    def start(self):
        if not self.pause_reasons:
            super().start()

    def pause_for(self, minutes):
        if minutes not in (15, 30, 60):
            raise ValueError("Invalid pause duration.")
        if not self.running and "timed" not in self.pause_reasons:
            return
        self.clear_pause_timer()
        self.pause_deadline = time.monotonic() + minutes * 60
        self.session_pause("timed", True)
        self.pause_tick()

    def clear_pause_timer(self):
        if self.pause_timer is not None:
            self.root.after_cancel(self.pause_timer)
            self.pause_timer = None

    def pause_remaining(self):
        import math

        return (
            max(0, math.ceil(self.pause_deadline - time.monotonic()))
            if self.pause_deadline is not None
            else 0
        )

    def pause_tick(self):
        self.pause_timer = None
        if self.pause_deadline is None:
            return
        if self.pause_remaining() == 0:
            self.resume_now()
            return
        self.pause_timer = self.root.after(1000, self.pause_tick)

    def resume_now(self):
        self.clear_pause_timer()
        self.pause_deadline = None
        self.session_pause("timed", False)

    def stop(self):
        self.clear_pause_timer()
        self.pause_deadline = None
        self.pause_reasons.discard("timed")
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
        self.remember_curve()
        self.preferences["custom_points"] = points
        self.preferences["brightness_curve"] = "custom"
        if self.controller:
            self.controller.image_curve = "custom"
        self.persist()

    def refresh_displays(self):
        if self.busy or self.running:
            return
        from .monitors import list_displays

        self.work(list_displays, lambda displays: setattr(self, "displays", displays), "displays")

    def select_display(self, identity):
        if self.running or self.busy or self.resume_pending:
            raise ValueError("Stop automatic mode before changing settings.")
        from . import monitors

        previous = self.preferences["display_target"]
        self.preferences["display_profiles"][previous] = {
            key: copy.deepcopy(self.preferences[key]) for key in PROFILE_KEYS
        }
        settings = copy.deepcopy(self.preferences)
        settings["display_target"] = identity
        settings.update(settings["display_profiles"].get(identity, {}))
        self.apply_preferences(settings)
        monitors.select(identity)
        self.display_value.set("—")

    def remember_curve(self):
        history = self.preferences["curve_history"]
        points = copy.deepcopy(self.preferences["custom_points"])
        if not history or history[-1] != points:
            history.append(points)
            self.preferences["curve_history"] = history[-20:]

    def undo_curve(self):
        if self.running or self.busy:
            raise ValueError("Stop automatic mode before changing settings.")
        if not self.preferences["curve_history"]:
            raise ValueError("No saved curve changes to undo.")
        self.preferences["custom_points"] = self.preferences["curve_history"].pop()
        self.preferences["brightness_curve"] = "custom"
        self.persist()

    def apply_preferences(self, settings):
        if self.running or self.busy or self.resume_pending:
            raise ValueError("Stop automatic mode before changing settings.")
        from .settings import validate, save_settings

        candidate = validate(settings)
        history = copy.deepcopy(self.preferences["curve_history"])
        if candidate["custom_points"] != self.preferences["custom_points"]:
            points = copy.deepcopy(self.preferences["custom_points"])
            if not history or history[-1] != points:
                history.append(points)
        candidate["curve_history"] = history[-20:]
        try:
            save_settings(self.directory, candidate)
        except OSError as error:
            self.error_details = str(error)
            self.health_events.append(
                {"time": time.monotonic(), "category": "settings_write_failed"}
            )
            raise ValueError("Could not save settings. Check folder permissions.") from error
        self.preferences = candidate
        for key, var in (
            ("low", self.low),
            ("high", self.high),
            ("interval_ac", self.interval_ac),
            ("interval_battery", self.interval_battery),
            ("restore", self.restore),
        ):
            var.set(candidate[key])
        self.language = resolve_language(candidate["language"])
        self.theme = resolve_theme(candidate["theme"])
        self.palette = PALETTES[self.theme]
        self.controller = None
        self.verified = False
        self.manual_offer = None
        self.last_meter = None
        self.history.clear()
        self.sampling_budget.reset()

    def apply_profile(self, name):
        from .extras import profile_settings

        settings = copy.deepcopy(self.preferences)
        settings.update(profile_settings(settings, name))
        self.apply_preferences(settings)

    def save_profile(self, name):
        name = name.strip()
        if not name or len(name) > 40 or name in ("work", "gaming", "night"):
            raise ValueError("Choose a different profile name (1–40 characters).")
        if name not in self.preferences["profiles"] and len(self.preferences["profiles"]) >= 20:
            raise ValueError("Maximum of 20 profiles reached.")
        self.preferences["profiles"][name] = {
            key: copy.deepcopy(self.preferences[key]) for key in PROFILE_KEYS
        }
        self.persist()

    def retry_camera(self):
        self.timer = None
        if not self.running or self.pause_reasons:
            return
        if self.busy:
            self.timer = self.root.after(500, self.retry_camera)
            return

        def done(devices):
            if not self.running:
                return
            chosen = next((device for device in devices if device["id"] == self.camera_id), None)
            if chosen:
                self.devices = devices
                self.choose_device(chosen)
                self.cancel.clear()
                self.begin_pair_cycle()
            else:
                self.schedule_retry()

        self.work(ui.list_devices, done, "retry_devices")

    def schedule_retry(self):
        self.retry_attempt += 1
        delay = min(60, 5 * 2 ** min(self.retry_attempt - 1, 4))
        if self.timer is not None:
            self.root.after_cancel(self.timer)
        self.timer = self.root.after(delay * 1000, self.retry_camera)
        self.diagnostic = "camera_retry"
        self.status_title.set(self.t("watching"))
        self.status.set(
            "الكاميرا مشغولة أو غير متاحة. سيُعاد الفحص بعد " + str(delay) + " ثانية."
            if self.language == "ar"
            else f"Camera busy or unavailable. Retrying in {delay} seconds."
        )

    def handle_error(self, operation, error):
        if operation == "test":
            for name in ("resume_original", "resume_expected"):
                if hasattr(self, name):
                    delattr(self, name)
        from .recovery import error_category

        category = error_category(operation, error)
        self.health_events.append({"time": time.monotonic(), "category": category})
        if (
            self.running
            and category != "permission_denied"
            and (
                operation == "retry_devices"
                or (operation in ("control", "measure") and "camera" in str(error).lower())
            )
        ):
            self.error_details = str(error)
            self.cancel.clear()
            self.schedule_retry()
            return
        self.diagnostic = "camera_error" if "camera" in str(error).lower() else "display_error"
        super().handle_error(operation, error)

    def update_readings(self):
        pass

    def draw_curve(self):
        pass

    def render_status(self):
        if "timed" in self.pause_reasons:
            self.status_title.set(self.t("stopped"))
            self.status.set(
                "الوضع التلقائي متوقف مؤقتًا؛ السطوع محفوظ والكاميرا متوقفة."
                if self.language == "ar"
                else "Automatic mode paused; brightness held and camera stopped."
            )
            return
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
            self.manual_applied,
            "control",
        )

    def manual_applied(self, actual):
        self.display_value.set(str(actual))
        self.manual_offer = None
        if (
            self.last_meter
            and self.last_meter.get("quality", 0) >= 0.35
            and self.history
            and time.monotonic() - self.history[-1][0] <= 60
        ):
            self.manual_offer = (
                self.last_meter["level"],
                int(actual),
                time.monotonic(),
                self.preferences["display_target"],
            )

    def manual_offer_available(self):
        offer = self.manual_offer
        return bool(
            offer
            and time.monotonic() - offer[2] <= 60
            and str(offer[1]) == self.display_value.get()
            and offer[3] == self.preferences["display_target"]
            and not self.running
            and not self.busy
            and not self.resume_pending
        )

    def save_manual_preference(self):
        if not self.manual_offer_available():
            raise ValueError("Take a fresh light reading first.")
        from .comfort import learned_points

        candidate = copy.deepcopy(self.preferences)
        level, actual, _, _ = self.manual_offer
        candidate["custom_points"] = learned_points(candidate["custom_points"], level, actual)
        candidate["brightness_curve"] = "custom"
        self.apply_preferences(candidate)
        self.manual_offer = None
