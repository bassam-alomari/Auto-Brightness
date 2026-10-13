"""Capability-gated external-monitor control with deterministic handle cleanup."""

import ctypes
from ctypes import wintypes
from contextlib import contextmanager
import json

selected_target = "internal"
quantization_error = 0


class Physical(ctypes.Structure):
    _fields_ = [("handle", wintypes.HANDLE), ("description", wintypes.WCHAR * 128)]


class DisplayDevice(ctypes.Structure):
    _fields_ = [
        ("size", wintypes.DWORD),
        ("name", wintypes.WCHAR * 32),
        ("description", wintypes.WCHAR * 128),
        ("flags", wintypes.DWORD),
        ("identity", wintypes.WCHAR * 128),
        ("key", wintypes.WCHAR * 128),
    ]


class MonitorInfo(ctypes.Structure):
    _fields_ = [
        ("size", wintypes.DWORD),
        ("monitor", wintypes.RECT),
        ("work", wintypes.RECT),
        ("flags", wintypes.DWORD),
        ("device", wintypes.WCHAR * 32),
    ]


def select(target):
    global selected_target
    selected_target = target


class Native:
    def __init__(self):
        self.api = ctypes.WinDLL("dxva2", use_last_error=True)
        self.user = ctypes.WinDLL("user32", use_last_error=True)
        self.callback = ctypes.WINFUNCTYPE(
            wintypes.BOOL,
            wintypes.HANDLE,
            wintypes.HDC,
            ctypes.POINTER(wintypes.RECT),
            wintypes.LPARAM,
        )
        signatures = {
            "GetNumberOfPhysicalMonitorsFromHMONITOR": [
                wintypes.HANDLE,
                ctypes.POINTER(wintypes.DWORD),
            ],
            "GetPhysicalMonitorsFromHMONITOR": [
                wintypes.HANDLE,
                wintypes.DWORD,
                ctypes.POINTER(Physical),
            ],
            "DestroyPhysicalMonitors": [wintypes.DWORD, ctypes.POINTER(Physical)],
            "GetMonitorCapabilities": [
                wintypes.HANDLE,
                ctypes.POINTER(wintypes.DWORD),
                ctypes.POINTER(wintypes.DWORD),
            ],
            "GetMonitorBrightness": [
                wintypes.HANDLE,
                ctypes.POINTER(wintypes.DWORD),
                ctypes.POINTER(wintypes.DWORD),
                ctypes.POINTER(wintypes.DWORD),
            ],
            "SetMonitorBrightness": [wintypes.HANDLE, wintypes.DWORD],
        }
        for name, args in signatures.items():
            function = getattr(self.api, name)
            function.argtypes = args
            function.restype = wintypes.BOOL
        self.user.EnumDisplayMonitors.argtypes = [
            wintypes.HDC,
            ctypes.POINTER(wintypes.RECT),
            self.callback,
            wintypes.LPARAM,
        ]
        self.user.EnumDisplayMonitors.restype = wintypes.BOOL
        self.user.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MonitorInfo)]
        self.user.GetMonitorInfoW.restype = wintypes.BOOL
        self.user.EnumDisplayDevicesW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            ctypes.POINTER(DisplayDevice),
            wintypes.DWORD,
        ]
        self.user.EnumDisplayDevicesW.restype = wintypes.BOOL

    @contextmanager
    def handles(self):
        groups = []
        items = []
        error = []

        def visit(monitor, dc, rect, param):
            try:
                info = MonitorInfo()
                info.size = ctypes.sizeof(info)
                count = wintypes.DWORD()
                if not self.user.GetMonitorInfoW(monitor, ctypes.byref(info)):
                    return True
                if (
                    not self.api.GetNumberOfPhysicalMonitorsFromHMONITOR(
                        monitor, ctypes.byref(count)
                    )
                    or not 1 <= count.value <= 64
                ):
                    return True
                array = (Physical * count.value)()
                if not self.api.GetPhysicalMonitorsFromHMONITOR(monitor, count.value, array):
                    return True
                groups.append(array)
                for index, physical in enumerate(array):
                    device = DisplayDevice()
                    device.size = ctypes.sizeof(device)
                    if (
                        not self.user.EnumDisplayDevicesW(
                            info.device, index, ctypes.byref(device), 1
                        )
                        or not device.identity
                    ):
                        continue
                    identity = json.dumps(
                        [device.identity, info.device, index, physical.description],
                        ensure_ascii=True,
                        separators=(",", ":"),
                    )
                    items.append(
                        (identity, physical.description + " · " + info.device, physical.handle)
                    )
            except Exception as exc:
                error.append(exc)
                return False
            return True

        callback = self.callback(visit)
        try:
            if not self.user.EnumDisplayMonitors(None, None, callback, 0):
                raise RuntimeError("Could not enumerate monitors.") from (
                    error[0] if error else None
                )
            yield items
        finally:
            for array in groups:
                self.api.DestroyPhysicalMonitors(len(array), array)

    def read(self, handle):
        minimum, current, maximum = wintypes.DWORD(), wintypes.DWORD(), wintypes.DWORD()
        if not self.api.GetMonitorBrightness(
            handle, ctypes.byref(minimum), ctypes.byref(current), ctypes.byref(maximum)
        ):
            raise RuntimeError("Monitor brightness unavailable. Enable DDC/CI in the monitor menu.")
        if not minimum.value <= current.value <= maximum.value or minimum.value >= maximum.value:
            raise RuntimeError("Invalid monitor brightness range.")
        return minimum.value, current.value, maximum.value

    def supported(self, handle):
        caps, temperatures = wintypes.DWORD(), wintypes.DWORD()
        return bool(
            self.api.GetMonitorCapabilities(handle, ctypes.byref(caps), ctypes.byref(temperatures))
            and caps.value & 2
        )

    def write(self, handle, value):
        if not self.api.SetMonitorBrightness(handle, value):
            raise RuntimeError("External monitor rejected brightness change.")


def to_percent(minimum, current, maximum):
    if not minimum <= current <= maximum or minimum >= maximum:
        raise ValueError("Invalid monitor range.")
    return round((current - minimum) * 100 / (maximum - minimum))


def raw_value(minimum, maximum, percent):
    if type(percent) is not int or not 0 <= percent <= 100:
        raise ValueError("Invalid brightness.")
    return round(minimum + (maximum - minimum) * percent / 100)


def list_displays(native=None):
    native = native or Native()
    displays = [{"id": "internal", "name": "Built-in display"}]
    with native.handles() as items:
        for identity, name, handle in items:
            if not native.supported(handle):
                continue
            try:
                minimum, current, maximum = native.read(handle)
            except RuntimeError:
                continue
            displays.append(
                {"id": identity, "name": name, "brightness": to_percent(minimum, current, maximum)}
            )
    return displays


@contextmanager
def selected(native=None):
    native = native or Native()
    identity = selected_target
    with native.handles() as items:
        item = next((item for item in items if item[0] == identity), None)
        if item is None or not native.supported(item[2]):
            raise RuntimeError(
                "Selected external monitor disconnected or unsupported. Refresh displays."
            )
        yield native, item[2]


def brightness(value=None):
    global quantization_error
    with selected() as (native, handle):
        minimum, current, maximum = native.read(handle)
        quantization_error = max(1, round(50 / (maximum - minimum)) + 1)
        if value is not None:
            wanted = raw_value(minimum, maximum, value)
            native.write(handle, wanted)
            minimum, current, maximum = native.read(handle)
            if abs(current - wanted) > 0:
                raise RuntimeError("External monitor brightness readback mismatch.")
        return to_percent(minimum, current, maximum)


def smooth(start, target, cancel, progress, duration):
    with selected() as (native, handle):
        minimum, current, maximum = native.read(handle)
        actual = to_percent(minimum, current, maximum)
        if actual != start:
            return actual, True
        count = max(1, abs(target - start))
        delay = duration / count
        direction = 1 if target > start else -1
        for requested in range(start + direction, target + direction, direction):
            if cancel.is_set():
                break
            minimum, current, maximum = native.read(handle)
            if to_percent(minimum, current, maximum) != actual:
                return to_percent(minimum, current, maximum), True
            raw = raw_value(minimum, maximum, requested)
            native.write(handle, raw)
            minimum, current, maximum = native.read(handle)
            if current != raw:
                raise RuntimeError("External monitor brightness readback mismatch.")
            actual = to_percent(minimum, current, maximum)
            progress(actual)
            if cancel.wait(delay):
                break
        return actual, False
