"""Portable preferences, bounded histories, quiet retries, and power-saving decisions."""

from collections import deque
import copy
import re

PORTABLE_KEYS = (
    "language",
    "arabic_dialect",
    "theme",
    "glass_tint",
    "brightness_curve",
    "custom_points",
    "low",
    "high",
    "interval_ac",
    "interval_battery",
    "restore",
    "protect_dim",
    "stability_guard",
    "deadband",
    "transition_speed",
    "power_profiles",
    "ac_limits",
    "battery_limits",
    "meter_region",
    "adaptive_sampling",
    "max_interval_ac",
    "max_interval_battery",
    "shortcuts_enabled",
    "profiles",
)
PROFILE_KEYS = tuple(
    key
    for key in PORTABLE_KEYS
    if key
    not in ("profiles", "language", "arabic_dialect", "theme", "glass_tint", "shortcuts_enabled")
)


def valid_region(region):
    import math

    return (
        isinstance(region, list)
        and len(region) == 4
        and all(type(v) in (int, float) and math.isfinite(v) for v in region)
        and 0 <= region[0] < region[2] <= 1
        and 0 <= region[1] < region[3] <= 1
        and region[2] - region[0] >= 0.1
        and region[3] - region[1] >= 0.1
    )


def crop_frame(frame, region):
    if not valid_region(region):
        raise ValueError("Invalid camera metering region.")
    height, width = frame.shape[:2]
    x0, y0, x1, y1 = region
    crop = frame[round(y0 * height) : round(y1 * height), round(x0 * width) : round(x1 * width)]
    if crop.shape[0] < 1 or crop.shape[1] < 1:
        raise ValueError("Metering region is empty.")
    return crop


def export_preferences(settings):
    return {
        "app": "Auto Brightness",
        "format": 1,
        "settings": {key: copy.deepcopy(settings[key]) for key in PORTABLE_KEYS},
    }


def import_preferences(document, current):
    from .settings import validate

    if (
        not isinstance(document, dict)
        or document.get("app") != "Auto Brightness"
        or document.get("format") != 1
        or not isinstance(document.get("settings"), dict)
    ):
        raise ValueError("Invalid Auto Brightness settings file.")
    raw = copy.deepcopy(current)
    raw.update({key: value for key, value in document["settings"].items() if key in PORTABLE_KEYS})
    return validate(raw)


def profile_settings(current, name):
    custom = current.get("profiles", {}).get(name)
    if custom is not None:
        return copy.deepcopy(custom)
    presets = {
        "work": {
            "brightness_curve": "custom",
            "transition_speed": "balanced",
            "adaptive_sampling": True,
        },
        "gaming": {
            "brightness_curve": "day",
            "transition_speed": "fast",
            "interval_ac": 15,
            "interval_battery": 30,
        },
        "night": {"brightness_curve": "night", "low": 0, "high": 50, "transition_speed": "calm"},
    }
    if name not in presets:
        raise ValueError("Unknown profile.")
    return copy.deepcopy(presets[name])


def release_version(tag):
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", tag or "")
    if not match:
        raise ValueError("Invalid release version.")
    return tuple(int(value) for value in match.groups())


def parse_release(document, current_version):
    if not isinstance(document, dict) or document.get("draft") or document.get("prerelease"):
        return None
    tag = document.get("tag_name", "")
    if release_version(tag) <= release_version(current_version):
        return None
    url = document.get("html_url", "")
    prefix = "https://github.com/bassam-alomari/Auto-Brightness/releases/tag/"
    if not isinstance(url, str) or not url.startswith(prefix) or url[len(prefix) :] != tag:
        raise ValueError("Unexpected update link.")
    return {"version": tag, "url": url}


class SamplingBudget:
    def __init__(self):
        self.levels = deque(maxlen=4)
        self.targets = deque(maxlen=4)
        self.stable_cycles = 0

    def observe(self, meter):
        if (
            meter.get("quality", 0) < 0.35
            or meter.get("reason") in ("transient", "uncertain", "confirming_change")
            or abs(meter.get("target", 0) - meter.get("current", 0)) > 3
        ):
            self.reset()
            return
        self.levels.append(meter["level"])
        self.targets.append(meter["target"])
        if (
            len(self.levels) == 4
            and max(self.levels) - min(self.levels) <= 2
            and max(self.targets) - min(self.targets) <= 3
        ):
            self.stable_cycles += 1
        else:
            self.stable_cycles = 0

    def reset(self):
        self.levels.clear()
        self.targets.clear()
        self.stable_cycles = 0

    def interval(self, base, maximum, enabled):
        if not enabled or not self.stable_cycles:
            return base
        return min(max(base, maximum), base * 2 ** min(4, 1 + (self.stable_cycles - 1) // 4))


def check_release(current_version):
    import json
    import urllib.request

    request = urllib.request.Request(
        "https://api.github.com/repos/bassam-alomari/Auto-Brightness/releases/latest",
        headers={
            "User-Agent": "AutoBrightness/" + current_version,
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(request, timeout=8) as response:
        payload = response.read(262145)
    if len(payload) > 262144:
        raise ValueError("Update response too large.")
    return parse_release(json.loads(payload), current_version)
