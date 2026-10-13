import unittest
from contextlib import contextmanager
from unittest.mock import patch
import threading
from room_brightness import monitors


class FakeNative:
    def __init__(self):
        self.raw = 30
        self.closed = 0
        self.writes = []

    @contextmanager
    def handles(self):
        try:
            yield [("external", "External display", 123), ("unsupported", "Unknown", 456)]
        finally:
            self.closed += 1

    def supported(self, handle):
        return handle == 123

    def read(self, handle):
        return 10, self.raw, 110

    def write(self, handle, value):
        self.raw = value
        self.writes.append(value)


class MonitorTests(unittest.TestCase):
    def tearDown(self):
        monitors.select("internal")

    def test_enumeration_filters_unsupported_and_releases_handles(self):
        native = FakeNative()
        rows = monitors.list_displays(native)
        self.assertEqual([row["id"] for row in rows], ["internal", "external"])
        self.assertEqual(rows[1]["brightness"], 20)
        self.assertEqual(native.closed, 1)

    def test_range_conversion(self):
        self.assertEqual(monitors.raw_value(10, 110, 50), 60)
        self.assertEqual(monitors.to_percent(10, 60, 110), 50)
        with self.assertRaises(ValueError):
            monitors.to_percent(10, 30, 10)

    def test_selected_display_routes_writes_and_releases_handle(self):
        native = FakeNative()
        monitors.select("external")
        with patch.object(monitors, "Native", return_value=native):
            self.assertEqual(monitors.brightness(70), 70)
        self.assertEqual(native.writes, [80])
        self.assertEqual(native.closed, 1)

    def test_disconnected_selection_does_not_write_any_other_display(self):
        native = FakeNative()
        monitors.select("missing")
        with patch.object(monitors, "Native", return_value=native):
            with self.assertRaises(RuntimeError):
                monitors.brightness(50)
        self.assertFalse(native.writes)
        self.assertEqual(native.closed, 1)

    def test_external_ramp_honors_manual_override_and_cancellation(self):
        native = FakeNative()
        monitors.select("external")
        with patch.object(monitors, "Native", return_value=native):
            actual, manual = monitors.smooth(50, 70, threading.Event(), lambda _: None, 1)
        self.assertEqual(actual, 20)
        self.assertTrue(manual)
        self.assertFalse(native.writes)
        cancelled = threading.Event()
        cancelled.set()
        with patch.object(monitors, "Native", return_value=native):
            actual, manual = monitors.smooth(20, 70, cancelled, lambda _: None, 1)
        self.assertEqual(actual, 20)
        self.assertFalse(manual)
        self.assertFalse(native.writes)

    def test_native_cleanup_runs_if_consumer_fails(self):
        from types import SimpleNamespace

        native = monitors.Native.__new__(monitors.Native)
        native.callback = lambda callback: callback
        released = []

        def info(handle, pointer):
            pointer._obj.device = "DISPLAY1"
            return True

        def count(handle, pointer):
            pointer._obj.value = 1
            return True

        def physical(handle, size, array):
            array[0].handle = 123
            array[0].description = "External"
            return True

        def device(name, index, pointer, flags):
            pointer._obj.identity = "monitor-instance-123"
            return True

        native.user = SimpleNamespace(
            EnumDisplayDevicesW=device,
            GetMonitorInfoW=info,
            EnumDisplayMonitors=lambda dc, rect, callback, param: callback(1, None, None, 0),
        )
        native.api = SimpleNamespace(
            GetNumberOfPhysicalMonitorsFromHMONITOR=count,
            GetPhysicalMonitorsFromHMONITOR=physical,
            DestroyPhysicalMonitors=lambda size, array: released.append(size) or True,
        )
        with self.assertRaises(RuntimeError):
            with native.handles() as handles:
                self.assertEqual(handles[0][2], 123)
                self.assertIn("monitor-instance-123", handles[0][0])
                raise RuntimeError("consumer failed")
        self.assertEqual(released, [1])
