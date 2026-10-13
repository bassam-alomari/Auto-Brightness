import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch


@unittest.skipUnless(os.name == "nt", "Windows")
class NativeEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        from room_brightness.qt_engine import Engine, Scheduler

        self.folder = tempfile.TemporaryDirectory()
        self.scheduler = Scheduler()
        self.engine = Engine(self.scheduler, discover=False, directory=Path(self.folder.name))
        self.device = dict(index=0, name="Demo camera", id="demo")
        self.engine.devices = [self.device]
        self.engine.choose_device(self.device)

    def tearDown(self):
        from room_brightness import monitors

        monitors.select("internal")
        self.scheduler.destroy()
        self.app.processEvents()
        self.folder.cleanup()

    def wait(self):
        deadline = time.monotonic() + 8
        while self.engine.busy and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.01)
        self.assertFalse(self.engine.busy)

    def test_verified_start_raises_safety_floor_then_follows_light_changes(self):
        from room_brightness import ui

        state = [40]
        writes = []

        def control(value=None):
            if value is not None:
                state[0] = value
                writes.append(value)
            return state[0]

        measurement = dict(
            score=2, level=29, confidence=1, zones=[2] * 8, exposure=-8, exposure_corrected=True
        )
        with (
            patch.object(ui, "brightness", side_effect=control),
            patch.object(ui, "set_checked", side_effect=control),
            patch.object(
                ui,
                "smooth_to",
                side_effect=lambda start, target, cancel, progress, **kwargs: (
                    progress(control(target)) or target,
                    False,
                ),
            ),
            patch.object(ui, "sample", return_value=measurement),
            patch.object(ui, "list_devices", return_value=[self.device]),
            patch.object(self.engine.cancel, "wait", return_value=False),
        ):
            self.engine.start()
            self.wait()
            measurement["score"] = 5
            measurement["zones"] = [5] * 8
            for _ in range(5):
                if self.engine.timer:
                    self.scheduler.after_cancel(self.engine.timer)
                    self.engine.timer = None
                self.engine.tick()
                self.wait()
            self.assertEqual(state[0], 80)
            self.assertIn(45, writes)  # Verification occurred before adaptation.
            self.assertEqual(self.engine.last_meter["target"], 80)
            # Manual adjustment just before Stop must win over restoration.
            state[0] = 65
            self.engine.stop()
            self.wait()
            self.assertEqual(state[0], 65)

    def test_shutdown_cancels_all_qt_scheduler_timers(self):
        self.engine.close()
        deadline = time.monotonic() + 2
        while self.scheduler.alive and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.02)
        self.assertFalse(self.scheduler.alive)
        self.assertFalse(self.scheduler.timers)

    def test_startup_default_registers_only_once(self):
        from room_brightness.qt_engine import Engine, Scheduler
        from room_brightness.settings import load_settings
        from room_brightness import startup

        directory = Path(self.folder.name) / "startup-default"
        scheduler = Scheduler()
        try:
            with (
                patch.object(startup, "set_enabled") as setter,
                patch.object(startup, "is_enabled", return_value=True),
            ):
                Engine(scheduler, discover=True, directory=directory)
                setter.assert_called_once_with(True)
            self.assertEqual(load_settings(directory)["startup_defaults_revision"], 1)
        finally:
            scheduler.destroy()
        scheduler = Scheduler()
        try:
            with (
                patch.object(startup, "set_enabled") as setter,
                patch.object(startup, "is_enabled", return_value=False),
            ):
                Engine(scheduler, discover=True, directory=directory)
                setter.assert_not_called()
            self.assertFalse(load_settings(directory)["startup"])
        finally:
            scheduler.destroy()

    def test_lock_cancels_work_and_unlock_resumes_only_after_all_reasons_clear(self):
        self.engine.running = True
        self.engine.session_pause("lock", True)
        self.assertFalse(self.engine.running)
        self.assertTrue(self.engine.cancel.is_set())
        self.assertTrue(self.engine.resume_pending)
        self.engine.session_pause("sleep", True)
        with patch.object(self.engine, "verify") as verify:
            self.engine.session_pause("lock", False)
            verify.assert_not_called()
            self.engine.session_pause("sleep", False)
            verify.assert_called_once_with(start_after=True)
        self.assertFalse(self.engine.resume_pending)

    def test_stop_cancels_unlock_resume(self):
        self.engine.running = True
        self.engine.session_pause("lock", True)
        self.engine.stop()
        with patch.object(self.engine, "verify") as verify:
            self.engine.session_pause("lock", False)
            verify.assert_not_called()

    def test_power_profile_reconfigures_production_controller(self):
        from room_brightness.adaptive import AdaptiveController

        self.engine.running = True
        self.engine.controller = AdaptiveController(mapping="image")
        self.engine.preferences["power_profiles"] = True
        self.engine.preferences["ac_limits"] = [0, 100]
        with patch(
            "room_brightness.qt_engine.ctypes.windll.kernel32.GetSystemPowerStatus",
            side_effect=lambda pointer: setattr(pointer._obj, "ac", 1) or 1,
        ):
            self.engine.begin_pair_cycle()
        self.assertEqual((self.engine.controller.low, self.engine.controller.high), (0, 100))
        self.assertTrue(self.engine.controller.options["stability_guard"])

    def test_camera_busy_retry_keeps_brightness_and_stop_cancels_retry(self):
        from room_brightness.adaptive import AdaptiveController

        self.engine.running = True
        self.engine.controller = AdaptiveController(mapping="image")
        self.engine.original = 40
        self.engine.restore.set(False)
        with patch("room_brightness.ui.set_checked") as write:
            self.engine.handle_error("control", "Camera unavailable. Close video apps.")
            self.assertTrue(self.engine.running)
            self.assertEqual(self.engine.diagnostic, "camera_retry")
            self.assertIsNotNone(self.engine.timer)
            self.assertEqual(self.engine.original, 40)
            self.engine.stop()
            self.assertIsNone(self.engine.timer)
            write.assert_not_called()

    def test_profile_apply_is_persistent_and_blocked_during_control(self):
        from room_brightness.settings import load_settings

        self.engine.running = True
        with self.assertRaises(ValueError):
            self.engine.apply_profile("night")
        self.engine.running = False
        self.engine.apply_profile("night")
        self.assertEqual((self.engine.low.get(), self.engine.high.get()), (0, 50))
        self.assertEqual(load_settings(self.engine.directory)["brightness_curve"], "night")

    def test_each_display_restores_its_own_settings(self):
        self.engine.select_display("external")
        self.engine.low.set(0)
        self.engine.high.set(100)
        self.engine.persist()
        self.engine.select_display("internal")
        self.assertEqual((self.engine.low.get(), self.engine.high.get()), (10, 80))
        self.engine.select_display("external")
        self.assertEqual((self.engine.low.get(), self.engine.high.get()), (0, 100))

    def test_undo_restores_previous_saved_curve(self):
        original = [point[:] for point in self.engine.preferences["custom_points"]]
        self.engine.remember_curve()
        self.engine.preferences["custom_points"][1][1] = 55
        self.engine.persist()
        self.engine.undo_curve()
        self.assertEqual(self.engine.preferences["custom_points"], original)
