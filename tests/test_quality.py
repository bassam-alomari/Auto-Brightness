import copy
import threading
import unittest
from unittest.mock import patch, Mock
from room_brightness.quality import ExposureGate, PreferenceEvidence, MultiDisplays
from room_brightness.settings import DEFAULTS


class QualityTests(unittest.TestCase):
    def test_exposure_changes_hold_until_two_stable_cycles(self):
        gate = ExposureGate()
        self.assertTrue(gate.allow(dict(exposure=-6, gain=10)))
        self.assertFalse(gate.allow(dict(exposure=-5, gain=10)))
        self.assertFalse(gate.allow(dict(exposure=-5, gain=10)))
        self.assertTrue(gate.allow(dict(exposure=-5, gain=10)))
        self.assertFalse(gate.allow(dict(exposure=-5, gain=30)))
        self.assertFalse(gate.allow({}))
        self.assertTrue(ExposureGate().allow({}))

    def test_pair_exposure_change_is_not_hidden_by_average(self):
        from room_brightness.metering import average_pair

        first = dict(level=20, score=-2, confidence=1, exposure=-6, gain=10)
        second = dict(first, exposure=-5)
        pair = average_pair(first, second)
        self.assertTrue(pair["exposure_unstable"])
        self.assertFalse(ExposureGate().allow(pair))

    def test_manual_evidence_requires_three_independent_consistent_adjustments(self):
        evidence = PreferenceEvidence()
        context = ("camera", "internal", "ac")
        points = copy.deepcopy(DEFAULTS["custom_points"])
        for now, value in ((0, 61), (10, 61), (31, 62)):
            evidence.observe(20, value, context, now)
        self.assertIsNone(evidence.proposal(points, context, 32))
        evidence.observe(20, 60, context, 62)
        proposal = evidence.proposal(points, context, 63)
        self.assertIn([20, 61], proposal)
        self.assertEqual(points, DEFAULTS["custom_points"])
        self.assertIsNone(evidence.proposal(points, ("other", "internal", "ac"), 63))
        self.assertIsNone(evidence.proposal(points, context, 90000))

    def test_conflicting_evidence_never_changes_curve(self):
        evidence = PreferenceEvidence()
        context = ("c", "d", "battery")
        for now, value in ((0, 20), (31, 70), (62, 95)):
            evidence.observe(20, value, context, now)
        self.assertIsNone(evidence.proposal(DEFAULTS["custom_points"], context, 63))

    def test_external_monitor_readback_error_is_verification_not_disconnection(self):
        from room_brightness.recovery import error_category

        self.assertEqual(
            error_category("control", "External monitor brightness readback mismatch."),
            "brightness_verification_failed",
        )

    def test_explicit_display_does_not_change_global_selection_and_bool_is_rejected(self):
        from room_brightness import monitors
        from room_brightness.brightness import brightness, smooth_to

        old = monitors.selected_target
        with patch("room_brightness.monitors.brightness", return_value=50) as control:
            self.assertEqual(brightness(display="external-test"), 50)
            control.assert_called_once_with(None, target="external-test")
            self.assertEqual(monitors.selected_target, old)
            with self.assertRaises(ValueError):
                brightness(True, display="external-test")
        with patch("room_brightness.monitors.smooth") as fade:
            with self.assertRaises(ValueError):
                smooth_to(True, 80, threading.Event(), lambda n: None, display="external-test")
            fade.assert_not_called()


class FakeDisplay:
    def __init__(self, current=50):
        self.current = current
        self.calls = []

    def read(self):
        self.calls.append("read")
        return self.current

    def write(self, value):
        self.current = value
        self.calls.append(("write", value))
        return value

    def verify(self):
        self.calls.append("verify")
        return self.current

    def smooth(self, current, wanted, cancel, progress, duration):
        self.calls.append(("fade", wanted))
        self.current = wanted
        progress(wanted)
        return wanted, False


class MultiDisplayTests(unittest.TestCase):
    def setUp(self):
        self.options = copy.deepcopy(DEFAULTS)
        self.options.update(
            multi_display_enabled=True, multi_display_targets=["a", "b"], stability_guard=False
        )
        self.options["display_profiles"]["b"] = dict(low=0, high=30, stability_guard=False)
        self.controls = {"a": FakeDisplay(), "b": FakeDisplay()}
        self.session = MultiDisplays()
        self.cancel = threading.Event()
        self.reading = dict(level=20, confidence=1)

    def run_cycle(self, now=0):
        self.session.process(
            self.reading, self.options, "ac", self.cancel, now, factory=self.controls.__getitem__
        )

    def test_independent_targets_manual_priority_and_restoration(self):
        self.run_cycle()
        self.assertEqual(self.controls["a"].current, 70)
        self.assertEqual(self.controls["b"].current, 30)
        self.controls["a"].current = 42
        self.run_cycle(1)
        self.assertEqual(self.controls["a"].current, 42)
        self.assertEqual(self.session.status["a"]["state"], "manual_hold")
        self.session.restore(True, factory=self.controls.__getitem__)
        self.assertEqual(self.controls["a"].current, 42)
        self.assertEqual(self.controls["b"].current, 50)

    def test_reuses_profiles_and_invalidates_only_changed_display(self):
        from room_brightness.settings import validate

        with patch("room_brightness.settings.validate", wraps=validate) as validate_profile:
            self.run_cycle()
            self.assertEqual(validate_profile.call_count, 2)
            self.run_cycle(1)
            self.assertEqual(validate_profile.call_count, 2)
            self.options["display_profiles"]["b"]["high"] = 25
            self.run_cycle(2)
            self.assertEqual(validate_profile.call_count, 3)
        self.assertEqual(self.controls["b"].current, 25)

    def test_cancel_prevents_any_control_and_primary_is_not_duplicated(self):
        self.cancel.set()
        self.run_cycle()
        self.assertEqual(self.controls["a"].calls, [])
        self.cancel.clear()
        self.options["display_target"] = "a"
        self.run_cycle()
        self.assertEqual(self.controls["a"].calls, [])
        self.assertEqual(self.controls["b"].current, 30)

    def test_one_failure_does_not_stop_other_display_and_verification_is_not_retried(self):
        self.controls["a"].verify = Mock(
            side_effect=RuntimeError("External monitor restoration failed.")
        )
        self.run_cycle()
        self.assertEqual(self.controls["b"].current, 30)
        self.run_cycle(100)
        self.controls["a"].verify.assert_called_once()
        results = self.session.restore(True, factory=self.controls.__getitem__)
        self.assertEqual(results["a"], "restore_failed")
        self.assertFalse(
            any(isinstance(call, tuple) and call[0] == "write" for call in self.controls["a"].calls)
        )

    def test_alternating_contexts_does_not_bypass_evidence_debounce(self):
        from room_brightness.quality import PreferenceEvidence

        evidence = PreferenceEvidence()
        a = ("camera", "screen-a", "ac")
        b = ("camera", "screen-b", "ac")
        evidence.observe(20, 60, a, 0)
        evidence.observe(20, 60, b, 1)
        evidence.observe(20, 60, a, 2)
        self.assertEqual(len(evidence.samples), 2)

    def test_cancelling_explicit_internal_fade_never_touches_global_external_target(self):
        import io
        from room_brightness.brightness import smooth_to
        from room_brightness import monitors

        original = monitors.selected_target
        monitors.select("external-main")
        process = Mock(returncode=0)
        process.stdout = io.StringIO("")
        process.poll.return_value = 0
        cancel = threading.Event()
        cancel.set()
        try:
            with (
                patch("room_brightness.brightness.subprocess.Popen", return_value=process),
                patch("room_brightness.brightness.brightness", return_value=50) as control,
                patch("room_brightness.brightness.set_checked") as legacy,
            ):
                result = smooth_to(50, 70, cancel, lambda value: None, display="internal")
                self.assertEqual(result[0], 50)
                self.assertTrue(
                    all(call.kwargs.get("display") == "internal" for call in control.call_args_list)
                )
                self.assertEqual(control.call_count, 2)
                legacy.assert_not_called()
        finally:
            monitors.select(original)
