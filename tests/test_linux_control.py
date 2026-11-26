from pathlib import Path
import tempfile
import unittest
from threading import Event
from unittest.mock import patch

from room_brightness.linux_control import Backlight, DdcDisplay, main, run_session


class LinuxBacklightTests(unittest.TestCase):
    def test_restore_keeps_external_manual_adjustment(self):
        from unittest.mock import Mock

        reading = {"level": 40, "confidence": 1, "score": 0}
        for final, expected in ((80, [80, 40]), (55, [80])):
            device = Mock()
            device.read.side_effect = [40, 40, 40, 40, final]
            device.write.side_effect = lambda value: value
            stop = Event()

            def report(row):
                if row["applied"]:
                    stop.set()

            with (
                patch("room_brightness.linux_control.capture", return_value=reading),
                patch.object(stop, "wait", return_value=False),
            ):
                run_session("/dev/video0", device, stop, report, monitor=False, restore=True)
            self.assertEqual([call.args[0] for call in device.write.call_args_list], expected)

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
