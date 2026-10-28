import copy
import unittest
from room_brightness.settings import DEFAULTS, validate
from room_brightness.experience import effective_curve


class ExperienceTests(unittest.TestCase):
    def test_nearly_black_flat_frames_flag_possible_cover_not_all_dark_scenes(self):
        import numpy as np
        from room_brightness.metering import analyze_frame, combine_frames, average_pair

        black = analyze_frame(np.zeros((240, 320), dtype=np.uint8), -6)
        textured = analyze_frame(np.tile(np.arange(0, 8, dtype=np.uint8), (240, 40)), -6)
        self.assertTrue(black["possibly_covered"])
        self.assertFalse(textured["possibly_covered"])
        combined = combine_frames([black, black])
        self.assertTrue(combined["possibly_covered"])
        self.assertFalse(average_pair(combined, combine_frames([textured]))["possibly_covered"])

    def test_cover_holds_repeated_readings_and_clears_on_visible_scene(self):
        from room_brightness.adaptive import AdaptiveController

        options = copy.deepcopy(DEFAULTS)
        controller = AdaptiveController(
            low=10, high=80, mapping="image", expected=60, options=options
        )
        covered = dict(level=0, confidence=0.1, possibly_covered=True)
        self.assertEqual(controller.update(covered, 60, 0), 60)
        self.assertEqual(controller.update(covered, 60, 1), 60)
        self.assertEqual(controller.reason, "possible_cover")
        controller.update(dict(level=20, confidence=1, possibly_covered=False), 60, 2)
        self.assertNotEqual(controller.reason, "possible_cover")
        options["cover_guard"] = False
        controller.update(covered, 60, 3)
        self.assertNotEqual(controller.reason, "possible_cover")

    def test_power_curves_validated_portable_and_independent(self):
        from room_brightness.extras import import_preferences, export_preferences

        options = copy.deepcopy(DEFAULTS)
        options["separate_power_curves"] = True
        options["power_curves"]["battery"]["points"] = [[12, 0], [20, 40], [40, 100]]
        loaded = import_preferences(export_preferences(options), DEFAULTS)
        self.assertEqual(effective_curve(loaded, "battery")["points"][1], [20, 40])
        self.assertEqual(effective_curve(loaded, "ac")["points"][1], [15, 50])
        options["power_curves"]["battery"]["points"] = [[12, 100], [20, 0]]
        self.assertEqual(
            validate(options)["power_curves"]["battery"]["points"], DEFAULTS["custom_points"]
        )
