import unittest
from room_brightness.comfort import Stability, target, valid_points, learned_points, DEFAULT_POINTS
from room_brightness.settings import validate
from room_brightness.adaptive import AdaptiveController


class ComfortTests(unittest.TestCase):
    def test_exact_points_and_continuous_monotonic_curve(self):
        for x, y in DEFAULT_POINTS:
            self.assertEqual(target(x, 0, 100, DEFAULT_POINTS), y)
        values = [target(i / 10, 10, 80, DEFAULT_POINTS) for i in range(2560)]
        self.assertEqual(values, sorted(values))
        self.assertEqual((min(values), max(values)), (10, 80))

    def test_transient_pair_cannot_change_brightness(self):
        guard = Stability()
        for _ in range(3):
            self.assertEqual(guard.decide(dict(confidence=1, pair_levels=[12, 27]), 100, 50), 50)
        self.assertEqual(guard.reason, "transient")

    def test_large_sustained_change_requires_two_cycles(self):
        guard = Stability()
        reading = dict(confidence=1, pair_levels=[25, 25])
        self.assertEqual(guard.decide(reading, 90, 50), 50)
        self.assertEqual(guard.decide(reading, 92, 50), 92)

    def test_reversal_does_not_confirm_old_change(self):
        guard = Stability()
        reading = dict(confidence=1)
        self.assertEqual(guard.decide(reading, 90, 50), 50)
        self.assertEqual(guard.decide(reading, 20, 50), 50)
        self.assertEqual(guard.decide(reading, 20, 50), 20)

    def test_jitter_is_held_and_guard_can_be_disabled(self):
        guard = Stability()
        reading = dict(confidence=1)
        self.assertEqual(guard.decide(reading, 51, 50), 50)
        self.assertEqual(guard.decide(reading, 51, 50, False), 51)

    def test_invalid_quality_resets_confirmation(self):
        guard = Stability()
        guard.decide(dict(confidence=1), 90, 50)
        guard.decide(dict(confidence=0.1), 90, 50)
        self.assertEqual(guard.decide(dict(confidence=1), 90, 50), 50)

    def test_learned_point_preserves_order_and_rejects_reversal(self):
        points = learned_points(DEFAULT_POINTS, 18, 60)
        self.assertIn([18, 60], points)
        self.assertTrue(valid_points(points))
        self.assertEqual(DEFAULT_POINTS, [[12, 0], [15, 50], [20, 70], [25, 90], [27, 100]])
        for level, value in ((12, 30), (27, 80), (18, 95)):
            with self.assertRaises(ValueError):
                learned_points(DEFAULT_POINTS, level, value)

    def test_invalid_settings_fall_back_safely(self):
        result = validate(
            dict(
                custom_points=[[12, 0], [15, 80], [14, 100]],
                ac_limits=[80, 20],
                transition_speed="instant",
                deadband=99,
            )
        )
        self.assertEqual(result["custom_points"], DEFAULT_POINTS)
        self.assertEqual(result["ac_limits"], [10, 100])
        self.assertEqual(result["transition_speed"], "balanced")
        self.assertEqual(result["deadband"], 3)

    def test_controller_uses_saved_curve_and_manual_override(self):
        settings = validate(
            dict(custom_points=[[12, 0], [15, 60], [27, 100]], stability_guard=False)
        )
        controller = AdaptiveController(
            low=0, high=100, mapping="image", options=settings, expected=40
        )
        self.assertEqual(controller.update(dict(level=15, confidence=1), 40, 0), 60)
        controller.committed(60)
        self.assertEqual(controller.update(dict(level=20, confidence=1), 55, 1), 55)
        self.assertGreater(controller.hold_until, 1)

    def test_controller_rejecting_a_cycle_breaks_pending_confirmation(self):
        settings = validate({})
        controller = AdaptiveController(
            low=0, high=100, mapping="image", options=settings, expected=50
        )
        self.assertEqual(controller.update(dict(level=25, confidence=1), 50, 0), 50)
        self.assertEqual(controller.update(dict(level=25, confidence=0.1), 50, 1), 50)
        self.assertEqual(controller.update(dict(level=25, confidence=1), 50, 2), 50)
        self.assertEqual(controller.update(dict(level=25, confidence=1), 50, 3), 90)
