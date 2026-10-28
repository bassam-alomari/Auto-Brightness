"""Editable curve, recent history, and comfort controls for the Qt interface."""

import time
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget, QDialog, QVBoxLayout, QHBoxLayout, QPushButton
from .comfort import valid_points, target, DEFAULT_POINTS


class CurveEditor(QWidget):
    def __init__(self, points):
        super().__init__()
        self.points = [list(p) for p in points]
        self.selected = None
        self.setMinimumSize(450, 230)
        self.setMouseTracking(True)

    def coordinate(self, point):
        span = max(40, self.points[-1][0] + 5)
        return QPointF(
            24 + (self.width() - 48) * (point[0] - 12) / (span - 12),
            self.height() - 30 - (self.height() - 55) * point[1] / 100,
        )

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor("#182331"))
        p.setPen(QColor("#415066"))
        for value in (0, 25, 50, 75, 100):
            y = self.coordinate((12, value)).y()
            p.drawLine(QPointF(24, y), QPointF(self.width() - 24, y))
        path = QPainterPath()
        span = max(40, self.points[-1][0] + 5)
        for i in range(201):
            x = 12 + (span - 12) * i / 200
            point = self.coordinate((x, target(x, 0, 100, self.points)))
            path.lineTo(point) if i else path.moveTo(point)
        p.setPen(QPen(QColor("#65b7ff"), 3))
        p.drawPath(path)
        for i, point in enumerate(self.points):
            p.setBrush(QColor("#ffffff" if i == self.selected else "#65b7ff"))
            p.drawEllipse(self.coordinate(point), 6, 6)
        p.setPen(QColor("white"))
        if self.selected is not None:
            x, y = self.points[self.selected]
            p.drawText(24, 18, f"{x:g} → {y:g}%")
        p.drawText(24, self.height() - 8, "12")
        p.drawText(self.width() - 60, self.height() - 8, f"{span:g}")

    def mousePressEvent(self, event):
        distances = [
            (self.coordinate(point) - event.position()).manhattanLength() for point in self.points
        ]
        self.selected = distances.index(min(distances)) if min(distances) < 24 else None
        self.update()

    def mouseMoveEvent(self, event):
        if self.selected is None or not event.buttons() & Qt.MouseButton.LeftButton:
            return
        i = self.selected
        if i == 0:
            return
        span = max(40, self.points[-1][0] + 5)
        x = round(12 + (event.position().x() - 24) / (self.width() - 48) * (span - 12), 1)
        y = round((self.height() - 30 - event.position().y()) / (self.height() - 55) * 100)
        x = max(self.points[i - 1][0] + 0.1, min(255, x))
        y = max(self.points[i - 1][1], min(100, y))
        if i < len(self.points) - 1:
            x = min(self.points[i + 1][0] - 0.1, x)
            y = min(self.points[i + 1][1], y)
        else:
            y = 100
        self.points[i] = [round(x, 1), y]
        self.update()

    def add_point(self):
        if len(self.points) >= 12:
            return
        i = max(
            range(len(self.points) - 1), key=lambda j: self.points[j + 1][0] - self.points[j][0]
        )
        x = round((self.points[i][0] + self.points[i + 1][0]) / 2, 1)
        if self.points[i][0] < x < self.points[i + 1][0]:
            self.points.insert(i + 1, [x, target(x, 0, 100, self.points)])
            self.selected = i + 1
            self.update()

    def remove_point(self):
        if self.selected is not None and 0 < self.selected < len(self.points) - 1:
            self.points.pop(self.selected)
            self.selected = None
            self.update()


class CurveDialog(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.setLayoutDirection(window.layoutDirection())
        self.window = window
        self.setStyleSheet("QDialog { background: #20242b; }")
        self.setWindowTitle(window.tr("Edit your curve", "تعديل منحناك"))
        self.resize(600, 350)
        layout = QVBoxLayout(self)
        layout.addWidget(
            window.label(
                window.tr(
                    "Drag points. Select a point to remove it.", "اسحب النقاط. اختر نقطة لحذفها."
                )
            )
        )
        self.editor = CurveEditor(window.engine.preferences["custom_points"])
        layout.addWidget(self.editor)
        buttons = QHBoxLayout()
        for en, ar, action in [
            ("Add point", "إضافة نقطة", self.editor.add_point),
            ("Remove point", "حذف نقطة", self.editor.remove_point),
            ("Reset", "استعادة الافتراضي", self.reset),
            ("Save", "حفظ", self.save),
        ]:
            button = QPushButton(window.tr(en, ar))
            button.clicked.connect(action)
            buttons.addWidget(button)
        layout.addLayout(buttons)

    def reset(self):
        self.editor.points = [point[:] for point in DEFAULT_POINTS]
        self.editor.selected = None
        self.editor.update()

    def save(self):
        if not valid_points(self.editor.points):
            return
        e = self.window.engine
        e.remember_curve()
        e.preferences["custom_points"] = [point[:] for point in self.editor.points]
        e.preferences["brightness_curve"] = "custom"
        e.persist()
        self.accept()
        self.window.build()


class History(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.setMinimumHeight(155)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        now = time.monotonic()
        rows = [row for row in self.window.engine.history if now - row[0] <= 60]
        p.setPen(QColor(self.window.engine.palette["muted"]))
        if not rows:
            p.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                self.window.tr("Waiting for readings", "بانتظار القراءات"),
            )
            return
        maxlight = max(30, max(row[1] for row in rows))
        for column, scale, color in (
            (1, maxlight, "#f5c366"),
            (2, 100, "#67b7ff"),
            (3, 100, "#79dda5"),
        ):
            path = QPainterPath()
            for i, row in enumerate(rows):
                point = QPointF(
                    12 + (self.width() - 24) * max(0, 1 - (now - row[0]) / 60),
                    self.height() - 24 - (self.height() - 40) * row[column] / scale,
                )
                path.lineTo(point) if i else path.moveTo(point)
            p.setPen(QPen(QColor(color), 2))
            p.drawPath(path)
            if len(rows) == 1:
                p.drawEllipse(point, 3, 3)
        p.setPen(QColor(self.window.engine.palette["muted"]))
        p.drawText(
            12,
            self.height() - 5,
            self.window.tr(
                "Light (yellow) · Target (blue) · Screen (green)",
                "الضوء: أصفر · المستهدف: أزرق · الشاشة: أخضر",
            ),
        )


DIAGNOSTICS = {
    "device_wait": (
        "Waiting for the selected device to reconnect",
        "بانتظار إعادة توصيل الجهاز المحدد",
    ),
    "camera_retry": (
        "Camera busy or disconnected; retrying quietly",
        "الكاميرا مشغولة أو مفصولة؛ تُعاد المحاولة تلقائيًا",
    ),
    "image_curve": ("Following the selected curve", "اتباع المنحنى المحدد"),
    "uncertain": ("Reading is unreliable; brightness held", "القراءة غير موثوقة؛ تم تثبيت السطوع"),
    "deadband": ("Small difference; brightness held", "فرق بسيط؛ تم تثبيت السطوع"),
    "confirming_change": (
        "Waiting for a second cycle to confirm the change",
        "بانتظار دورة ثانية لتأكيد التغيير",
    ),
    "transient": (
        "The two readings disagree; ignoring a brief light change",
        "القراءتان مختلفتان؛ تم تجاهل تغيّر عابر",
    ),
    "paused": ("Camera paused while locked or sleeping", "الكاميرا متوقفة أثناء القفل أو السكون"),
    "camera_error": (
        "Camera unavailable; close other camera apps and refresh",
        "الكاميرا غير متاحة؛ أغلق التطبيقات الأخرى ثم حدّث قائمة الكاميرات",
    ),
    "display_error": (
        "Display control failed; check Details for the driver error",
        "تعذّر التحكم بالشاشة؛ افتح التفاصيل لمعرفة خطأ برنامج التشغيل",
    ),
}
