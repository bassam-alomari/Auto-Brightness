import unittest
import numpy as np
from room_brightness.vision import scene_features, scene_distance


class VisionTests(unittest.TestCase):
    def test_uniform_exposure_change_keeps_structure(self):
        frame = np.tile(np.linspace(20, 90, 96, dtype=np.uint8), (72, 1))
        a = scene_features(frame)
        b = scene_features(frame * 2)
        self.assertLess(scene_distance(a["scene_signature"], b["scene_signature"]), 0.03)
        self.assertGreater(b["illumination_level"], a["illumination_level"])

    def test_different_scene_is_detected(self):
        a = np.full((72, 96), 20, np.uint8)
        a[:, :32] = 180
        b = np.full((72, 96), 20, np.uint8)
        b[:, 64:] = 180
        self.assertGreater(
            scene_distance(
                scene_features(a)["scene_signature"], scene_features(b)["scene_signature"]
            ),
            0.35,
        )

    def test_black_frame_is_not_visible(self):
        self.assertEqual(scene_features(np.zeros((72, 96, 3), np.uint8))["visible_fraction"], 0)
