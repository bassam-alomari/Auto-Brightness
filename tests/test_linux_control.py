from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from room_brightness.linux_control import Backlight, DdcDisplay, main


class LinuxBacklightTests(unittest.TestCase):
    def test_compatibility_check_reads_without_writing(self):
        with (
            patch("sys.platform", "linux"),
            patch("room_brightness.linux_control.DdcDisplay") as backlight,
            patch("room_brightness.linux_control.capture", return_value={"level": 20}),
            patch("builtins.print") as output,
        ):
            backlight.return_value.read.return_value = 50
            main(["--camera", "/dev/video0", "--ddc-edid", "ab" * 128, "--check"])
        backlight.return_value.write.assert_not_called()
        self.assertIn('"write_tested": false', output.call_args.args[0])

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
