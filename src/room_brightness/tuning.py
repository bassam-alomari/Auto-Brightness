"""Guided curves, optional spatial rejection and bounded local performance counters."""

import math
import re
import time
import os
from collections import deque


def app_names(value):
    if not isinstance(value, list) or len(value) > 30:
        return []
    return sorted(
        {
            v.lower()
            for v in value
            if isinstance(v, str) and re.fullmatch(r"[\w .()+-]{1,75}\.exe", v, re.ASCII)
        }
    )


def transition_duration(options, current, wanted):
    if options.get("directional_response", False):
        return 1 if wanted > current else 8
    return {"calm": 8, "balanced": 4, "fast": 1}[options.get("transition_speed", "balanced")]


def calibrated_points(samples):
    """Preserve the established endpoints; require distinct usable ambient readings."""
    from .comfort import valid_points

    if len(samples) != 3:
        raise ValueError("Three reliable readings are required.")
    if any(
        len(row) != 2 or any(type(v) not in (float, int) or not math.isfinite(v) for v in row)
        for row in samples
    ):
        raise ValueError("Invalid calibration reading.")
    rows = [[round(x, 1), round(y)] for x, y in samples]
    if not all(12 < x < 254 and 0 <= y <= 100 for x, y in rows):
        raise ValueError("Use readings above 12 and below 254.")
    if any(b[0] - a[0] < 1 or b[1] < a[1] for a, b in zip(rows, rows[1:])):
        raise ValueError("Increase room light between steps and keep brightness nondecreasing.")
    points = [[12, 0], *rows, [min(255, max(27, rows[-1][0] + 1)), 100]]
    if not valid_points(points):
        raise ValueError("Invalid calibration curve.")
    return points


def protected_frame(frame):
    """Reject centre and isolated extreme 4x4 tiles; no face or lux inference."""
    import numpy as np

    height, width = frame.shape[:2]
    levels, rectangles = [], []
    for y in range(4):
        for x in range(4):
            rect = (x * width // 4, y * height // 4, (x + 1) * width // 4, (y + 1) * height // 4)
            x0, y0, x1, y1 = rect
            if x in (1, 2) and y in (1, 2):
                continue
            levels.append(float(np.median(frame[y0:y1, x0:x1])))
            rectangles.append(rect)
    median = float(np.median(levels))
    selected = [
        r for r, value in zip(rectangles, levels) if abs(value - median) <= max(12, median * 0.6)
    ]
    if len(selected) < 6:
        selected = rectangles
    mask = np.zeros((height, width), dtype=bool)
    for x0, y0, x1, y1 in selected:
        mask[y0:y1, x0:x1] = True
    result = frame.copy()
    result[~mask] = np.median(frame[mask], axis=0).astype(frame.dtype)
    return result, mask


def foreground_app():
    """Return only the executable basename; never retain titles or full paths."""
    import ctypes
    from ctypes import wintypes as w
    from pathlib import PureWindowsPath

    if os.name != "nt":
        return None
    user = ctypes.WinDLL("user32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    user.GetForegroundWindow.restype = w.HWND
    user.GetWindowThreadProcessId.argtypes = [w.HWND, ctypes.POINTER(w.DWORD)]
    kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
    kernel.OpenProcess.restype = w.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = [
        w.HANDLE,
        w.DWORD,
        w.LPWSTR,
        ctypes.POINTER(w.DWORD),
    ]
    kernel.CloseHandle.argtypes = [w.HANDLE]
    hwnd = user.GetForegroundWindow()
    if not hwnd:
        return None
    pid = w.DWORD()
    if not user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid)):
        return None
    handle = kernel.OpenProcess(0x1000, False, pid.value)
    if not handle:
        return None
    try:
        size = w.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if kernel.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return PureWindowsPath(buffer.value).name.lower()
    finally:
        kernel.CloseHandle(handle)
    return None


def memory_mb():
    import ctypes
    from ctypes import wintypes as w

    if os.name != "nt":
        return None

    class Counters(ctypes.Structure):
        _fields_ = [("cb", w.DWORD), ("faults", w.DWORD)] + [
            (name, ctypes.c_size_t)
            for name in (
                "peak",
                "working",
                "pool_peak",
                "pool",
                "nonpaged_peak",
                "nonpaged",
                "pagefile",
                "pagefile_peak",
            )
        ]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel.GetCurrentProcess.restype = w.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [w.HANDLE, ctypes.POINTER(Counters), w.DWORD]
    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    return (
        counters.working / 1048576
        if psapi.GetProcessMemoryInfo(
            kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb
        )
        else None
    )


class Performance:
    def __init__(self):
        self.started = self.last_time = time.monotonic()
        self.last_cpu = time.process_time()
        self.samples = deque(maxlen=120)
        self.camera_seconds = self.camera_cpu = 0.0
        self.captures = 0

    def capture(self, reading):
        for key, attr in (("camera_seconds", "camera_seconds"), ("camera_cpu", "camera_cpu")):
            value = reading.get(key, 0)
            if type(value) in (int, float) and math.isfinite(value) and 0 <= value < 120:
                setattr(self, attr, getattr(self, attr) + value)
        self.captures += 1

    def snapshot(self):
        now, cpu = time.monotonic(), time.process_time()
        percent = max(0, 100 * (cpu - self.last_cpu) / max(0.001, now - self.last_time))
        self.last_time, self.last_cpu = now, cpu
        row = dict(
            cpu=round(percent, 1),
            memory=memory_mb(),
            camera_seconds=round(self.camera_seconds, 1),
            camera_cpu=round(self.camera_cpu, 2),
            captures=self.captures,
            uptime=round(now - self.started),
        )
        self.samples.append(row)
        return row
