"""Qt view over the existing serialized control engine; no screen captures are used."""

import base64
import ctypes
import sys
import time
from pathlib import Path

from PySide6.QtCore import QEvent, QEventLoop, QPoint, QRectF, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import (
    QColor,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QIcon,
    QRegion,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QBoxLayout,
    QFrame,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QSizePolicy,
    QSystemTrayIcon,
    QStyle,
    QStyleOptionButton,
    QStyleOptionSlider,
    QStyleOptionComboBox,
    QStyledItemDelegate,
    QVBoxLayout,
    QWidget,
)

from .adaptive import image_target, CURVES
from .comfort_ui import CurveDialog, History, DIAGNOSTICS
from .comfort import target as custom_target
from .extras_ui import ExtrasMixin
from .easy_ui import EasyMixin
from .tuning_ui import TuningMixin
from .camera import sample
from . import __version__
from .i18n import LANGUAGES, literal
from .themes import THEME_NAMES


class ToggleSwitch(QCheckBox):
    """Accessible checkbox semantics with an animated, pill-shaped switch."""

    def __init__(self, text=""):
        super().__init__(text)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.show_focus_ring = False
        self.position = 0.0
        self.animation = QVariantAnimation(self)
        self.animation.setDuration(160)
        self.animation.valueChanged.connect(self.animate)
        self.toggled.connect(self.transition)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(50)

    def focusInEvent(self, event):
        self.show_focus_ring = event.reason() in (
            Qt.FocusReason.TabFocusReason,
            Qt.FocusReason.BacktabFocusReason,
            Qt.FocusReason.ShortcutFocusReason,
        )
        super().focusInEvent(event)
        self.update()

    def mousePressEvent(self, event):
        self.show_focus_ring = False
        super().mousePressEvent(event)
        self.update()

    def hitButton(self, position):
        return self.rect().contains(position)

    def animate(self, value):
        self.position = float(value)
        self.update()

    def transition(self, checked):
        self.animation.stop()
        if not self.isVisible():
            self.position = float(checked)
            self.update()
            return
        self.animation.setStartValue(self.position)
        self.animation.setEndValue(float(checked))
        self.animation.start()

    def paintEvent(self, event):
        option = QStyleOptionButton()
        self.initStyleOption(option)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        owner = getattr(self.window(), "engine", None)
        rtl = (
            owner.language == "ar"
            if owner is not None
            else self.layoutDirection() == Qt.LayoutDirection.RightToLeft
        )
        track = QRectF(4, (self.height() - 28) / 2, 60, 28)
        text_rect = QRectF(76, 2, max(0, self.width() - 80), self.height() - 4)
        painter.setPen(option.palette.color(option.palette.ColorRole.WindowText))
        if not self.isEnabled():
            painter.setOpacity(0.45)
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignVCenter
            | Qt.AlignmentFlag.AlignAbsolute
            | (Qt.AlignmentFlag.AlignRight if rtl else Qt.AlignmentFlag.AlignLeft)
            | Qt.TextFlag.TextWordWrap
            | (Qt.TextFlag.TextForceRightToLeft if rtl else Qt.TextFlag.TextForceLeftToRight),
            self.text(),
        )
        painter.setOpacity(1.0)
        enabled = self.isEnabled()
        owner = getattr(self.window(), "engine", None)
        glass = owner is not None and owner.theme == "glass"
        color = (
            QColor(65, 151, 237, 35 if glass else 190)
            if self.isChecked()
            else QColor(130, 145, 160, 8 if glass else 65)
        )
        if not enabled:
            color.setAlpha(45)
        painter.setPen(QPen(QColor(255, 255, 255, 95 if enabled else 35), 1))
        painter.setBrush(color)
        painter.drawRoundedRect(track, track.height() / 2, track.height() / 2)
        progress = self.position
        if self.layoutDirection() == Qt.LayoutDirection.RightToLeft:
            progress = 1 - progress
        thumb_width, thumb_height = 40, 24
        x = track.left() + 2 + progress * (track.width() - thumb_width - 4)
        knob = QRectF(x, track.top() + 2, thumb_width, thumb_height)
        painter.setPen(Qt.PenStyle.NoPen)
        if glass:
            painter.setBrush(QColor(0, 0, 0, 45))
            painter.drawRoundedRect(knob.translated(0, 2), 12, 12)
            wash = QLinearGradient(knob.topLeft(), knob.bottomLeft())
            wash.setColorAt(0, QColor(255, 255, 255, 65))
            wash.setColorAt(0.45, QColor(160, 180, 200, 20))
            wash.setColorAt(1, QColor(255, 255, 255, 35))
            painter.setBrush(wash)
        else:
            painter.setBrush(QColor("#ffffff"))
        painter.setPen(QPen(QColor(215, 235, 255, 100 if glass else 170), 1))
        painter.drawRoundedRect(knob, 12, 12)
        if self.hasFocus() and self.show_focus_ring:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor("#64b5ff"), 2))
            painter.drawRoundedRect(track.adjusted(-2, -2, 2, 2), 14, 14)


class NoWheelSpinBox(QSpinBox):
    def wheelEvent(self, event):
        event.ignore()


class GlassSlider(QSlider):
    """Native slider input with explicit rounded painting independent of QSS."""

    def wheelEvent(self, event):
        event.ignore()

    def __init__(self, orientation):
        super().__init__(orientation)
        self.setMinimumHeight(44)

    def paintEvent(self, event):
        option = QStyleOptionSlider()
        self.initStyleOption(option)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        handle = self.style().subControlRect(
            QStyle.ComplexControl.CC_Slider, option, QStyle.SubControl.SC_SliderHandle, self
        )
        center = handle.center().x()
        y = self.height() / 2
        glass = getattr(self.window(), "engine", None)
        glass = glass is not None and glass.theme == "glass"
        half = 28 if glass else 13
        inset = half + 3
        center = max(inset, min(center, self.width() - inset))
        track = QRectF(inset, y - 2.5, max(0, self.width() - 2 * inset), 5)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(160, 173, 189, 100))
        painter.drawRoundedRect(track, 2.5, 2.5)
        start, end = (center, track.right()) if option.upsideDown else (track.left(), center)
        painter.setBrush(QColor(65, 151, 250, 220))
        painter.drawRoundedRect(QRectF(start, y - 2.5, max(0, end - start), 5), 2.5, 2.5)
        knob = QRectF(center - half, y - (17 if glass else 13), half * 2, 34 if glass else 26)
        radius = knob.height() / 2
        if glass:
            painter.setBrush(QColor(0, 0, 0, 45))
            painter.drawRoundedRect(knob.translated(0, 2), radius, radius)
        wash = QLinearGradient(knob.topLeft(), knob.bottomLeft())
        wash.setColorAt(0, QColor(255, 255, 255, 65 if glass else 255))
        wash.setColorAt(0.45, QColor(160, 180, 200, 20 if glass else 255))
        wash.setColorAt(1, QColor(255, 255, 255, 35 if glass else 255))
        painter.setBrush(wash if glass else QColor("#ffffff"))
        painter.setPen(QPen(QColor(215, 235, 255, 100) if glass else QColor("#b9c7d6"), 1))
        painter.drawRoundedRect(knob, radius, radius)
        if self.hasFocus():
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor("#64b5ff"), 1))
            painter.drawRoundedRect(knob.adjusted(-2, -2, 2, 2), radius + 2, radius + 2)


class GlassMenu(QMenu):
    def __init__(self, parent):
        super().__init__(parent)
        if parent.engine.theme == "glass":
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)

    def showEvent(self, event):
        super().showEvent(event)
        if self.parent().engine.theme == "glass":
            from .backdrop import apply_backdrop

            apply_backdrop(int(self.winId()), True)
            path = QPainterPath()
            path.addRoundedRect(QRectF(self.rect()), 14, 14)
            self.setMask(QRegion(path.toFillPolygon().toPolygon()))


class RoundedItemDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        rect = QRectF(option.rect).adjusted(4, 2, -4, -2)
        if selected:
            painter.setPen(Qt.PenStyle.NoPen)
            owner = getattr(self.parent().window(), "engine", None)
            painter.setBrush(
                QColor(65, 151, 237, 55)
                if owner is not None and owner.theme == "glass"
                else option.palette.highlight()
            )
            painter.drawRoundedRect(rect, 16, 16)
        painter.setPen(
            option.palette.highlightedText().color() if selected else option.palette.text().color()
        )
        painter.drawText(
            rect.adjusted(12, 0, -12, 0),
            Qt.AlignmentFlag.AlignVCenter
            | (
                Qt.AlignmentFlag.AlignRight
                if option.direction == Qt.LayoutDirection.RightToLeft
                else Qt.AlignmentFlag.AlignLeft
            ),
            str(index.data() or ""),
        )
        painter.restore()

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        size.setHeight(max(40, size.height()))
        return size


class RoundedCombo(QComboBox):
    def paintEvent(self, event):
        option = QStyleOptionComboBox()
        self.initStyleOption(option)
        owner = getattr(self.window(), "engine", None)
        rtl = owner is not None and owner.language == "ar"
        option.direction = Qt.LayoutDirection.RightToLeft if rtl else Qt.LayoutDirection.LeftToRight
        text = option.currentText
        option.currentText = ""
        painter = QPainter(self)
        self.style().drawComplexControl(QStyle.ComplexControl.CC_ComboBox, option, painter, self)
        rect = (
            self.style()
            .subControlRect(
                QStyle.ComplexControl.CC_ComboBox,
                option,
                QStyle.SubControl.SC_ComboBoxEditField,
                self,
            )
            .adjusted(4, 0, -4, 0)
        )
        painter.setPen(option.palette.color(option.palette.ColorRole.Text))
        flags = Qt.AlignmentFlag.AlignVCenter | (
            Qt.AlignmentFlag.AlignRight if rtl else Qt.AlignmentFlag.AlignLeft
        )
        painter.drawText(
            rect,
            flags,
            self.fontMetrics().elidedText(text, Qt.TextElideMode.ElideRight, rect.width()),
        )

    def wheelEvent(self, event):
        event.ignore()

    def __init__(self):
        super().__init__()
        self.setItemDelegate(RoundedItemDelegate(self))

    def showPopup(self):
        popup = self.view().window()
        owner = getattr(self.window(), "engine", None)
        glass = owner is not None and owner.theme == "glass"
        popup.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, glass)
        self.view().viewport().setAutoFillBackground(not glass)
        self.view().setFrameShape(QFrame.Shape.NoFrame)
        if isinstance(popup, QFrame):
            popup.setFrameShape(QFrame.Shape.NoFrame)
        if glass:
            popup.setObjectName("glassComboPopup")
            popup.setStyleSheet("""#glassComboPopup { background: rgba(20,35,50,65); border: none; border-radius: 22px; }
                #glassComboPopup QAbstractItemView { background: transparent; border: none; border-radius: 22px; }""")
        else:
            popup.setStyleSheet("")
        super().showPopup()
        if glass:
            from .backdrop import apply_backdrop

            apply_backdrop(int(popup.winId()), True)
        path = QPainterPath()
        path.addRoundedRect(QRectF(popup.rect()), 22, 22)
        popup.setMask(QRegion(path.toFillPolygon().toPolygon()))


class TitleButton(QPushButton):
    def __init__(self, kind, owner):
        super().__init__("")
        self.kind = kind
        self.owner = owner

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        engine = self.owner.engine
        pen = QPen(QColor("white" if engine.theme == "glass" else engine.palette["ink"]), 1.3)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        x, y = self.width() // 2, self.height() // 2
        if self.kind == "−":
            painter.drawLine(x - 5, y, x + 5, y)
        elif self.kind == "□":
            painter.drawRect(QRectF(x - 5, y - 5, 10, 10))
        else:
            painter.drawLine(x - 5, y - 5, x + 5, y + 5)
            painter.drawLine(x - 5, y + 5, x + 5, y - 5)


class TitleHeader(QWidget):
    def __init__(self, window):
        super().__init__()
        self.owner = window

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.owner.windowHandle():
            self.owner.windowHandle().startSystemMove()
        else:
            super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.owner.toggle_maximize()


class Surface(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.layout_box = QVBoxLayout(self)
        self.layout_box.setContentsMargins(26, 24, 26, 26)
        self.layout_box.setSpacing(14)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        bounds = QRectF(2, 3, self.width() - 4, self.height() - 6)
        path = QPainterPath()
        path.addRoundedRect(bounds, 30, 30)
        glass = self.window.engine.theme == "glass"
        if glass:
            painter.fillPath(path, QColor(8, 25, 40, self.window.glass_alpha(14, 120)))
            wash = QLinearGradient(0, 0, self.width(), self.height())
            wash.setColorAt(0, QColor(255, 255, 255, 12))
            wash.setColorAt(0.45, QColor(190, 225, 255, 8))
            wash.setColorAt(1, QColor(12, 35, 70, self.window.glass_alpha(8, 40)))
            painter.fillPath(path, wash)
            painter.setClipping(False)
            # A broad translucent bevel, with no bright double outline.
            rim = QLinearGradient(0, 0, 0, self.height())
            rim.setColorAt(0, QColor(255, 255, 255, 80))
            rim.setColorAt(0.12, QColor(235, 245, 255, 25))
            rim.setColorAt(0.5, QColor(255, 255, 255, 10))
            rim.setColorAt(1, QColor(255, 255, 255, 35))
            painter.setPen(QPen(rim, 3.5))
            painter.drawPath(path)
            edge = QLinearGradient(0, 0, 0, self.height())
            edge.setColorAt(0, QColor(255, 255, 255, 105))
            edge.setColorAt(0.25, QColor(255, 255, 255, 28))
            edge.setColorAt(1, QColor(255, 255, 255, 45))
            painter.setPen(QPen(edge, 0.7))
            painter.drawPath(path)
        else:
            palette = self.window.engine.palette
            painter.fillPath(path, QColor(palette["card"]))
            painter.setPen(QPen(QColor(palette["line"]), 1))
            painter.drawPath(path)


class Curve(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.setMinimumHeight(160)

    def paintEvent(self, event):
        e = self.window.engine
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(
            QPen(QColor(255, 255, 255, 55) if e.theme == "glass" else QColor(e.palette["line"]), 1)
        )
        for y in (25, 60, 95, 130):
            painter.drawLine(15, y, self.width() - 15, y)
        path = QPainterPath()
        span = max(80, e.preferences["custom_points"][-1][0])
        for i in range(101):
            value = image_target(
                i * span / 100, e.low.get(), e.high.get(), e.preferences["brightness_curve"]
            )
            if e.preferences["brightness_curve"] == "custom":
                value = custom_target(
                    i * span / 100, e.low.get(), e.high.get(), e.preferences["custom_points"]
                )
            x, y = 15 + (self.width() - 30) * i / 100, 135 - value
            if i:
                path.lineTo(x, y)
            else:
                path.moveTo(x, y)
        painter.setPen(QPen(QColor("#d1f9ff" if e.theme == "glass" else e.palette["accent"]), 3))
        painter.drawPath(path)
        painter.setPen(QColor("white" if e.theme == "glass" else e.palette["muted"]))
        flags = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignAbsolute
        for key, arabic, value, right in (
            ("Dim", "خافت", e.low.get(), False),
            ("Bright", "ساطع", e.high.get(), True),
        ):
            label = self.window.tr(key, arabic)
            number = f"{value}%"
            if e.language == "ar":
                caption = "\u200f" + label + ": \u2066" + number + "\u2069"
                direction = Qt.TextFlag.TextForceRightToLeft
            else:
                caption = label + ": " + number
                direction = Qt.TextFlag.TextForceLeftToRight
            width = (self.width() - 30) / 2
            rect = QRectF(15 + (width if right else 0), 138, width, 22)
            align = Qt.AlignmentFlag.AlignRight if right else Qt.AlignmentFlag.AlignLeft
            painter.drawText(rect, flags | align | direction, caption)


class Window(TuningMixin, EasyMixin, ExtrasMixin, QWidget):
    def __init__(self, root, engine):
        super().__init__()
        self.root, self.engine = root, engine
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMouseTracking(True)
        self.backdrop_available = False
        self.expanded = False
        self.restore_geometry = None
        self.page = "home"
        self.advanced_visible = False
        self.settings_query = ""
        self.signature = None
        self.closing = False
        self.update_pending = False
        self.pending_update = None
        self.update_message = ""
        self.shortcut_keys = []
        self.shortcut_status = ""
        self._pumping = False
        self.tray = QSystemTrayIcon(self)
        icon = self.make_icon()
        self.setWindowIcon(icon)
        QApplication.instance().setWindowIcon(icon)
        self.tray.setIcon(icon)
        self.tray.activated.connect(self.tray_activate)
        self.resize(1000, 830)
        self.setMinimumSize(540, 480)
        self.build()
        self.session_registered = False
        try:
            api = ctypes.windll.wtsapi32.WTSRegisterSessionNotification
            api.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
            api.restype = ctypes.c_int
            self.session_registered = bool(api(ctypes.c_void_p(int(self.winId())), 0))
        except (AttributeError, OSError):
            pass
        self.pump = QTimer(self)
        self.pump.timeout.connect(self.sync)
        self.glass_save = QTimer(self)
        self.glass_save.setSingleShot(True)
        self.glass_save.timeout.connect(self.engine.persist)
        self.pump.start(100)
        self.configure_shortcuts()

    def tr(self, english, arabic):
        return literal(
            self.engine.language, english, arabic, self.engine.preferences["arabic_dialect"]
        )

    def make_icon(self):
        return QIcon(str(Path(__file__).with_name("app.ico")))

    def label(self, text, heading=False):
        label = QLabel(text)
        label.setWordWrap(True)
        if heading:
            label.setObjectName("heading")
        return label

    def button(self, key, action, primary=False):
        button = QPushButton(self.engine.t(key))
        if primary:
            button.setObjectName("primary")
        button.clicked.connect(action)
        return button

    def combo(self, labels, index, action):
        combo = RoundedCombo()
        combo.addItems(labels)
        combo.setCurrentIndex(index)
        combo.currentIndexChanged.connect(action)
        return combo

    def card(self, parent_layout):
        card = Surface(self)
        parent_layout.addWidget(card, 1)
        return card.layout_box

    def checkbox(self, key, value, action):
        check = ToggleSwitch(self.engine.t(key))
        check.setChecked(value)
        check.toggled.connect(action)
        return check

    def build(self):
        e = self.engine
        if self.layout():
            old = self.layout()
            while old.count():
                item = old.takeAt(0)
                if item.widget():
                    item.widget().hide()
                    item.widget().deleteLater()
            old_holder = QWidget()
            old_holder.setLayout(old)
            old_holder.deleteLater()
        glass = e.theme == "glass"
        dark_theme = e.theme == "dark" or e.palette.get("dark", False)
        ink = "#ffffff" if glass else e.palette["ink"]
        muted = "#deedfc" if glass else e.palette["muted"]
        fill = "rgba(10,35,60,45)" if glass else e.palette["tint"]
        border = "rgba(255,255,255,105)" if glass else e.palette["line"]
        popup_bg = "rgba(20,35,50,65)" if glass else e.palette["card"]
        popup_ink = "#f5f5f7" if glass else e.palette["ink"]
        popup_selection = "rgba(65,151,237,55)" if glass else e.palette["tint"]
        icons = "dark" if glass or dark_theme else "light"
        down = (Path(__file__).parent / f"down-{icons}.svg").as_posix()
        up = (Path(__file__).parent / f"up-{icons}.svg").as_posix()
        self.setStyleSheet(f"""
            QWidget {{ font-family: 'Segoe UI'; font-size: 14px; color: {ink}; background: transparent; }}
            QLabel#heading {{ font-size: 20px; font-weight: 600; }}
            QLabel#metric {{ font-size: 82px; font-weight: 600; }}
            QLabel#muted {{ color: {muted}; }}
            QPushButton, QComboBox, QSpinBox, QLineEdit#settingsSearch {{ background: {fill}; border: 1px solid {border}; border-radius: 18px; padding: 10px 16px; min-height: 22px; }}
            QComboBox {{ padding-left: 16px; padding-right: 42px; }}
            QComboBox::drop-down {{ subcontrol-origin: padding; subcontrol-position: top right; width: 30px; border: none; background: transparent; }}
            QComboBox::down-arrow {{ image: url("{down}"); width: 14px; height: 12px; }}
            QSpinBox {{ padding-right: 42px; }}
            QSpinBox::up-button {{ subcontrol-origin: padding; subcontrol-position: top right; width: 30px; border: none; background: transparent; }}
            QSpinBox::down-button {{ subcontrol-origin: padding; subcontrol-position: bottom right; width: 30px; border: none; background: transparent; }}
            QSpinBox::up-arrow {{ image: url("{up}"); width: 12px; height: 10px; }}
            QSpinBox::down-arrow {{ image: url("{down}"); width: 12px; height: 10px; }}
            QPushButton:hover {{ background: {"rgba(255,255,255,60)" if glass else e.palette["line"]}; }}
            QPushButton#primary {{ background: {"rgba(90,170,255,35)" if glass else e.palette["accent"]}; color: white; border-color: {border}; }}
            QPushButton:disabled {{ color: {"#abc8df" if glass else e.palette["muted"]}; }}
            QComboBox QAbstractItemView {{ background: {popup_bg}; color: {popup_ink}; selection-background-color: {popup_selection}; selection-color: {popup_ink}; border: {"none" if glass else "1px solid " + border}; padding: 8px; border-radius: 22px; outline: 0; }}
            QMenu {{ background: {popup_bg}; color: {popup_ink}; border-radius: 14px; padding: 8px; }}
            QMenu::item {{ padding: 10px 18px; margin: 2px 4px; border-radius: 9px; border: none; }}
            QMenu::item:selected {{ background: {popup_selection}; border-radius: 9px; }}
            QScrollArea {{ border: none; }}
            QScrollBar:vertical {{ background: transparent; width: 8px; }}
            QScrollBar::handle:vertical {{ background: {"rgba(255,255,255,25)" if glass else border}; border-radius: 4px; min-height: 30px; }}
            QScrollBar::handle:vertical:hover {{ background: {"rgba(255,255,255,65)" if glass else border}; }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
            QCheckBox {{ spacing: 10px; padding: 4px; }}
            QCheckBox::indicator {{ width: 60px; height: 28px; border: 1px solid {border}; border-radius: 6px; background: {fill}; }}
            QCheckBox::indicator:checked {{ background: #4b9fe5; border: 2px solid white; }}
            QSlider {{ padding: 3px; }}
            QSlider::groove:horizontal {{ background: {border}; height: 5px; border-radius: 2px; }}
            QSlider::handle:horizontal {{ background: {"rgba(255,255,255,25)" if glass else "white"}; border: 1px solid {"rgba(255,255,255,130)" if glass else "#aac9e9"}; width: {56 if glass else 26}px; margin: -10px 0; border-radius: 13px; }}
            QSlider::handle:horizontal:hover {{ background: {"rgba(255,255,255,55)" if glass else "#e4f1ff"}; }}
            QSlider::handle:horizontal:pressed {{ background: {"rgba(255,255,255,75)" if glass else "#c6e3ff"}; }}
        """)
        self.setLayoutDirection(
            Qt.LayoutDirection.RightToLeft if e.language == "ar" else Qt.LayoutDirection.LeftToRight
        )
        self.setWindowTitle(e.t("app") + " · " + __version__)
        from .backdrop import apply_backdrop

        self.backdrop_available = apply_backdrop(int(self.winId()), glass)
        try:
            dark = ctypes.c_int(glass or dark_theme)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                ctypes.c_void_p(int(self.winId())), 20, ctypes.byref(dark), 4
            )
        except (AttributeError, OSError):
            pass
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 22)
        outer.setSpacing(20)
        header = TitleHeader(self)
        row = QHBoxLayout(header)
        row.setContentsMargins(2, 0, 2, 0)
        titles = QVBoxLayout()
        titles.addWidget(self.label(e.t("app"), True))
        titles.addWidget(self.label(e.t("simple_subtitle")))
        row.addLayout(titles, 1)
        self.language_button = self.button("language", self.language_menu)
        row.addWidget(self.language_button)
        row.addWidget(
            self.button("home" if self.page == "settings" else "settings", self.toggle_page)
        )
        controls = QHBoxLayout()
        for text, tip, action in [
            ("−", self.tr("Minimize", "تصغير"), self.showMinimized),
            ("□", self.tr("Maximize / restore", "تكبير / استعادة"), self.toggle_maximize),
            ("×", self.tr("Close", "إغلاق"), self.close),
        ]:
            control = TitleButton(text, self)
            control.setToolTip(tip)
            control.setAccessibleName(tip)
            control.setFixedSize(38, 34)
            control.setStyleSheet(
                "QPushButton { padding: 0; border: none; background: transparent; font-size: 14px; }"
                "QToolTip { font-family: 'Segoe UI'; font-size: 14px; font-weight: normal; "
                "padding: 4px 8px; color: #f5f5f7; background: #24262b; "
                "border: 1px solid #454850; border-radius: 4px; }"
            )
            control.clicked.connect(action)
            controls.addWidget(control)
        row.addLayout(controls)
        outer.addWidget(header)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.viewport().setAutoFillBackground(False)
        content = QWidget()
        content.setAutoFillBackground(False)
        self.content_layout = QVBoxLayout(content)
        self.content_layout.setContentsMargins(
            12 if e.language == "ar" else 0, 0, 0 if e.language == "ar" else 12, 0
        )
        self.content_layout.setSpacing(20)
        panels = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self.panels = panels
        panels.setDirection(
            QBoxLayout.Direction.TopToBottom
            if self.width() < 900
            else QBoxLayout.Direction.LeftToRight
        )
        panels.setSpacing(20)
        self.content_layout.addLayout(panels)
        if self.page == "home":
            self.home(panels)
        else:
            self.settings(panels)
        about = self.label(e.t("about_short"))
        about.setObjectName("muted")
        if glass:
            about.setStyleSheet(
                "background: rgba(8,25,52,125); border-radius: 12px; padding: 8px; color: white;"
            )
        self.content_layout.addWidget(about)
        self.content_layout.addStretch()
        scroll.setWidget(content)
        scroll.verticalScrollBar().valueChanged.connect(self.repaint_surfaces)
        outer.addWidget(scroll, 1)
        status_card = Surface(self)
        self.status_title = self.label("", True)
        self.status_text = self.label("")
        self.reason_text = self.label("")
        status_card.layout_box.addWidget(self.reason_text)
        status_card.layout_box.addWidget(self.status_title)
        status_card.layout_box.addWidget(self.status_text)
        outer.addWidget(status_card)
        self.signature = (e.language, e.theme, self.page)
        self.update_values()
        self.update()
        self.update_tray_menu()
        self.configure_shortcuts()

    def home(self, panels):
        e = self.engine
        left, right = self.card(panels), self.card(panels)
        left.addWidget(self.label(e.t("automatic"), True))
        self.mode_label = self.label("")
        left.addWidget(self.mode_label)
        left.addWidget(self.label(e.t("screen_level")))
        self.metric_label = QLabel("—%")
        self.metric_label.setObjectName("metric")
        self.metric_label.setAlignment(
            Qt.AlignmentFlag.AlignVCenter
            | (Qt.AlignmentFlag.AlignRight if e.language == "ar" else Qt.AlignmentFlag.AlignLeft)
        )
        left.addWidget(self.metric_label)
        left.addWidget(self.label(e.t("one_click")))
        buttons = QHBoxLayout()
        self.start_button = self.button("start_simple", e.start, True)
        self.stop_button = self.button("stop", e.stop)
        buttons.addWidget(self.start_button)
        buttons.addWidget(self.stop_button)
        left.addLayout(buttons)
        self.pause_combo = self.combo(
            [
                self.tr("Pause temporarily…", "إيقاف مؤقت…"),
                self.tr("15 minutes", "15 دقيقة"),
                self.tr("30 minutes", "30 دقيقة"),
                self.tr("60 minutes", "60 دقيقة"),
            ],
            0,
            self.pause_for,
        )
        left.addWidget(self.pause_combo)
        self.pause_countdown = self.label("")
        left.addWidget(self.pause_countdown)
        self.resume_button = QPushButton(self.tr("Resume now", "استئناف الآن"))
        self.resume_button.clicked.connect(e.resume_now)
        left.addWidget(self.resume_button)
        manual_row = QHBoxLayout()
        self.manual_slider = GlassSlider(Qt.Orientation.Horizontal)
        self.manual_slider.setRange(0, 100)
        self.manual_slider.setValue(50)
        self.manual_slider.setToolTip(
            self.tr(
                "Scale: 0–100%. Brightness range: 0–100%.",
                "المقياس من ٠ إلى ١٠٠٪. تطبيق السطوع بطلب ١٠٪ على الأقل.",
            )
        )
        self.manual_text = QLabel("50%")
        self.manual_text.setFixedWidth(
            self.manual_text.fontMetrics().horizontalAdvance("100%") + 16
        )
        self.manual_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.manual_slider.valueChanged.connect(lambda v: self.manual_text.setText(f"{v}%"))
        manual_row.addWidget(self.manual_slider, 1)
        left.addLayout(manual_row)
        left.addWidget(self.manual_text, 0, Qt.AlignmentFlag.AlignHCenter)
        self.manual_button = self.button("manual_set", self.manual)
        left.addWidget(self.manual_button)
        self.save_manual_button = QPushButton(
            self.tr("Save this brightness to my curve", "حفظ هذا السطوع في منحناي")
        )
        self.save_manual_button.clicked.connect(self.save_manual_preference)
        left.addWidget(self.save_manual_button)
        left.addWidget(self.label(e.t("manual_tip")))
        left.addStretch()
        right.addWidget(self.label(self.tr("Display", "الشاشة"), True))
        self.displays_combo = RoundedCombo()
        self.displays_combo.currentIndexChanged.connect(self.choose_display)
        right.addWidget(self.displays_combo)
        self.displays_refresh = QPushButton(self.tr("Refresh displays", "تحديث الشاشات"))
        self.displays_refresh.clicked.connect(e.refresh_displays)
        right.addWidget(self.displays_refresh)
        right.addWidget(
            self.label(
                self.tr(
                    "External displays require DDC/CI support. Each display keeps its own settings.",
                    "تحتاج الشاشات الخارجية إلى دعم DDC/CI. تُحفظ إعدادات مستقلة لكل شاشة.",
                )
            )
        )
        right.addWidget(self.label(e.t("camera"), True))
        self.cameras = RoundedCombo()
        self.cameras.currentIndexChanged.connect(self.choose_camera)
        right.addWidget(self.cameras)
        self.refresh_button = self.button("refresh", e.refresh_cameras)
        right.addWidget(self.refresh_button)
        right.addWidget(self.label(e.t("live_meter"), True))
        self.reading = self.label("—")
        right.addWidget(self.reading)
        self.exposure = self.label("")
        self.exposure.setObjectName("muted")
        right.addWidget(self.exposure)
        self.check_button = QPushButton(self.tr("Check now", "افحص هسا"))
        self.check_button.clicked.connect(self.check_now)
        right.addWidget(self.check_button)
        preview = ToggleSwitch(
            self.tr(
                "Show latest camera frame (memory only)", "عرض آخر صورة للكاميرا (بالذاكرة فقط)"
            )
        )
        preview.setChecked(e.preview_enabled)
        preview.toggled.connect(self.toggle_preview)
        right.addWidget(preview)
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setVisible(e.preview_enabled)
        right.addWidget(self.preview)
        note = self.label(
            self.tr(
                "Image luminance is not room illuminance. Stability means repeatable readings, not accuracy.",
                "شدة الصورة مش قياس إضاءة الغرفة. الثبات معناه القراءة متكررة، مش إنها دقيقة.",
            )
        )
        note.setObjectName("muted")
        right.addWidget(note)
        right.addWidget(self.label(e.t("privacy_help")))
        right.addWidget(self.label(self.tr("Last minute", "آخر دقيقة"), True))
        self.history_chart = History(self)
        right.addWidget(self.history_chart)
        self.diagnostics_label = self.label("")
        right.addWidget(self.diagnostics_label)
        learn = QPushButton(
            self.tr("Save this brightness for this light", "حفظ هذا السطوع للإضاءة الحالية")
        )
        learn.clicked.connect(self.learn_preference)
        right.addWidget(learn)
        right.addStretch()

    def settings(self, panels):
        e = self.engine
        left, right = self.card(panels), self.card(panels)
        self.locked = []
        left.addWidget(self.label(e.t("personalize"), True))
        left.addWidget(self.label(e.t("language")))
        left.addWidget(
            self.combo(
                [e.t("system") if key == "auto" else value for key, value in LANGUAGES.items()],
                list(LANGUAGES).index(e.preferences["language"]),
                lambda i: self.change_language(list(LANGUAGES)[i]),
            )
        )
        if e.language == "ar":
            left.addWidget(self.label("أسلوب العربية"))
            left.addWidget(
                self.combo(
                    ["الفصحى", "الأردنية", "المصرية", "الخليجية"],
                    ("msa", "jo", "eg", "gulf").index(e.preferences["arabic_dialect"]),
                    self.change_arabic_dialect,
                )
            )
        left.addWidget(self.label(e.t("appearance")))
        preview = QPushButton(self.tr("Preview appearance…", "معاينة المظهر…"))
        preview.clicked.connect(self.preview_appearance)
        left.addWidget(preview)
        left.addWidget(
            self.combo(
                [e.t("system"), e.t("light_mode"), e.t("dark_mode"), e.t("glass_mode")]
                + [self.tr(*name) for name in THEME_NAMES.values()],
                ("auto", "light", "dark", "glass", *THEME_NAMES).index(e.preferences["theme"]),
                lambda i: self.change_theme(("auto", "light", "dark", "glass", *THEME_NAMES)[i]),
            )
        )
        if e.theme == "glass":
            left.addWidget(self.label(self.tr("Glass transparency", "شفافية الزجاج"), True))
            glass_row = QHBoxLayout()
            glass_row.addWidget(self.label(self.tr("Clear", "صافي")))
            self.glass_slider = GlassSlider(Qt.Orientation.Horizontal)
            self.glass_slider.setRange(0, 100)
            self.glass_slider.setValue(e.preferences["glass_tint"])
            self.glass_slider.setAccessibleName(self.tr("Glass tint strength", "شدة تلوين الزجاج"))
            self.glass_slider.valueChanged.connect(self.change_glass_tint)
            glass_row.addWidget(self.glass_slider, 1)
            glass_row.addWidget(self.label(self.tr("Tinted", "ملوّن")))
            left.addLayout(glass_row)
            self.glass_value = self.label("")
            left.addWidget(self.glass_value)
            self.update_glass_label()
            left.addWidget(
                self.label(
                    self.tr(
                        "Clear reveals more of what's behind the window. Tinted adds contrast for easier reading.",
                        "الصافي ببيّن أكثر اللي ورا النافذة. الملوّن بزيد التباين وبيسهّل القراءة.",
                    )
                )
            )
        left.addWidget(self.checkbox("startup", e.startup_choice.get(), self.startup_change))
        left.addWidget(self.label(e.t("startup_help")))
        for key in ("minimize_tray", "close_tray"):
            left.addWidget(
                self.checkbox(
                    key, e.preferences[key], lambda value, k=key: e.set_tray_option(k, value)
                )
            )
        left.addWidget(self.label(e.t("check_interval"), True))
        left.addWidget(self.label(e.t("interval_help")))
        for key, var in (("on_ac", e.interval_ac), ("on_battery", e.interval_battery)):
            left.addWidget(self.label(e.t(key)))
            spin = NoWheelSpinBox()
            spin.setAlignment(
                Qt.AlignmentFlag.AlignAbsolute
                | (
                    Qt.AlignmentFlag.AlignRight
                    if e.language == "ar"
                    else Qt.AlignmentFlag.AlignLeft
                )
            )
            spin.setRange(5, 600)
            spin.setValue(var.get())
            spin.setSuffix(self.tr(" s", " ثانية"))
            spin.valueChanged.connect(
                lambda value, variable=var: self.interval_change(variable, value)
            )
            left.addWidget(spin)
        right.addWidget(self.label(e.t("limits"), True))
        for key, var, minimum, maximum in (
            ("minimum", e.low, 0, 95),
            ("maximum", e.high, 15, 100),
        ):
            right.addWidget(self.label(e.t(key)))
            spin = NoWheelSpinBox()
            spin.setAlignment(
                Qt.AlignmentFlag.AlignAbsolute
                | (
                    Qt.AlignmentFlag.AlignRight
                    if e.language == "ar"
                    else Qt.AlignmentFlag.AlignLeft
                )
            )
            spin.setRange(minimum, maximum)
            spin.setValue(var.get())
            spin.setSuffix("%")
            spin.valueChanged.connect(lambda value, k=key: self.change_limit(k, value))
            right.addWidget(spin)
            self.locked.append(spin)
            if key == "minimum":
                self.low_spin = spin
            else:
                self.high_spin = spin
        restore = self.checkbox("restore_new", e.restore.get(), self.restore_change)
        right.addWidget(restore)
        self.locked.append(restore)
        protect = self.checkbox("protect_dim", e.preferences["protect_dim"], self.protection_change)
        right.addWidget(protect)
        self.locked.append(protect)
        right.addWidget(self.label(e.t("curve"), True))
        response = self.combo(
            [self.tr(v[0], v[1]) for v in CURVES.values()],
            list(CURVES).index(e.preferences["brightness_curve"]),
            self.change_curve,
        )
        right.addWidget(response)
        self.curve = Curve(self)
        right.addWidget(self.curve)
        preview = QPushButton(self.tr("Preview curve", "معاينة المنحنى"))
        preview.clicked.connect(self.preview_curve)
        right.addWidget(preview)
        right.addWidget(
            self.label(
                self.tr(
                    "Selected curve maps the image average to brightness within your limits.",
                    "المنحنى المحدد يربط متوسط الصورة بالسطوع ضمن الحدود التي تختارها.",
                )
            )
        )
        self.tuning_settings(left)
        self.extras_settings(left)
        left.addStretch()
        self.comfort_settings(right)
        for spin in self.findChildren(QSpinBox):
            spin.setAlignment(
                Qt.AlignmentFlag.AlignAbsolute
                | (
                    Qt.AlignmentFlag.AlignRight
                    if e.language == "ar"
                    else Qt.AlignmentFlag.AlignLeft
                )
            )
        right.addStretch()
        self.organize_settings(left, right)

    def option_change(self, key, value):
        self.engine.preferences[key] = value
        self.engine.persist()

    def comfort_settings(self, layout):
        e = self.engine
        layout.addWidget(self.label(self.tr("Comfort and stability", "الراحة والثبات"), True))
        guard = ToggleSwitch(
            self.tr(
                "Ignore brief changes and prevent flicker", "تجاهل التغيّرات العابرة ومنع التذبذب"
            )
        )
        guard.setChecked(e.preferences["stability_guard"])
        guard.toggled.connect(lambda value: self.option_change("stability_guard", value))
        layout.addWidget(guard)
        layout.addWidget(self.label(self.tr("Minimum change (%)", "أصغر تغيير (%)")))
        band = NoWheelSpinBox()
        band.setAlignment(
            Qt.AlignmentFlag.AlignAbsolute
            | (Qt.AlignmentFlag.AlignRight if e.language == "ar" else Qt.AlignmentFlag.AlignLeft)
        )
        band.setRange(1, 10)
        band.setValue(e.preferences["deadband"])
        band.valueChanged.connect(lambda value: self.option_change("deadband", value))
        layout.addWidget(band)
        layout.addWidget(self.label(self.tr("Transition speed", "سرعة الانتقال")))
        layout.addWidget(
            self.combo(
                [
                    self.tr("Calm (8 s)", "هادئ (8 ثوانٍ)"),
                    self.tr("Balanced (4 s)", "متوازن (4 ثوانٍ)"),
                    self.tr("Fast (1 s)", "سريع (ثانية)"),
                ],
                ("calm", "balanced", "fast").index(e.preferences["transition_speed"]),
                lambda i: self.option_change("transition_speed", ("calm", "balanced", "fast")[i]),
            )
        )
        edit = QPushButton(self.tr("Edit your curve", "تعديل منحناك"))
        edit.clicked.connect(self.edit_curve)
        layout.addWidget(edit)
        self.locked.append(edit)
        profile = ToggleSwitch(
            self.tr("Separate AC and battery limits", "حدود منفصلة للشاحن والبطارية")
        )
        profile.setChecked(e.preferences["power_profiles"])
        profile.toggled.connect(lambda value: self.option_change("power_profiles", value))
        layout.addWidget(profile)
        for mode, en, ar in (
            ("ac", "On AC power", "عند توصيل الشاحن"),
            ("battery", "On battery", "على البطارية"),
        ):
            layout.addWidget(self.label(self.tr(en, ar)))
            for index, label in (
                (0, self.tr("Minimum", "الحد الأدنى")),
                (1, self.tr("Maximum", "الحد الأعلى")),
            ):
                layout.addWidget(self.label(label))
                spin = NoWheelSpinBox()
                spin.setAlignment(
                    Qt.AlignmentFlag.AlignAbsolute
                    | (
                        Qt.AlignmentFlag.AlignRight
                        if e.language == "ar"
                        else Qt.AlignmentFlag.AlignLeft
                    )
                )
                spin.setRange(0, 100)
                spin.setSuffix("%")
                spin.setValue(e.preferences[mode + "_limits"][index])
                spin.valueChanged.connect(
                    lambda value, m=mode, i=index: self.profile_change(m, i, value)
                )
                layout.addWidget(spin)

    def profile_change(self, mode, index, value):
        limits = self.engine.preferences[mode + "_limits"][:]
        limits[index] = value
        if limits[0] >= limits[1]:
            QMessageBox.information(
                self,
                self.tr("Limits", "الحدود"),
                self.tr(
                    "Minimum must be below maximum.", "يجب أن يكون الحد الأدنى أقل من الحد الأعلى."
                ),
            )
            self.build()
            return
        self.option_change(mode + "_limits", limits)

    def edit_curve(self):
        if not self.engine.running and not self.engine.busy:
            self.curve_dialog = CurveDialog(self)
            self.curve_dialog.open()

    def learn_preference(self):
        try:
            self.engine.learn_current()
            QMessageBox.information(
                self,
                self.tr("Saved", "تم الحفظ"),
                self.tr("Preference saved to your curve.", "تم حفظ التفضيل في منحناك."),
            )
        except ValueError as exc:
            QMessageBox.information(
                self,
                self.tr("Preference", "التفضيل"),
                self.tr(
                    str(exc),
                    {
                        "Take a fresh light reading first.": "خذ قراءة جديدة للضوء أولًا.",
                        "Wait for the current operation to finish.": "انتظر انتهاء العملية الحالية.",
                        "Choose a reading between the curve endpoints.": "اختر قراءة بين طرفي المنحنى.",
                        "This preference would reverse the curve. Adjust neighboring points first.": "هذا التفضيل يعكس اتجاه المنحنى. عدّل النقاط المجاورة أولًا.",
                    }.get(str(exc), str(exc)),
                ),
            )

    def update_values(self):
        e = self.engine
        self.status_title.setText(e.status_title.get())
        self.status_text.setText(e.status.get())
        self.reason_text.setText(self.brightness_reason())
        if self.page == "home":
            self.save_manual_button.setVisible(e.manual_offer_available())
            self.metric_label.setText(e.display_value.get() + "%")
            mode = (
                self.tr("AUTOMATIC ON", "التلقائي شغّال")
                if e.running
                else self.tr("CHECKING / WORKING", "جاري الفحص")
                if e.busy
                else self.tr("AUTOMATIC OFF — press Start", "التلقائي متوقف — اضغط تشغيل")
            )
            self.mode_label.setText(mode)
            self.mode_label.setStyleSheet(
                "padding: 8px; border-radius: 12px; background: "
                + ("#164c3c" if e.running else "#5d4122")
                + "; color: white;"
            )
            self.check_button.setText(
                self.tr("Check now", "افحص هسا")
                if e.running
                else self.tr("Measure only (brightness unchanged)", "قياس فقط (بدون تغيير السطوع)")
            )
            self.start_button.setEnabled(
                not e.running and not e.busy and not e.pause_reasons and bool(e.devices)
            )
            timed = "timed" in e.pause_reasons
            self.pause_combo.setEnabled(e.running or timed)
            self.resume_button.setVisible(timed)
            self.pause_countdown.setVisible(timed)
            if timed:
                remaining = e.pause_remaining()
                minutes, seconds = divmod(remaining, 60)
                self.pause_countdown.setText(
                    self.tr("Resumes in ", "يُستأنف خلال ") + f"{minutes:02d}:{seconds:02d}"
                )
                self.mode_label.setText(self.tr("AUTOMATIC PAUSED", "السطوع التلقائي متوقف مؤقتًا"))
            self.stop_button.setEnabled(e.running or e.busy or e.resume_pending)
            self.manual_button.setEnabled(not e.running and not e.busy)
            self.manual_slider.setEnabled(not e.running and not e.busy)
            self.refresh_button.setEnabled(not e.running and not e.busy)
            self.check_button.setEnabled(not e.busy and not e.pause_reasons and bool(e.devices))
            self.cameras.setEnabled(not e.running and not e.busy and not e.resume_pending)
            names = e.device_labels()
            if [self.cameras.itemText(i) for i in range(self.cameras.count())] != names:
                self.cameras.blockSignals(True)
                self.cameras.clear()
                self.cameras.addItems(names)
                device = e.selected_device()
                if device:
                    self.cameras.setCurrentIndex(e.devices.index(device))
                self.cameras.blockSignals(False)
            m = e.last_meter
            if m:
                self.reading.setText(
                    self.tr(
                        "Image: {level}/255 · Stability: {quality}%\nTarget: {target}%",
                        "الصورة: {level}/٢٥٥ · الثبات: {quality}%\nالهدف: {target}٪",
                    ).format(
                        level=round(m["level"]),
                        quality=round(m["quality"] * 100),
                        target=m["target"],
                    )
                )
                exposure = m.get("exposure")
                if exposure is not None:
                    self.exposure.setText(
                        self.tr(
                            "Exposure: {value} ms",
                            "التعريض: {value} مللي ثانية",
                        ).format(value=f"{1000 * 2**exposure:.1f}")
                    )
                else:
                    self.exposure.setText(
                        self.tr(
                            "Exposure metadata unavailable. Auto-exposure may mask strong lighting.",
                            "بيانات التعريض مش متاحة. التعريض التلقائي ممكن يخفي الضوء القوي.",
                        )
                    )
                self.preview.setVisible(e.preview_enabled)
                png = m.get("preview")
                if e.preview_enabled and png and self.preview.property("source") != png:
                    data = base64.b64decode(png, validate=True)
                    image = QPixmap()
                    if image.loadFromData(data, "PNG"):
                        self.preview.setPixmap(image)
                        self.preview.setProperty("source", png)
        else:
            for widget in self.locked:
                widget.setEnabled(
                    not e.running and not e.busy and not e.resume_pending and not e.pause_reasons
                )

    def sync(self):
        if not self.root.winfo_exists():
            self.pump.stop()
            self.tray.hide()
            QApplication.instance().quit()
            return
        if (self.engine.language, self.engine.theme, self.page) != self.signature:
            self.build()
        self.update_values()
        self.maybe_wizard()
        if self.page == "settings":
            self.update_label.setText(self.update_message)
            self.update_link.setEnabled(bool(self.pending_update))
        if self.page == "home":
            labels = [
                self.tr("Built-in display", "الشاشة الداخلية")
                if d["id"] == "internal"
                else d["name"]
                for d in self.engine.displays
            ]
            target = self.engine.preferences["display_target"]
            if target not in [d["id"] for d in self.engine.displays]:
                labels.append(
                    self.tr(
                        "Saved display unavailable — refresh",
                        "الشاشة المحفوظة غير متاحة — حدّث القائمة",
                    )
                )
            if labels != [
                self.displays_combo.itemText(i) for i in range(self.displays_combo.count())
            ]:
                self.displays_combo.blockSignals(True)
                self.displays_combo.clear()
                self.displays_combo.addItems(labels)
                self.displays_combo.setCurrentIndex(
                    next(
                        (i for i, d in enumerate(self.engine.displays) if d["id"] == target),
                        len(labels) - 1,
                    )
                )
                self.displays_combo.blockSignals(False)
            self.displays_combo.setEnabled(
                not self.engine.running and not self.engine.busy and not self.engine.resume_pending
            )
            self.displays_refresh.setEnabled(not self.engine.running and not self.engine.busy)
            self.history_chart.update()
            reason = self.engine.diagnostic
            if "timed" in self.engine.pause_reasons:
                message = self.tr(
                    "Automatic mode paused; brightness held and camera stopped.",
                    "الوضع التلقائي متوقف مؤقتًا؛ السطوع محفوظ والكاميرا متوقفة.",
                )
            elif self.engine.controller and time.monotonic() < self.engine.controller.hold_until:
                message = self.tr(
                    "Manual brightness takes priority for three minutes",
                    "السطوع اليدوي له الأولوية لمدة ثلاث دقائق",
                )
            else:
                message = self.tr(
                    *DIAGNOSTICS.get(reason, ("Ready for a light reading", "جاهز لقراءة الضوء"))
                )
            self.diagnostics_label.setText(message)

    def glass_alpha(self, clear, tinted):
        return round(clear + (tinted - clear) * self.engine.preferences["glass_tint"] / 100)

    def update_glass_label(self):
        value = 100 - self.engine.preferences["glass_tint"]
        self.glass_value.setText(
            self.tr("Transparency: {value}%", "الشفافية: {value}%").format(value=value)
        )

    def change_glass_tint(self, value):
        self.engine.preferences["glass_tint"] = value
        self.glass_save.start(180)
        self.update_glass_label()
        self.repaint_surfaces()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Clear alpha pixels too when changing themes, so old glass rims cannot remain.
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.fillRect(self.rect(), Qt.GlobalColor.transparent)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 18, 18)
        if self.engine.theme == "glass":
            # Keep transparency even when compositor blur is unavailable.
            color = QColor(10, 20, 30, self.glass_alpha(8, 125))
            painter.fillPath(path, color)
        else:
            painter.fillPath(path, QColor(self.engine.palette["bg"]))

    def repaint_surfaces(self):
        for surface in self.findChildren(Surface):
            surface.update()

    def resizeEvent(self, event):
        if hasattr(self, "panels"):
            self.panels.setDirection(
                QBoxLayout.Direction.TopToBottom
                if self.width() < 900
                else QBoxLayout.Direction.LeftToRight
            )
        # Clip the native client too, avoiding a square compositor fringe.
        outline = QPainterPath()
        outline.addRoundedRect(QRectF(self.rect()), 18, 18)
        self.setMask(QRegion(outline.toFillPolygon().toPolygon()))
        self.repaint_surfaces()
        super().resizeEvent(event)

    def toggle_maximize(self):
        if self.expanded or self.isMaximized() or self.isFullScreen():
            self.showNormal()
            if self.restore_geometry is not None:
                self.setGeometry(self.restore_geometry)
            self.expanded = False
        else:
            self.restore_geometry = self.geometry()
            self.showNormal()
            self.setGeometry(self.screen().availableGeometry())
            self.expanded = True

    def resize_edges(self, position):
        edges = Qt.Edge(0)
        if position.x() < 8:
            edges |= Qt.Edge.LeftEdge
        if position.x() > self.width() - 8:
            edges |= Qt.Edge.RightEdge
        if position.y() < 8:
            edges |= Qt.Edge.TopEdge
        if position.y() > self.height() - 8:
            edges |= Qt.Edge.BottomEdge
        return edges

    def mousePressEvent(self, event):
        edges = self.resize_edges(event.position())
        if event.button() == Qt.MouseButton.LeftButton and edges and self.windowHandle():
            self.windowHandle().startSystemResize(edges)
        else:
            super().mousePressEvent(event)

    def toggle_page(self):
        self.page = "settings" if self.page == "home" else "home"
        self.build()

    def change_arabic_dialect(self, index):
        self.engine.preferences["arabic_dialect"] = ("msa", "jo", "eg", "gulf")[index]
        self.engine.persist()
        self.engine.render_status()
        self.build()

    def change_language(self, mode):
        self.engine.change_language(mode)
        self.build()

    def change_theme(self, mode):
        self.engine.change_theme(mode)
        self.build()

    def language_menu(self):
        if hasattr(self, "language_popup"):
            self.language_popup.deleteLater()
        menu = GlassMenu(self)
        self.language_popup = menu
        menu.setLayoutDirection(self.layoutDirection())
        for mode, key in LANGUAGES.items():
            action = menu.addAction(self.engine.t("system") if mode == "auto" else key)
            action.setCheckable(True)
            action.setChecked(self.engine.preferences["language"] == mode)
            action.triggered.connect(lambda checked, m=mode: self.change_language(m))
        anchor = self.language_button.mapToGlobal(QPoint(0, self.language_button.height() + 6))
        size = menu.sizeHint()
        if self.layoutDirection() == Qt.LayoutDirection.RightToLeft:
            anchor.setX(anchor.x() + self.language_button.width() - size.width())
        area = self.language_button.screen().availableGeometry()
        anchor.setX(max(area.left(), min(anchor.x(), area.right() - size.width() + 1)))
        anchor.setY(max(area.top(), min(anchor.y(), area.bottom() - size.height() + 1)))
        menu.popup(anchor)

    def choose_camera(self, index):
        if 0 <= index < len(self.engine.devices):
            self.engine.choose_device(self.engine.devices[index])

    def change_limit(self, key, value):
        e = self.engine
        if key == "minimum":
            e.low.set(min(value, e.high.get() - 1))
            self.low_spin.blockSignals(True)
            self.low_spin.setValue(e.low.get())
            self.low_spin.blockSignals(False)
        else:
            e.high.set(max(value, e.low.get() + 1))
            self.high_spin.blockSignals(True)
            self.high_spin.setValue(e.high.get())
            self.high_spin.blockSignals(False)
        e.persist()
        self.curve.update()

    def change_curve(self, index):
        key = list(CURVES)[index]
        self.engine.preferences["brightness_curve"] = key
        if self.engine.controller:
            self.engine.controller.image_curve = key
        self.engine.persist()
        self.curve.update()

    def interval_change(self, var, value):
        var.set(value)
        self.engine.interval_changed()

    def startup_change(self, value):
        self.engine.startup_choice.set(value)
        self.engine.toggle_startup()

    def protection_change(self, value):
        self.engine.preferences["protect_dim"] = value
        self.engine.persist()

    def restore_change(self, value):
        self.engine.restore.set(value)
        self.engine.persist()

    def manual(self):
        self.engine.manual_value.set(self.manual_slider.value())
        self.engine.apply_manual()

    def toggle_preview(self, value):
        self.engine.preview_enabled = value
        self.preview.setVisible(value)
        if not value:
            self.preview.clear()
            self.preview.setProperty("source", None)
            if self.engine.last_meter:
                self.engine.last_meter.pop("preview", None)

    def check_now(self):
        e = self.engine
        if e.pause_reasons or e.busy or not e.selected_device():
            return
        if e.running:
            if e.timer is not None:
                e.root.after_cancel(e.timer)
            e.timer = None
            e.tick()
        else:
            e.cancel.clear()
            index = e.selected_device()["index"]

            def done(result):
                m, current = result
                e.performance.capture(m)
                e.display_value.set(str(current))
                e.last_meter = dict(
                    level=m["level"],
                    quality=m["confidence"],
                    target=custom_target(
                        m["level"], e.low.get(), e.high.get(), e.preferences["custom_points"]
                    )
                    if e.preferences["brightness_curve"] == "custom"
                    else image_target(
                        m["level"], e.low.get(), e.high.get(), e.preferences["brightness_curve"]
                    ),
                    current=current,
                    exposure=m.get("exposure"),
                    exposure_corrected=m.get("exposure_corrected"),
                    preview=m.get("preview") if e.preview_enabled else None,
                )

                e.update_meter()

            from .brightness import brightness

            e.work(
                lambda: (
                    sample(
                        index,
                        e.cancel,
                        preview=e.preview_enabled,
                        region=e.preferences["meter_region"],
                        **({"protection": True} if e.preferences.get("spatial_protection") else {}),
                    ),
                    brightness(),
                ),
                done,
                "measure",
            )

    def update_tray_menu(self):
        if hasattr(self, "tray_menu"):
            self.tray_menu.deleteLater()
        menu = GlassMenu(self)
        self.tray_menu = menu
        for key, callback in (
            ("show", self.restore_window),
            ("stop", self.engine.stop),
            ("exit", self.exit_app),
        ):
            action = menu.addAction(self.engine.t(key))
            action.triggered.connect(callback)
        menu.addSeparator()
        pause_actions = []
        for minutes in (15, 30, 60):
            action = menu.addAction(
                self.tr("Pause for {minutes} minutes", "إيقاف مؤقت لمدة {minutes} دقيقة").format(
                    minutes=minutes
                )
            )
            action.triggered.connect(lambda checked=False, m=minutes: self.engine.pause_for(m))
            pause_actions.append(action)
        action = menu.addAction(self.tr("Resume now", "استئناف الآن"))
        action.triggered.connect(self.engine.resume_now)
        resume_action = action

        def refresh_pause_actions():
            for item in pause_actions:
                item.setEnabled(self.engine.running or "timed" in self.engine.pause_reasons)
            resume_action.setEnabled("timed" in self.engine.pause_reasons)

        menu.aboutToShow.connect(refresh_pause_actions)
        refresh_pause_actions()
        self.tray.setContextMenu(menu)
        self.tray.setToolTip(self.engine.t("app"))

    def restore_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()
        self.tray.hide()

    def tray_activate(self, reason):
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.restore_window()

    def hide_to_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            QMessageBox.information(self, self.engine.t("app"), self.engine.t("tray_missing"))
            return
        self.tray.show()
        self.hide()

    def changeEvent(self, event):
        if self.isMinimized() and self.engine.preferences["minimize_tray"]:
            self.hide_to_tray()
        super().changeEvent(event)

    def choose_display(self, index):
        if not 0 <= index < len(self.engine.displays):
            return
        try:
            self.engine.select_display(self.engine.displays[index]["id"])
            self.build()
        except ValueError as error:
            self.message_error(error)

    def shortcut_toggle(self):
        if self.engine.running or self.engine.resume_pending:
            self.engine.stop()
        elif not self.engine.busy and not self.engine.pause_reasons:
            self.engine.start()

    def shortcuts_change(self, value):
        self.option_change("shortcuts_enabled", value)
        self.configure_shortcuts()

    def configure_shortcuts(self):
        desired = self.engine.preferences["shortcuts_enabled"]
        if (desired and len(self.shortcut_keys) == 2) or (not desired and not self.shortcut_keys):
            return
        try:
            user = ctypes.windll.user32
            user.RegisterHotKey.argtypes = [
                ctypes.c_void_p,
                ctypes.c_int,
                ctypes.c_uint,
                ctypes.c_uint,
            ]
            user.RegisterHotKey.restype = ctypes.c_int
            user.UnregisterHotKey.argtypes = [ctypes.c_void_p, ctypes.c_int]
            for key in self.shortcut_keys:
                user.UnregisterHotKey(ctypes.c_void_p(int(self.winId())), key)
            self.shortcut_keys = []
            if not self.engine.preferences["shortcuts_enabled"]:
                return
            for key, vk in ((0xAB01, 0x42), (0xAB02, 0x4F)):
                if not user.RegisterHotKey(ctypes.c_void_p(int(self.winId())), key, 0x4003, vk):
                    for active in self.shortcut_keys:
                        user.UnregisterHotKey(ctypes.c_void_p(int(self.winId())), active)
                    self.shortcut_keys = []
                    self.shortcut_status = self.tr(
                        "Shortcut already used by another app.", "الاختصار مستخدم في تطبيق آخر."
                    )
                    self.engine.preferences["shortcuts_enabled"] = False
                    self.engine.persist()
                    QMessageBox.information(
                        self,
                        self.tr("Keyboard shortcuts", "اختصارات لوحة المفاتيح"),
                        self.shortcut_status,
                    )
                    return
                self.shortcut_keys.append(key)
        except (AttributeError, OSError):
            self.shortcut_keys = []

    def nativeEvent(self, event_type, message):
        from ctypes import wintypes

        try:
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == 0x312:
                if msg.wParam == 0xAB01:
                    self.shortcut_toggle()
                elif msg.wParam == 0xAB02:
                    self.restore_window()
            if msg.message == 0x2B1 and msg.wParam in (7, 8):
                self.engine.session_pause("lock", msg.wParam == 7)
            elif msg.message == 0x218:
                if msg.wParam == 4:
                    self.engine.session_pause("sleep", True)
                elif msg.wParam in (6, 7, 18):
                    self.engine.session_pause("sleep", False)
        except (TypeError, ValueError):
            pass
        return super().nativeEvent(event_type, message)

    def exit_app(self):
        if not self.closing:
            self.closing = True
            self.engine.resume_pending = False
            for key in self.shortcut_keys:
                ctypes.windll.user32.UnregisterHotKey(ctypes.c_void_p(int(self.winId())), key)
            self.shortcut_keys = []
            if self.session_registered:
                api = ctypes.windll.wtsapi32.WTSUnRegisterSessionNotification
                api.argtypes = [ctypes.c_void_p]
                api(ctypes.c_void_p(int(self.winId())))
                self.session_registered = False
            self.setEnabled(False)
            if self.glass_save.isActive():
                self.glass_save.stop()
                self.engine.persist()
            self.engine.close()

    def closeEvent(self, event):
        event.ignore()
        if self.engine.preferences["close_tray"] and not self.closing:
            self.hide_to_tray()
        else:
            self.exit_app()


def run_desktop(root):
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setQuitOnLastWindowClosed(False)
    window = Window(root, root._brightness_backend)
    window.show()
    # Keep the bounded dispatcher needed by this Windows runtime, but wake on
    # input/timers instead of imposing a fixed 35 ms frame delay.
    waiter = None
    if sys.platform == "win32":
        waiter = ctypes.WinDLL("user32").MsgWaitForMultipleObjectsEx
        waiter.argtypes = [
            ctypes.c_uint,
            ctypes.c_void_p,
            ctypes.c_uint,
            ctypes.c_uint,
            ctypes.c_uint,
        ]
        waiter.restype = ctypes.c_uint
    while root.winfo_exists():
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 4)
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        if waiter:
            # QS_ALLINPUT / MWMO_INPUTAVAILABLE: native messages wake immediately.
            waiter(0, None, 4 if window.isVisible() else 30, 0x04FF, 0x0004)
        else:
            time.sleep(0.004 if window.isVisible() else 0.03)
    window.pump.stop()
    window.tray.hide()
    window.hide()
