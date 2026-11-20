import sys
import unittest
from unittest.mock import patch

from room_brightness.__main__ import main
from room_brightness.updater import UpdateClient


class RequestEfficiencyTests(unittest.TestCase):
    def test_capture_refuses_reordered_camera_before_opening(self):
        args = ["room_brightness", "--meter", "1", "--camera-identity-json", '"camera-a"']
        with (
            patch.object(sys, "argv", args),
            patch(
                "room_brightness.devices.native_devices",
                return_value=[{"id": "camera-a", "index": 0}],
            ),
            patch("room_brightness.camera.camera_sample") as capture,
            self.assertRaises(SystemExit),
        ):
            main()
        capture.assert_not_called()

    def test_successful_update_check_is_reused(self):
        client = UpdateClient(".")
        with (
            patch("room_brightness.updater.check", return_value=None) as check,
            patch("threading.Thread.start", lambda worker: worker.run()),
            patch("room_brightness.updater.time.monotonic", return_value=60),
        ):
            client.check("0.10.1")
            client.check("0.10.1")
        check.assert_called_once_with("0.10.1")
