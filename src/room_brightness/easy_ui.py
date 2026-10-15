"""Searchable basic/advanced settings and a hardware-free curve preview."""

import copy
import unicodedata
from types import SimpleNamespace
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QAbstractButton,
    QComboBox,
    QLineEdit,
    QPushButton,
    QDialog,
    QHBoxLayout,
)
from .adaptive import image_target
from .comfort import target


def search_key(text):
    return "".join(
        character
        for character in unicodedata.normalize("NFKD", text.casefold())
        if not unicodedata.combining(character)
    ).translate(str.maketrans({"ى": "ي", "ة": "ه", "ـ": ""}))


class CurvePreview(QDialog):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        original = owner.engine
        low, high = (
            (original.controller.low, original.controller.high)
            if original.running and original.controller
            else (original.low.get(), original.high.get())
        )
        from .qt_engine import Value

        self.engine = SimpleNamespace(
            preferences=copy.deepcopy(original.preferences),
            low=Value(low),
            high=Value(high),
            language=original.language,
            theme=original.theme,
            palette=original.palette.copy(),
        )
        self.setLayoutDirection(owner.layoutDirection())
        self.setStyleSheet("QDialog {background:#20242b;}")
        self.setWindowTitle(self.tr("Preview curve", "معاينة المنحنى"))
        self.resize(580, 390)
        layout = QVBoxLayout(self)
        layout.addWidget(
            owner.label(
                self.tr(
                    "Try an image reading. This preview never changes screen brightness or settings.",
                    "جرّب قراءة للصورة. لا تغيّر هذه المعاينة سطوع الشاشة أو الإعدادات.",
                )
            )
        )
        from .qt_ui import Curve, GlassSlider, NoWheelSpinBox

        layout.addWidget(Curve(self))
        layout.addWidget(owner.label(self.tr("Image reading (0–255)", "قراءة الصورة (0–255)")))
        row = QHBoxLayout()
        layout.addLayout(row)
        self.slider = GlassSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 255)
        row.addWidget(self.slider, 1)
        self.input = NoWheelSpinBox()
        self.input.setRange(0, 255)
        self.input.setAlignment(
            Qt.AlignmentFlag.AlignAbsolute
            | (
                Qt.AlignmentFlag.AlignRight
                if original.language == "ar"
                else Qt.AlignmentFlag.AlignLeft
            )
        )
        row.addWidget(self.input)
        self.result = owner.label("", True)
        layout.addWidget(self.result)
        layout.addWidget(
            owner.label(
                self.tr(
                    "Curve target before stability confirmation and manual holds.",
                    "هدف المنحنى قبل تأكيد الثبات وأولوية السطوع اليدوي.",
                )
            )
        )
        self.slider.valueChanged.connect(self.input.setValue)
        self.input.valueChanged.connect(self.update_value)
        self.input.setValue(20)
        self.update_value(20)
        close = QPushButton(self.tr("Close", "إغلاق"))
        close.clicked.connect(self.accept)
        layout.addWidget(close)

    def tr(self, en, ar=None):
        return self.owner.tr(en, ar or en)

    def update_value(self, value):
        self.slider.blockSignals(True)
        self.slider.setValue(value)
        self.slider.blockSignals(False)
        e = self.engine
        curve = e.preferences["brightness_curve"]
        wanted = (
            target(value, e.low.get(), e.high.get(), e.preferences["custom_points"])
            if curve == "custom"
            else image_target(value, e.low.get(), e.high.get(), curve)
        )
        self.target_value = wanted
        self.result.setText(
            self.tr("Preview brightness: ", "السطوع في المعاينة: ") + str(wanted) + "%"
        )


class EasyMixin:
    def preview_curve(self):
        self.curve_preview = CurvePreview(self)
        self.curve_preview.open()

    def organize_settings(self, left, right):
        self.settings_sections = []
        advanced = {
            self.tr("Setup and tools", "الإعداد والأدوات"),
            self.tr("Usage profiles", "ملفات الاستخدام"),
            self.tr("Power saving", "توفير الطاقة"),
            self.tr("Updates", "التحديثات"),
            self.tr("Comfort and stability", "الراحة والثبات"),
        }
        for layout in (left, right):
            items = []
            while layout.count():
                items.append(layout.takeAt(0))
            groups = []
            group = []
            for item in items:
                if item.spacerItem():
                    continue
                widget = item.widget()
                if widget is not None and widget.objectName() == "heading" and group:
                    groups.append(group)
                    group = []
                group.append(item)
            if group:
                groups.append(group)
            for group in groups:
                section = QWidget()
                inner = QVBoxLayout(section)
                inner.setContentsMargins(0, 0, 0, 0)
                inner.setSpacing(12)
                title = group[0].widget().text() if isinstance(group[0].widget(), QLabel) else ""
                for item in group:
                    if item.widget() is not None:
                        inner.addWidget(item.widget())
                    elif item.layout() is not None:
                        child = item.layout()
                        child.setParent(None)
                        inner.addLayout(child)
                layout.addWidget(section)
                words = [title]
                for widget in section.findChildren(QWidget):
                    if isinstance(widget, (QLabel, QAbstractButton)):
                        words.append(widget.text())
                    elif isinstance(widget, QComboBox):
                        words.extend(widget.itemText(i) for i in range(widget.count()))
                self.settings_sections.append(
                    (section, title in advanced, search_key(" ".join(words)), layout.parentWidget())
                )
            layout.addStretch()
        self.settings_search = QLineEdit()
        self.settings_search.setObjectName("settingsSearch")
        self.settings_search.setPlaceholderText(self.tr("Search settings…", "البحث في الإعدادات…"))
        self.settings_search.setClearButtonEnabled(True)
        self.settings_search.setText(self.settings_query)
        self.settings_search.textChanged.connect(self.filter_settings)
        self.content_layout.insertWidget(0, self.settings_search)
        self.advanced_button = QPushButton()
        self.advanced_button.setCheckable(True)
        self.advanced_button.setChecked(self.advanced_visible)
        self.advanced_button.toggled.connect(self.toggle_advanced)
        self.content_layout.insertWidget(1, self.advanced_button)
        self.settings_no_results = self.label(
            self.tr("No matching settings.", "لا توجد إعدادات مطابقة.")
        )
        self.content_layout.insertWidget(2, self.settings_no_results)
        self.filter_settings(self.settings_query)

    def toggle_advanced(self, value):
        self.advanced_visible = value
        self.filter_settings(self.settings_query)

    def filter_settings(self, text):
        self.settings_query = text
        query = search_key(text.strip())
        visible = 0
        surfaces = {}
        for section, advanced, terms, surface in self.settings_sections:
            show = query in terms if query else not advanced or self.advanced_visible
            section.setVisible(show)
            visible += int(show)
            surfaces[surface] = surfaces.get(surface, False) or show
        for surface, show in surfaces.items():
            surface.setVisible(show)
        self.settings_no_results.setVisible(not visible)
        self.advanced_button.setText(
            self.tr("Hide advanced settings", "إخفاء الإعدادات المتقدمة")
            if self.advanced_visible
            else self.tr("Show advanced settings", "عرض الإعدادات المتقدمة")
        )

    def pause_for(self, index):
        if index <= 0:
            return
        self.engine.pause_for((15, 30, 60)[index - 1])
        self.pause_combo.blockSignals(True)
        self.pause_combo.setCurrentIndex(0)
        self.pause_combo.blockSignals(False)
