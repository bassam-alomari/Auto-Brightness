import unittest

from room_brightness.controller import BrightnessController, target


class ControllerTests(unittest.TestCase):
    def test_sustained_light_ramps_without_large_steps(self):
        controller = BrightnessController(20, 200, 25, 80)
        current = 30
        for _ in range(50):
            new = controller.update(200, current)
            self.assertGreaterEqual(new, current)
            self.assertLessEqual(new - current, 5)
            self.assertLessEqual(new, 80)
            current = new
        self.assertGreaterEqual(current, 75)

    def test_single_light_spike_does_not_change_brightness(self):
        controller = BrightnessController(20, 200, 25, 80)
        for value in [20, 20, 200, 20, 20, 20, 20, 20]:
            self.assertEqual(controller.update(value, 25), 25)

    def test_small_measurement_noise_is_ignored(self):
        controller = BrightnessController(20, 200, 25, 80)
        for _ in range(10):
            for value in [95, 105, 100, 110]:
                self.assertEqual(controller.update(value, 50), 50)

    def test_outside_calibrated_light_range_is_clamped(self):
        self.assertEqual(target(0, 20, 200, 25, 80), 25)
        self.assertEqual(target(255, 20, 200, 25, 80), 80)

    def test_invalid_calibration_and_measurements_are_rejected(self):
        for dark, bright, low, high in [
            (20, 20, 25, 80),
            (20, 25, 25, 80),
            (20, 200, 80, 25),
            (float("nan"), 200, 25, 80),
        ]:
            with self.assertRaises(ValueError):
                BrightnessController(dark, bright, low, high)
        controller = BrightnessController(20, 200)
        for value in [float("inf"), -1, 256]:
            with self.assertRaises(ValueError):
                controller.update(value, 40)
