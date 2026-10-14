"""Review-only diagnostic preview and explicit settings-backup restoration."""

import json
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QPlainTextEdit,
    QFileDialog,
    QMessageBox,
)
from pathlib import Path


class DiagnosticDialog(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.engine = window.engine
        self.setLayoutDirection(window.layoutDirection())
        self.setStyleSheet(
            "QDialog {background:#20242b;} QPlainTextEdit {background:#151a22;color:#eeeeee;border-radius:8px;padding:8px;}"
        )
        self.setWindowTitle(window.tr("Diagnostic report", "تقرير التشخيص"))
        self.resize(680, 520)
        layout = QVBoxLayout(self)
        layout.addWidget(
            window.label(
                window.tr(
                    "Review before saving. No images, device names, paths, or raw error messages are included. Nothing is sent automatically.",
                    "عاين التقرير قبل حفظه. لا يتضمن صورًا أو أسماء أجهزة أو مسارات أو رسائل خطأ خامًا. لا يُرسل شيء تلقائيًا.",
                )
            )
        )
        from .recovery import diagnostic_report
        from . import __version__

        self.document = diagnostic_report(window.engine, __version__)
        self.preview = QPlainTextEdit(json.dumps(self.document, ensure_ascii=False, indent=2))
        self.preview.setReadOnly(True)
        self.preview.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        layout.addWidget(self.preview)
        row = QHBoxLayout()
        layout.addLayout(row)
        save = QPushButton(window.tr("Save report", "حفظ التقرير"))
        save.clicked.connect(self.save)
        row.addWidget(save)
        close = QPushButton(window.tr("Close", "إغلاق"))
        close.clicked.connect(self.reject)
        row.addWidget(close)

    def save(self):
        file, _ = QFileDialog.getSaveFileName(
            self,
            self.window.tr("Save report", "حفظ التقرير"),
            "AutoBrightness-diagnostics.json",
            "JSON (*.json)",
        )
        if not file:
            return
        try:
            Path(file).write_text(self.preview.toPlainText(), encoding="utf-8")
        except OSError as error:
            self.window.message_error(error)


class BackupDialog(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.engine = window.engine
        self.setLayoutDirection(window.layoutDirection())
        self.setStyleSheet("QDialog {background:#20242b;}")
        self.setWindowTitle(window.tr("Restore a backup", "استعادة نسخة احتياطية"))
        self.resize(580, 320)
        layout = QVBoxLayout(self)
        layout.addWidget(
            window.label(
                window.tr(
                    "The last 10 settings changes are backed up locally. Restore keeps current camera, display, and sign-in startup choices.",
                    "تُحفظ آخر 10 تغييرات للإعدادات محليًا. تحافظ الاستعادة على اختيار الكاميرا والشاشة والتشغيل عند تسجيل الدخول.",
                )
            )
        )
        from .recovery import list_backups

        self.rows = list_backups(window.engine.directory)
        from .qt_ui import RoundedCombo

        self.combo = RoundedCombo()
        layout.addWidget(self.combo)
        for row in self.rows:
            self.combo.addItem(
                row["created_utc"][:19].replace("T", " ")
                + " UTC · "
                + str(row["low"])
                + "% – "
                + str(row["high"])
                + "%"
            )
        if not self.rows:
            layout.addWidget(
                window.label(window.tr("No backups available yet.", "لا توجد نسخ احتياطية بعد."))
            )
        restore = QPushButton(window.tr("Restore selected backup", "استعادة النسخة المختارة"))
        restore.setEnabled(bool(self.rows))
        restore.clicked.connect(self.restore)
        layout.addWidget(restore)
        close = QPushButton(window.tr("Close", "إغلاق"))
        close.clicked.connect(self.reject)
        layout.addWidget(close)

    def restore(self):
        e = self.window.engine
        if e.running or e.busy or e.resume_pending:
            return
        index = self.combo.currentIndex()
        if not 0 <= index < len(self.rows):
            return
        from .recovery import restore_preferences

        try:
            settings = restore_preferences(e.directory, self.rows[index]["name"], e.preferences)
            question = (
                self.window.tr(
                    "Restore this backup? Current settings will also be backed up.",
                    "هل تريد استعادة هذه النسخة؟ ستُحفظ نسخة من الإعدادات الحالية أيضًا.",
                )
                + f"\n{settings['low']}% – {settings['high']}%"
            )
            if (
                QMessageBox.question(
                    self, self.window.tr("Restore a backup", "استعادة نسخة احتياطية"), question
                )
                != QMessageBox.StandardButton.Yes
            ):
                return
            e.apply_preferences(settings)
            self.accept()
            self.window.build()
        except (OSError, ValueError) as error:
            self.window.message_error(error)
