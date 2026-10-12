import unittest
import numpy as np
from room_brightness.metering import analyze_frame, combine_frames


class MeterTests(unittest.TestCase):
    def test_central_face_or_screen_reflection_does_not_drive_meter(self):
        frame = np.full((90, 90), 80, dtype=np.uint8)
        original = analyze_frame(frame)
        frame[30:60, 30:60] = 240
        changed = analyze_frame(frame)
        self.assertAlmostEqual(original["score"], changed["score"])

    def test_small_edge_hotspot_is_trimmed(self):
        frame = np.full((90, 90), 80, dtype=np.uint8)
        original = analyze_frame(frame)
        frame[:30, :30] = 240
        self.assertAlmostEqual(original["score"], analyze_frame(frame)["score"])

    def test_room_wide_brightness_change_changes_score(self):
        dark = analyze_frame(np.full((90, 90), 40, dtype=np.uint8))
        bright = analyze_frame(np.full((90, 90), 120, dtype=np.uint8))
        self.assertGreater(bright["score"] - dark["score"], 2)

    def test_supported_exposure_is_normalized(self):
        first = analyze_frame(np.full((90, 90), 64, dtype=np.float32), -6)
        second = analyze_frame(np.full((90, 90), 64 * 2**0.5, dtype=np.float32), -5)
        self.assertAlmostEqual(first["score"], second["score"], places=5)

    def test_unsupported_exposure_is_not_trusted(self):
        reading = analyze_frame(np.full((90, 90), 80, dtype=np.uint8), 0)
        self.assertIsNone(reading["exposure"])

    def test_black_frames_and_unsettled_bursts_have_low_confidence(self):
        self.assertLess(analyze_frame(np.zeros((90, 90), dtype=np.uint8))["confidence"], 0.55)
        frames = [
            analyze_frame(np.full((90, 90), value, dtype=np.uint8)) for value in (30, 180, 40, 170)
        ]
        self.assertLess(combine_frames(frames)["confidence"], 0.55)


class SaturationTests(unittest.TestCase):
    def test_broad_bright_saturation_is_usable(self):
        import numpy as np
        from room_brightness.metering import analyze_frame

        result = analyze_frame(np.full((240, 320), 255, dtype=np.uint8))
        self.assertGreaterEqual(result["confidence"], 0.75)

    def test_unknown_dshow_minus_one_is_not_exposure(self):
        result = analyze_frame(np.full((90, 90), 29, dtype=np.uint8), -1)
        self.assertIsNone(result["exposure"])


class PairAverageTests(unittest.TestCase):
    def test_averages_light_before_curve_and_keeps_latest_preview(self):
        from room_brightness.metering import average_pair

        a = dict(level=12, score=-3, confidence=1, preview="first", zones=[1, 3])
        b = dict(level=30, score=1, confidence=0.8, preview="second", zones=[3, 5])
        result = average_pair(a, b)
        self.assertEqual(result["level"], 21)
        self.assertEqual(result["score"], -1)
        self.assertEqual(result["zones"], [2, 4])
        self.assertEqual(result["confidence"], 0.8)
        self.assertEqual(result["preview"], "second")
        self.assertEqual(result["pair_levels"], [12, 30])
