"""Pure, testable stability rules and editable monotonic camera curves."""

import math

DEFAULT_POINTS = [[12, 0], [15, 50], [20, 70], [25, 90], [27, 100]]


def valid_points(points):
    if not isinstance(points, list) or not 2 <= len(points) <= 12:
        return False
    for point in points:
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            return False
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in point):
            return False
        if not 12 <= point[0] <= 255 or not 0 <= point[1] <= 100:
            return False
    return (
        points[0][0] == 12
        and points[0][1] == 0
        and points[-1][1] == 100
        and all(a[0] < b[0] and a[1] <= b[1] for a, b in zip(points, points[1:]))
    )


def target(level, low, high, points):
    if level <= points[0][0]:
        return low
    if level >= points[-1][0]:
        return high
    knots = [tuple(point) for point in points]
    knots[0] = (12, low)
    for (x0, y0), (x1, y1) in zip(knots, knots[1:]):
        if level <= x1:
            t = (level - x0) / (x1 - x0)
            return max(low, min(high, round(y0 + (y1 - y0) * t * t * (3 - 2 * t))))
    return high


class Stability:
    def __init__(self):
        self.pending = None
        self.count = 0
        self.reason = ""

    def decide(self, reading, wanted, current, enabled=True, deadband=3, endpoints=(0, 100)):
        self.reason = ""
        if not enabled:
            return wanted
        if reading.get("confidence", 0) < 0.35:
            self.pending, self.count = None, 0
            self.reason = "uncertain"
            return current
        pair = reading.get("pair_levels") or []
        if len(pair) == 2 and abs(pair[0] - pair[1]) > 6:
            self.pending, self.count = None, 0
            self.reason = "transient"
            return current
        # Exact configured endpoints remain reachable even inside the deadband.
        if abs(wanted - current) < deadband and wanted not in endpoints:
            self.pending, self.count = None, 0
            self.reason = "deadband"
            return current
        if abs(wanted - current) >= 15:
            if self.pending is not None and abs(wanted - self.pending) <= 8:
                self.count += 1
            else:
                self.count = 1
            self.pending = wanted
            if self.count < 2:
                self.reason = "confirming_change"
                return current
        self.pending, self.count = None, 0
        return wanted


def learned_points(points, level, brightness):
    if not 12 < level < points[-1][0]:
        raise ValueError("Choose a reading between the curve endpoints.")
    updated = [list(point) for point in points if abs(point[0] - level) > 0.5]
    updated.append([round(level, 1), brightness])
    updated.sort()
    if not valid_points(updated):
        raise ValueError(
            "This preference would reverse the curve. Adjust neighboring points first."
        )
    return updated
