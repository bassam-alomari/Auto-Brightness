"""Linux device adapter and explicit terminal entry point."""

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
from threading import Event
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


class DdcDisplay:
    def __init__(self, edid):
        if not re.fullmatch(r"[0-9a-fA-F]{256}", edid):
            raise ValueError("Expected the 256 hex characters of a monitor's base EDID")
        self.edid = edid.lower()

    def _command(self, *args):
        matches = sum(
            path.read_bytes()[:128].hex() == self.edid
            for path in Path("/sys/class/drm").glob("*/edid")
        )
        if matches != 1:
            raise RuntimeError("The selected display EDID is missing or ambiguous")
        result = subprocess.run(
            ["ddcutil", "--edid", self.edid, *args],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode:
            raise RuntimeError("DDC/CI command failed. Check monitor support and permissions.")
        return result.stdout

    def _levels(self):
        match = re.search(r"^VCP 10 C (\d+) (\d+)$", self._command("--terse", "getvcp", "10"), re.M)
        if match:
            value, maximum = map(int, match.groups())
            if maximum > 0 and 0 <= value <= maximum:
                return value, maximum
        raise RuntimeError("Unexpected DDC brightness response")

    def read(self):
        value, maximum = self._levels()
        return round(value * 100 / maximum)

    def write(self, value):
        if type(value) is not int or not 1 <= value <= 100:
            raise ValueError("Display target must be between 1 and 100")
        _, maximum = self._levels()
        raw = max(1, round(value * maximum / 100))
        self._command("setvcp", "10", str(raw))
        actual, new_maximum = self._levels()
        if actual != raw or new_maximum != maximum:
            raise RuntimeError("DDC brightness readback did not match")
        return round(actual * 100 / maximum)


def capture(path, cancelled=lambda: False):
    worker = (
        "import json,sys; from room_brightness.camera import camera_sample; "
        "print(json.dumps(camera_sample(sys.argv[1])))"
    )
    deadline = time.monotonic() + 15
    with subprocess.Popen(
        [sys.executable, "-c", worker, str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ) as process:
        try:
            while not cancelled() and time.monotonic() < deadline:
                try:
                    output, _ = process.communicate(timeout=0.1)
                except subprocess.TimeoutExpired:
                    continue
                if process.returncode:
                    raise RuntimeError("Camera capture failed. Check device permissions.")
                return json.loads(output)
            if cancelled():
                raise InterruptedError("Capture stopped")
            raise TimeoutError("Camera capture timed out")
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()


def run_session(camera, device, stop, report, *, monitor=True, watch=True, restore=False):
    original = device.read()
    controller = AdaptiveController(
        low=10, high=80, mapping="image", options=DEFAULTS.copy(), expected=original
    )
    last_write = None

    def write(target):
        nonlocal last_write
        last_write = device.write(target)
        return last_write

    session = ControlSession(controller, device.read, write, monitor=monitor)
    try:
        while not stop.is_set():
            generation = session.generation()
            first = capture(camera, stop.is_set)
            second = capture(camera, stop.is_set)
            decision = session.evaluate(average_pair(first, second), generation, stop.is_set)
            report(vars(decision))
            if not watch or stop.wait(DEFAULTS["interval_" + power_mode()]):
                break
    except InterruptedError:
        if not stop.is_set():
            raise
    finally:
        if restore and last_write is not None:
            if device.read() == last_write and not controller.manual_reference:
                device.write(original)


def power_mode(root=Path("/sys/class/power_supply")):
    external = []
    for supply in root.iterdir() if root.is_dir() else ():
        try:
            if (supply / "type").read_text().strip() in {"Mains", "USB", "USB_C", "USB_PD"}:
                external.append((supply / "online").read_text().strip() == "1")
        except OSError:
            continue
    return "battery" if external and not any(external) else "ac"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Experimental Linux brightness control")
    parser.add_argument("--list", action="store_true", help="List camera and backlight paths")
    parser.add_argument("--camera", type=Path)
    display = parser.add_mutually_exclusive_group()
    display.add_argument("--backlight", type=Path)
    display.add_argument("--ddc-edid")
    parser.add_argument(
        "--apply", action="store_true", help="Allow writes to the selected backlight"
    )
    parser.add_argument("--watch", action="store_true", help="Continue until Ctrl+C")
    parser.add_argument(
        "--check", action="store_true", help="Check selected devices without writing"
    )
    parser.add_argument(
        "--restore", action="store_true", help="Restore brightness on exit after an automatic write"
    )
    options = parser.parse_args(argv)
    if options.check and (options.apply or options.watch):
        parser.error("--check cannot be combined with --apply or --watch.")
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
    if options.camera is None or not (options.backlight or options.ddc_edid):
        parser.error("Specify --camera and either --backlight or --ddc-edid.")
    if options.backlight is not None and (
        Path("/sys/class/backlight") not in options.backlight.absolute().parents
        or ".." in options.backlight.parts
    ):
        parser.error("Select a backlight under /sys/class/backlight.")
    try:
        device = DdcDisplay(options.ddc_edid) if options.ddc_edid else Backlight(options.backlight)
        current = device.read()
        if options.check:
            reading = capture(options.camera)
            print(
                json.dumps(
                    {
                        "camera": str(options.camera),
                        "display": str(options.backlight or "DDC/CI"),
                        "current": current,
                        "camera_level": reading["level"],
                        "power": power_mode(),
                        "write_tested": False,
                    }
                )
            )
            return
        run_session(
            options.camera,
            device,
            Event(),
            lambda row: print(json.dumps(row), flush=True),
            monitor=not options.apply,
            watch=options.watch,
            restore=options.restore,
        )
    except KeyboardInterrupt:
        return
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        parser.exit(1, str(error) + "\n")


if __name__ == "__main__":
    main()
