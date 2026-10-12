import unittest
from room_brightness.adaptive import AdaptiveController


def reading(score, confidence=1, zones=None):
    return dict(score=score, confidence=confidence, zones=[score] * 8 if zones is None else zones)


class AdaptiveTests(unittest.TestCase):
    def test_initial_reference_keeps_current_brightness(self):
        controller = AdaptiveController()
        self.assertEqual(controller.update(reading(0), 50, 0), 50)
        self.assertFalse(controller.needs_anchor)

    def test_sustained_room_change_reaches_target(self):
        controller = AdaptiveController()
        current = controller.update(reading(0), 50, 0)
        for i in range(20):
            updated = controller.update(reading(2), current, 30 * (i + 1))
            self.assertLessEqual(updated, 80)
            controller.committed(updated)
            current = updated
        self.assertGreater(current, 60)

    def test_single_flash_is_ignored(self):
        controller = AdaptiveController()
        for i, score in enumerate([0, 0, 3, 0, 0, 0]):
            self.assertEqual(controller.update(reading(score), 50, i * 30), 50)

    def test_localized_bright_region_is_ignored(self):
        controller = AdaptiveController()
        controller.update(reading(0), 50, 0)
        for i in range(20):
            self.assertEqual(
                controller.update(reading(2, zones=[3, 0, 0, 0, 0, 0, 0, 0]), 50, i * 30 + 1), 50
            )

    def test_manual_change_is_held_and_reanchored(self):
        controller = AdaptiveController()
        controller.update(reading(0), 50, 0)
        self.assertEqual(controller.update(reading(2), 70, 1), 70)
        self.assertEqual(controller.update(reading(-2), 70, 100), 70)
        self.assertEqual(controller.update(reading(2), 70, 182), 70)
        for i in range(10):
            self.assertEqual(controller.update(reading(2), 70, 200 + i * 30), 70)

    def test_manual_zero_is_never_replaced_by_automatic_write(self):
        controller = AdaptiveController(expected=50)
        for i in range(20):
            self.assertEqual(controller.update(reading(2), 0, i * 30), 0)

    def test_uncertain_measurements_do_not_change_brightness(self):
        controller = AdaptiveController()
        controller.update(reading(0), 50, 0)
        for i in range(10):
            self.assertEqual(controller.update(reading(2, 0.2), 50, i * 30), 50)

    def test_small_sustained_change_is_detected(self):
        controller = AdaptiveController()
        current = controller.update(reading(0), 50, 0)
        for i in range(4):
            current = controller.update(reading(0.3), current, (i + 1) * 15)
            controller.committed(current)
        self.assertGreater(current, 0)


class CurveTests(unittest.TestCase):
    def test_spans_full_range_from_low_start(self):
        from room_brightness.adaptive import curve_target

        self.assertEqual(curve_target(3, 25, 25, 100), 100)
        self.assertEqual(curve_target(-3, 70, 10, 100), 10)

    def test_monotonic_and_bounded(self):
        from room_brightness.adaptive import curve_target

        values = [curve_target(i / 20, 40, 25, 80) for i in range(-100, 101)]
        self.assertEqual(values, sorted(values))
        self.assertGreaterEqual(min(values), 25)
        self.assertLessEqual(max(values), 80)

    def test_responsive_reaches_high_sooner(self):
        from room_brightness.adaptive import curve_target

        self.assertGreater(curve_target(0.5, 25, 25, 80, 1.8), curve_target(0.5, 25, 25, 80, 0.55))

    def test_sustained_bright_reading_reaches_maximum(self):
        controller = AdaptiveController(low=25, high=100)
        current = controller.update(reading(0), 25, 0)
        for i in range(10):
            current = controller.update(reading(3), current, 15 * (i + 1))
            controller.committed(current)
        self.assertEqual(current, 100)


class SceneMappingTests(unittest.TestCase):
    def test_strong_scene_at_start_is_not_anchored_to_dim_screen(self):
        controller = AdaptiveController(low=25, high=100, mapping="scene")
        current = 30
        measurement = dict(score=2, confidence=1, zones=[2] * 8, exposure_corrected=True)
        for i in range(4):
            current = controller.update(measurement, current, i * 15)
            controller.committed(current)
        self.assertEqual(current, 100)

    def test_direct_scene_curve_requires_exposure_metadata(self):
        controller = AdaptiveController(low=25, high=100)
        for i in range(5):
            self.assertEqual(controller.update(reading(2), 30, i * 15), 30)

    def test_manual_choice_remains_reference_after_hold(self):
        controller = AdaptiveController(low=25, high=100)
        measurement = dict(score=2, confidence=1, zones=[2] * 8, exposure_corrected=True)
        controller.update(measurement, 50, 0)
        controller.committed(100)
        self.assertEqual(controller.update(measurement, 65, 5), 65)
        for i in range(5):
            self.assertEqual(controller.update(measurement, 65, 190 + i * 15), 65)

    def test_scene_curve_monotonic(self):
        from room_brightness.adaptive import scene_target

        values = [scene_target(i / 10, 25, 100) for i in range(-70, 50)]
        self.assertEqual(values, sorted(values))
        self.assertEqual(min(values), 25)
        self.assertEqual(max(values), 100)


class ReadabilityTests(unittest.TestCase):
    def test_confirmed_darkening_lowers_screen_but_keeps_comfort_floor(self):
        c = AdaptiveController(low=55)
        current = c.update(reading(0), 70, 0)
        for i in range(30):
            current = c.update(reading(-5), current, i * 15 + 1)
            c.committed(current)
            self.assertGreaterEqual(current, 55)

        self.assertLess(current, 70)

    def test_default_does_not_use_absolute_exposure_curve(self):
        c = AdaptiveController(low=55)
        m = dict(score=-3, confidence=1, zones=[-3] * 8, exposure_corrected=True)
        for i in range(20):
            self.assertEqual(c.update(m, 70, i * 15), 70)

    def test_unreadable_start_is_raised_to_comfort_minimum(self):
        c = AdaptiveController(low=55)
        self.assertEqual(c.update(reading(-3), 40, 0), 55)


class SafeDimmingTests(unittest.TestCase):
    def test_three_confirmations_required_for_dimming(self):
        c = AdaptiveController(low=55)
        c.update(reading(0), 80, 0)
        self.assertEqual(c.update(reading(-3), 80, 15), 80)
        self.assertEqual(c.update(reading(-3), 80, 30), 80)
        self.assertLess(c.update(reading(-3), 80, 45), 80)

    def test_darkening_not_confused_with_changed_scene_signature(self):
        c = AdaptiveController(low=55)
        initial = reading(0)
        initial["scene_signature"] = [1] * 48
        dark = reading(-3, 0.35)
        dark["scene_signature"] = [0] * 48
        c.update(initial, 80, 0)
        current = 80
        for i in range(6):
            current = c.update(dark, current, 15 * (i + 1))
            c.committed(current)
        self.assertEqual(current, 55)


class DarkImageFloorTests(unittest.TestCase):
    def test_two_dark_readings_use_configured_floor_without_anchor(self):
        for floor in (0, 10, 35):
            c = AdaptiveController(low=floor, high=100)
            m = dict(score=-3, confidence=1, level=9)
            self.assertEqual(c.update(m, 55, 0), 55)
            self.assertEqual(c.reason, "confirming_dim")
            self.assertEqual(c.update(m, 55, 5), floor)

    def test_bright_or_uncertain_reading_resets_dark_confirmation(self):
        c = AdaptiveController(low=10, high=100)
        dark = dict(score=-3, confidence=1, level=9)
        c.update(dark, 55, 0)
        c.update(dict(score=-3, confidence=0.1, level=9), 55, 1)
        self.assertEqual(c.update(dark, 55, 2), 55)

    def test_manual_override_keeps_priority_over_dark_floor(self):
        c = AdaptiveController(low=0, high=100)
        c.committed(55)
        m = dict(score=-3, confidence=1, level=9)
        self.assertEqual(c.update(m, 70, 0), 70)
        self.assertEqual(c.update(m, 70, 5), 70)


class DarkRecoveryTests(unittest.TestCase):
    def test_light_returns_after_dark_floor_even_from_bright_initial_anchor(self):
        c = AdaptiveController(low=0, high=100)
        c.update(dict(score=-1, confidence=1, level=22), 100, 0)
        dark = dict(score=-3, confidence=1, level=9)
        c.update(dark, 100, 1)
        self.assertEqual(c.update(dark, 100, 2), 0)
        c.committed(0)
        current = 0
        for i in range(3, 9):
            current = c.update(dict(score=-1, confidence=1, level=22), current, i)
            c.committed(current)
        self.assertGreater(current, 0)


class ImageRecoveryTests(unittest.TestCase):
    def test_same_exposure_score_does_not_block_light_recovery(self):
        c = AdaptiveController(low=0, high=100)
        dark = dict(score=-3, confidence=1, level=9)
        c.update(dark, 55, 0)
        c.update(dark, 55, 1)
        c.committed(0)
        light = dict(score=-3, confidence=1, level=22, scene_signature=[4] * 48)
        self.assertEqual(c.update(light, 0, 2), 0)
        self.assertGreater(c.update(light, 0, 3), 0)

    def test_restart_at_floor_recovers_without_prior_dark_sample(self):
        c = AdaptiveController(low=0, high=100)
        light = dict(score=-3, confidence=1, level=22)
        c.update(light, 0, 0)
        self.assertGreater(c.update(light, 0, 1), 0)


class ExplicitImageCurveTests(unittest.TestCase):
    def test_exact_user_points_and_limits(self):
        from room_brightness.adaptive import image_target

        for low in (0, 10, 25):
            for level in (0, 9, 12):
                self.assertEqual(image_target(level, low, 100), low)
            for level, target in [(15, 50), (20, 70), (25, 90), (27, 100), (255, 100)]:
                self.assertEqual(image_target(level, low, 100), target)
        self.assertEqual(image_target(27, 10, 80), 80)

    def test_production_mapping_ignores_fixed_exposure_score(self):
        c = AdaptiveController(low=0, high=100, mapping="image")
        for level, target in [(9, 0), (15, 50), (20, 70), (25, 90), (27, 100), (12, 0)]:
            current = c.expected if c.expected is not None else 0
            self.assertEqual(
                c.update(dict(level=level, score=-3, confidence=1), current, 0), target
            )
            c.committed(target)


class CurvePresetTests(unittest.TestCase):
    def test_presets_are_monotonic_bounded_and_distinct(self):
        from room_brightness.adaptive import CURVES, image_target

        results = set()
        for key in CURVES:
            values = [image_target(i, 10, 100, key) for i in range(256)]
            self.assertEqual(values, sorted(values))
            self.assertEqual(values[0], 10)
            self.assertEqual(values[-1], 100)
            results.add(tuple(values))
        self.assertEqual(len(results), len(CURVES))
