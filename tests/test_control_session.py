import unittest
from unittest.mock import Mock

from room_brightness.adaptive import AdaptiveController
from room_brightness.control_session import ControlSession


class SessionTests(unittest.TestCase):
    def make_session(self, monitor=False):
        controller = AdaptiveController(mapping="image", expected=40)
        return ControlSession(controller, Mock(return_value=40), Mock(return_value=80), monitor)

    def test_monitor_reports_target_without_writing(self):
        session = self.make_session(monitor=True)
        decision = session.evaluate(dict(level=40, confidence=1), session.generation())
        self.assertGreater(decision.target, decision.current)
        session.write.assert_not_called()

    def test_cancellation_during_final_read_prevents_write(self):
        session = self.make_session()

        def stop_on_second_read():
            if session.read.call_count == 2:
                session.cancel()
            return 40

        session.read.side_effect = stop_on_second_read
        decision = session.evaluate(dict(level=40, confidence=1), session.generation())
        self.assertEqual(decision.reason, "cancelled")
        session.write.assert_not_called()
