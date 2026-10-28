import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch


@unittest.skipUnless(os.name == "nt", "Windows desktop")
class QtInterfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication

        cls.qt = QApplication.instance() or QApplication([])
        cls.qt.setQuitOnLastWindowClosed(False)

    def setUp(self):
        from room_brightness.qt_engine import Engine, Scheduler
        from room_brightness.qt_ui import Window

        self.folder = tempfile.TemporaryDirectory()
        self.root = Scheduler()
        self.engine = Engine(self.root, discover=False, directory=Path(self.folder.name))
        self.device = dict(index=0, name="Demo camera", id="demo")
        self.engine.devices = [self.device]
        self.engine.choose_device(self.device)
        self.window = Window(self.root, self.engine)
        self.window.show()
        self.qt.processEvents()

    def tearDown(self):
        self.window.pump.stop()
        self.window.tray.hide()
        self.window.hide()
        self.window.deleteLater()
        self.qt.processEvents()
        self.root.destroy()
        self.folder.cleanup()

    def test_glass_surfaces_render_and_language_is_mirrored(self):
        self.window.change_theme("glass")
        self.window.change_language("ar")
        self.qt.processEvents()
        pixmap = self.window.grab()
        self.assertFalse(pixmap.isNull())
        from PySide6.QtCore import Qt

        self.assertEqual(self.window.layoutDirection(), Qt.LayoutDirection.RightToLeft)
        self.assertEqual(self.engine.preferences["theme"], "glass")

    def test_settings_intervals_and_curve_keep_values(self):
        self.window.toggle_page()
        self.window.interval_change(self.engine.interval_ac, 10)
        self.window.change_curve(2)
        self.window.change_limit("maximum", 100)
        from room_brightness.settings import load_settings

        saved = load_settings(Path(self.folder.name))
        self.assertEqual(saved["interval_ac"], 10)
        self.assertEqual(saved["brightness_curve"], "smooth")
        self.assertEqual(saved["high"], 100)

    def test_readout_distinguishes_stability_from_accuracy(self):
        self.engine.last_meter = dict(level=29, quality=1, target=80, exposure=-8)
        self.window.update_values()
        self.assertIn("29", self.window.reading.text())
        self.assertIn("80", self.window.reading.text())
        self.assertNotIn("Quality", self.window.reading.text())
        self.assertTrue(self.window.exposure.text())

    def test_preview_is_opt_in_and_cleared(self):
        self.assertFalse(self.engine.preview_enabled)
        self.engine.last_meter = dict(level=29, quality=1, target=80, preview="dummy")
        self.window.toggle_preview(False)
        self.assertNotIn("preview", self.engine.last_meter)

    def test_stopped_check_samples_without_setting_screen(self):
        from room_brightness import qt_ui

        reading = dict(
            score=2, level=29, confidence=1, zones=[2] * 8, exposure=-8, exposure_corrected=True
        )
        with (
            patch.object(qt_ui, "sample", return_value=reading),
            patch("room_brightness.brightness.brightness", return_value=50),
            patch("room_brightness.ui.set_checked") as setter,
        ):
            self.window.check_now()
            deadline = time.monotonic() + 3
            while self.engine.busy and time.monotonic() < deadline:
                self.window.sync()
                self.qt.processEvents()
                time.sleep(0.03)
        setter.assert_not_called()
        self.assertEqual(self.engine.last_meter["level"], 29)

    def test_close_waits_for_backend_cleanup(self):
        self.window.exit_app()
        deadline = time.monotonic() + 2
        while self.window.pump.isActive() and time.monotonic() < deadline:
            self.window.sync()
            self.qt.processEvents()
            time.sleep(0.03)
        self.assertFalse(self.window.pump.isActive())

    def test_slider_has_true_percentage_midpoint(self):
        self.assertEqual(self.window.manual_slider.minimum(), 0)
        self.assertEqual(self.window.manual_slider.maximum(), 100)
        from PySide6.QtWidgets import QStyle

        self.assertEqual(QStyle.sliderPositionFromValue(0, 100, 50, 100), 50)
        self.window.manual_slider.setValue(5)
        self.window.update_values()
        self.assertTrue(self.window.manual_button.isEnabled())

    def test_dark_popups_and_vector_arrows_are_themed(self):
        self.window.change_theme("dark")
        style = self.window.styleSheet()
        self.assertIn("background: " + self.engine.palette["card"], style)
        self.assertIn("down-dark.svg", style)
        self.assertIn("QSpinBox::up-button", style)

    def test_title_bar_is_integrated_and_glass_has_no_artwork(self):
        from PySide6.QtCore import Qt

        self.assertTrue(self.window.windowFlags() & Qt.WindowType.FramelessWindowHint)
        self.assertFalse(hasattr(self.window, "art"))
        self.window.change_theme("glass")
        self.assertTrue(self.window.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground))
        self.assertIsInstance(self.window.backdrop_available, bool)

    def test_dropdown_popup_has_rounded_mask(self):
        self.window.cameras.showPopup()
        self.qt.processEvents()
        self.assertFalse(self.window.cameras.view().window().mask().isEmpty())
        self.window.cameras.hidePopup()

    def test_integrated_maximize_and_restore(self):
        self.window.toggle_maximize()
        self.qt.processEvents()
        self.assertTrue(self.window.expanded)
        self.assertEqual(self.window.size(), self.window.screen().availableGeometry().size())
        self.window.toggle_maximize()
        self.qt.processEvents()
        self.assertFalse(self.window.expanded)

    def test_glass_transparency_is_live_persistent_and_theme_specific(self):
        from room_brightness.settings import load_settings

        self.window.page = "settings"
        self.window.change_theme("glass")
        self.qt.processEvents()
        self.assertTrue(self.window.glass_slider.isVisible())
        self.window.glass_slider.setValue(0)
        clear_alpha = self.window.glass_alpha(8, 125)
        self.window.glass_slider.setValue(100)
        self.assertGreater(self.window.glass_alpha(8, 125), clear_alpha)
        self.qt.processEvents()
        time.sleep(0.22)
        self.qt.processEvents()
        self.assertEqual(load_settings(Path(self.folder.name))["glass_tint"], 100)
        self.window.change_theme("dark")
        self.qt.processEvents()
        self.assertFalse(self.window.glass_slider.isVisible())
        self.window.change_theme("glass")
        self.qt.processEvents()
        self.assertEqual(self.window.glass_slider.value(), 100)

    def test_language_menu_is_anchored_to_button_in_both_directions(self):
        from PySide6.QtCore import QPoint

        for language in ("ar", "en"):
            self.window.change_language(language)
            self.qt.processEvents()
            self.window.language_menu()
            self.qt.processEvents()
            menu = self.window.language_popup
            button = self.window.language_button
            origin = button.mapToGlobal(QPoint(0, button.height()))
            self.assertAlmostEqual(menu.pos().y(), origin.y() + 6, delta=2)
            expected = (
                origin.x() + button.width() - menu.width() if language == "ar" else origin.x()
            )
            self.assertAlmostEqual(menu.pos().x(), expected, delta=2)
            menu.hide()

    def test_preset_changes_live_controller_and_preview_selection(self):
        from room_brightness.adaptive import AdaptiveController, CURVES

        self.engine.controller = AdaptiveController(low=10, high=100, mapping="image")
        self.window.page = "settings"
        self.window.build()
        self.window.change_curve(list(CURVES).index("night"))
        self.assertEqual(self.engine.controller.image_curve, "night")
        value = self.engine.controller.update(dict(level=21, confidence=1), 50, 0)
        from room_brightness.adaptive import image_target

        self.assertEqual(value, image_target(21, 10, 100, "night"))

    def test_multilingual_dynamic_reading_is_translated(self):
        self.window.change_language("fr")
        self.engine.last_meter = dict(level=21, quality=1, target=55, exposure=-6)
        self.window.update_values()
        self.assertIn("Cible", self.window.reading.text())
        self.assertIn("Exposition", self.window.exposure.text())

    def test_added_themes_render_and_persist(self):
        from room_brightness.themes import THEME_NAMES
        from room_brightness.settings import load_settings

        for theme in THEME_NAMES:
            self.window.change_theme(theme)
            self.qt.processEvents()
            self.assertEqual(self.engine.theme, theme)
            self.assertEqual(load_settings(Path(self.folder.name))["theme"], theme)
            self.assertFalse(self.window.grab().isNull())

    def test_arabic_style_choice_is_live_and_persistent(self):
        from room_brightness.settings import load_settings

        self.window.change_language("ar")
        self.window.page = "settings"
        self.window.build()
        self.window.change_arabic_dialect(1)
        self.assertEqual(load_settings(Path(self.folder.name))["arabic_dialect"], "jo")
        self.window.change_arabic_dialect(0)
        self.assertEqual(self.engine.t("app"), "الإضاءة التلقائية")
        self.assertEqual(self.engine.t("watching"), "تكيّف تدريجي")

    def test_slider_width_stays_fixed_for_all_percentage_digit_counts(self):
        widths = []
        for value in (0, 9, 50, 72, 100):
            self.window.manual_slider.setValue(value)
            self.qt.processEvents()
            widths.append(self.window.manual_slider.width())
        self.assertEqual(len(set(widths)), 1)

    def test_brightness_percentage_alignment_follows_language(self):
        from PySide6.QtCore import Qt

        self.window.change_language("ar")
        self.assertTrue(self.window.metric_label.alignment() & Qt.AlignmentFlag.AlignRight)
        self.window.change_language("en")
        self.assertTrue(self.window.metric_label.alignment() & Qt.AlignmentFlag.AlignLeft)

    def test_wheel_does_not_modify_preferences_or_brightness(self):
        from PySide6.QtCore import QPoint, QPointF, Qt
        from PySide6.QtGui import QWheelEvent
        from room_brightness.qt_ui import RoundedCombo, NoWheelSpinBox, GlassSlider
        from PySide6.QtWidgets import QApplication

        for page in ("home", "settings"):
            self.window.page = page
            self.window.build()
            self.qt.processEvents()
            controls = (
                self.window.findChildren(RoundedCombo)
                + self.window.findChildren(NoWheelSpinBox)
                + self.window.findChildren(GlassSlider)
            )
            for control in controls:
                before = (
                    control.currentIndex() if isinstance(control, RoundedCombo) else control.value()
                )
                control.setFocus()
                event = QWheelEvent(
                    QPointF(10, 10),
                    QPointF(control.mapToGlobal(QPoint(10, 10))),
                    QPoint(0, -20),
                    QPoint(0, -120),
                    Qt.MouseButton.NoButton,
                    Qt.KeyboardModifier.NoModifier,
                    Qt.ScrollPhase.ScrollUpdate,
                    False,
                )
                QApplication.sendEvent(control, event)
                after = (
                    control.currentIndex() if isinstance(control, RoundedCombo) else control.value()
                )
                self.assertEqual(before, after)
                # The containing scroll area may accept the ignored event to scroll the page.
                # Input values must remain unchanged regardless of propagation.

    def test_numeric_settings_are_right_aligned_in_arabic(self):
        from PySide6.QtCore import Qt
        from room_brightness.qt_ui import NoWheelSpinBox

        self.window.page = "settings"
        self.window.change_language("ar")
        for spin in self.window.findChildren(NoWheelSpinBox):
            self.assertTrue(spin.alignment() & Qt.AlignmentFlag.AlignRight)
            self.assertTrue(spin.alignment() & Qt.AlignmentFlag.AlignAbsolute)

    def test_new_brand_icon_is_used_by_window_and_tray(self):
        icon = self.window.windowIcon()
        self.assertFalse(icon.isNull())
        self.assertFalse(self.window.tray.icon().isNull())
        for size in (16, 32, 64, 256):
            self.assertFalse(icon.pixmap(size, size).isNull())

    def test_locked_session_does_not_allow_explicit_camera_check(self):
        from room_brightness import qt_ui

        self.engine.session_pause("lock", True)
        with patch.object(qt_ui, "sample") as sample:
            self.window.check_now()
            sample.assert_not_called()
        self.assertFalse(self.engine.busy)

    def test_setup_wizard_cannot_finish_until_display_test_passes(self):
        from room_brightness.extras_ui import SetupWizard

        wizard = SetupWizard(self.window)
        wizard.pages.setCurrentIndex(2)
        wizard.sync()
        self.assertFalse(wizard.finish.isEnabled())
        self.engine.verified = True
        wizard.sync()
        self.assertTrue(wizard.finish.isEnabled())
        wizard.low.setValue(0)
        wizard.high.setValue(100)
        wizard.complete()
        self.assertTrue(self.engine.preferences["onboarding_done"])
        self.assertEqual((self.engine.low.get(), self.engine.high.get()), (0, 100))
        wizard.timer.stop()
        wizard.deleteLater()

    def test_region_preview_restores_prior_privacy_setting(self):
        from room_brightness.extras_ui import RegionDialog

        dialog = RegionDialog(self.window)
        with patch.object(self.window, "check_now") as check:
            dialog.capture()
            check.assert_called_once()
        self.assertTrue(self.engine.preview_enabled)
        dialog.reject()
        self.assertFalse(self.engine.preview_enabled)
        dialog.deleteLater()

    def test_diagnostic_preview_excludes_raw_errors(self):
        from room_brightness.recovery_ui import DiagnosticDialog

        self.engine.error_details = "private-path/private-camera"
        dialog = DiagnosticDialog(self.window)
        self.assertTrue(dialog.preview.isReadOnly())
        self.assertNotIn("private-path", dialog.preview.toPlainText())
        self.assertIn("report_format", dialog.preview.toPlainText())
        dialog.reject()
        dialog.deleteLater()

    def test_settings_search_reveals_advanced_without_changing_values(self):
        self.window.page = "settings"
        self.window.change_language("ar")
        self.window.build()
        advanced = [
            section
            for section, is_advanced, terms, surface in self.window.settings_sections
            if is_advanced
        ]
        self.assertTrue(advanced)
        self.assertTrue(all(section.isHidden() for section in advanced))
        before = self.engine.preferences.copy()
        self.window.settings_search.setText("نسخة احتياطية")
        self.assertTrue(any(not section.isHidden() for section in advanced))
        self.assertEqual(self.engine.preferences, before)
        self.window.settings_search.clear()
        self.assertTrue(all(section.isHidden() for section in advanced))
        self.window.settings_search.setText("not-a-real-setting-xyz")
        self.assertFalse(self.window.settings_no_results.isHidden())

    def test_curve_preview_does_not_call_hardware_or_change_settings(self):
        from room_brightness.easy_ui import CurvePreview
        import copy

        before = copy.deepcopy(self.engine.preferences)
        with (
            patch("room_brightness.ui.set_checked") as write,
            patch("room_brightness.brightness.smooth_to") as ramp,
            patch("room_brightness.camera.sample") as sample,
        ):
            dialog = CurvePreview(self.window)
            for reading, expected in ((15, 50), (20, 70), (25, 80), (27, 80)):
                dialog.input.setValue(reading)
                self.assertEqual(dialog.target_value, expected)
            write.assert_not_called()
            ramp.assert_not_called()
            sample.assert_not_called()
            self.assertEqual(before, self.engine.preferences)
            dialog.reject()
            dialog.deleteLater()

    def test_appearance_preview_cancel_and_save_are_transactional(self):
        import copy
        from room_brightness.easy_ui import AppearancePreview
        from room_brightness.settings import load_settings

        before = copy.deepcopy(self.engine.preferences)
        dialog = AppearancePreview(self.window)
        dialog.mode.setCurrentIndex(dialog.modes.index("glass"))
        dialog.tint.setValue(72)
        self.assertEqual(self.engine.preferences, before)
        dialog.reject()
        self.assertEqual(self.engine.preferences, before)
        dialog = AppearancePreview(self.window)
        dialog.mode.setCurrentIndex(dialog.modes.index("dark"))
        dialog.tint.setValue(63)
        dialog.save()
        self.assertEqual(self.engine.preferences["theme"], "dark")
        self.assertEqual(load_settings(Path(self.folder.name))["glass_tint"], 63)
        dialog.deleteLater()

    def test_manual_preference_offer_requires_fresh_reading_and_explicit_save(self):
        import copy

        before = copy.deepcopy(self.engine.preferences)
        self.engine.last_meter = dict(level=20, quality=1)
        self.engine.history.append((time.monotonic(), 20, 70, 70))
        self.engine.manual_applied(65)
        self.assertTrue(self.engine.manual_offer_available())
        self.assertEqual(self.engine.preferences, before)
        self.engine.save_manual_preference()
        self.assertIn([20, 65], self.engine.preferences["custom_points"])
        self.assertEqual(self.engine.preferences["brightness_curve"], "custom")
        self.assertFalse(self.engine.manual_offer_available())
        self.engine.last_meter = dict(level=20, quality=0.1)
        self.engine.manual_applied(60)
        self.assertFalse(self.engine.manual_offer_available())
        with self.assertRaises(ValueError):
            self.engine.save_manual_preference()

    def test_narrow_window_uses_vertical_panels_and_rtl(self):
        from PySide6.QtWidgets import QBoxLayout
        from PySide6.QtCore import Qt

        self.window.change_language("ar")
        self.window.resize(600, 600)
        self.qt.processEvents()
        self.assertEqual(self.window.panels.direction(), QBoxLayout.Direction.TopToBottom)
        self.assertEqual(self.window.layoutDirection(), Qt.LayoutDirection.RightToLeft)
        self.window.resize(1050, 800)
        self.qt.processEvents()
        self.assertEqual(self.window.panels.direction(), QBoxLayout.Direction.LeftToRight)

    def test_tray_pause_actions_and_primary_reason(self):
        from room_brightness.adaptive import AdaptiveController

        self.engine.running = True
        self.engine.controller = AdaptiveController(low=10, high=80, expected=70)
        self.window.update_tray_menu()
        pause = next(a for a in self.window.tray_menu.actions() if "15" in a.text())
        pause.trigger()
        self.assertIn("timed", self.engine.pause_reasons)
        self.assertIn("paused", self.window.brightness_reason())
        self.engine.stop()
        self.assertFalse(self.engine.resume_pending)

    def test_guided_calibration_requires_explicit_comparison_save(self):
        from room_brightness.tuning_ui import CalibrationDialog
        import copy

        before = copy.deepcopy(self.engine.preferences)
        dialog = CalibrationDialog(self.window)
        dialog.show()
        for level, value in ((15, 25), (20, 60), (25, 90)):
            dialog.reading = level
            dialog.input.setValue(value)
            dialog.keep()
        self.assertEqual(self.engine.preferences, before)
        compare = dialog.comparison
        self.assertEqual(compare.mapped(20, True), 60)
        compare.save_candidate(compare.candidate)
        self.assertEqual(self.engine.preferences["custom_points"][2], [20, 60])
        self.assertTrue(self.engine.preferences["curve_history"])
        dialog.deleteLater()

    def test_comparison_and_performance_dialogs_do_not_touch_hardware(self):
        from room_brightness.tuning_ui import CompareDialog, PerformanceDialog
        import copy

        before = copy.deepcopy(self.engine.preferences)
        with (
            patch("room_brightness.ui.set_checked") as write,
            patch("room_brightness.camera.sample") as camera,
        ):
            compare = CompareDialog(self.window)
            compare.choose(1)
            compare.reading.setValue(22)
            self.assertEqual(self.engine.preferences, before)
            compare.reject()
            performance = PerformanceDialog(self.window)
            performance.refresh()
            performance.reject()
            write.assert_not_called()
            camera.assert_not_called()
        compare.deleteLater()
        performance.deleteLater()

    def test_application_pause_preserves_other_reasons_and_stop_cancels_resume(self):
        from room_brightness.adaptive import AdaptiveController

        self.engine.preferences.update(pause_apps_enabled=True, pause_apps=["vlc.exe"])
        self.engine.running = True
        self.engine.controller = AdaptiveController(low=10, high=80, expected=70)
        with patch("room_brightness.tuning.foreground_app", return_value="vlc.exe"):
            self.engine.check_foreground()
        self.assertIn("application", self.engine.pause_reasons)
        self.assertFalse(self.engine.running)
        self.assertTrue(self.engine.resume_pending)
        self.engine.pause_reasons.add("locked")
        with patch("room_brightness.tuning.foreground_app", return_value=None):
            self.engine.check_foreground()
        self.assertIn("application", self.engine.pause_reasons)
        with (
            patch("room_brightness.tuning.foreground_app", return_value="explorer.exe"),
            patch.object(self.engine, "verify") as verify,
        ):
            self.engine.check_foreground()
            verify.assert_not_called()
            self.assertNotIn("application", self.engine.pause_reasons)
            self.engine.stop()
            self.assertFalse(self.engine.resume_pending)
            self.engine.session_pause("locked", False)
            verify.assert_not_called()

    def test_compatibility_read_only_and_restoration_paths(self):
        from room_brightness.tuning_ui import CompatibilityDialog

        dialog = CompatibilityDialog(self.window)

        def immediate(function, done, operation):
            done(function())

        with (
            patch.object(self.engine, "work", side_effect=immediate),
            patch("room_brightness.brightness.brightness", return_value=60),
            patch(
                "room_brightness.camera.sample", return_value=dict(level=20, confidence=0.9)
            ) as camera,
            patch("room_brightness.brightness.verify_control") as control,
        ):
            dialog.run(False)
            camera.assert_called_once()
            control.assert_not_called()
            self.assertIn("Passed", dialog.results.text())
            dialog.run(True)
            control.assert_called_once()
        with (
            patch.object(self.engine, "work", side_effect=immediate),
            patch(
                "room_brightness.brightness.verify_control",
                side_effect=RuntimeError("Could not confirm restoration"),
            ),
        ):
            dialog.run(True)
            self.assertIn("restore brightness manually", dialog.results.text())
        dialog.reject()
        dialog.deleteLater()

    def test_calibration_capture_failure_is_local_and_retryable(self):
        from room_brightness.tuning_ui import CalibrationDialog

        dialog = CalibrationDialog(self.window)
        dialog.show()
        with (
            patch.object(self.engine, "work", side_effect=lambda f, d, o: d(f())),
            patch("room_brightness.camera.sample", side_effect=RuntimeError("busy")),
            patch("room_brightness.brightness.verify_control") as control,
        ):
            dialog.capture()
            self.assertIsNone(dialog.reading)
            self.assertTrue(dialog.capture_button.isEnabled())
            self.assertIn("failed", dialog.feedback.text())
            control.assert_not_called()
        dialog.reject()
        dialog.deleteLater()

    def test_camera_preferences_are_independent_and_persisted(self):
        from room_brightness.settings import load_settings

        first = self.device
        second = dict(index=1, id="second-camera", name="Second camera")
        self.engine.devices = [first, second]
        self.engine.preferences["meter_region"] = [0, 0.1, 0.8, 0.9]
        self.engine.preferences["spatial_protection"] = True
        self.engine.persist()
        self.engine.choose_device(second)
        self.engine.preferences["meter_region"] = [0.2, 0, 1, 1]
        self.engine.preferences["spatial_protection"] = False
        self.engine.persist()
        self.engine.choose_device(first)
        self.assertEqual(self.engine.preferences["meter_region"], [0, 0.1, 0.8, 0.9])
        self.assertTrue(self.engine.preferences["spatial_protection"])
        saved = load_settings(Path(self.folder.name))
        self.assertEqual(saved["camera_profiles"]["second-camera"]["meter_region"], [0.2, 0, 1, 1])

    def test_general_settings_undo_persists_and_keeps_device_identity(self):
        import copy

        candidate = copy.deepcopy(self.engine.preferences)
        candidate.update(reduce_motion=True, theme="dark")
        before = self.engine.preferences["theme"]
        self.engine.apply_preferences(candidate)
        self.assertTrue(self.engine.preferences["reduce_motion"])
        self.assertTrue(self.engine.undo_options())
        self.assertFalse(self.engine.preferences["reduce_motion"])
        self.assertEqual(self.engine.preferences["theme"], before)
        self.assertEqual(self.engine.camera_id, self.device["id"])
        with patch("room_brightness.settings.save_settings", side_effect=OSError("denied")):
            candidate = copy.deepcopy(self.engine.preferences)
            candidate["reduce_motion"] = True
            count = len(self.engine.settings_undo)
            with self.assertRaises(ValueError):
                self.engine.apply_preferences(candidate)
            self.assertEqual(len(self.engine.settings_undo), count)

    def test_clock_pause_and_stop_cancel_all_pending_recovery(self):
        from PySide6.QtCore import QTime
        from room_brightness.adaptive import AdaptiveController

        self.engine.running = True
        self.engine.run_requested = True
        self.engine.controller = AdaptiveController(low=10, high=80, expected=70)
        self.engine.pause_until(QTime.currentTime().addSecs(3600))
        self.assertIn("timed", self.engine.pause_reasons)
        self.assertGreater(self.engine.pause_remaining(), 3500)
        self.engine.pause_until_charger()
        self.assertTrue(self.engine.pause_until_ac)
        self.engine.stop()
        self.assertFalse(self.engine.pause_until_ac)
        self.assertFalse(self.engine.resume_pending)
        self.assertFalse(self.engine.run_requested)

    def test_device_recovery_requires_exact_camera_and_stop_prevents_resume(self):
        from room_brightness.adaptive import AdaptiveController

        self.engine.running = True
        self.engine.run_requested = True
        self.engine.controller = AdaptiveController(low=10, high=80, expected=70)
        self.engine.wait_for_devices()
        self.assertIn("device", self.engine.pause_reasons)
        with (
            patch.object(self.engine, "work", side_effect=lambda f, d, o: d(f())),
            patch(
                "room_brightness.ui.list_devices",
                return_value=[dict(id="different", name="Other", index=0)],
            ),
            patch("room_brightness.ui.brightness") as read,
            patch.object(self.engine, "verify") as verify,
        ):
            self.engine.recover_devices()
            read.assert_not_called()
            verify.assert_not_called()
            self.assertTrue(self.engine.resume_pending)
            self.engine.stop()
            self.engine.recover_devices()
            verify.assert_not_called()
        self.assertIsNone(self.engine.device_retry_timer)

    def test_update_options_defaults_and_reduced_motion_accessible_dialog(self):
        from room_brightness.session_ui import SessionDialog
        from room_brightness.qt_ui import ToggleSwitch

        self.assertFalse(self.engine.preferences["resume_automatic"])
        self.assertFalse(self.engine.preferences["auto_download_updates"])
        self.assertTrue(self.engine.preferences["update_checks"])
        with patch("room_brightness.updater.open_url") as network:
            dialog = SessionDialog(self.window)
            self.assertTrue(dialog.download_button.accessibleName())
            self.assertTrue(dialog.notes.accessibleName())
            network.assert_not_called()
            dialog.reject()
            dialog.deleteLater()
        self.engine.preferences["reduce_motion"] = True
        switch = ToggleSwitch("Accessible switch")
        switch.setParent(self.window)
        switch.show()
        switch.setChecked(True)
        self.assertEqual(switch.position, 1)
        self.assertEqual(switch.animation.state(), switch.animation.State.Stopped)
        switch.deleteLater()

    def test_startup_resume_opt_in_and_daily_checks_without_network(self):
        self.engine.preferences.update(
            resume_automatic=False, resume_was_running=True, onboarding_done=True
        )
        self.engine.init_lifecycle(True)
        self.assertFalse(self.engine.startup_resume_pending)
        self.engine.preferences["resume_automatic"] = True
        self.engine.init_lifecycle(True)
        self.assertTrue(self.engine.startup_resume_pending)
        with (
            patch.object(self.engine, "start") as start,
            patch.object(self.engine.update_client, "check") as check,
        ):
            self.engine.lifecycle_tick()
            start.assert_called_once()
            check.assert_called_once()
            self.engine.update_client.last_attempt = time.monotonic()
            self.engine.lifecycle_tick()
            self.assertEqual(check.call_count, 1)
            self.engine.update_client.last_attempt = time.monotonic() - 86401
            self.engine.lifecycle_tick()
            self.assertEqual(check.call_count, 2)
        with patch("room_brightness.ui.App.close"):
            self.engine.running = True
            self.engine.close()
            self.assertTrue(self.engine.preferences["resume_was_running"])
            self.assertTrue(self.engine.update_client.closed)

    def test_session_dialog_widgets_belong_to_scroll_content(self):
        from room_brightness.session_ui import SessionDialog
        from PySide6.QtWidgets import QScrollArea

        dialog = SessionDialog(self.window)
        dialog.show()
        self.qt.processEvents()
        content = dialog.findChild(QScrollArea).widget()
        self.assertIs(dialog.check_button.parentWidget(), content)
        self.assertTrue(dialog.check_button.isVisible())
        self.assertTrue(dialog.install_button.accessibleName())
        dialog.reject()
        dialog.deleteLater()

    def test_restoration_failure_does_not_enter_automatic_device_retry(self):
        self.engine.run_requested = True
        self.engine.running = True
        with (
            patch.object(self.engine, "wait_for_devices") as wait,
            patch("room_brightness.ui.App.handle_error"),
        ):
            self.engine.handle_error(
                "test", "Could not confirm restoration. Restore brightness manually."
            )
            wait.assert_not_called()
            self.assertFalse(self.engine.run_requested)

    def test_missing_saved_camera_requires_explicit_selection_of_replacement(self):
        replacement = dict(id="replacement", name="Replacement camera", index=0)
        self.engine.devices = [replacement]
        self.window.update_values()
        self.assertEqual(self.window.cameras.currentIndex(), -1)
        self.assertFalse(self.window.start_button.isEnabled())
        self.window.cameras.setCurrentIndex(0)
        self.assertEqual(self.engine.selected_device()["id"], "replacement")

    def test_trial_never_persists_until_keep_and_expiry_restores(self):
        import copy
        from room_brightness.settings import load_settings

        original = copy.deepcopy(self.engine.preferences)
        baseline = load_settings(Path(self.folder.name))
        candidate = copy.deepcopy(original)
        candidate.update(low=20, high=70, brightness_curve="night")
        self.engine.begin_trial(candidate)
        self.assertEqual(self.engine.low.get(), 20)
        self.engine.persist()
        self.assertEqual(load_settings(Path(self.folder.name))["low"], baseline["low"])
        self.engine.trial_deadline = time.monotonic() - 1
        self.engine.trial_tick()
        self.assertIsNone(self.engine.trial_original)
        self.assertEqual(self.engine.preferences["low"], original["low"])
        self.assertEqual(load_settings(Path(self.folder.name))["low"], baseline["low"])
        self.engine.begin_trial(candidate)
        self.engine.end_trial(True)
        self.assertIsNone(self.engine.trial_original)
        self.assertEqual(load_settings(Path(self.folder.name))["low"], 20)
        self.assertTrue(self.engine.undo_options())
        self.assertEqual(self.engine.low.get(), original["low"])

    def test_trial_keep_failure_restores_previous_runtime_without_writing(self):
        import copy

        candidate = copy.deepcopy(self.engine.preferences)
        candidate["low"] = 22
        old = self.engine.low.get()
        self.engine.begin_trial(candidate)
        with patch("room_brightness.settings.save_settings", side_effect=OSError("denied")):
            self.engine.end_trial(True)
        self.assertEqual(self.engine.low.get(), old)
        self.assertIsNone(self.engine.trial_original)
        self.assertFalse(self.engine.trial_transition)

    def test_trial_stop_and_busy_revert_wait_before_settings_change(self):
        import copy

        candidate = copy.deepcopy(self.engine.preferences)
        candidate["low"] = 22
        self.engine.begin_trial(candidate)
        self.engine.busy = True
        self.engine.stop()
        self.assertTrue(self.engine.trial_ending)
        self.assertTrue(self.engine.cancel.is_set())
        self.engine.busy = False
        for _ in range(5):
            self.qt.processEvents()
            time.sleep(0.04)
        self.assertIsNone(self.engine.trial_original)
        self.assertEqual(self.engine.low.get(), 10)

    def test_power_curves_are_applied_to_next_controller_cycle(self):
        from room_brightness.adaptive import AdaptiveController
        from room_brightness.experience import effective_curve

        self.engine.preferences["separate_power_curves"] = True
        self.engine.preferences["power_curves"]["ac"]["points"] = [[12, 0], [20, 40], [40, 100]]
        self.engine.controller = AdaptiveController(low=10, high=80, expected=60)
        self.engine.running = True
        self.engine.begin_pair_cycle()
        curve = effective_curve(self.engine.preferences, self.engine.power_mode)
        self.assertEqual(self.engine.controller.options["custom_points"], curve["points"])
        self.assertEqual(self.engine.controller.image_curve, curve["curve"])
        self.engine.stop()

    def test_quick_panel_and_issue_report_do_not_capture_or_upload(self):
        from room_brightness.experience_ui import QuickPanel, IssueDialog

        with (
            patch("room_brightness.camera.sample") as camera,
            patch("room_brightness.updater.open_url") as network,
        ):
            self.engine.display_value.set("55")
            panel = QuickPanel(self.window)
            self.assertIn("55%", panel.metric_label.text())
            panel.reject()
            panel.deleteLater()
            issue = IssueDialog(self.window)
            report = issue.preview.toPlainText()
            self.assertIn("device_health", report)
            self.assertNotIn("Demo camera", report)
            self.assertNotIn(self.folder.name, report)
            issue.reject()
            issue.deleteLater()
            camera.assert_not_called()
            network.assert_not_called()

    def test_numeric_decision_explains_raw_target_and_held_brightness(self):
        self.engine.last_meter = dict(level=20, target=60, current=60, quality=1)
        self.engine.display_value.set("60")
        values = self.engine.decision_values()
        self.assertEqual(values["raw"], 70)
        self.assertEqual(values["target"], 60)
        self.window.update_values()
        self.assertIn("70", self.window.decision_label.text())
        self.assertIn("60", self.window.decision_label.text())

    def test_trial_exit_reverts_before_normal_shutdown(self):
        import copy

        candidate = copy.deepcopy(self.engine.preferences)
        candidate["low"] = 24
        self.engine.begin_trial(candidate)
        self.engine.exit_running_intent = True
        with patch("room_brightness.ui.App.close") as close:
            self.engine.close()
            for _ in range(6):
                self.qt.processEvents()
                time.sleep(0.04)
            close.assert_called_once()
        self.assertIsNone(self.engine.trial_original)
        self.assertEqual(self.engine.low.get(), 10)
        self.assertFalse(self.engine.preferences["resume_was_running"])

    def test_comparison_saves_active_power_curve_without_overwriting_other_source(self):
        from room_brightness.tuning_ui import CompareDialog

        self.engine.preferences["separate_power_curves"] = True
        before = self.engine.preferences["power_curves"]["battery"]["points"]
        dialog = CompareDialog(self.window, [[12, 0], [20, 40], [40, 100]])
        dialog.power_mode = "ac"
        dialog.save_comparison()
        self.assertEqual(self.engine.preferences["power_curves"]["ac"]["points"][1], [20, 40])
        self.assertEqual(self.engine.preferences["power_curves"]["battery"]["points"], before)
        dialog.deleteLater()

    def test_reviewed_issue_bundle_export_contains_no_images_or_paths(self):
        from room_brightness.experience_ui import IssueDialog
        import zipfile
        import json

        target = Path(self.folder.name) / "problem.zip"
        dialog = IssueDialog(self.window)
        with patch(
            "room_brightness.experience_ui.QFileDialog.getSaveFileName",
            return_value=(str(target), "ZIP"),
        ):
            dialog.save()
        with zipfile.ZipFile(target) as archive:
            self.assertEqual(set(archive.namelist()), {"diagnostics.json", "ISSUE.md"})
            report = archive.read("diagnostics.json").decode()
            self.assertNotIn(self.folder.name, report)
            self.assertNotIn("Demo camera", report)
            self.assertIn("device_health", json.loads(report))
        dialog.reject()
        dialog.deleteLater()

    def test_rollback_is_not_launched_from_source_or_portable(self):
        with (
            patch("subprocess.Popen") as launch,
            patch("room_brightness.experience_ui.QMessageBox.information"),
        ):
            self.window.rollback_installed()
            launch.assert_not_called()

    def test_trial_revert_during_lock_keeps_manual_override_detection(self):
        import copy
        from room_brightness.adaptive import AdaptiveController

        candidate = copy.deepcopy(self.engine.preferences)
        candidate["low"] = 22
        self.engine.begin_trial(candidate)
        self.engine.original = 50
        self.engine.controller = AdaptiveController(low=22, high=80, expected=70)
        self.engine.pause_reasons.add("locked")
        self.engine.end_trial(False)
        self.assertEqual(self.engine.controller.expected, 70)
        self.assertEqual(self.engine.low.get(), 10)
        with (
            patch.object(self.engine, "work", side_effect=lambda f, d, o: d(f())),
            patch("room_brightness.ui.brightness", return_value=65),
            patch("room_brightness.ui.set_checked") as write,
        ):
            self.engine.session_pause("locked", False)
            write.assert_not_called()
        self.assertIsNone(self.engine.original)

    def test_quick_panel_reuses_one_window_and_refreshes_language(self):
        self.window.quick_panel()
        first = self.window.quick_window
        first.reject()
        self.window.quick_panel()
        self.assertIs(self.window.quick_window, first)
        self.assertTrue(first.timer.isActive())
        first.reject()
        self.window.change_language("ar")
        self.window.quick_panel()
        self.assertIsNot(self.window.quick_window, first)
        self.window.quick_window.reject()
