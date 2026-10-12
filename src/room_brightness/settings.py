"""Validated, atomic per-user preferences, including legacy calibration migration."""

import ctypes
import json
import math
import os
from pathlib import Path
from .i18n import LANGUAGES
from .themes import THEME_NAMES

DEFAULTS = {
    "language": "auto",
    "theme": "auto",
    "glass_tint": 50,
    "glass_defaults_revision": 1,
    "arabic_dialect": "msa",
    "tray_defaults_revision": 1,
    "startup_defaults_revision": 0,
    "brightness_curve": "custom",
    "sensitivity": "balanced",
    "minimize_tray": False,
    "close_tray": True,
    "startup": True,
    "interval_defaults_revision": 1,
    "interval_ac": 5,
    "interval_battery": 10,
    "low": 10,
    "floor_revision": 2,
    "protect_dim": True,
    "high": 80,
    "restore": True,
    "camera_id": "",
    "camera_name": "",
    "camera_index": 0,
    "calibration_id": "",
    "dark": None,
    "bright": None,
}


def system_language():
    # Read the explicit Windows UI override, including changes made while running.
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop") as key:
            preferred = winreg.QueryValueEx(key, "PreferredUILanguages")[0]
        if isinstance(preferred, str):
            preferred = [preferred]
        if isinstance(preferred, list) and preferred:
            code = preferred[0].split("-")[0].lower()
            return code if code in LANGUAGES and code != "auto" else "en"
    except (ImportError, OSError):
        pass
    try:
        language_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
        return {1: "ar", 10: "es", 12: "fr", 7: "de", 22: "pt", 4: "zh", 57: "hi"}.get(
            language_id & 0x3FF, "en"
        )
    except (AttributeError, OSError):
        return "en"


def resolve_language(preference):
    return preference if preference in LANGUAGES and preference != "auto" else system_language()


def system_theme():
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        ) as key:
            light = winreg.QueryValueEx(key, "AppsUseLightTheme")[0]
        return "light" if light else "dark"
    except (ImportError, OSError):
        return "light"


def resolve_theme(preference):
    return preference if preference in ("light", "dark", "glass", *THEME_NAMES) else system_theme()


def validate(raw):
    result = DEFAULTS.copy()
    if not isinstance(raw, dict):
        return result
    from .adaptive import CURVES

    if raw.get("brightness_curve") in CURVES:
        result["brightness_curve"] = raw["brightness_curve"]
    if raw.get("arabic_dialect") in ("msa", "jo", "eg", "gulf"):
        result["arabic_dialect"] = raw["arabic_dialect"]
    if raw.get("startup_defaults_revision") == 1:
        result["startup_defaults_revision"] = 1
    if raw.get("language") in LANGUAGES:
        result["language"] = raw["language"]
    if raw.get("theme") in ("auto", "light", "dark", "glass", *THEME_NAMES):
        result["theme"] = raw["theme"]
    if type(raw.get("glass_tint")) is int and 0 <= raw["glass_tint"] <= 100:
        result["glass_tint"] = raw["glass_tint"]
        if raw["glass_tint"] == 30 and raw.get("glass_defaults_revision") != 1:
            result["glass_tint"] = 50
    if type(raw.get("startup")) is bool:
        result["startup"] = raw["startup"]
    for key in ("interval_ac", "interval_battery"):
        if type(raw.get(key)) is int and 5 <= raw[key] <= 600:
            result[key] = raw[key]
    if (
        raw.get("interval_defaults_revision") != 1
        and raw.get("interval_ac") == 15
        and raw.get("interval_battery") == 60
    ):
        result.update(interval_ac=5, interval_battery=10)
    if raw.get("sensitivity") in ("gentle", "balanced", "responsive"):
        result["sensitivity"] = raw["sensitivity"]
    for key in ("minimize_tray", "close_tray", "protect_dim"):
        if type(raw.get(key)) is bool:
            result[key] = raw[key]
    if raw.get("tray_defaults_revision") != 1:
        result["close_tray"] = True
    low, high = raw.get("low"), raw.get("high")
    if type(low) is int and type(high) is int and 0 <= low < high <= 100:
        result.update(low=low, high=high)
        # One-time migration of the former default; other personal floors stay intact.
        if low in (25, 55) and raw.get("floor_revision") != 2:
            result["low"] = 10
    if type(raw.get("restore")) is bool:
        result["restore"] = raw["restore"]
    for key in ("camera_id", "camera_name", "calibration_id"):
        if isinstance(raw.get(key), str):
            result[key] = raw[key]
    if type(raw.get("camera_index")) is int and raw["camera_index"] >= 0:
        result["camera_index"] = raw["camera_index"]
    for key in ("dark", "bright"):
        value = raw.get(key)
        if type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 255:
            result[key] = value
    return result


def load_settings(directory: Path):
    try:
        return validate(json.loads((directory / "settings.json").read_text(encoding="utf-8")))
    except (OSError, ValueError):
        try:
            old = json.loads((directory / "calibration.json").read_text(encoding="utf-8"))
            return validate(
                dict(low=old.get("low"), high=old.get("high"), camera_index=old.get("camera", 0))
            )
        except (OSError, ValueError, AttributeError):
            return DEFAULTS.copy()


def save_settings(directory: Path, values):
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / "settings.json"
    temporary = directory / "settings.json.tmp"
    temporary.write_text(
        json.dumps(validate(values), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    os.replace(temporary, destination)
