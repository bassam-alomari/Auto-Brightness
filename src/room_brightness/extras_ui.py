"""First-run guidance, metering region, portable settings, profiles and update UI."""

import base64
import copy
import json
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, QRectF
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QStackedWidget,
    QWidget,
    QFileDialog,
    QMessageBox,
    QInputDialog,
)
from .extras import export_preferences, import_preferences


class RegionPicker(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.engine = window.engine
        self.region = window.engine.preferences["meter_region"][:]
        self.anchor = None
        self.setMinimumSize(400, 300)

    def normalized(self, point):
        return [max(0, min(1, point.x() / self.width())), max(0, min(1, point.y() / self.height()))]

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.anchor = self.normalized(event.position())

    def mouseMoveEvent(self, event):
        if self.anchor is None or not event.buttons() & Qt.MouseButton.LeftButton:
            return
        x, y = self.normalized(event.position())
        a, b = self.anchor
        if abs(x - a) >= 0.1 and abs(y - b) >= 0.1:
            self.region = [min(x, a), min(y, b), max(x, a), max(y, b)]
            self.update()

    def paintEvent(self, event):
        from PySide6.QtGui import QPixmap

        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#172332"))
        preview = (self.window.engine.last_meter or {}).get("preview")
        if preview:
            image = QPixmap()
            image.loadFromData(base64.b64decode(preview), "PNG")
            p.drawPixmap(self.rect(), image)
        else:
            p.setPen(QColor("white"))
            p.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                self.window.tr(
                    "Capture a preview, then drag a rectangle", "التقط معاينة ثم اسحب مستطيلًا"
                ),
            )
        x0, y0, x1, y1 = self.region
        rect = QRectF(
            x0 * self.width(),
            y0 * self.height(),
            (x1 - x0) * self.width(),
            (y1 - y0) * self.height(),
        )
        p.setPen(QPen(QColor("#65b7ff"), 3))
        p.drawRect(rect)


class RegionDialog(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.setLayoutDirection(window.layoutDirection())
        self.window = window
        self.engine = window.engine
        self.setWindowTitle(window.tr("Metering region", "منطقة قياس الضوء"))
        self.setStyleSheet("QDialog {background:#20242b;}")
        layout = QVBoxLayout(self)
        layout.addWidget(
            window.label(
                window.tr(
                    "Avoid windows, faces, and bright objects. Preview stays in memory.",
                    "تجنّب النوافذ والوجوه والأجسام الساطعة. تبقى المعاينة في الذاكرة.",
                )
            )
        )
        self.previous_preview = window.engine.preview_enabled
        self.picker = RegionPicker(window)
        layout.addWidget(self.picker)
        buttons = QHBoxLayout()
        for en, ar, action in [
            ("Capture preview", "التقاط معاينة", self.capture),
            ("Whole image", "الصورة كاملة", self.reset),
            ("Save", "حفظ", self.save),
        ]:
            button = QPushButton(window.tr(en, ar))
            button.clicked.connect(action)
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.picker.update)
        self.timer.start(300)
        self.finished.connect(lambda _: self.timer.stop())
        self.finished.connect(self.restore_preview)

    def restore_preview(self, result):
        self.window.engine.preview_enabled = self.previous_preview
        if not self.previous_preview:
            if self.window.engine.last_meter:
                self.window.engine.last_meter.pop("preview", None)
            if hasattr(self.window, "preview"):
                self.window.preview.clear()
                self.window.preview.setVisible(False)

    def capture(self):
        self.window.engine.preview_enabled = True
        self.window.check_now()

    def reset(self):
        self.picker.region = [0, 0, 1, 1]
        self.picker.update()

    def save(self):
        e = self.window.engine
        if e.running or e.busy or e.resume_pending or e.pause_reasons:
            return
        settings = copy.deepcopy(e.preferences)
        settings["meter_region"] = self.picker.region[:]
        e.apply_preferences(settings)
        self.accept()
        self.window.build()


class SetupWizard(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.setLayoutDirection(window.layoutDirection())
        self.window = window
        self.engine = window.engine
        self.setWindowTitle(window.tr("First setup", "الإعداد الأول"))
        self.setStyleSheet("QDialog {background:#20242b;}")
        self.resize(550, 420)
        layout = QVBoxLayout(self)
        self.pages = QStackedWidget()
        layout.addWidget(self.pages)
        intro = QWidget()
        box = QVBoxLayout(intro)
        box.addWidget(
            window.label(
                window.tr("Welcome to Auto Brightness", "مرحبًا بك في الإضاءة التلقائية"), True
            )
        )
        box.addWidget(
            window.label(
                window.tr(
                    "Choose your camera and comfortable brightness limits. Camera frames stay in memory. The display test briefly changes brightness and restores it.",
                    "اختر الكاميرا وحدود السطوع المريحة لك. تبقى الصور في الذاكرة. يغيّر اختبار الشاشة السطوع قليلًا ثم يعيده.",
                )
            )
        )
        self.pages.addWidget(intro)
        camera = QWidget()
        box = QVBoxLayout(camera)
        box.addWidget(window.label(window.tr("Display", "الشاشة")))
        self.display_combo = window.combo([], 0, self.choose_display)
        box.addWidget(self.display_combo)
        displays = QPushButton(window.tr("Refresh displays", "تحديث الشاشات"))
        displays.clicked.connect(window.engine.refresh_displays)
        box.addWidget(displays)
        box.addWidget(window.label(window.tr("Choose a camera", "اختيار الكاميرا"), True))
        self.camera_combo = window.combo([], 0, self.choose_camera)
        box.addWidget(self.camera_combo)
        button = QPushButton(window.tr("Refresh cameras", "تحديث الكاميرات"))
        button.clicked.connect(window.engine.refresh_cameras)
        box.addWidget(button)
        self.pages.addWidget(camera)
        limits = QWidget()
        box = QVBoxLayout(limits)
        from .qt_ui import NoWheelSpinBox

        self.low = NoWheelSpinBox()
        self.low.setRange(0, 95)
        self.low.setValue(window.engine.low.get())
        self.low.setSuffix("%")
        self.high = NoWheelSpinBox()
        self.high.setRange(1, 100)
        self.high.setValue(window.engine.high.get())
        self.high.setSuffix("%")
        for en, ar, spin in [
            ("Minimum", "الحد الأدنى", self.low),
            ("Maximum", "الحد الأعلى", self.high),
        ]:
            spin.setAlignment(
                Qt.AlignmentFlag.AlignAbsolute
                | (
                    Qt.AlignmentFlag.AlignRight
                    if window.engine.language == "ar"
                    else Qt.AlignmentFlag.AlignLeft
                )
            )
            box.addWidget(window.label(window.tr(en, ar)))
            box.addWidget(spin)
        button = QPushButton(window.tr("Test display control", "اختبار التحكم بالشاشة"))
        button.clicked.connect(lambda: window.engine.verify(False))
        box.addWidget(button)
        self.status = window.label("")
        box.addWidget(self.status)
        self.pages.addWidget(limits)
        row = QHBoxLayout()
        layout.addLayout(row)
        self.back = QPushButton(window.tr("Back", "السابق"))
        self.back.clicked.connect(
            lambda: self.pages.setCurrentIndex(max(0, self.pages.currentIndex() - 1))
        )
        row.addWidget(self.back)
        self.next = QPushButton(window.tr("Next", "التالي"))
        self.next.clicked.connect(self.advance)
        row.addWidget(self.next)
        self.finish = QPushButton(window.tr("Finish", "إنهاء"))
        self.finish.clicked.connect(self.complete)
        row.addWidget(self.finish)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.sync)
        self.timer.start(300)
        self.finished.connect(lambda _: self.timer.stop())
        self.sync()

    def choose_display(self, index):
        e = self.window.engine
        if not e.busy and not e.running and 0 <= index < len(e.displays):
            try:
                e.select_display(e.displays[index]["id"])
            except ValueError as error:
                self.window.message_error(error)

    def choose_camera(self, index):
        e = self.window.engine
        if not e.busy and not e.running and 0 <= index < len(e.devices):
            e.choose_device(e.devices[index])

    def advance(self):
        if self.pages.currentIndex() == 1 and not self.window.engine.selected_device():
            return
        self.pages.setCurrentIndex(min(2, self.pages.currentIndex() + 1))
        self.sync()

    def sync(self):
        e = self.window.engine
        labels = [device["name"] for device in e.devices]
        if [self.camera_combo.itemText(i) for i in range(self.camera_combo.count())] != labels:
            self.camera_combo.blockSignals(True)
            self.camera_combo.clear()
            self.camera_combo.addItems(labels)
            self.camera_combo.setCurrentIndex(
                next((i for i, d in enumerate(e.devices) if d["id"] == e.camera_id), 0)
            )
            self.camera_combo.blockSignals(False)
        displays = [
            self.window.tr("Built-in display", "الشاشة الداخلية")
            if d["id"] == "internal"
            else d["name"]
            for d in e.displays
        ]
        if displays != [self.display_combo.itemText(i) for i in range(self.display_combo.count())]:
            self.display_combo.blockSignals(True)
            self.display_combo.clear()
            self.display_combo.addItems(displays)
            self.display_combo.setCurrentIndex(
                next(
                    (
                        i
                        for i, d in enumerate(e.displays)
                        if d["id"] == e.preferences["display_target"]
                    ),
                    0,
                )
            )
            self.display_combo.blockSignals(False)
        self.display_combo.setEnabled(not e.busy)
        self.camera_combo.setEnabled(not e.busy)
        self.status.setText(e.status.get())
        self.finish.setEnabled(
            self.pages.currentIndex() == 2
            and e.verified
            and not e.busy
            and self.low.value() < self.high.value()
            and bool(e.selected_device())
        )
        self.next.setEnabled(self.pages.currentIndex() < 2)
        self.back.setEnabled(self.pages.currentIndex() > 0)

    def complete(self):
        e = self.window.engine
        if not e.verified or e.busy or self.low.value() >= self.high.value():
            return
        settings = copy.deepcopy(e.preferences)
        settings.update(low=self.low.value(), high=self.high.value(), onboarding_done=True)
        e.apply_preferences(settings)
        self.accept()
        self.window.build()


class ExtrasMixin:
    def message_error(self, error):
        QMessageBox.information(
            self,
            self.tr("Settings", "الإعدادات"),
            self.tr(
                str(error),
                {
                    "Stop automatic mode before changing settings.": "أوقف الوضع التلقائي قبل تغيير الإعدادات.",
                    "No saved curve changes to undo.": "لا توجد تعديلات محفوظة للتراجع عنها.",
                    "Invalid Auto Brightness settings file.": "ملف إعدادات الإضاءة التلقائية غير صالح.",
                    "Could not save settings. Check folder permissions.": "تعذّر حفظ الإعدادات. تحقّق من صلاحيات المجلد.",
                }.get(str(error), str(error)),
            ),
        )

    def export_options(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            self.tr("Export settings", "تصدير الإعدادات"),
            "AutoBrightness-settings.json",
            "JSON (*.json)",
        )
        if not path:
            return
        try:
            self.engine.persist()
            Path(path).write_text(
                json.dumps(
                    export_preferences(self.engine.preferences), ensure_ascii=False, indent=2
                ),
                encoding="utf-8",
            )
        except (OSError, ValueError) as error:
            self.message_error(error)

    def import_options(self):
        if (
            self.engine.running
            or self.engine.busy
            or self.engine.resume_pending
            or self.engine.pause_reasons
        ):
            self.message_error(ValueError("Stop automatic mode before changing settings."))
            return
        path, _ = QFileDialog.getOpenFileName(
            self, self.tr("Import settings", "استيراد الإعدادات"), "", "JSON (*.json)"
        )
        if not path:
            return
        try:
            file = Path(path)
            if file.stat().st_size > 65536:
                raise ValueError("Settings file is too large.")
            settings = import_preferences(
                json.loads(file.read_text(encoding="utf-8")), self.engine.preferences
            )
            summary = (
                self.tr("Import these settings?", "هل تريد استيراد هذه الإعدادات؟")
                + f"\n{settings['low']}% – {settings['high']}%\n"
                + self.tr("Intervals", "فترات الفحص")
                + f": {settings['interval_ac']} / {settings['interval_battery']} s"
            )
            if (
                QMessageBox.question(self, self.tr("Import settings", "استيراد الإعدادات"), summary)
                != QMessageBox.StandardButton.Yes
            ):
                return
            self.engine.apply_preferences(settings)
            self.build()
        except (OSError, ValueError, TypeError) as error:
            self.message_error(error)

    def reset_options(self):
        from .settings import DEFAULTS
        from .extras import PORTABLE_KEYS

        if (
            self.engine.running
            or self.engine.busy
            or self.engine.resume_pending
            or self.engine.pause_reasons
        ):
            return
        if (
            QMessageBox.question(
                self,
                self.tr("Reset settings", "استعادة الإعدادات"),
                self.tr("Restore default preferences?", "هل تريد استعادة الإعدادات الافتراضية؟"),
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        settings = copy.deepcopy(self.engine.preferences)
        settings.update({key: copy.deepcopy(DEFAULTS[key]) for key in PORTABLE_KEYS})
        self.engine.apply_preferences(settings)
        self.build()

    def undo_saved_curve(self):
        try:
            self.engine.undo_curve()
            self.build()
        except ValueError as error:
            self.message_error(error)

    def choose_profile(self, index):
        if index == 0:
            return
        names = ["work", "gaming", "night"] + list(self.engine.preferences["profiles"])
        try:
            self.engine.apply_profile(names[index - 1])
            self.build()
        except ValueError as error:
            self.message_error(error)

    def save_named_profile(self):
        name, ok = QInputDialog.getText(
            self,
            self.tr("Save profile", "حفظ ملف استخدام"),
            self.tr("Profile name", "اسم ملف الاستخدام"),
        )
        if not ok:
            return
        try:
            self.engine.save_profile(name)
            self.build()
        except ValueError as error:
            self.message_error(error)

    def open_wizard(self):
        if (
            self.engine.running
            or self.engine.busy
            or self.engine.resume_pending
            or self.engine.pause_reasons
        ):
            return
        self.setup_wizard = SetupWizard(self)
        self.setup_wizard.open()

    def maybe_wizard(self):
        e = self.engine
        if (
            e.wizard_eligible
            and not e.preferences["onboarding_done"]
            and not e.running
            and not e.busy
        ):
            e.wizard_eligible = False
            self.open_wizard()

    def region_dialog(self):
        if (
            self.engine.running
            or self.engine.busy
            or self.engine.resume_pending
            or self.engine.pause_reasons
        ):
            return
        self.meter_dialog = RegionDialog(self)
        self.meter_dialog.open()

    def update_check(self):
        if self.update_pending:
            return
        from .extras import check_release
        from . import __version__
        import threading

        self.update_pending = True
        self.update_message = self.tr("Checking for updates…", "جارٍ البحث عن تحديثات…")

        def worker():
            try:
                result = check_release(__version__)
                message = (
                    self.tr(
                        "No newer published release was found.", "لم يُعثر على إصدار منشور أحدث."
                    )
                    if result is None
                    else self.tr("New release available: ", "يتوفر إصدار جديد: ")
                    + result["version"]
                )
                self.pending_update = result
            except Exception:
                message = self.tr(
                    "Could not check updates. Try again later.",
                    "تعذّر البحث عن تحديثات. حاول لاحقًا.",
                )
            self.update_message = message
            self.update_pending = False

        threading.Thread(target=worker, daemon=True).start()

    def open_update(self):
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl

        if self.pending_update:
            QDesktopServices.openUrl(QUrl(self.pending_update["url"]))

    def diagnostics_dialog(self):
        from .recovery_ui import DiagnosticDialog

        self.diagnostic_dialog = DiagnosticDialog(self)
        self.diagnostic_dialog.open()

    def backups_dialog(self):
        if self.engine.running or self.engine.busy or self.engine.resume_pending:
            return
        from .recovery_ui import BackupDialog

        self.backup_dialog = BackupDialog(self)
        self.backup_dialog.open()

    def extras_settings(self, layout):
        from .qt_ui import ToggleSwitch, NoWheelSpinBox

        e = self.engine
        layout.addWidget(self.label(self.tr("Setup and tools", "الإعداد والأدوات"), True))
        for en, ar, action in [
            ("Diagnostic report", "تقرير التشخيص", self.diagnostics_dialog),
            ("Restore a backup", "استعادة نسخة احتياطية", self.backups_dialog),
            ("First setup", "الإعداد الأول", self.open_wizard),
            ("Metering region", "منطقة قياس الضوء", self.region_dialog),
            ("Export settings", "تصدير الإعدادات", self.export_options),
            ("Import settings", "استيراد الإعدادات", self.import_options),
            ("Reset settings", "استعادة الإعدادات", self.reset_options),
            ("Undo saved curve change", "التراجع عن تعديل المنحنى", self.undo_saved_curve),
        ]:
            button = QPushButton(self.tr(en, ar))
            button.clicked.connect(action)
            layout.addWidget(button)
            if action not in (self.export_options, self.diagnostics_dialog):
                self.locked.append(button)
        layout.addWidget(self.label(self.tr("Usage profiles", "ملفات الاستخدام"), True))
        combo = self.combo(
            [
                self.tr("Choose a profile", "اختر ملف استخدام"),
                self.tr("Work", "العمل"),
                self.tr("Gaming", "الألعاب"),
                self.tr("Night", "الليل"),
            ]
            + list(e.preferences["profiles"]),
            0,
            self.choose_profile,
        )
        layout.addWidget(combo)
        self.locked.append(combo)
        save = QPushButton(self.tr("Save current profile", "حفظ ملف الاستخدام الحالي"))
        save.clicked.connect(self.save_named_profile)
        layout.addWidget(save)
        layout.addWidget(self.label(self.tr("Power saving", "توفير الطاقة"), True))
        toggle = ToggleSwitch(
            self.tr("Slow sampling when light is stable", "تقليل الفحص عندما يكون الضوء ثابتًا")
        )
        toggle.setChecked(e.preferences["adaptive_sampling"])
        toggle.toggled.connect(lambda value: self.option_change("adaptive_sampling", value))
        layout.addWidget(toggle)
        for key, en, ar in [
            ("max_interval_ac", "Maximum interval on AC", "أطول فترة فحص على الشاحن"),
            ("max_interval_battery", "Maximum interval on battery", "أطول فترة فحص على البطارية"),
        ]:
            layout.addWidget(self.label(self.tr(en, ar)))
            spin = NoWheelSpinBox()
            spin.setRange(5, 600)
            spin.setValue(e.preferences[key])
            spin.setSuffix(self.tr(" s", " ثانية"))
            spin.valueChanged.connect(lambda value, k=key: self.option_change(k, value))
            spin.setAlignment(
                Qt.AlignmentFlag.AlignAbsolute
                | (
                    Qt.AlignmentFlag.AlignRight
                    if e.language == "ar"
                    else Qt.AlignmentFlag.AlignLeft
                )
            )
            layout.addWidget(spin)
        shortcuts = ToggleSwitch(
            self.tr("Enable keyboard shortcuts", "تفعيل اختصارات لوحة المفاتيح")
        )
        shortcuts.setChecked(e.preferences["shortcuts_enabled"])
        shortcuts.toggled.connect(self.shortcuts_change)
        layout.addWidget(shortcuts)
        layout.addWidget(
            self.label(
                self.tr(
                    "Ctrl+Alt+B: start/stop · Ctrl+Alt+O: open window",
                    "Ctrl+Alt+B: تشغيل/إيقاف · Ctrl+Alt+O: فتح النافذة",
                )
            )
        )
        layout.addWidget(self.label(self.tr("Updates", "التحديثات"), True))
        button = QPushButton(self.tr("Check for updates", "البحث عن تحديثات"))
        button.clicked.connect(self.update_check)
        layout.addWidget(button)
        self.update_label = self.label(self.update_message)
        layout.addWidget(self.update_label)
        self.update_link = QPushButton(self.tr("Open release page", "فتح صفحة الإصدار"))
        self.update_link.clicked.connect(self.open_update)
        self.update_link.setEnabled(bool(self.pending_update))
        layout.addWidget(self.update_link)
