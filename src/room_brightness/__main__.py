"""CLI entry point and single-instance Windows desktop launcher."""

import argparse
import json
import os
import sys

from . import __version__


def main():
    parser = argparse.ArgumentParser(
        description="Local camera-based screen brightness for Windows."
    )
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--sample", type=int, help=argparse.SUPPRESS)
    parser.add_argument("--meter", type=int, help=argparse.SUPPRESS)
    parser.add_argument(
        "--autostart", action="store_true", help="Open the app after Windows sign-in."
    )
    parser.add_argument("--list-cameras", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--preview", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--self-test", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--region", default="0,0,1,1", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if os.name != "nt":
        parser.exit(1, "Auto Brightness requires Windows 10 or Windows 11.\n")
    if args.list_cameras:
        from .devices import native_devices

        try:
            sys.stdout.reconfigure(encoding="utf-8")
            print(json.dumps(native_devices(), ensure_ascii=False))
        except Exception as exc:
            parser.exit(1, str(exc) + "\n")
        return
    if args.sample is not None or args.meter is not None:
        index = args.sample if args.sample is not None else args.meter
        if index < 0:
            parser.exit(1, "Invalid camera selection.\n")
        from .camera import camera_sample

        try:
            reading = camera_sample(
                index, preview=args.preview, region=[float(v) for v in args.region.split(",")]
            )
            print(json.dumps(reading) if args.meter is not None else reading["level"])
        except Exception as exc:
            parser.exit(1, str(exc) + "\n")
        return

    if getattr(sys, "frozen", False):
        import ctypes

        handle = ctypes.windll.kernel32.GetConsoleWindow()
        if handle:
            ctypes.windll.user32.ShowWindow(ctypes.c_void_p(handle), 0)
    import msvcrt
    from .paths import DATA_DIR
    from .i18n import text
    from .settings import system_language

    try:
        from PySide6.QtWidgets import QApplication, QMessageBox
        from .qt_engine import Scheduler, Engine
        from .qt_ui import run_desktop
    except ImportError as exc:
        parser.exit(1, "Run Setup.cmd to install the updated interface. " + str(exc) + "\n")
    _app = QApplication.instance() or QApplication(sys.argv[:1])
    if args.self_test:
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as folder:
            root = Scheduler()
            root._brightness_backend = Engine(root, discover=False, directory=Path(folder))
            root.after(500, root._brightness_backend.close)
            run_desktop(root)
        print("Desktop smoke check passed: " + __version__)
        return
    language = system_language()
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with (DATA_DIR / "instance.lock").open("a+b") as instance:
            instance.seek(0, 2)
            if instance.tell() == 0:
                instance.write(b"0")
                instance.flush()
            instance.seek(0)
            try:
                msvcrt.locking(instance.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                QMessageBox.information(None, text(language, "app"), text(language, "already"))
                return
            root = Scheduler()
            root._brightness_backend = Engine(root)
            run_desktop(root)
    except OSError as exc:
        QMessageBox.critical(None, text(language, "cannot_start"), str(exc))
        sys.exit(1)


if __name__ == "__main__":
    main()
