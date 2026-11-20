import queue
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from room_brightness.quality import ExposureGate
from room_brightness.settings import DEFAULTS, validate
from room_brightness.ui import App


class EngineeringRegressions(unittest.TestCase):
    def test_invalid_enum_types_fall_back(self):
        result = validate(
            {"brightness_curve": [], "language": {}, "power_curves": {"ac": {"curve": []}}}
        )
        self.assertEqual(result["brightness_curve"], DEFAULTS["brightness_curve"])
        self.assertEqual(result["language"], DEFAULTS["language"])
        self.assertEqual(result["power_curves"]["ac"], DEFAULTS["power_curves"]["ac"])

    def test_poll_keeps_running_after_callback_failure(self):
        collector = SimpleNamespace(
            events=queue.Queue(),
            operation="control",
            running=True,
            busy=True,
            cancel=threading.Event(),
            root=Mock(),
            poll=Mock(),
            handle_error=Mock(),
            update_controls=Mock(),
        )
        succeeded = Mock()
        collector.events.put((Mock(side_effect=RuntimeError("test")), None, None))
        collector.events.put((succeeded, 42, None))
        with self.assertLogs("room_brightness.ui", level="ERROR"):
            App.poll(collector)
        self.assertTrue(collector.cancel.is_set())
        collector.handle_error.assert_called_once()
        App.poll(collector)
        succeeded.assert_called_once_with(42)
        self.assertEqual(collector.root.after.call_count, 2)

    def test_exposure_can_recover_from_missing_metadata_with_stable_image(self):
        gate = ExposureGate()
        self.assertFalse(gate.allow({"exposure_unstable": True}))
        for level in (10, 20, 30, 30):
            self.assertFalse(gate.allow({"level": level, "confidence": 0.95}))
        self.assertTrue(gate.allow({"level": 30, "confidence": 0.95}))
