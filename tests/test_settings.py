import json
from pathlib import Path
import string
import tempfile
import unittest
from unittest.mock import patch

from room_brightness.i18n import STRINGS, text
from room_brightness.settings import (
    load_settings,
    save_settings,
    validate,
    system_language,
    resolve_language,
)


class SettingsTests(unittest.TestCase):
    @patch("winreg.QueryValueEx")
    @patch("winreg.OpenKey")
    def test_requested_ui_language_is_read_live(self, opened, query):
        from unittest.mock import MagicMock

        opened.return_value = MagicMock()
        for value, expected in [(["ar-JO"], "ar"), ("en-US", "en"), (["arn-CL"], "en")]:
            query.return_value = (value, 7)
            self.assertEqual(system_language(), expected)

    @patch("winreg.QueryValueEx")
    @patch("winreg.OpenKey")
    def test_system_app_theme_is_read_live(self, opened, query):
        from unittest.mock import MagicMock
        from room_brightness.settings import system_theme

        opened.return_value = MagicMock()
        query.return_value = (0, 4)
        self.assertEqual(system_theme(), "dark")
        query.return_value = (1, 4)
        self.assertEqual(system_theme(), "light")

    def test_system_ui_language_selects_arabic_variants(self):
        registry = patch("winreg.OpenKey", side_effect=OSError("No explicit UI override"))
        registry.start()
        self.addCleanup(registry.stop)
        for lang_id in (0x0401, 0x2C01):
            with patch(
                "room_brightness.settings.ctypes.windll.kernel32.GetUserDefaultUILanguage",
                return_value=lang_id,
            ):
                self.assertEqual(system_language(), "ar")
        with patch(
            "room_brightness.settings.ctypes.windll.kernel32.GetUserDefaultUILanguage",
            return_value=0x0409,
        ):
            self.assertEqual(system_language(), "en")

    def test_manual_choice_overrides_system_language(self):
        with patch("room_brightness.settings.system_language", return_value="ar"):
            self.assertEqual(resolve_language("en"), "en")
            self.assertEqual(resolve_language("auto"), "ar")

    def test_unicode_preferences_and_partial_calibration_roundtrip(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            save_settings(
                directory,
                dict(
                    language="ar",
                    low=30,
                    high=90,
                    camera_name="كاميرا USB",
                    camera_id="device",
                    calibration_id="device",
                    dark=37.2,
                ),
            )
            saved = load_settings(directory)
            self.assertEqual(saved["language"], "ar")
            self.assertEqual(saved["camera_name"], "كاميرا USB")
            self.assertEqual(saved["dark"], 37.2)
            self.assertIsNone(saved["bright"])
            self.assertFalse((directory / "settings.json.tmp").exists())

    def test_invalid_old_ranges_are_repaired(self):
        self.assertEqual(validate(dict(low=0, high=100))["low"], 0)
        self.assertEqual(validate(dict(low=90, high=20))["high"], 80)
        self.assertIsNone(validate(dict(dark=float("nan")))["dark"])

    def test_corrupt_preferences_use_safe_defaults(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            (directory / "settings.json").write_text("{broken", encoding="utf-8")
            self.assertEqual(load_settings(directory)["language"], "auto")

    def test_legacy_numeric_camera_is_not_trusted_as_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            (directory / "calibration.json").write_text(
                json.dumps(dict(low=35, high=90, camera=1, dark=20, light=200))
            )
            saved = load_settings(directory)
            self.assertEqual(saved["low"], 35)
            self.assertIsNone(saved["dark"])
            self.assertEqual(saved["camera_id"], "")

    def test_translations_cover_the_same_placeholders(self):
        formatter = string.Formatter()
        for key, (english, arabic) in STRINGS.items():
            en_fields = {field for _, field, _, _ in formatter.parse(english) if field}
            ar_fields = {field for _, field, _, _ in formatter.parse(arabic) if field}
            self.assertEqual(en_fields, ar_fields, key)
            values = {field: "42" for field in en_fields}
            self.assertTrue(text("en", key, **values))
            self.assertTrue(text("ar", key, **values))


class IntervalTests(unittest.TestCase):
    def test_intervals_are_validated(self):
        from room_brightness.settings import validate

        self.assertEqual(validate({"interval_ac": 5, "interval_battery": 600})["interval_ac"], 5)
        for value in [True, 0, 601, "30"]:
            self.assertEqual(validate({"interval_ac": value})["interval_ac"], 5)

    def test_glass_tint_validates_range_and_rejects_boolean(self):
        for value in [0, 50, 100]:
            self.assertEqual(validate({"glass_tint": value})["glass_tint"], value)
        for value in [-1, 101, True, "50", None]:
            self.assertEqual(validate({"glass_tint": value})["glass_tint"], 50)

    def test_old_default_floor_migrates_once_and_preserves_personal_floor(self):
        self.assertEqual(validate({"low": 55, "high": 100})["low"], 10)
        self.assertEqual(validate({"low": 55, "high": 100, "floor_revision": 2})["low"], 55)
        self.assertEqual(validate({"low": 40, "high": 100})["low"], 40)


class MoreLanguagesTests(unittest.TestCase):
    def test_supported_languages_and_curves_are_saved(self):
        from room_brightness.i18n import LANGUAGES, text
        from room_brightness.settings import resolve_language

        for code in LANGUAGES:
            self.assertEqual(validate({"language": code})["language"], code)
            if code != "auto":
                self.assertEqual(resolve_language(code), code)
                self.assertTrue(text(code, "manual_help", seconds=10))
        self.assertEqual(validate({"brightness_curve": "night"})["brightness_curve"], "night")


class NewDefaultsAndDialectTests(unittest.TestCase):
    def test_defaults_and_subsequent_opt_outs(self):
        from room_brightness.settings import DEFAULTS

        self.assertEqual(DEFAULTS["glass_tint"], 50)
        self.assertTrue(DEFAULTS["close_tray"])
        self.assertTrue(DEFAULTS["startup"])
        self.assertFalse(validate(dict(close_tray=False, tray_defaults_revision=1))["close_tray"])
        self.assertEqual(validate(dict(glass_tint=30, glass_defaults_revision=1))["glass_tint"], 30)
        self.assertEqual(validate(dict(glass_tint=30))["glass_tint"], 50)
        for style in ("msa", "jo", "eg", "gulf"):
            self.assertEqual(validate({"arabic_dialect": style})["arabic_dialect"], style)

    def test_arabic_styles_preserve_format_placeholders(self):
        from room_brightness.i18n import ARABIC_STYLES

        formatter = string.Formatter()
        for style, catalog in ARABIC_STYLES.items():
            for english, arabic in catalog.items():
                a = {key for _, key, _, _ in formatter.parse(english) if key}
                b = {key for _, key, _, _ in formatter.parse(arabic) if key}
                self.assertEqual(a, b, (style, english))

class ArabicDirectionTests(unittest.TestCase):
    def test_windows_is_directionally_isolated_in_arabic_label(self):
        from room_brightness.i18n import text
        value=text("ar","startup")
        self.assertTrue(value.startswith("\u200f"))
        self.assertIn("ويندوز",value)
        self.assertTrue(value.endswith("ويندوز"))

class ConsistentArabicDigitsTests(unittest.TestCase):
    def test_arabic_reading_uses_one_digit_set(self):
        from room_brightness.i18n import literal
        for style in ("msa","jo","eg","gulf"):
            value=literal("ar","Image: {level}/255 · Stability: {quality}%\nTarget: {target}%",dialect=style).format(level=29,quality=100,target=55)
            self.assertIn("29/255",value)
            self.assertFalse(any(c in value for c in "٠١٢٣٤٥٦٧٨٩"))
