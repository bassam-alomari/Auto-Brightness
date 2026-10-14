"""Validated, atomic per-user preferences, including legacy calibration migration."""

import copy
import ctypes
import json
import math
from pathlib import Path
from .i18n import LANGUAGES
from .themes import THEME_NAMES

DEFAULTS = {
    "onboarding_done": False,
    "meter_region": [0, 0, 1, 1],
    "adaptive_sampling": False,
    "max_interval_ac": 30,
    "max_interval_battery": 60,
    "shortcuts_enabled": False,
    "profiles": {},
    "curve_history": [],
    "display_target": "internal",
    "display_profiles": {},
    "stability_guard": True,
    "deadband": 3,
    "transition_speed": "balanced",
    "custom_points": [[12, 0], [15, 50], [20, 70], [25, 90], [27, 100]],
    "power_profiles": False,
    "ac_limits": [10, 100],
    "battery_limits": [10, 80],
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
    result = copy.deepcopy(DEFAULTS)
    if not isinstance(raw, dict):
        return result
    from .extras import valid_region, PROFILE_KEYS

    for key in ("onboarding_done", "adaptive_sampling", "shortcuts_enabled"):
        if type(raw.get(key)) is bool:
            result[key] = raw[key]
    for key in ("max_interval_ac", "max_interval_battery"):
        if type(raw.get(key)) is int and 5 <= raw[key] <= 600:
            result[key] = raw[key]
    if valid_region(raw.get("meter_region")):
        result["meter_region"] = raw["meter_region"][:]
    if isinstance(raw.get("display_target"), str) and len(raw["display_target"]) <= 1024:
        result["display_target"] = raw["display_target"]
    for key in ("profiles", "display_profiles"):
        profiles = raw.get(key, {})
        if isinstance(profiles, dict):
            for name, values in list(profiles.items())[:20]:
                if (
                    isinstance(name, str)
                    and 0 < len(name) <= (1024 if key == "display_profiles" else 40)
                    and isinstance(values, dict)
                ):
                    clean = validate({k: v for k, v in values.items() if k in PROFILE_KEYS})
                    result[key][name] = {k: clean[k] for k in PROFILE_KEYS if k in values}
    from .comfort import valid_points

    history = raw.get("curve_history", [])
    if isinstance(history, list):
        result["curve_history"] = [
            copy.deepcopy(points) for points in history[-20:] if valid_points(points)
        ]

    for key in ("stability_guard", "power_profiles"):
        if type(raw.get(key)) is bool:
            result[key] = raw[key]
    if type(raw.get("deadband")) is int and 1 <= raw["deadband"] <= 10:
        result["deadband"] = raw["deadband"]
    if raw.get("transition_speed") in ("calm", "balanced", "fast"):
        result["transition_speed"] = raw["transition_speed"]
    if valid_points(raw.get("custom_points")):
        result["custom_points"] = [list(point) for point in raw["custom_points"]]
    for key in ("ac_limits", "battery_limits"):
        limits = raw.get(key)
        if (
            isinstance(limits, list)
            and len(limits) == 2
            and all(type(v) is int for v in limits)
            and 0 <= limits[0] < limits[1] <= 100
        ):
            result[key] = limits[:]
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
        raw = json.loads((directory / "settings.json").read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("Settings must be an object.")
        return validate(raw)
    except (OSError, ValueError):
        from .recovery import recover_settings

        recovered = recover_settings(directory)
        if recovered is not None:
            return recovered
        try:
            old = json.loads((directory / "calibration.json").read_text(encoding="utf-8"))
            return validate(
                dict(low=old.get("low"), high=old.get("high"), camera_index=old.get("camera", 0))
            )
        except (OSError, ValueError, AttributeError):
            return copy.deepcopy(DEFAULTS)


def save_settings(directory: Path, values):
    from .recovery import snapshot, write_atomic

    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / "settings.json"
    cleaned = validate(values)
    if destination.exists():
        try:
            previous = json.loads(destination.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            previous = None
        if isinstance(previous, dict):
            if validate(previous) == cleaned:
                return
            snapshot(directory, previous, cleaned)
    write_atomic(destination, json.dumps(cleaned, ensure_ascii=False, indent=2))
