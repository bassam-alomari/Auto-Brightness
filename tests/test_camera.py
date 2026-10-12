import threading
import json
import unittest
from unittest.mock import Mock, patch

from room_brightness.camera import sample


class CameraTests(unittest.TestCase):
    @patch("room_brightness.camera.subprocess.Popen")
    def test_cancelled_before_sampling_does_not_open_camera(self, popen):
        cancel = threading.Event()
        cancel.set()
        with self.assertRaisesRegex(RuntimeError, "Stopped"):
            sample(0, cancel)
        popen.assert_not_called()

    @patch("room_brightness.camera.time.sleep")
    @patch("room_brightness.camera.subprocess.Popen")
    def test_timeout_kills_camera_process(self, popen, sleep):
        process = Mock()
        process.poll.return_value = None
        process.communicate.return_value = ("", "")
        popen.return_value = process
        with self.assertRaisesRegex(RuntimeError, "timed out"):
            sample(0, threading.Event(), timeout=-1)
        process.kill.assert_called_once()
        process.communicate.assert_called_once()

    @patch("room_brightness.camera.subprocess.Popen")
    def test_camera_error_is_reported(self, popen):
        process = Mock(returncode=1)
        process.poll.return_value = 1
        process.communicate.return_value = ("", "Camera unavailable")
        popen.return_value = process
        with self.assertRaisesRegex(RuntimeError, "Camera unavailable"):
            sample(0, threading.Event())

    @patch("room_brightness.camera.subprocess.Popen")
    def test_measurement_is_returned_without_frames(self, popen):
        process = Mock(returncode=0)
        process.poll.return_value = 0
        reading = dict(level=123.5, score=-2.0, confidence=0.9, zones=[-2.0] * 8)
        process.communicate.return_value = (json.dumps(reading), "")
        popen.return_value = process
        self.assertEqual(sample(0, threading.Event()), reading)

    @patch("room_brightness.camera.time.sleep")
    @patch("room_brightness.camera.subprocess.Popen")
    def test_cancellation_kills_active_camera_process(self, popen, sleep):
        cancel = threading.Event()
        process = Mock()
        process.poll.return_value = None
        process.communicate.return_value = ("", "")
        popen.return_value = process
        sleep.side_effect = lambda _: cancel.set()
        with self.assertRaisesRegex(RuntimeError, "Stopped"):
            sample(0, cancel)
        process.kill.assert_called_once()

    @patch("room_brightness.camera.subprocess.Popen")
    def test_preview_is_drained_before_child_exit(self, popen):
        import base64

        reading = dict(
            level=29,
            score=2,
            confidence=1,
            zones=[2] * 8,
            preview=base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"x" * 50000).decode(),
        )
        process = Mock(returncode=0)
        process.communicate.return_value = (json.dumps(reading), "")
        process.poll.return_value = 0
        popen.return_value = process
        self.assertEqual(sample(0, threading.Event(), preview=True), reading)
        process.communicate.assert_called_once()
        self.assertIn("--preview", popen.call_args.args[0])
