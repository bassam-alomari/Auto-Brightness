"""User-controlled session features and update download/install interface."""

import copy
from PySide6.QtCore import QTimer, QTime, Qt
from PySide6.QtWidgets import (
    QPlainTextEdit,
    QTimeEdit,
    QProgressBar,
    QScrollArea,
    QWidget,
    QVBoxLayout,
    QLabel,
    QAbstractButton,
    QComboBox,
    QSpinBox,
    QSlider,
)
from .tuning_ui import ToolDialog


class QuietTimeEdit(QTimeEdit):
    def wheelEvent(self, event):
        event.ignore()


def accessible_widgets(widget):
    """Give standard Qt controls names, buddies and keyboard focus without stealing focus."""
    previous = None
    for child in widget.children():
        if isinstance(child, QLabel) and child.text().strip():
            previous = child
        elif isinstance(child, QAbstractButton):
            if not child.accessibleName():
                child.setAccessibleName(child.text())
        elif isinstance(child, (QComboBox, QSpinBox, QSlider, QTimeEdit, QPlainTextEdit)):
            if not child.accessibleName():
                child.setAccessibleName(
                    previous.text() if previous else child.toolTip() or "Control"
                )
            child.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            if previous is not None:
                previous.setBuddy(child)
        if hasattr(child, "children"):
            accessible_widgets(child)


class SessionDialog(ToolDialog):
    def __init__(self, window):
        super().__init__(window, ("Session and updates", "الجلسة والتحديثات"))
        from .qt_ui import ToggleSwitch
        from . import __version__

        self.resize(640, 820)
        self.client = self.engine.update_client
        self.text("Installed version: " + __version__, "الإصدار الحالي: " + __version__)
        self.flags = {}
        for key, en, ar in [
            (
                "resume_automatic",
                "Remember automatic mode and start the camera after sign-in if previously running",
                "تذكّر الوضع التلقائي وتشغيل الكاميرا بعد تسجيل الدخول إذا كان يعمل سابقًا",
            ),
            ("reduce_motion", "Reduce switch animations", "تقليل حركة مفاتيح الخيارات"),
            (
                "update_checks",
                "Check on opening and daily (connects to GitHub)",
                "البحث عن تحديثات عند الفتح ويوميًا (اتصال بـ GitHub)",
            ),
            (
                "auto_download_updates",
                "Download verified updates automatically; never install automatically",
                "تنزيل التحديثات المتحقق منها تلقائيًا؛ دون تثبيت تلقائي",
            ),
        ]:
            check = ToggleSwitch(window.tr(en, ar))
            check.setChecked(self.engine.preferences[key])
            self.flags[key] = check
            self.box.addWidget(check)
        self.button("Save these options", "حفظ هذه الخيارات", self.save_options)
        self.button("Undo last settings change", "التراجع عن آخر تغيير في الإعدادات", self.undo)
        self.time = QuietTimeEdit(QTime.currentTime().addSecs(3600))
        self.time.setDisplayFormat("HH:mm")
        self.time.setAccessibleName(window.tr("Pause until local time", "إيقاف حتى الوقت المحلي"))
        self.box.addWidget(self.time)
        self.button(
            "Pause until this time (next 24 hours)",
            "إيقاف حتى هذا الوقت (خلال 24 ساعة)",
            lambda: self.pause(False),
        )
        self.button(
            "Pause until charger is connected", "إيقاف حتى توصيل الشاحن", lambda: self.pause(True)
        )
        self.button("Stop automatic mode", "إيقاف الوضع التلقائي", self.engine.stop)
        self.message = self.text("", "")
        self.notes = QPlainTextEdit()
        self.notes.setReadOnly(True)
        self.notes.setMaximumHeight(100)
        self.notes.setAccessibleName(window.tr("Release notes", "تغييرات الإصدار"))
        self.box.addWidget(self.notes)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setAccessibleName(window.tr("Update download progress", "تقدّم تنزيل التحديث"))
        self.box.addWidget(self.progress)
        self.check_button = self.button("Check now", "التحقق الآن", self.check)
        self.download_button = self.button("Download update", "تنزيل التحديث", self.client.download)
        self.cancel_button = self.button("Cancel download", "إلغاء التنزيل", self.client.cancel.set)
        self.install_button = self.button(
            "Install and restart", "تثبيت وإعادة التشغيل", self.install
        )
        self.button("Close", "إغلاق", self.reject)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(400)
        self.finished.connect(self.timer.stop)
        content = QWidget()
        content.setObjectName("sessionContent")
        body = QVBoxLayout(content)
        while self.box.count():
            item = self.box.takeAt(0)
            if item.widget():
                body.addWidget(item.widget())
            else:
                body.addItem(item)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        scroll.setStyleSheet(
            "QScrollArea {border:none;background:#20242b;} QWidget#sessionContent {background:#20242b;}"
        )
        self.box.addWidget(scroll)
        accessible_widgets(self)
        self.refresh()

    def save_options(self):
        candidate = copy.deepcopy(self.engine.preferences)
        candidate.update({key: check.isChecked() for key, check in self.flags.items()})
        if self.save_candidate(candidate):
            return

    def undo(self):
        try:
            changed = self.engine.undo_options()
        except ValueError:
            changed = False
        if changed:
            self.accept()
            self.window.build()
        else:
            self.message.setText(
                self.window.tr(
                    "No change to undo, or stop automatic mode first.",
                    "لا يوجد تغيير للتراجع عنه، أو يجب إيقاف الوضع التلقائي أولًا.",
                )
            )

    def pause(self, charger):
        if charger:
            self.engine.pause_until_charger()
        else:
            self.engine.pause_until(self.time.time())
        self.accept()

    def check(self):
        from . import __version__

        self.client.check(__version__, False)

    def refresh(self):
        messages = {
            "idle": ("Ready to check.", "جاهز للتحقق."),
            "checking": ("Checking for updates…", "جارٍ البحث عن تحديثات…"),
            "current": ("No newer stable release was found.", "لم يُعثر على إصدار مستقر أحدث."),
            "available": ("A newer release is available.", "يتوفر إصدار أحدث."),
            "check_error": (
                "Could not check updates; try later.",
                "تعذّر التحقق من التحديثات؛ حاول لاحقًا.",
            ),
            "downloading": ("Downloading…", "جارٍ التنزيل…"),
            "ready": (
                "Download verified; ready to install.",
                "تم التحقق من التنزيل؛ جاهز للتثبيت.",
            ),
            "download_error": (
                "Download failed verification or could not finish. Your current version is unchanged.",
                "فشل التحقق أو لم يكتمل التنزيل. نسختك الحالية لم تتغير.",
            ),
            "cancelled": ("Download cancelled.", "أُلغي التنزيل."),
        }
        message = self.window.tr(*messages.get(self.client.state, messages["idle"]))
        release = self.client.release
        if release:
            message += " " + release["version"]
            if not release.get("asset"):
                message += " " + self.window.tr(
                    "A Windows installer with a SHA-256 digest has not been published.",
                    "لم يُنشر مثبّت ويندوز مع بصمة SHA-256.",
                )
            notes = release.get("notes", "")
            if self.notes.toPlainText() != notes:
                self.notes.setPlainText(notes)
        self.message.setText(message)
        self.notes.setVisible(bool(release))
        self.progress.setVisible(self.client.state in ("downloading", "ready"))
        self.progress.setValue(self.client.progress)
        self.check_button.setEnabled(not self.client.busy)
        self.download_button.setEnabled(
            not self.client.busy and bool(release and release.get("asset"))
        )
        self.cancel_button.setEnabled(self.client.state == "downloading")
        self.install_button.setEnabled(
            not self.client.busy and self.client.state == "ready" and not self.engine.busy
        )

    def install(self):
        if (
            self.engine.busy
            or self.engine.running
            or self.engine.resume_pending
            or self.engine.pause_reasons
        ):
            self.message.setText(
                self.window.tr(
                    "Stop automatic mode and wait for work to finish before installing.",
                    "أوقف الوضع التلقائي وانتظر انتهاء العمليات قبل التثبيت.",
                )
            )
            return
        try:
            self.client.launch()
        except (OSError, ValueError):
            self.client.state = "download_error"
            self.refresh()
            return
        self.accept()
        self.window.exit_app()


class SessionMixin:
    def session_dialog(self):
        self.session_window = SessionDialog(self)
        self.session_window.open()
