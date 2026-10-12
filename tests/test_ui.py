import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from room_brightness.adaptive import AdaptiveController


@unittest.skipUnless(os.name == "nt", "Windows desktop UI tests")
class UITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import tkinter as tk

        cls.host = tk.Tk()
        cls.host.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.host.update_idletasks()
        cls.host.destroy()

    def setUp(self):
        import tkinter as tk
        from room_brightness import ui

        self.ui = ui
        self.folder = tempfile.TemporaryDirectory()
        self.patches = [
            patch.object(ui, "DATA_DIR", Path(self.folder.name)),
            patch.object(
                ui,
                "resolve_language",
                side_effect=lambda mode: mode if mode in ("ar", "en") else "en",
            ),
            patch.object(
                ui,
                "resolve_theme",
                side_effect=lambda mode: mode if mode in ("light", "dark", "glass") else "light",
            ),
            patch.object(ui.startup, "is_enabled", return_value=False),
        ]
        for item in self.patches:
            item.start()
        self.root = tk.Toplevel(self.host)
        self.root.withdraw()
        self.app = ui.App(self.root, discover=False)
        self.device = dict(index=0, name="Built-in HD Camera", id="built-in")
        self.app.devices = [self.device]
        self.app.choose_device(self.device)

    def tearDown(self):
        self.root.update_idletasks()
        for timer in self.root.tk.call("after", "info"):
            self.root.after_cancel(timer)
        self.root.update_idletasks()
        self.root.destroy()
        for item in reversed(self.patches):
            item.stop()
        self.folder.cleanup()

    def wait_worker(self):
        deadline = time.monotonic() + 5
        while self.app.busy and time.monotonic() < deadline:
            self.root.update()
            time.sleep(0.02)
        self.assertFalse(self.app.busy)

    def test_failed_verification_blocks_automatic_mode(self):
        with patch.object(self.ui, "brightness", side_effect=RuntimeError("CIM blocked")):
            self.app.start()
            self.wait_worker()
        self.assertFalse(self.app.running)
        self.assertFalse(self.app.verified)

    def test_one_click_start_checks_hardware_and_learns_without_calibration(self):
        reading = dict(score=0.0, level=100.0, confidence=1.0, zones=[0.0] * 8)

        def hardware(value=None):
            return 60 if value is None else value

        with (
            patch.object(self.ui, "brightness", side_effect=hardware),
            patch.object(self.ui, "set_checked", side_effect=hardware),
            patch.object(self.ui, "sample", return_value=reading),
            patch.object(self.ui, "list_devices", return_value=[self.device]),
        ):
            self.app.start()
            self.wait_worker()
        self.assertTrue(self.app.running)
        self.assertEqual(self.app.controller.mapping, "image")

    def test_language_button_is_localized_and_choice_survives_reopen(self):
        self.assertEqual(self.app.language_button.cget("text"), "Language")
        self.app.change_language("ar")
        self.assertEqual(self.app.language_button.cget("text"), "اللغة")
        from room_brightness.settings import load_settings

        self.assertEqual(load_settings(Path(self.folder.name))["language"], "ar")
        for timer in self.root.tk.call("after", "info"):
            self.root.after_cancel(timer)
        self.root.destroy()
        import tkinter as tk

        self.root = tk.Toplevel(self.host)
        self.root.withdraw()
        self.app = self.ui.App(self.root, discover=False)
        self.assertEqual(self.app.language, "ar")

    def test_system_language_and_theme_update_while_running(self):
        self.app.running = True
        self.app.set_status("watching", "watching_help")
        self.root.after_cancel(self.app.environment_timer)
        with (
            patch.object(self.ui, "resolve_language", return_value="ar"),
            patch.object(self.ui, "resolve_theme", return_value="dark"),
        ):
            self.app.sync_environment()
        self.assertTrue(self.app.running)
        self.assertEqual((self.app.language, self.app.theme), ("ar", "dark"))
        self.assertEqual(self.app.language_button.cget("text"), "اللغة")
        self.assertEqual(self.app.start_button.cget("state"), "disabled")

    def test_manual_choices_override_system_preferences(self):
        self.app.change_language("en")
        self.app.change_theme("dark")
        self.root.after_cancel(self.app.environment_timer)
        self.app.sync_environment()
        self.assertEqual((self.app.language, self.app.theme), ("en", "dark"))

    def test_language_menu_remains_available_until_selection(self):
        # Windows' native popup enters a modal tracking loop; don't display it
        # during unattended tests. Exercise menu construction and commands.
        with patch("tkinter.Menu.tk_popup"):
            self.app.open_language_menu()
        menu = self.app.language_menu
        self.assertTrue(menu.winfo_exists())
        menu.invoke(2)
        self.assertEqual(self.app.language, "ar")
        self.app.change_theme("dark")
        self.assertEqual(self.app.language_button.cget("text"), "اللغة")

    def test_windows_manual_brightness_becomes_latest_restore_target(self):
        self.app.running = True
        self.app.original = 40
        self.app.controller = AdaptiveController(expected=40)
        with (
            patch.object(self.ui, "brightness", return_value=70),
            patch.object(self.ui, "set_checked") as writer,
        ):
            self.app.watch_screen()
            self.wait_worker()
            writer.assert_not_called()
        self.assertEqual(self.app.original, 70)
        self.assertEqual(self.app.display_value.get(), "70")
        self.assertEqual(self.app.status_state[0], "manual_hold")

    def test_reordered_camera_is_never_captured(self):
        self.app.running = True
        self.app.controller = AdaptiveController(expected=40)
        with (
            patch.object(self.ui, "list_devices", return_value=[dict(self.device, index=1)]),
            patch.object(self.ui, "sample") as reader,
        ):
            self.app.tick()
            self.wait_worker()
            reader.assert_not_called()
        self.assertFalse(self.app.running)

    def test_settings_sliders_and_theme_persist_without_start(self):
        self.app.toggle_view()
        self.app.range_changed("minimum", "0")
        self.assertEqual(self.app.low.get(), 0)
        self.app.range_changed("minimum", "95")
        self.assertGreater(self.app.high.get(), self.app.low.get())
        self.app.change_theme("dark")
        from room_brightness.settings import load_settings

        self.assertEqual(load_settings(Path(self.folder.name))["theme"], "dark")

    def test_startup_requires_a_user_toggle_and_registration_success(self):
        with patch.object(self.ui.startup, "set_enabled") as register:
            register.assert_not_called()
            self.app.toggle_view()
            self.app.startup_choice.set(True)
            self.app.toggle_startup()
            register.assert_called_once_with(True)
        from room_brightness.settings import load_settings

        self.assertTrue(load_settings(Path(self.folder.name))["startup"])

    def test_startup_failure_rolls_back_checkbox(self):
        self.app.startup_choice.set(True)
        with patch.object(self.ui.startup, "set_enabled", side_effect=OSError("Access denied")):
            self.app.toggle_startup()
        self.assertFalse(self.app.startup_choice.get())
        self.assertIn("Access denied", self.app.error_details)

    def test_stop_reports_restoration_failure(self):
        self.app.original = 40
        with patch.object(self.ui, "set_checked", side_effect=RuntimeError("Restore manually")):
            self.app.stop()
            self.wait_worker()
        self.assertEqual(self.app.status_state[1], "error_restore")

    def test_stop_preserves_manual_change_before_periodic_observer(self):
        self.app.original = 40
        self.app.controller = AdaptiveController(expected=50)
        with (
            patch.object(self.ui, "brightness", return_value=70),
            patch.object(self.ui, "set_checked") as writer,
        ):
            self.app.stop()
            self.wait_worker()
            writer.assert_not_called()
        self.assertIn("70", self.app.status.get())

    def test_automatic_target_is_written_in_gradual_verified_steps(self):
        app = self.app
        app.controller = AdaptiveController(expected=50)
        app.controller.update(dict(score=0, confidence=1, zones=[0] * 8), 50, 0)
        app.controller.update(dict(score=2, confidence=1, zones=[2] * 8), 50, 1)
        app.running = True
        state = [50]
        writes = []

        def write(value):
            writes.append(value)
            state[0] = value
            return value

        with (
            patch.object(self.ui, "brightness", side_effect=lambda: state[0]),
            patch.object(self.ui, "set_checked", side_effect=write),
            patch.object(self.ui, "list_devices", return_value=[self.device]),
            patch.object(
                self.ui, "sample", return_value=dict(score=2, confidence=1, zones=[2] * 8)
            ),
            patch.object(app.cancel, "wait", return_value=False),
        ):
            app.tick()
            self.wait_worker()
        self.assertGreater(len(writes), 2)
        for before, after in zip([50] + writes, writes):
            self.assertLessEqual(abs(after - before), 2)
        self.assertGreater(state[0], 60)
        self.assertEqual(app.controller.expected, state[0])

    def test_check_intervals_persist(self):
        self.app.interval_ac.set(10)
        self.app.interval_battery.set(120)
        self.app.interval_changed()
        from room_brightness.settings import load_settings

        saved = load_settings(Path(self.folder.name))
        self.assertEqual(saved["interval_ac"], 10)
        self.assertEqual(saved["interval_battery"], 120)

    def test_manual_brightness_is_verified(self):
        self.app.manual_value.set(65)
        with patch.object(self.ui, "set_checked", return_value=65) as setter:
            self.app.apply_manual()
            self.wait_worker()
        setter.assert_called_once_with(65)
        self.assertEqual(self.app.display_value.get(), "65")

    def test_curve_choice_persists_and_live_controller_updates(self):
        self.app.view = "settings"
        self.app.build()
        self.app.controller = AdaptiveController()
        self.app.change_curve(2)
        self.assertEqual(self.app.controller.sensitivity, 1.8)
        from room_brightness.settings import load_settings

        self.assertEqual(load_settings(Path(self.folder.name))["sensitivity"], "responsive")

    def test_tray_callbacks_execute_on_ui_queue_without_completing_worker(self):
        self.app.busy = True
        called = []
        self.app.events.put(("tray", lambda: called.append(True), None))
        self.app.poll()
        self.assertEqual(called, [True])
        self.assertTrue(self.app.busy)

    def test_tray_hide_restore_and_exit_callbacks(self):
        import sys
        import types
        from unittest.mock import MagicMock

        icon = MagicMock()
        icon.run.side_effect = lambda setup: setup(icon)
        fake = types.SimpleNamespace(
            Icon=MagicMock(return_value=icon),
            Menu=lambda *items: items,
            MenuItem=lambda label, callback, **kw: (label, callback),
        )
        with patch.dict(sys.modules, {"pystray": fake}):
            self.app.hide_to_tray()
            for _ in range(10):
                self.root.update()
                time.sleep(0.02)
            icon.run.assert_called_once()
            self.assertEqual(self.root.state(), "withdrawn")
            self.app.show_from_tray()
            icon.stop.assert_called_once()
            self.assertIsNone(self.app.tray_icon)

    def test_failed_tray_creation_keeps_window_accessible(self):
        import sys
        from unittest.mock import MagicMock

        fake = MagicMock()
        fake.Icon.side_effect = RuntimeError("no tray")
        with (
            patch.dict(sys.modules, {"pystray": fake}),
            patch.object(self.ui.messagebox, "showinfo"),
        ):
            self.app.hide_to_tray()
        self.assertNotEqual(self.root.state(), "withdrawn")
        self.assertIsNone(self.app.tray_icon)

    def test_glass_theme_persists_and_opacity_resets(self):
        self.app.change_theme("glass")
        self.assertEqual(self.app.theme, "glass")
        self.root.update()
        self.assertAlmostEqual(float(self.root.attributes("-alpha")), 0.97, places=2)
        from room_brightness.settings import load_settings

        self.assertEqual(load_settings(Path(self.folder.name))["theme"], "glass")
        self.app.change_theme("light")
        self.root.update()
        self.assertAlmostEqual(float(self.root.attributes("-alpha")), 1.0, places=2)
