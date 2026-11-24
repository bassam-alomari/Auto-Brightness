from pathlib import Path
import tempfile
import unittest

from room_brightness.linux_control import Backlight


class LinuxBacklightTests(unittest.TestCase):
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
