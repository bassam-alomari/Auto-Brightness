import ctypes
import json
import unittest
from unittest.mock import Mock, patch

from room_brightness.devices import GUID, Variant, list_devices


class DeviceTests(unittest.TestCase):
    def test_native_structure_layout(self):
        self.assertEqual(ctypes.sizeof(GUID), 16)
        self.assertEqual(ctypes.sizeof(Variant), 24 if ctypes.sizeof(ctypes.c_void_p) == 8 else 16)
        guid = GUID.parse("62be5d10-60eb-11d0-bd3b-00a0c911ce86")
        self.assertEqual(guid.data1, 0x62BE5D10)

    @patch("room_brightness.devices.subprocess.run")
    def test_name_and_identity_are_returned_without_capture(self, run):
        devices = [dict(name="HD USB Camera", index=0, id="device-path")]
        run.return_value = Mock(returncode=0, stdout=json.dumps(devices))
        self.assertEqual(list_devices(), devices)
        self.assertIn("--list-cameras", run.call_args.args[0])
        self.assertNotIn("--sample", run.call_args.args[0])

    @patch("room_brightness.devices.subprocess.run")
    def test_invalid_device_list_is_rejected(self, run):
        run.return_value = Mock(returncode=0, stdout='[{"name":"Camera","index":-1,"id":"x"}]')
        with self.assertRaisesRegex(RuntimeError, "Invalid camera list"):
            list_devices()
