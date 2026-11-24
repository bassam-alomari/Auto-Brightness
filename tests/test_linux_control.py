from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from room_brightness.linux_control import Backlight, DdcDisplay


class LinuxBacklightTests(unittest.TestCase):
    def test_ddc_preserves_native_range_and_verifies_write(self):
        display = DdcDisplay("ab" * 128)
        with patch.object(
            display, "_command", side_effect=["VCP 10 C 100 200", "", "VCP 10 C 120 200"]
        ) as command:
            self.assertEqual(display.write(60), 60)
        self.assertEqual(command.call_args_list[1].args, ("setvcp", "10", "120"))

    def test_backlight_scales_and_verifies_hardware_readback(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "max_brightness").write_text("500")
            (path / "actual_brightness").write_text("250")
            backlight = Backlight(path)
            self.assertEqual(backlight.read(), 50)
            self.assertEqual(backlight.write(50), 50)
            self.assertEqual((path / "brightness").read_text(), "250")
            with self.assertRaises(RuntimeError):
                backlight.write(80)
            with self.assertRaises(ValueError):
                backlight.write(0)
