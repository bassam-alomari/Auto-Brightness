"""Spatial illumination cues and exposure-independent scene structure."""

import math


def scene_features(frame):
    import cv2
    import numpy as np

    image = cv2.resize(frame, (96, 72), interpolation=cv2.INTER_AREA).astype(np.float32)
    value = np.max(image, axis=2) if image.ndim == 3 else image
    # Retinex-style illumination envelope: blur suppresses small texture edges.
    envelope = cv2.GaussianBlur(value, (0, 0), 4)
    zones = []
    for y, row in enumerate(np.array_split(envelope, 3, axis=0)):
        for x, tile in enumerate(np.array_split(row, 3, axis=1)):
            if (y, x) != (1, 1):
                zones.append(float(np.percentile(tile, 75)))
    ordered = sorted(zones)
    level = float(np.mean(ordered[1:-1]))
    # Normalize coarse scene structure to remove uniform exposure/lighting shifts.
    coarse = cv2.resize(value, (8, 6), interpolation=cv2.INTER_AREA)
    mask = np.ones((6, 8), dtype=bool)
    mask[2:4, 2:6] = False
    normalized = coarse / max(float(np.mean(coarse[mask])), 5)
    normalized[~mask] = 0
    signature = np.clip(normalized, 0, 4).reshape(-1).tolist()
    return dict(
        illumination_level=level,
        illumination_zones=zones,
        scene_signature=signature,
        visible_fraction=float(np.mean(value > 12)),
    )


def scene_distance(before, after):
    if len(before) != 48 or len(after) != 48:
        return 0
    return sum(abs(a - b) for a, b in zip(before, after)) / 48


def vision_score(level, exposure):
    correction = exposure if exposure is not None else 0
    return 2 * math.log2(max(level, 1) / 255) - correction
