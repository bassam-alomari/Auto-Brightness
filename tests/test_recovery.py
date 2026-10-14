import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from collections import deque
from room_brightness.settings import validate, save_settings, load_settings
from room_brightness.recovery import (
    list_backups,
    restore_preferences,
    read_backup,
    diagnostic_report,
    error_category,
)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)

    def tearDown(self):
        self.folder.cleanup()

    def test_changes_create_bounded_snapshots_and_unchanged_saves_do_not(self):
        settings = validate({})
        save_settings(self.root, settings)
        self.assertFalse(list_backups(self.root))
        for value in range(20):
            settings["glass_tint"] = value
            save_settings(self.root, settings)
        self.assertEqual(len(list_backups(self.root)), 10)
        names = [row["name"] for row in list_backups(self.root)]
        save_settings(self.root, settings)
        self.assertEqual(names, [row["name"] for row in list_backups(self.root)])

    def test_corrupt_current_file_recovers_latest_valid_backup(self):
        settings = validate(dict(low=0, high=100))
        save_settings(self.root, settings)
        settings["low"] = 10
        save_settings(self.root, settings)
        (self.root / "settings.json").write_text("broken")
        self.assertEqual(load_settings(self.root)["low"], 0)
        (self.root / "settings.json").write_text("[]")
        self.assertEqual(load_settings(self.root)["low"], 0)

    def test_restore_preserves_local_device_and_startup_choices(self):
        settings = validate(dict(low=0, high=100, camera_id="old"))
        save_settings(self.root, settings)
        settings.update(low=10, camera_id="new", startup=False, startup_defaults_revision=1)
        save_settings(self.root, settings)
        restored = restore_preferences(self.root, list_backups(self.root)[0]["name"], settings)
        self.assertEqual(restored["low"], 0)
        self.assertEqual(restored["camera_id"], "new")
        self.assertFalse(restored["startup"])

    def test_invalid_backup_names_and_broken_backups_are_rejected(self):
        with self.assertRaises(ValueError):
            read_backup(self.root, "../settings.json")
        folder = self.root / "settings-backups"
        folder.mkdir()
        (folder / "settings-bad.json").write_text("{")
        self.assertFalse(list_backups(self.root))

    def test_failed_atomic_replace_keeps_previous_settings(self):
        settings = validate({})
        save_settings(self.root, settings)
        old = (self.root / "settings.json").read_bytes()
        settings["low"] = 0
        with patch("room_brightness.recovery.os.replace", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                save_settings(self.root, settings)
        self.assertEqual((self.root / "settings.json").read_bytes(), old)
        self.assertFalse(list(self.root.rglob("*.tmp")))

    def test_report_never_exports_raw_errors_device_names_paths_or_images(self):
        engine = SimpleNamespace(
            preferences=validate(dict(camera_id="private-id", camera_name="private-camera")),
            running=True,
            busy=False,
            pause_reasons=set(),
            error_details="C:/Users/private-user/secret",
            health_events=deque([dict(time=10, category="camera_unavailable")]),
            history=deque([(10, 20, 70, 70)]),
            last_meter={"preview": "private-image"},
        )
        report = diagnostic_report(engine, "0.3.1", now=12)
        content = json.dumps(report)
        for private in (
            "private-id",
            "private-camera",
            "private-user",
            "private-image",
            "error_details",
        ):
            self.assertNotIn(private, content)
        self.assertEqual(report["readings"][0]["seconds_ago"], 2)

    def test_permission_errors_are_classified_separately_from_camera_contention(self):
        self.assertEqual(error_category("control", "Camera permission denied"), "permission_denied")
        self.assertEqual(error_category("control", "Camera unavailable"), "camera_unavailable")
        self.assertEqual(
            error_category(
                "control",
                "Camera unavailable. Close video apps and check Windows camera permissions.",
            ),
            "camera_unavailable",
        )
        self.assertEqual(
            error_category("control", "brightness readback mismatch"),
            "brightness_verification_failed",
        )
