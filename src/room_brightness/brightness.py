"""Windows CIM brightness control; no WMIC executable is required."""

import os
import subprocess
from collections.abc import Callable

from .paths import RESOURCE_DIR


def brightness(value: int | None = None) -> int:
    if os.name != "nt":
        raise RuntimeError("Brightness control requires Windows.")
    args = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(RESOURCE_DIR / "brightness.ps1"),
        "-Action",
        "read" if value is None else "set",
    ]
    if value is not None:
        if not isinstance(value, int) or not 0 <= value <= 100:
            raise ValueError("Brightness must be an integer between 0 and 100.")
        args += ["-Value", str(value)]
    result = subprocess.run(
        args, capture_output=True, text=True, timeout=20, creationflags=subprocess.CREATE_NO_WINDOW
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "CIM brightness control failed.")
    try:
        actual = int(result.stdout.strip())
    except ValueError as exc:
        raise RuntimeError("Windows returned an invalid brightness reading.") from exc
    if not 0 <= actual <= 100:
        raise RuntimeError("Windows returned brightness outside 0–100%.")
    return actual


def set_checked(value: int, control: Callable = brightness) -> int:
    actual = control(value)
    if actual != value:
        raise RuntimeError("Brightness readback does not match the requested value.")
    return actual


def verify_control(control: Callable = brightness, original: int | None = None) -> int:
    """Always attempt restoration, even if the test write or readback fails."""
    original = control() if original is None else original
    test_value = original + 5 if original <= 95 else original - 5
    try:
        set_checked(test_value, control)
    finally:
        try:
            set_checked(original, control)
        except Exception as exc:
            raise RuntimeError(
                "Could not confirm restoration. Restore brightness manually."
            ) from exc
    return original


def smooth_to(start, target, cancel, progress):
    """One cancellable CIM process for the entire verified one-percent ramp."""
    import queue
    import threading
    import time

    if not 0 <= start <= 100 or not 0 <= target <= 100:
        raise ValueError("Brightness outside 0–100%.")
    process = subprocess.Popen(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(RESOURCE_DIR / "smooth.ps1"),
            "-Start",
            str(start),
            "-Target",
            str(target),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    lines = queue.Queue()

    def read():
        try:
            for line in process.stdout:
                lines.put(line.strip())
        finally:
            lines.put(None)

    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    actual = start
    manual = False
    error = None
    deadline = time.monotonic() + 120
    try:
        while True:
            if cancel.is_set():
                process.terminate()
                process.wait(timeout=5)
                # Cancel any remaining native fade by reapplying its current level.
                actual = brightness()
                set_checked(actual)
                break
            if time.monotonic() > deadline:
                raise RuntimeError("Brightness transition timed out.")
            try:
                line = lines.get(timeout=0.05)
            except queue.Empty:
                continue
            if line is None:
                break
            if line.startswith(("P ", "M ")):
                value = int(line[2:])
                if not 0 <= value <= 100:
                    raise RuntimeError("Invalid brightness readback.")
                actual = value
                manual = line.startswith("M ")
                if not manual:
                    progress(actual)
            elif line.startswith("E "):
                error = line[2:]
        process.wait(timeout=5)
        if not cancel.is_set() and (error or process.returncode):
            raise RuntimeError(error or "Brightness transition failed.")
        return actual, manual
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
        reader.join(timeout=1)
        process.stdout.close()
