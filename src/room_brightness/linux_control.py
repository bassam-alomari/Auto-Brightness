"""Linux device adapter and explicit terminal entry point."""

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

from .adaptive import AdaptiveController
from .control_session import ControlSession
from .metering import average_pair
from .settings import DEFAULTS


class Backlight:
    def __init__(self, path):
        self.path = Path(path)
        self.maximum = self._read("max_brightness")
        if self.maximum < 1:
            raise ValueError("Invalid backlight maximum")

    def _read(self, key):
        return int((self.path / key).read_text(encoding="ascii"))

    def read(self):
        value = self._read("actual_brightness")
        if not 0 <= value <= self.maximum:
            raise ValueError("Invalid backlight reading")
        return round(value * 100 / self.maximum)

    def write(self, value):
        if type(value) is not int or not 1 <= value <= 100:
            raise ValueError("Linux backlight target must be between 1 and 100")
        raw = max(1, round(value * self.maximum / 100))
        (self.path / "brightness").write_text(str(raw), encoding="ascii")
        actual = self.read()
        if abs(actual - round(raw * 100 / self.maximum)) > 1:
            raise RuntimeError("Backlight readback did not match the requested value")
        return actual


def capture(path):
    worker = (
        "import json,sys; from room_brightness.camera import camera_sample; "
        "print(json.dumps(camera_sample(sys.argv[1])))"
    )
    result = subprocess.run(
        [sys.executable, "-c", worker, str(path)], capture_output=True, text=True, timeout=15
    )
    if result.returncode:
        raise RuntimeError("Camera capture failed. Check the device and its permissions.")
    return json.loads(result.stdout)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Experimental Linux brightness control")
    parser.add_argument("--list", action="store_true", help="List camera and backlight paths")
    parser.add_argument("--camera", type=Path)
    parser.add_argument("--backlight", type=Path)
    parser.add_argument(
        "--apply", action="store_true", help="Allow writes to the selected backlight"
    )
    parser.add_argument("--watch", action="store_true", help="Continue until Ctrl+C")
    options = parser.parse_args(argv)
    if not sys.platform.startswith("linux"):
        parser.error("This entry point requires Linux.")
    if options.list:
        print(
            json.dumps(
                {
                    "cameras": sorted(str(p) for p in Path("/dev/v4l/by-id").glob("*"))
                    or sorted(str(p) for p in Path("/dev").glob("video[0-9]*")),
                    "backlights": sorted(str(p) for p in Path("/sys/class/backlight").glob("*")),
                },
                indent=2,
            )
        )
        return
    if options.camera is None or options.backlight is None:
        parser.error("Specify --camera and --backlight using the paths from --list.")
    if (
        Path("/sys/class/backlight") not in options.backlight.absolute().parents
        or ".." in options.backlight.parts
    ):
        parser.error("Select a backlight under /sys/class/backlight.")
    try:
        device = Backlight(options.backlight)
        controller = AdaptiveController(
            low=10, high=80, mapping="image", options=DEFAULTS.copy(), expected=device.read()
        )
        session = ControlSession(controller, device.read, device.write, monitor=not options.apply)
        while True:
            generation = session.generation()
            reading = average_pair(capture(options.camera), capture(options.camera))
            decision = session.evaluate(reading, generation)
            print(json.dumps(vars(decision)), flush=True)
            if not options.watch:
                break
            time.sleep(5)
    except KeyboardInterrupt:
        return
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        parser.exit(1, str(error) + "\n")
