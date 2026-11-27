"""Desktop controls for the Linux preview."""

import json
import os
from pathlib import Path
import sys
import time
from threading import Event, Thread

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .adaptive import CURVES
from .recovery import write_atomic
from .linux_control import Backlight, DdcDisplay, capture, run_session


class LinuxWindow(QWidget):
    status = Signal(str)
    done = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Auto Brightness · Linux preview")
        self.resize(480, 350)
        self.stop = Event()
        self.stop_requested_at = None
        self.worker = None
        config = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
        self.settings_path = config / "auto-brightness" / "linux-preview.json"
        try:
            saved = json.loads(self.settings_path.read_text(encoding="utf-8"))
            if not isinstance(saved, dict):
                saved = {}
        except (OSError, ValueError):
            saved = {}
        layout = QVBoxLayout(self)
        self.camera = QComboBox()
        self.display = QComboBox()
        self.edid = QLineEdit()
        self.edid.setPlaceholderText("External monitor EDID (256 hex characters)")
        self.refresh = QPushButton("Refresh devices")
        self.refresh.clicked.connect(self.refresh_devices)
        self.refresh_devices()
        self.monitor = QCheckBox("Monitor only (no brightness changes)")
        self.monitor.setChecked(True)
        self.restore = QCheckBox("Restore brightness when stopped")
        self.restore.setChecked(True)
        self.curve = QComboBox()
        self.curve.addItems(list(CURVES))
        self.low, self.high = QSpinBox(), QSpinBox()
        for field, key, default in ((self.low, "low", 10), (self.high, "high", 80)):
            field.setRange(1, 100)
            value = saved.get(key)
            field.setValue(value if type(value) is int else default)
        for field, key in (
            (self.camera, "camera"),
            (self.display, "display"),
            (self.curve, "curve"),
        ):
            value = saved.get(key)
            if isinstance(value, str) and field.findText(value) >= 0:
                field.setCurrentText(value)
        if isinstance(saved.get("display"), str):
            self.display.setCurrentIndex(self.display.findData(saved["display"]))
        if isinstance(saved.get("edid"), str):
            self.edid.setText(saved["edid"])
        self.check = QPushButton("Check compatibility (read-only)")
        self.start = QPushButton("Start")
        self.stop_button = QPushButton("Stop")
        self.details = QLabel("Choose a camera and display.")
        self.details.setWordWrap(True)
        for control in (
            QLabel("Camera"),
            self.camera,
            QLabel("Display"),
            self.display,
            self.edid,
            self.refresh,
            self.monitor,
            self.restore,
            QLabel("Curve"),
            self.curve,
            QLabel("Minimum brightness"),
            self.low,
            QLabel("Maximum brightness"),
            self.high,
            self.check,
            self.start,
            self.stop_button,
            self.details,
        ):
            layout.addWidget(control)
        self.check.clicked.connect(lambda: self.launch(check=True))
        self.start.clicked.connect(lambda: self.launch(check=False))
        self.stop_button.clicked.connect(self.request_stop)
        self.status.connect(self.details.setText)
        self.done.connect(lambda: self.set_busy(False))
        self.set_busy(False)

    def refresh_devices(self):
        from collections import Counter

        camera, target = self.camera.currentText(), self.display.currentData()
        cameras = sorted(Path("/dev/v4l/by-id").glob("*")) or sorted(
            Path("/dev").glob("video[0-9]*")
        )
        self.camera.clear()
        self.camera.addItems([str(path) for path in cameras])
        if camera:
            self.camera.setCurrentIndex(self.camera.findText(camera))
        self.display.clear()
        for path in sorted(Path("/sys/class/backlight").glob("*")):
            self.display.addItem(path.name, str(path))
        edids = []
        for path in sorted(Path("/sys/class/drm").glob("*/edid")):
            try:
                data = path.read_bytes()
            except OSError:
                continue
            if len(data) >= 128:
                edids.append((path.parent.name, data[:128].hex()))
        counts = Counter(edid for _, edid in edids)
        for name, edid in edids:
            if counts[edid] == 1:
                self.display.addItem(name + " (DDC/CI)", "edid:" + edid)
        self.display.addItem("External monitor (manual EDID)", "ddc")
        if target is not None:
            self.display.setCurrentIndex(self.display.findData(target))

    def set_busy(self, busy):
        for control in (
            self.camera,
            self.display,
            self.edid,
            self.refresh,
            self.monitor,
            self.restore,
            self.curve,
            self.low,
            self.high,
            self.start,
            self.check,
        ):
            control.setEnabled(not busy)
        self.stop_button.setEnabled(busy)

    def request_stop(self):
        if self.stop_requested_at is None:
            self.stop_requested_at = time.monotonic()
        self.stop.set()

    def launch(self, check):
        if self.worker and self.worker.is_alive():
            return
        camera = self.camera.currentText()
        if not camera:
            self.details.setText("No camera is listed. Connect one and reopen the preview.")
            return
        target = self.display.currentData()
        if target is None:
            self.details.setText("Select a display from the list.")
            return
        external = target == "ddc" or target.startswith("edid:")
        edid = target[5:] if target.startswith("edid:") else self.edid.text().strip()
        monitor, restore = self.monitor.isChecked(), self.restore.isChecked()
        curve, low, high = self.curve.currentText(), self.low.value(), self.high.value()
        if low >= high:
            self.details.setText("Minimum brightness must be below maximum.")
            return
        if not check:
            try:
                self.settings_path.parent.mkdir(parents=True, exist_ok=True)
                write_atomic(
                    self.settings_path,
                    json.dumps(
                        dict(
                            camera=camera,
                            display=target,
                            edid=edid,
                            curve=curve,
                            low=low,
                            high=high,
                        )
                    ),
                )
            except OSError as error:
                self.details.setText(f"Could not save preferences: {error}")
                return
        self.stop.clear()
        self.stop_requested_at = None
        self.set_busy(True)
        self.details.setText("Reading devices…")

        def work():
            try:
                device = DdcDisplay(edid) if external else Backlight(target)
                if check:
                    current = device.read()
                    reading = capture(camera, self.stop.is_set)
                    self.status.emit(
                        f"Display: {current}% · Camera level: {reading['level']:.1f}/255"
                    )
                else:

                    def report(row):
                        action = "Applied" if row["applied"] else "Held"
                        self.status.emit(
                            f"{action} · Screen {row['current']}% · Target {row['target']}%"
                            f" · {row['reason'] or 'curve'}"
                            f"\nCapture: {row['capture_ms']} ms · Decision and display I/O:"
                            f" {row['decision_and_io_ms']} ms"
                            + (
                                f" · Write and verification: {row['write_and_readback_ms']} ms"
                                if row["write_and_readback_ms"] is not None
                                else ""
                            )
                        )

                    run_session(
                        camera,
                        device,
                        self.stop,
                        report,
                        monitor=monitor,
                        restore=restore,
                        low=low,
                        high=high,
                        curve=curve,
                    )
                if self.stop.is_set():
                    self.report_stop()
            except InterruptedError:
                self.report_stop()
            except (OSError, RuntimeError, ValueError) as error:
                self.status.emit(str(error))
            finally:
                self.done.emit()

        self.worker = Thread(target=work)
        self.worker.start()

    def report_stop(self):
        started = self.stop_requested_at
        if started is None:
            self.status.emit("Stopped.")
        else:
            self.status.emit(f"Stopped in {round((time.monotonic() - started) * 1000)} ms.")

    def closeEvent(self, event):
        if self.worker and self.worker.is_alive():
            self.request_stop()
            self.details.setText("Stopping… Close again when finished.")
            event.ignore()
            return
        super().closeEvent(event)


def main():
    if not sys.platform.startswith("linux"):
        raise SystemExit("This preview requires Linux.")
    app = QApplication(sys.argv)
    window = LinuxWindow()
    window.show()
    return app.exec()
