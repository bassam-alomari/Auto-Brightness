"""Reviewed one-minute trials, power curves, quick controls and issue bundles."""

import copy
import json
import zipfile
from pathlib import Path
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QPushButton,
    QFileDialog,
    QMessageBox,
    QScrollArea,
    QWidget,
    QVBoxLayout,
    QApplication,
)
from .tuning_ui import ToolDialog
from .comfort_ui import CurveEditor
from .comfort import valid_points
from .experience import problem_bundle


class PowerCurvesDialog(ToolDialog):
    def __init__(self, window):
        super().__init__(window, ("Battery and charger curves", "منحنيات البطارية والشاحن"))
        from .qt_ui import ToggleSwitch

        self.staged = copy.deepcopy(self.engine.preferences["power_curves"])
        self.mode = "ac"
        self.enabled = ToggleSwitch(
            window.tr("Use separate power curves", "استخدام منحنيين منفصلين للبطارية والشاحن")
        )
        self.enabled.setChecked(self.engine.preferences["separate_power_curves"])
        self.box.addWidget(self.enabled)
        self.text(
            "Each power source has its own full custom curve. Comfort limits and stability protection still apply. Switching source takes effect at the next reading cycle.",
            "لكل مصدر طاقة منحنى مخصص كامل. تبقى حدود السطوع وحماية الثبات سارية. يُطبق تغيير مصدر الطاقة عند دورة القراءة التالية.",
        )
        self.choice = window.combo(
            [window.tr("Charger", "الشاحن"), window.tr("Battery", "البطارية")], 0, self.switch
        )
        self.box.addWidget(self.choice)
        self.editor = CurveEditor(self.staged["ac"]["points"])
        self.box.addWidget(self.editor)
        self.button("Add point", "إضافة نقطة", self.editor.add_point)
        self.button("Remove selected point", "حذف النقطة المحددة", self.editor.remove_point)
        self.button("Save both curves", "حفظ المنحنيين", self.save)
        self.button("Cancel", "إلغاء", self.reject)

    def switch(self, index):
        self.staged[self.mode] = {"curve": "custom", "points": copy.deepcopy(self.editor.points)}
        self.mode = ("ac", "battery")[index]
        self.editor.points = copy.deepcopy(self.staged[self.mode]["points"])
        self.editor.selected = None
        self.editor.update()

    def save(self):
        self.staged[self.mode] = {"curve": "custom", "points": copy.deepcopy(self.editor.points)}
        if not all(valid_points(profile["points"]) for profile in self.staged.values()):
            return
        candidate = copy.deepcopy(self.engine.preferences)
        candidate.update(power_curves=self.staged, separate_power_curves=self.enabled.isChecked())
        self.save_candidate(candidate)


class TrialDialog(ToolDialog):
    def __init__(self, window):
        super().__init__(window, ("Try settings for one minute", "تجربة الإعدادات لمدة دقيقة"))
        from .qt_ui import NoWheelSpinBox, ToggleSwitch
        from .adaptive import CURVES

        self.text(
            "This trial opens the camera and changes screen brightness. It uses one shared curve for both power sources. Stop automatic mode first. Keep explicitly saves the trial settings; expiry, Stop or Exit restores the previous settings. Keep/revert stops automatic mode. No trial settings are written to disk until Keep.",
            "تفتح التجربة الكاميرا وتغيّر سطوع الشاشة، وتستخدم منحنى موحدًا لمصدري الطاقة. أوقف الوضع التلقائي أولًا. يحفظ «احتفاظ» إعدادات التجربة صراحةً، وتعيد نهاية الدقيقة أو الإيقاف أو الخروج الإعدادات السابقة. يوقف الاحتفاظ أو الرجوع الوضع التلقائي. لا تُكتب إعدادات التجربة على القرص قبل الاحتفاظ.",
        )
        self.low = NoWheelSpinBox()
        self.high = NoWheelSpinBox()
        for widget, value in (
            (self.low, self.engine.low.get()),
            (self.high, self.engine.high.get()),
        ):
            widget.setRange(0, 100)
            widget.setValue(value)
            widget.setSuffix("%")
            widget.setAlignment(
                Qt.AlignmentFlag.AlignAbsolute
                | (
                    Qt.AlignmentFlag.AlignRight
                    if self.engine.language == "ar"
                    else Qt.AlignmentFlag.AlignLeft
                )
            )
        self.text("Minimum brightness", "أدنى سطوع")
        self.box.addWidget(self.low)
        self.text("Maximum brightness", "أعلى سطوع")
        self.box.addWidget(self.high)
        self.keys = tuple(CURVES)
        self.choice = window.combo(
            [window.tr(v[0], v[1]) for v in CURVES.values()],
            self.keys.index(self.engine.preferences["brightness_curve"]),
            lambda _: None,
        )
        self.box.addWidget(self.choice)
        self.cover = ToggleSwitch(
            window.tr(
                "Hold brightness if the lens may be covered", "تثبيت السطوع عند احتمال تغطية العدسة"
            )
        )
        self.cover.setChecked(self.engine.preferences["cover_guard"])
        self.box.addWidget(self.cover)
        self.text(
            "A covered lens and an extremely dark room can look alike. The warning is approximate and does not identify a physical shutter.",
            "قد تتشابه العدسة المغطاة والغرفة شديدة الظلام. التنبيه تقريبي ولا يكتشف غطاءً ماديًا بشكل مؤكد.",
        )
        self.message = self.text("", "")
        self.button(
            "Apply and start one-minute trial", "تطبيق التجربة وتشغيلها لمدة دقيقة", self.start
        )
        self.button("Cancel", "إلغاء", self.reject)
        self.resize(590, 700)
        content = QWidget()
        content.setObjectName("trialContent")
        layout = QVBoxLayout(content)
        while self.box.count():
            item = self.box.takeAt(0)
            if item.widget():
                layout.addWidget(item.widget())
            else:
                layout.addItem(item)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        scroll.setStyleSheet(
            "QScrollArea {border:none;background:#20242b;} QWidget#trialContent {background:#20242b;}"
        )
        self.box.addWidget(scroll)

    def start(self):
        if self.low.value() >= self.high.value() or not self.engine.selected_device():
            self.message.setText(
                self.window.tr(
                    "Choose a camera and valid minimum/maximum.", "اختر كاميرا وحدود سطوع صحيحة."
                )
            )
            return
        candidate = copy.deepcopy(self.engine.preferences)
        candidate.update(
            low=self.low.value(),
            high=self.high.value(),
            brightness_curve=self.keys[self.choice.currentIndex()],
            cover_guard=self.cover.isChecked(),
            separate_power_curves=False,
            power_profiles=False,
        )
        try:
            self.engine.begin_trial(candidate)
        except ValueError:
            self.message.setText(
                self.window.tr(
                    "Stop automatic mode and finish any current trial first.",
                    "أوقف الوضع التلقائي وأنهِ أي تجربة حالية أولًا.",
                )
            )
            return
        self.accept()
        self.window.build()
        self.engine.start()


class QuickPanel(ToolDialog):
    def __init__(self, window):
        super().__init__(window, ("Quick controls", "التحكم السريع"))
        self.setWindowFlag(Qt.WindowType.Popup, True)
        self.resize(370, 380)
        self.metric_label = self.text("", "")
        self.start_button = self.button(
            "Start automatic", "تشغيل الوضع التلقائي", self.engine.start
        )
        self.stop_button = self.button("Stop", "إيقاف", self.engine.stop)
        self.pause = window.combo(
            [window.tr("Pause…", "إيقاف مؤقت…"), "15", "30", "60"], 0, self.pause_for
        )
        self.box.addWidget(self.pause)
        self.resume_button = self.button("Resume now", "استئناف الآن", self.engine.resume_now)
        self.profile = window.combo(
            [
                window.tr("Choose profile", "اختر ملف استخدام"),
                window.tr("Work", "العمل"),
                window.tr("Gaming", "الألعاب"),
                window.tr("Night", "الليل"),
            ]
            + list(self.engine.preferences["profiles"]),
            0,
            self.profile_selected,
        )
        self.box.addWidget(self.profile)
        self.button("Open main window", "فتح النافذة الرئيسية", self.main)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(400)
        self.finished.connect(self.timer.stop)
        self.refresh()

    def pause_for(self, index):
        if index:
            self.engine.pause_for((15, 30, 60)[index - 1])
            self.pause.setCurrentIndex(0)

    def profile_selected(self, index):
        if not index:
            return
        keys = ["work", "gaming", "night", *self.engine.preferences["profiles"]]
        try:
            self.engine.apply_profile(keys[index - 1])
        except ValueError:
            pass
        self.profile.setCurrentIndex(0)

    def refresh(self):
        self.metric_label.setText(
            self.engine.display_value.get() + "%\n" + self.window.brightness_reason()
        )
        self.start_button.setEnabled(
            not self.engine.running
            and not self.engine.busy
            and not self.engine.pause_reasons
            and self.engine.selected_device() is not None
        )
        self.stop_button.setEnabled(
            self.engine.running or self.engine.busy or self.engine.resume_pending
        )
        self.pause.setEnabled(self.engine.running or "timed" in self.engine.pause_reasons)
        self.resume_button.setEnabled("timed" in self.engine.pause_reasons)
        self.profile.setEnabled(
            not self.engine.running
            and not self.engine.busy
            and not self.engine.resume_pending
            and self.engine.trial_original is None
        )

    def main(self):
        self.reject()
        self.window.restore_window()


class IssueDialog(ToolDialog):
    def __init__(self, window):
        super().__init__(window, ("Prepare problem report", "تجهيز تقرير مشكلة"))
        from . import __version__
        from PySide6.QtWidgets import QPlainTextEdit

        self.document = problem_bundle(self.engine, __version__)
        self.text(
            "Review before exporting. Includes version, anonymous device status, recent readings and error categories. No photos, device names, paths, raw errors or automatic upload. Attach the ZIP manually to a GitHub issue if you choose.",
            "عاين التقرير قبل تصديره. يتضمن الإصدار وحالة أجهزة دون أسماء وقراءات حديثة وفئات الأخطاء. لا يتضمن صورًا أو أسماء أجهزة أو مسارات أو أخطاء خامًا، ولا يُرسل تلقائيًا. يمكنك إرفاق الملف يدويًا بمشكلة على GitHub.",
        )
        self.preview = QPlainTextEdit(json.dumps(self.document, ensure_ascii=False, indent=2))
        self.preview.setReadOnly(True)
        self.preview.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.box.addWidget(self.preview)
        self.button("Export reviewed problem bundle", "تصدير حزمة المشكلة بعد المعاينة", self.save)
        self.button("Close", "إغلاق", self.reject)

    def save(self):
        file, _ = QFileDialog.getSaveFileName(
            self, self.windowTitle(), "AutoBrightness-problem.zip", "ZIP (*.zip)"
        )
        if not file:
            return
        try:
            with zipfile.ZipFile(file, "w", zipfile.ZIP_DEFLATED) as bundle:
                bundle.writestr("diagnostics.json", self.preview.toPlainText())
                bundle.writestr(
                    "ISSUE.md",
                    "# Auto Brightness problem\n\nVersion: "
                    + self.document["version"]
                    + "\n\nWhat happened:\n\nExpected behavior:\n\nSteps to reproduce:\n\nReview diagnostics.json before attaching.\n",
                )
        except OSError as error:
            self.window.message_error(error)


class ExperienceMixin:
    def experience_settings(self, layout):
        from .qt_ui import ToggleSwitch

        layout.addWidget(self.label(self.tr("Comfort and safeguards", "الراحة والحماية"), True))
        guard = ToggleSwitch(
            self.tr(
                "Hold brightness if the lens may be covered", "تثبيت السطوع عند احتمال تغطية العدسة"
            )
        )
        guard.setChecked(self.engine.preferences["cover_guard"])

        def set_guard(value):
            candidate = copy.deepcopy(self.engine.preferences)
            candidate["cover_guard"] = value
            try:
                self.engine.apply_preferences(candidate)
            except ValueError:
                self.build()

        guard.toggled.connect(set_guard)
        layout.addWidget(guard)
        self.locked.append(guard)
        for kind, en, ar in [
            (PowerCurvesDialog, "Battery and charger curves", "منحنيات البطارية والشاحن"),
            (TrialDialog, "Try settings for one minute", "تجربة الإعدادات لمدة دقيقة"),
            (IssueDialog, "Prepare problem report", "تجهيز تقرير مشكلة"),
        ]:
            button = QPushButton(self.tr(en, ar))
            button.clicked.connect(lambda checked=False, cls=kind: self.open_experience(cls))
            layout.addWidget(button)
        button = QPushButton(
            self.tr("Return to previous installed version", "العودة إلى الإصدار المثبّت السابق")
        )
        button.clicked.connect(self.rollback_installed)
        layout.addWidget(button)

    def open_experience(self, kind):
        self.experience_dialog = kind(self)
        self.experience_dialog.open()

    def quick_panel(self):
        signature = (self.engine.language, self.engine.preferences["arabic_dialect"])
        if not hasattr(self, "quick_window") or getattr(self, "quick_signature", None) != signature:
            if hasattr(self, "quick_window"):
                self.quick_window.reject()
                self.quick_window.deleteLater()
            self.quick_window = QuickPanel(self)
            self.quick_signature = signature
        self.quick_window.refresh()
        self.quick_window.timer.start(400)
        self.quick_window.show()
        anchor = self.tray.geometry()
        screen = QApplication.screenAt(anchor.center()) if not anchor.isEmpty() else self.screen()
        area = (screen or self.screen()).availableGeometry()
        x = (
            anchor.right() - self.quick_window.width()
            if not anchor.isEmpty()
            else area.right() - self.quick_window.width()
        )
        y = (
            anchor.top() - self.quick_window.height()
            if not anchor.isEmpty()
            else area.bottom() - self.quick_window.height()
        )
        self.quick_window.move(
            max(area.left(), min(x, area.right() - self.quick_window.width())),
            max(area.top(), min(y, area.bottom() - self.quick_window.height())),
        )

    def rollback_installed(self):
        import sys
        import subprocess
        import os

        root = Path(sys.executable).parent
        previous = root.with_name(root.name + "-previous")
        expected = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "AutoBrightness"
        if (
            not getattr(sys, "frozen", False)
            or root.resolve() != expected.resolve()
            or not (root / "Rollback.ps1").is_file()
            or not (root / ".autobrightness-install").is_file()
            or not (previous / ".autobrightness-install").is_file()
        ):
            QMessageBox.information(
                self,
                self.engine.t("app"),
                self.tr(
                    "Rollback becomes available after updating an installed copy.",
                    "يتاح الرجوع بعد تحديث نسخة مثبّتة.",
                ),
            )
            return
        if (
            self.engine.running
            or self.engine.busy
            or self.engine.resume_pending
            or self.engine.trial_original is not None
        ):
            QMessageBox.information(
                self,
                self.engine.t("app"),
                self.tr("Stop automatic mode first.", "أوقف الوضع التلقائي أولًا."),
            )
            return
        if (
            QMessageBox.question(
                self,
                self.engine.t("app"),
                self.tr(
                    "Close and restore the previous installed version? Your settings stay in place.",
                    "هل تريد الإغلاق واستعادة الإصدار المثبّت السابق؟ تبقى إعداداتك محفوظة.",
                ),
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        try:
            subprocess.Popen(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(root / "Rollback.ps1"),
                    "-WaitPid",
                    str(os.getpid()),
                ],
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError as error:
            self.message_error(error)
            return
        self.exit_app()
