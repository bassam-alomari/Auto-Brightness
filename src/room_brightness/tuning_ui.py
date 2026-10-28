"""Explicit calibration, curve comparison, compatibility and resource tools."""

import copy
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen, QPainterPath
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QPushButton,
    QLabel,
    QPlainTextEdit,
    QWidget,
    QMessageBox,
)
from .adaptive import image_target
from .comfort import target
from .tuning import calibrated_points, app_names


class ToolDialog(QDialog):
    def __init__(self, window, title):
        super().__init__(window)
        self.window = window
        self.engine = window.engine
        self.setWindowTitle(window.tr(*title))
        self.setLayoutDirection(window.layoutDirection())
        self.setStyleSheet(
            "QDialog {background:#20242b;} QLabel,QCheckBox {color:#f5f5f7; background:transparent; font-size:14px;} QPushButton {padding:10px; color:white; background:#19364d; border-radius:12px;} QPlainTextEdit {color:white; background:#19364d;}"
        )
        self.resize(590, 580)
        self.box = QVBoxLayout(self)

    def text(self, en, ar):
        label = QLabel(self.window.tr(en, ar))
        label.setWordWrap(True)
        label.setAlignment(
            Qt.AlignmentFlag.AlignAbsolute
            | (
                Qt.AlignmentFlag.AlignRight
                if self.engine.language == "ar"
                else Qt.AlignmentFlag.AlignLeft
            )
        )
        self.box.addWidget(label)
        return label

    def button(self, en, ar, callback):
        button = QPushButton(self.window.tr(en, ar))
        button.clicked.connect(callback)
        self.box.addWidget(button)
        return button

    def save_candidate(self, candidate):
        try:
            self.engine.apply_preferences(candidate)
        except ValueError:
            QMessageBox.information(
                self,
                self.windowTitle(),
                self.window.tr(
                    "Stop automatic mode and wait for current work; check folder permissions if saving fails.",
                    "أوقف الوضع التلقائي وانتظر انتهاء العملية الحالية. تحقق من أذونات المجلد إذا تعذّر الحفظ.",
                ),
            )
            return False
        self.accept()
        self.window.build()
        return True


class ComparePlot(QWidget):
    def __init__(self, dialog):
        super().__init__()
        self.dialog = dialog
        self.setMinimumHeight(160)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor("#142333"))
        end = self.dialog.domain()
        for proposed, color in ((False, "#e3bf65"), (True, "#68b9ff")):
            path = QPainterPath()
            for i in range(256):
                level = i / 255 * end
                value = self.dialog.mapped(level, proposed)
                x, y = (
                    10 + (self.width() - 20) * i / 255,
                    self.height() - 10 - (self.height() - 20) * value / 100,
                )
                path.moveTo(x, y) if i == 0 else path.lineTo(x, y)
            p.setPen(QPen(QColor(color), 2))
            p.drawPath(path)


class CompareDialog(ToolDialog):
    def __init__(self, window, proposed=None):
        super().__init__(window, ("Compare curves", "مقارنة المنحنيات"))
        from .qt_ui import GlassSlider

        self.original = copy.deepcopy(self.engine.preferences)
        self.engine.refresh_power()
        self.power_mode = self.engine.power_mode
        from .experience import effective_curve

        active = effective_curve(self.original, self.power_mode)
        self.original.update(
            brightness_curve=active["curve"], custom_points=copy.deepcopy(active["points"])
        )
        self.candidate = copy.deepcopy(self.original)
        self.text(
            "Current: yellow · Proposed: blue. Simulation only; no brightness or camera changes.",
            "الحالي: أصفر · المقترح: أزرق. محاكاة فقط؛ لا تتغير إضاءة الشاشة ولا تُشغّل الكاميرا.",
        )
        if proposed is not None:
            self.candidate.update(custom_points=copy.deepcopy(proposed), brightness_curve="custom")
        else:
            from .adaptive import CURVES

            self.keys = tuple(CURVES)
            self.choice = window.combo(
                [window.tr(v[0], v[1]) for v in CURVES.values()],
                self.keys.index(self.original["brightness_curve"]),
                self.choose,
            )
            self.box.addWidget(self.choice)
        if self.original["separate_power_curves"]:
            self.text(
                "Comparison/saving applies to the power source selected when opened: "
                + self.power_mode,
                "تنطبق المقارنة والحفظ على مصدر الطاقة عند فتح النافذة: "
                + ("الشاحن" if self.power_mode == "ac" else "البطارية"),
            )
        self.plot = ComparePlot(self)
        self.box.addWidget(self.plot)
        self.reading = GlassSlider(Qt.Orientation.Horizontal)
        self.reading.setRange(0, 255)
        self.reading.setValue(20)
        self.box.addWidget(self.reading)
        self.values = self.text("", "")
        self.reading.valueChanged.connect(self.refresh)
        self.text(
            "Both targets respect your configured comfort limits; automatic stability rules apply separately.",
            "يراعي الهدفان حدود السطوع المريح المحددة؛ وتُطبَّق قواعد الثبات بشكل منفصل عند التشغيل.",
        )
        self.button(
            "Save proposed curve",
            "حفظ المنحنى المقترح",
            self.save_comparison,
        )
        self.button("Cancel", "إلغاء", self.reject)
        self.refresh()

    def save_comparison(self):
        if not self.engine.preferences["separate_power_curves"]:
            return self.save_candidate(self.candidate)
        candidate = copy.deepcopy(self.engine.preferences)
        candidate["power_curves"][self.power_mode] = {
            "curve": self.candidate["brightness_curve"],
            "points": copy.deepcopy(self.candidate["custom_points"]),
        }
        return self.save_candidate(candidate)

    def choose(self, index):
        self.candidate["brightness_curve"] = self.keys[index]
        self.refresh()

    def mapped(self, level, proposed):
        pref = self.candidate if proposed else self.original
        low, high = pref["low"], pref["high"]
        return (
            target(level, low, high, pref["custom_points"])
            if pref["brightness_curve"] == "custom"
            else image_target(level, low, high, pref["brightness_curve"])
        )

    def domain(self):
        from .adaptive import CURVES

        return max(
            40,
            self.candidate["custom_points"][-1][0]
            if self.candidate["brightness_curve"] == "custom"
            else CURVES[self.candidate["brightness_curve"]][2][-1][0],
            self.original["custom_points"][-1][0]
            if self.original["brightness_curve"] == "custom"
            else 40,
        )

    def refresh(self):
        level = self.reading.value()
        self.values.setText(
            self.window.tr(
                "Image: {level}/255 · Current: {old}% · Proposed: {new}%",
                "قراءة الصورة: {level}/255 · الحالي: {old}% · المقترح: {new}%",
            ).format(level=level, old=self.mapped(level, False), new=self.mapped(level, True))
        )
        self.plot.update()


class CalibrationDialog(ToolDialog):
    def __init__(self, window):
        super().__init__(window, ("Guided calibration", "المعايرة الموجّهة"))
        from .qt_ui import NoWheelSpinBox

        self.rows = []
        self.reading = None
        self.text(
            "Arrange dim, medium, then bright room lighting. Capture each reading and choose a comfortable brightness. This tool does not adjust the screen; use Windows brightness to find your preference. Keep camera position and metering options unchanged.",
            "جهّز إضاءة خافتة، ثم متوسطة، ثم قوية. التقط كل قراءة واختر السطوع المريح. لا تغيّر هذه الأداة سطوع الشاشة؛ استخدم سطوع ويندوز لتحديد تفضيلك. حافظ على موضع الكاميرا وخيارات القياس نفسها.",
        )
        self.step = self.text("", "")
        self.input = NoWheelSpinBox()
        self.input.setRange(0, 100)
        self.input.setSuffix("%")
        self.input.setValue(30)
        self.input.setAlignment(
            Qt.AlignmentFlag.AlignAbsolute
            | (
                Qt.AlignmentFlag.AlignRight
                if self.engine.language == "ar"
                else Qt.AlignmentFlag.AlignLeft
            )
        )
        self.box.addWidget(self.input)
        self.capture_button = self.button(
            "Capture this lighting", "التقاط قراءة هذه الإضاءة", self.capture
        )
        self.add_button = self.button(
            "Keep reading and continue", "اعتماد القراءة والمتابعة", self.keep
        )
        self.feedback = self.text("", "")
        self.button("Cancel", "إلغاء", self.reject)
        self.refresh()

    def refresh(self):
        names = [("Dim", "خافتة"), ("Medium", "متوسطة"), ("Bright", "قوية")]
        self.step.setText(
            self.window.tr("Step {n}/3: {name}", "الخطوة {n}/3: إضاءة {name}").format(
                n=len(self.rows) + 1, name=self.window.tr(*names[min(2, len(self.rows))])
            )
        )
        self.add_button.setEnabled(self.reading is not None)

    def capture(self):
        from .camera import sample

        e = self.engine
        if e.busy or e.running or e.resume_pending or e.pause_reasons or not e.selected_device():
            self.feedback.setText(
                self.window.tr(
                    "Stop automatic mode, wait for current work and select a camera.",
                    "أوقف الوضع التلقائي وانتظر انتهاء العملية واختر كاميرا.",
                )
            )
            return
        self.reading = None
        self.refresh()
        self.capture_button.setEnabled(False)
        e.cancel.clear()
        region = e.preferences["meter_region"][:]
        protection = e.preferences["spatial_protection"]

        def done(reading):
            if not self.isVisible():
                return
            self.capture_button.setEnabled(True)
            if reading is None:
                self.feedback.setText(
                    self.window.tr(
                        "Camera check failed. Close camera apps, check Windows permissions and retry.",
                        "تعذّرت قراءة الكاميرا. أغلق تطبيقات التصوير وتحقق من أذونات ويندوز ثم أعد المحاولة.",
                    )
                )
                return
            e.performance.capture(reading)
            if reading.get("confidence", 0) < 0.35:
                self.feedback.setText(
                    self.window.tr(
                        "Reading unstable; hold still and try again.",
                        "القراءة غير مستقرة؛ ثبّت الكاميرا وأعد المحاولة.",
                    )
                )
                return
            self.reading = reading["level"]
            self.feedback.setText(
                self.window.tr("Image reading: {level}/255", "قراءة الصورة: {level}/255").format(
                    level=round(self.reading, 1)
                )
            )
            self.refresh()

        index = e.selected_device()["index"]

        def capture_reading():
            try:
                return sample(index, e.cancel, region=region, protection=protection)
            except Exception:
                return None

        e.work(capture_reading, done, "calibration")

    def reject(self):
        if self.engine.busy and self.engine.operation == "calibration":
            self.engine.cancel.set()
            return
        super().reject()

    def keep(self):
        if self.reading is None:
            return
        proposed = self.rows + [[self.reading, self.input.value()]]
        if not 12 < self.reading < 254 or (
            self.rows
            and (self.reading - self.rows[-1][0] < 1 or self.input.value() < self.rows[-1][1])
        ):
            self.feedback.setText(
                self.window.tr(
                    "Use a higher light reading and nondecreasing brightness; readings must be between 12 and 254.",
                    "زد إضاءة الغرفة واختر سطوعًا لا يقل عن السابق؛ يجب أن تكون القراءة بين 12 و254.",
                )
            )
            return
        self.rows = proposed
        self.reading = None
        if len(self.rows) == 3:
            points = calibrated_points(self.rows)
            self.comparison = CompareDialog(self.window, points)
            self.comparison.open()
            self.accept()
            return
        self.input.setValue(min(100, self.input.value() + 25))
        self.feedback.setText("")
        self.refresh()


class TuningDialog(ToolDialog):
    def __init__(self, window):
        super().__init__(window, ("Measurement and response", "القياس والاستجابة"))
        from .qt_ui import ToggleSwitch

        self.flags = {}
        for key, en, ar in [
            (
                "directional_response",
                "Brighten quickly (1s), dim slowly (8s)",
                "رفع السطوع سريعًا (ثانية) وخفضه ببطء (8 ثوانٍ)",
            ),
            (
                "spatial_protection",
                "Ignore centre and isolated extreme light patches",
                "تجاهل وسط الصورة وبقع الضوء المتطرفة المنفردة",
            ),
            (
                "pause_apps_enabled",
                "Pause while a listed app is in the foreground",
                "إيقاف مؤقت عندما يكون أحد التطبيقات التالية في المقدمة",
            ),
        ]:
            check = ToggleSwitch(window.tr(en, ar))
            check.setChecked(self.engine.preferences[key])
            self.flags[key] = check
            self.box.addWidget(check)
        self.text(
            "Spatial protection is a heuristic, not face recognition. It can also exclude real room light. Use the metering-region preview: darkened areas are ignored. Recalibrate if you change this option.",
            "الحماية المكانية تقدير تقريبي وليست تعرّفًا على الوجوه، وقد تستبعد ضوءًا حقيقيًا. استخدم معاينة منطقة القياس؛ المناطق المعتمة مستبعدة. أعد المعايرة عند تغيير الخيار.",
        )
        self.text(
            "Executable names only, one per line, e.g. vlc.exe. No window titles or app-use history are stored. Unknown foreground apps keep the current pause until a known foreground can be checked.",
            "أسماء ملفات التشغيل فقط، كل اسم في سطر، مثل vlc.exe. لا تُحفظ عناوين النوافذ أو سجلات استخدام التطبيقات. عند تعذّر تحديد التطبيق الأمامي يستمر الإيقاف الحالي حتى تنجح القراءة.",
        )
        self.apps = QPlainTextEdit("\n".join(self.engine.preferences["pause_apps"]))
        self.apps.setMaximumHeight(120)
        self.box.addWidget(self.apps)
        self.button("Save", "حفظ", self.save)
        self.button("Cancel", "إلغاء", self.reject)

    def save(self):
        names = [line.strip() for line in self.apps.toPlainText().splitlines() if line.strip()]
        clean = app_names(names)
        if len(clean) != len(set(v.lower() for v in names)):
            QMessageBox.information(
                self,
                self.windowTitle(),
                self.window.tr(
                    "Enter up to 30 executable basenames ending in .exe, without paths.",
                    "أدخل حتى 30 اسم ملف تشغيل ينتهي بـ .exe دون مسارات.",
                ),
            )
            return
        candidate = copy.deepcopy(self.engine.preferences)
        candidate.update({key: check.isChecked() for key, check in self.flags.items()})
        candidate["pause_apps"] = clean
        self.save_candidate(candidate)


class PerformanceDialog(ToolDialog):
    def __init__(self, window):
        super().__init__(window, ("Resource usage", "استهلاك الموارد"))
        self.text(
            "Live CPU and memory cover the app process only. Camera CPU and active time are totals reported by completed camera captures, including calibration and checks; failed captures are not counted. CPU is per logical core (may exceed 100%). Values stay in memory.",
            "المعالج والذاكرة المباشران يخصان عملية التطبيق فقط. وقت المعالج وتشغيل الكاميرا مجموع القراءات المكتملة بما فيها المعايرة والفحص؛ لا تُحسب المحاولات الفاشلة. نسبة المعالج محسوبة لكل نواة منطقية وقد تتجاوز 100%. تبقى القيم في الذاكرة.",
        )
        self.values = self.text("", "")
        self.text(
            "For fewer captures, enable Adaptive sampling in Power saving and compare camera time during equal sessions. Camera work is capped to low-resolution frames; no preview PNG is encoded unless requested.",
            "لتقليل القراءات، فعّل الفحص المتكيف من توفير الطاقة وقارن وقت الكاميرا خلال فترتين متساويتين. يُستخدم تصوير منخفض الدقة، ولا تُنشأ صورة معاينة إلا عند طلبها.",
        )
        self.button("Close", "إغلاق", self.accept)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(2000)
        self.finished.connect(self.timer.stop)
        self.refresh()

    def refresh(self):
        row = self.engine.performance.snapshot()
        memory = "—" if row["memory"] is None else f"{row['memory']:.1f}"
        self.values.setText(
            self.window.tr(
                "App CPU: {cpu}%\nApp memory: {memory} MiB\nCompleted captures: {captures}\nCamera active: {camera_seconds}s\nCamera CPU total: {camera_cpu}s\nSession: {uptime}s",
                "معالج التطبيق: {cpu}%\nذاكرة التطبيق: {memory} MiB\nالقراءات المكتملة: {captures}\nوقت تشغيل الكاميرا: {camera_seconds} ثانية\nوقت معالج الكاميرا: {camera_cpu} ثانية\nالجلسة: {uptime} ثانية",
            ).format(memory=memory, **{k: v for k, v in row.items() if k != "memory"})
        )


class CompatibilityDialog(ToolDialog):
    def __init__(self, window):
        super().__init__(window, ("Compatibility check", "فحص التوافق"))
        self.text(
            "Read-only check opens the selected camera and reads display brightness. The separate control test briefly changes brightness by 5 points and attempts to restore it. Stop automatic mode first. Keep this window open until work ends.",
            "يفتح الفحص الأول الكاميرا المحددة ويقرأ سطوع الشاشة دون تغييره. اختبار التحكم المنفصل يغيّر السطوع مؤقتًا بمقدار 5 درجات ثم يحاول استعادته. أوقف الوضع التلقائي أولًا واترك النافذة مفتوحة حتى انتهاء الفحص.",
        )
        self.results = self.text("", "")
        self.button(
            "Check camera and brightness reading",
            "فحص الكاميرا وقراءة السطوع",
            lambda: self.run(False),
        )
        self.button(
            "Test display control and restore",
            "اختبار التحكم بالشاشة والاستعادة",
            lambda: self.run(True),
        )
        self.button("Close", "إغلاق", self.reject)

    def run(self, control):
        from .camera import sample
        from .brightness import brightness, verify_control

        e = self.engine
        if e.running or e.busy or e.resume_pending or e.pause_reasons:
            self.results.setText(
                self.window.tr(
                    "Stop automatic mode and wait for current work.",
                    "أوقف الوضع التلقائي وانتظر انتهاء العملية الحالية.",
                )
            )
            return
        self.results.setText(self.window.tr("Checking…", "جارٍ الفحص…"))
        e.cancel.clear()
        device = e.selected_device()

        def work():
            if control:
                try:
                    verify_control()
                    return [("control", True)]
                except Exception as error:
                    return [("restore" if "restor" in str(error).lower() else "control", False)]
            results = []
            try:
                brightness()
                results.append(("read", True))
            except Exception:
                results.append(("read", False))
            if device:
                try:
                    reading = sample(
                        device["index"],
                        e.cancel,
                        region=e.preferences["meter_region"],
                        protection=e.preferences["spatial_protection"],
                    )
                    e.performance.capture(reading)
                    results.append(("camera", True))
                except Exception:
                    results.append(("camera", False))
            else:
                results.append(("camera", False))
            return results

        def done(results):
            lines = []
            labels = {
                "camera": ("Camera", "الكاميرا"),
                "read": ("Brightness reading", "قراءة السطوع"),
                "control": ("Display control and restoration", "التحكم بالشاشة والاستعادة"),
                "restore": (
                    "Restoration failed: restore brightness manually now",
                    "فشلت الاستعادة: أعد السطوع يدويًا الآن",
                ),
            }
            for key, ok in results:
                lines.append(
                    self.window.tr(*labels[key])
                    + ": "
                    + self.window.tr("Passed" if ok else "Failed", "ناجح" if ok else "غير ناجح")
                )
                if not ok:
                    lines.append(
                        self.window.tr(
                            "For camera failures, close camera apps, select the camera and check Windows permissions. For display failures, update the driver; external displays need DDC/CI enabled.",
                            "عند فشل الكاميرا، أغلق تطبيقات التصوير وحدد الكاميرا وتحقق من أذونات ويندوز. عند فشل الشاشة، حدّث برنامج التشغيل؛ وتحتاج الشاشة الخارجية إلى تفعيل DDC/CI.",
                        )
                    )
            self.results.setText("\n".join(lines))

        e.work(work, done, "compatibility")

    def reject(self):
        if self.engine.busy and self.engine.operation == "compatibility":
            return  # Allow the independent control worker to restore brightness first.
        super().reject()


class TuningMixin:
    def tuning_settings(self, layout):
        layout.addWidget(
            self.label(self.tr("Calibration and measurement", "المعايرة والقياس"), True)
        )
        for cls, en, ar in [
            (CalibrationDialog, "Guided calibration", "المعايرة الموجّهة"),
            (CompareDialog, "Compare curves", "مقارنة المنحنيات"),
            (
                TuningDialog,
                "Measurement, response and app pauses",
                "القياس والاستجابة وإيقاف التطبيقات",
            ),
            (CompatibilityDialog, "Compatibility check", "فحص التوافق"),
            (PerformanceDialog, "Resource usage", "استهلاك الموارد"),
        ]:
            button = QPushButton(self.tr(en, ar))
            button.clicked.connect(lambda checked=False, kind=cls: self.open_tuning(kind))
            layout.addWidget(button)

    def open_tuning(self, kind):
        self.tuning_dialog = kind(self)
        self.tuning_dialog.open()
