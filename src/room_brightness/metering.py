"""Robust low-resolution spatial light estimate, not a calibrated lux sensor."""

import math


def analyze_frame(gray, exposure=None):
    import numpy as np

    image = np.asarray(gray, dtype=np.float32)
    if image.ndim != 2 or not image.size:
        raise ValueError("Expected a grayscale frame.")
    rows, columns = np.array_split(image, 3, axis=0), 3
    zones = []
    for y, row in enumerate(rows):
        for x, tile in enumerate(np.array_split(row, columns, axis=1)):
            if (y, x) == (1, 1):
                continue  # Downweight face/screen reflections by ignoring the centre.
            p20, p50, p80 = np.percentile(tile, [20, 50, 80])
            zones.append(float(0.25 * p20 + 0.5 * p50 + 0.25 * p80))
    ordered = sorted(zones)
    luminance = float(np.mean(ordered[1:-1]))  # Reject isolated bright/dark regions.
    p10, p90 = np.percentile(image, [10, 90])
    clipped = float(np.mean((image < 3) | (image > 252)))
    confidence = max(0.1, 1 - clipped)
    if luminance >= 220 and np.mean(image > 220) >= 0.7:
        confidence = max(confidence, 0.75)  # Broad sustained bright saturation is useful evidence.
    # DSHOW reports supported exposure times in log2 seconds. Unsupported zero,
    # implausible values, and nonintegral metadata are ignored.
    supported = (
        exposure is not None
        and math.isfinite(exposure)
        and -13 <= exposure <= -2
        and abs(exposure - round(exposure)) < 0.05
    )
    correction = exposure if supported else 0
    score = 2 * math.log2(max(luminance, 1) / 255) - correction
    return dict(
        score=score,
        level=luminance,
        confidence=confidence,
        exposure=exposure if supported else None,
        contrast=float(p90 - p10),
        possibly_covered=bool(luminance <= 2 and p90 - p10 <= 1.5 and np.mean(image < 3) >= 0.98),
        zones=[2 * math.log2(max(value, 1) / 255) - correction for value in zones],
    )


def combine_frames(frames):
    import numpy as np

    if not frames:
        raise ValueError("No camera readings.")
    scores = [frame["score"] for frame in frames]
    middle = float(np.median(scores))
    deviation = float(np.median(np.abs(np.asarray(scores) - middle)))
    confidence = float(np.median([frame["confidence"] for frame in frames]))
    if deviation > 0.25:
        confidence *= 0.35  # Wait out exposure/scene settling.
    return dict(
        score=middle,
        possibly_covered=all(frame.get("possibly_covered", False) for frame in frames),
        level=float(np.median([frame["level"] for frame in frames])),
        confidence=confidence,
        exposure=float(np.median([frame["exposure"] for frame in frames]))
        if all(frame["exposure"] is not None for frame in frames)
        else None,
        exposure_corrected=all(frame["exposure"] is not None for frame in frames),
        zones=np.median([frame["zones"] for frame in frames], axis=0).tolist(),
    )


def average_pair(first, second):
    """Average numeric lighting estimates; keep only the latest in-memory preview."""
    result = second.copy()
    result["possibly_covered"] = bool(
        first.get("possibly_covered") and second.get("possibly_covered")
    )
    for key in ("level", "score"):
        result[key] = (first[key] + second[key]) / 2
    result["confidence"] = min(first["confidence"], second["confidence"])
    result["exposure_corrected"] = bool(
        first.get("exposure_corrected") and second.get("exposure_corrected")
    )
    a, b = first.get("zones", []), second.get("zones", [])
    if a and len(a) == len(b):
        result["zones"] = [(x + y) / 2 for x, y in zip(a, b)]
    result["pair_levels"] = [first["level"], second["level"]]
    return result
