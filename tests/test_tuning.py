import copy
import threading
import unittest
from unittest.mock import patch, Mock

from room_brightness.tuning import (
    calibrated_points,
    transition_duration,
    app_names,
    protected_frame,
    Performance,
)
from room_brightness.settings import validate, DEFAULTS


class TuningTests(unittest.TestCase):
    def test_calibration_interpolates_chosen_points_and_preserves_endpoints(self):
        from room_brightness.comfort import target, valid_points

        points = calibrated_points([[15, 30], [20, 60], [25, 90]])
        self.assertTrue(valid_points(points))
        for x, y in [[15, 30], [20, 60], [25, 90]]:
            self.assertEqual(target(x, 0, 100, points), y)
        self.assertEqual(target(0, 10, 80, points), 10)
        self.assertEqual(target(255, 10, 80, points), 80)
        for invalid in (
            [[12, 10], [20, 60], [25, 90]],
            [[15, 60], [20, 40], [25, 90]],
            [[15, 30], [15.5, 60], [25, 90]],
            [[15, 30], [20, 60], [float("nan"), 90]],
        ):
            with self.assertRaises(ValueError):
                calibrated_points(invalid)

    def test_directional_option_does_not_change_legacy_speed_until_enabled(self):
        options = copy.deepcopy(DEFAULTS)
        self.assertEqual(transition_duration(options, 20, 80), 4)
        self.assertEqual(transition_duration(options, 80, 20), 4)
        options["directional_response"] = True
        self.assertEqual(transition_duration(options, 20, 80), 1)
        self.assertEqual(transition_duration(options, 80, 20), 8)

    def test_spatial_rejection_excludes_bright_centre_and_patch_not_uniform_light(self):
        import numpy as np

        frame = np.full((240, 320, 3), 30, dtype=np.uint8)
        frame[60:180, 80:240] = 250
        frame[:60, :80] = 255
        output, mask = protected_frame(frame)
        self.assertFalse(mask[100, 100])
        self.assertFalse(mask[10, 10])
        self.assertTrue(mask[10, 100])
        self.assertAlmostEqual(float(np.mean(output)), 30)
        self.assertEqual(frame[100, 100, 0], 250)  # input not mutated
        broad = np.full((240, 320, 3), 240, dtype=np.uint8)
        corrected, _ = protected_frame(broad)
        self.assertTrue(np.array_equal(corrected, broad))

    def test_portable_new_preferences_validate_and_keep_app_paths_out(self):
        from room_brightness.extras import export_preferences, import_preferences

        pref = validate(
            dict(
                DEFAULTS,
                directional_response=True,
                spatial_protection=True,
                pause_apps_enabled=True,
                pause_apps=["VLC.exe", "bad/path.exe", "vlc.exe"],
            )
        )
        self.assertEqual(pref["pause_apps"], ["vlc.exe"])
        loaded = import_preferences(export_preferences(pref), DEFAULTS)
        self.assertTrue(loaded["directional_response"])
        self.assertTrue(loaded["spatial_protection"])
        self.assertEqual(app_names(["x.exe"] * 31), [])

    def test_performance_counters_bounded_and_invalid_values_ignored(self):
        stats = Performance()
        stats.capture(dict(camera_seconds=3, camera_cpu=0.4))
        stats.capture(dict(camera_seconds=float("nan"), camera_cpu=-1))
        with patch("room_brightness.tuning.memory_mb", return_value=20):
            for _ in range(130):
                row = stats.snapshot()
        self.assertEqual(row["camera_seconds"], 3)
        self.assertEqual(row["camera_cpu"], 0.4)
        self.assertEqual(len(stats.samples), 120)
        self.assertEqual(row["memory"], 20)

    def test_camera_protection_forwarded_to_worker_only_when_selected(self):
        import json
        from room_brightness.camera import sample

        process = Mock(returncode=0)
        process.poll.return_value = 0
        process.communicate.return_value = (
            json.dumps(dict(level=20, score=-2, confidence=0.9, zones=[])),
            "",
        )
        with patch("room_brightness.camera.subprocess.Popen", return_value=process) as launch:
            sample(0, threading.Event(), protection=True)
        self.assertIn("--protection", launch.call_args.args[0])
