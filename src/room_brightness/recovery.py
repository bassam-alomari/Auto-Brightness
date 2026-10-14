"""Bounded atomic settings snapshots and redacted diagnostic reports."""

from datetime import datetime, timezone
from pathlib import Path
import json
import os
import uuid
import time

KEEP_BACKUPS = 10


def write_atomic(path, text):
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temporary.write_text(text, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def snapshot(directory, previous, new):
    from .settings import validate

    if validate(previous) == validate(new):
        return
    folder = directory / "settings-backups"
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    document = {
        "app": "Auto Brightness",
        "format": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "settings": validate(previous),
    }
    file = folder / ("settings-" + stamp + "-" + uuid.uuid4().hex[:8] + ".json")
    write_atomic(file, json.dumps(document, ensure_ascii=False, indent=2))
    files = sorted(folder.glob("settings-*.json"), key=lambda path: path.name, reverse=True)
    for expired in files[KEEP_BACKUPS:]:
        expired.unlink()


def list_backups(directory):
    rows = []
    for file in sorted((directory / "settings-backups").glob("settings-*.json"), reverse=True):
        try:
            document = read_backup(directory, file.name)
            rows.append(
                {
                    "name": file.name,
                    "created_utc": document["created_utc"],
                    "low": document["settings"]["low"],
                    "high": document["settings"]["high"],
                }
            )
        except (OSError, ValueError, KeyError):
            continue
    return rows[:KEEP_BACKUPS]


def read_backup(directory, name):
    if (
        not isinstance(name, str)
        or Path(name).name != name
        or not name.startswith("settings-")
        or not name.endswith(".json")
    ):
        raise ValueError("Invalid backup name.")
    file = directory / "settings-backups" / name
    if file.is_symlink() or file.stat().st_size > 262144:
        raise ValueError("Invalid backup file.")
    document = json.loads(file.read_text(encoding="utf-8"))
    if (
        not isinstance(document, dict)
        or document.get("app") != "Auto Brightness"
        or document.get("format") != 1
        or not isinstance(document.get("settings"), dict)
        or not isinstance(document.get("created_utc"), str)
    ):
        raise ValueError("Invalid settings backup.")
    from .settings import validate

    document["settings"] = validate(document["settings"])
    return document


def recover_settings(directory):
    try:
        backups = list_backups(directory)
    except OSError:
        return None
    for backup in backups:
        try:
            return read_backup(directory, backup["name"])["settings"]
        except (OSError, ValueError):
            continue
    return None


def restore_preferences(directory, name, current):
    import copy
    from .extras import PORTABLE_KEYS
    from .settings import validate

    old = read_backup(directory, name)["settings"]
    result = copy.deepcopy(current)
    for key in (*PORTABLE_KEYS, "close_tray", "minimize_tray"):
        result[key] = copy.deepcopy(old[key])
    return validate(result)


def error_category(operation, message):
    lower = str(message).lower()
    if any(
        word in lower
        for word in (
            "permission denied",
            "access denied",
            "access is denied",
            "camera access blocked",
            "denied by privacy",
            "disabled by policy",
        )
    ):
        return "permission_denied"
    if "camera" in lower or operation in ("devices", "retry_devices", "measure"):
        if "disconnect" in lower or "reorder" in lower:
            return "camera_disconnected"
        if "timed out" in lower or "timeout" in lower:
            return "camera_timeout"
        return "camera_unavailable"
    if operation == "displays" or "monitor" in lower:
        return "display_unavailable"
    if "readback" in lower or "restoration" in lower:
        return "brightness_verification_failed"
    if operation in ("settings", "persist"):
        return "settings_write_failed"
    if operation == "restore":
        return "brightness_restore_failed"
    return "display_control_failed"


def diagnostic_report(engine, version, now=None):
    now = time.monotonic() if now is None else now
    preferences = engine.preferences
    # Only fixed field names, enum values and numerical summaries are exported.
    report = {
        "app": "Auto Brightness",
        "version": version,
        "report_format": 1,
        "mode": {
            "running": bool(engine.running),
            "busy": bool(engine.busy),
            "paused": bool(engine.pause_reasons),
            "display": "internal" if preferences["display_target"] == "internal" else "external",
        },
        "control": {
            key: preferences[key]
            for key in (
                "low",
                "high",
                "brightness_curve",
                "stability_guard",
                "deadband",
                "transition_speed",
                "interval_ac",
                "interval_battery",
                "adaptive_sampling",
            )
        },
        "events": [
            {"seconds_ago": max(0, round(now - event["time"], 1)), "category": event["category"]}
            for event in engine.health_events
        ],
        "readings": [
            {
                "seconds_ago": max(0, round(now - row[0], 1)),
                "image": round(row[1], 2),
                "target": row[2],
                "screen": row[3],
            }
            for row in list(engine.history)[-60:]
        ],
    }
    return report
