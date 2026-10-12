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
                self.assertFalse(event.isAccepted())

    def test_numeric_settings_are_right_aligned_in_arabic(self):
        from PySide6.QtCore import Qt
        from room_brightness.qt_ui import NoWheelSpinBox
        self.window.page="settings"
        self.window.change_language("ar")
        for spin in self.window.findChildren(NoWheelSpinBox):
            self.assertTrue(spin.alignment() & Qt.AlignmentFlag.AlignRight)
            self.assertTrue(spin.alignment() & Qt.AlignmentFlag.AlignAbsolute)

    def test_new_brand_icon_is_used_by_window_and_tray(self):
        icon=self.window.windowIcon()
        self.assertFalse(icon.isNull())
        self.assertFalse(self.window.tray.icon().isNull())
        for size in (16,32,64,256):
            self.assertFalse(icon.pixmap(size,size).isNull())
