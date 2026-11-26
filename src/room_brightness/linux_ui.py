"""Desktop controls for the Linux preview."""

from pathlib import Path
import sys
from threading import Event, Thread

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .linux_control import Backlight, DdcDisplay, capture, run_session


class LinuxWindow(QWidget):
    status = Signal(str)
    done = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Auto Brightness · Linux preview")
        self.resize(480, 350)
        self.stop = Event()
        self.worker = None
        layout = QVBoxLayout(self)
        self.camera = QComboBox()
        self.display = QComboBox()
        cameras = sorted(Path("/dev/v4l/by-id").glob("*")) or sorted(
            Path("/dev").glob("video[0-9]*")
        )
        self.camera.addItems([str(path) for path in cameras])
        self.display.addItems(
            [str(path) for path in sorted(Path("/sys/class/backlight").glob("*"))]
        )
        self.display.addItem("External monitor (DDC/CI)", "ddc")
        self.edid = QLineEdit()
        self.edid.setPlaceholderText("External monitor EDID (256 hex characters)")
        self.monitor = QCheckBox("Monitor only (no brightness changes)")
        self.monitor.setChecked(True)
        self.restore = QCheckBox("Restore brightness when stopped")
        self.restore.setChecked(True)
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
            self.monitor,
            self.restore,
            self.check,
            self.start,
            self.stop_button,
            self.details,
        ):
            layout.addWidget(control)
        self.check.clicked.connect(lambda: self.launch(check=True))
        self.start.clicked.connect(lambda: self.launch(check=False))
        self.stop_button.clicked.connect(self.stop.set)
        self.status.connect(self.details.setText)
        self.done.connect(lambda: self.set_busy(False))
        self.set_busy(False)

    def set_busy(self, busy):
        for control in (
            self.camera,
            self.display,
            self.edid,
            self.monitor,
            self.restore,
            self.start,
            self.check,
        ):
            control.setEnabled(not busy)
        self.stop_button.setEnabled(busy)

    def launch(self, check):
        if self.worker and self.worker.is_alive():
            return
        camera = self.camera.currentText()
        if not camera:
            self.details.setText("No camera is listed. Connect one and reopen the preview.")
            return
        target = self.display.currentText()
        edid = self.edid.text().strip() if self.display.currentData() == "ddc" else ""
        external = self.display.currentData() == "ddc"
        monitor, restore = self.monitor.isChecked(), self.restore.isChecked()
        self.stop.clear()
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
                        )

                    run_session(camera, device, self.stop, report, monitor=monitor, restore=restore)
                if self.stop.is_set():
                    self.status.emit("Stopped.")
            except InterruptedError:
                self.status.emit("Stopped.")
            except (OSError, RuntimeError, ValueError) as error:
                self.status.emit(str(error))
            finally:
                self.done.emit()

        self.worker = Thread(target=work)
        self.worker.start()

    def closeEvent(self, event):
        if self.worker and self.worker.is_alive():
            self.stop.set()
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
