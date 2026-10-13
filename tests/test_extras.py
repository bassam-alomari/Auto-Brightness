import unittest
from unittest.mock import patch
from room_brightness.extras import (
    export_preferences,
    import_preferences,
    parse_release,
    SamplingBudget,
    valid_region,
    profile_settings,
)
from room_brightness.settings import validate, DEFAULTS


class ExtrasTests(unittest.TestCase):
    def test_export_omits_camera_identity_startup_and_paths(self):
        settings = validate(
            dict(camera_id="private-camera", camera_name="private-name", startup=True)
        )
        exported = export_preferences(settings)
        self.assertNotIn("camera_id", exported["settings"])
        self.assertNotIn("startup", exported["settings"])
        self.assertNotIn("display_target", exported["settings"])
        exported["settings"]["custom_points"][1][1] = 55
        self.assertEqual(settings["custom_points"][1][1], 50)

    def test_import_preserves_local_identity_and_validates_numeric_values(self):
        local = validate(dict(camera_id="local", startup=False, startup_defaults_revision=1))
        document = export_preferences(validate(dict(low=0, high=100)))
        document["settings"].update(camera_id="foreign", startup=True, deadband=99)
        result = import_preferences(document, local)
        self.assertEqual((result["low"], result["high"]), (0, 100))
        self.assertEqual(result["camera_id"], "local")
        self.assertFalse(result["startup"])
        self.assertEqual(result["deadband"], 3)
        with self.assertRaises(ValueError):
            import_preferences({"format": 2}, local)

    def test_regions_reject_inverted_tiny_and_nonfinite_coordinates(self):
        for region in ([0, 0, 1, 1], [0.2, 0.2, 0.8, 0.8]):
            self.assertTrue(valid_region(region))
        for region in (
            [0.8, 0, 0.2, 1],
            [0, 0, 0.01, 1],
            [0, 0, float("nan"), 1],
            [False, 0, 1, 1],
            [-1, 0, 1, 1],
        ):
            self.assertFalse(valid_region(region))

    def test_power_saving_is_bounded_and_change_restores_fast_sampling(self):
        budget = SamplingBudget()
        for _ in range(30):
            budget.observe(dict(level=20, quality=1, target=70, current=70))
        self.assertEqual(budget.interval(5, 30, True), 30)
        self.assertEqual(budget.interval(5, 30, False), 5)
        budget.observe(dict(level=28, quality=1, target=100, current=100))
        self.assertEqual(budget.interval(5, 30, True), 5)
        self.assertEqual(budget.interval(60, 30, True), 60)

    def test_version_comparison_uses_numeric_components_and_trusted_links(self):
        data = dict(
            tag_name="v0.10.0",
            html_url="https://github.com/bassam-alomari/Auto-Brightness/releases/tag/v0.10.0",
        )
        self.assertIsNotNone(parse_release(data, "0.3.0"))
        self.assertIsNone(parse_release(data, "0.11.0"))
        self.assertIsNone(parse_release(dict(data, prerelease=True), "0.3.0"))
        with self.assertRaises(ValueError):
            parse_release(dict(data, html_url="https://other.example/update"), "0.3.0")
        with self.assertRaises(ValueError):
            parse_release(dict(data, tag_name="malformed"), "0.3.0")

    def test_named_profiles_are_validated_without_recursive_payloads(self):
        settings = validate(
            dict(profiles={"Desk": {"low": 0, "high": 100, "profiles": {"recursive": {}}}})
        )
        self.assertEqual(profile_settings(settings, "Desk"), {"low": 0, "high": 100})
        self.assertEqual(profile_settings(settings, "night")["high"], 50)
        with self.assertRaises(ValueError):
            profile_settings(settings, "missing")

    def test_defaults_are_independent(self):
        first = validate({})
        second = validate({})
        first["meter_region"][0] = 0.3
        self.assertEqual(second["meter_region"], [0, 0, 1, 1])
        self.assertEqual(DEFAULTS["meter_region"], [0, 0, 1, 1])

    def test_metering_region_is_forwarded_to_camera_child(self):
        import threading
        from room_brightness.camera import sample

        with patch("room_brightness.camera.subprocess.Popen") as popen:
            popen.return_value.communicate.return_value = ("{}", "")
            popen.return_value.poll.return_value = 0
            popen.return_value.returncode = 0
            try:
                sample(0, threading.Event(), region=[0.2, 0.2, 0.8, 0.8])
            except RuntimeError:
                pass
            command = popen.call_args.args[0]
            self.assertIn("--region", command)
            self.assertEqual(command[command.index("--region") + 1], "0.2,0.2,0.8,0.8")

    def test_region_measures_selected_pixels_only(self):
        import numpy as np
        from room_brightness.extras import crop_frame

        frame = np.full((100, 100, 3), 255, dtype=np.uint8)
        frame[25:75, 25:75] = 20
        self.assertEqual(crop_frame(frame, [0.25, 0.25, 0.75, 0.75]).mean(), 20)
        self.assertEqual(crop_frame(frame, [0, 0, 1, 1]).shape, frame.shape)
