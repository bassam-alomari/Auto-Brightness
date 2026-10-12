"""Opt-in startup registration for the current Windows user only."""

from pathlib import Path
import subprocess
import sys

KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
NAME = "RoomBrightness"


def command():
    if getattr(sys, "frozen", False):
        return subprocess.list2cmdline([sys.executable, "--autostart"])
    interpreter = Path(sys.executable)
    windowed = interpreter.with_name("pythonw.exe")
    return subprocess.list2cmdline(
        [
            str(windowed if windowed.exists() else interpreter),
            "-m",
            "room_brightness",
            "--autostart",
        ]
    )


def is_enabled():
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY) as key:
            return bool(winreg.QueryValueEx(key, NAME)[0])
    except (ImportError, OSError):
        return False


def set_enabled(enabled):
    import winreg

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, KEY) as key:
        if enabled:
            value = command()
            if len(value) > 260:
                raise OSError("Startup path is too long. Move the project to a shorter path.")
            winreg.SetValueEx(key, NAME, 0, winreg.REG_SZ, value)
        else:
            try:
                winreg.DeleteValue(key, NAME)
            except FileNotFoundError:
                pass
