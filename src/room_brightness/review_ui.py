"""Categorized settings, independently configured displays and reviewed suggestions."""

import copy
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QPushButton, QLabel, QTabWidget, QVBoxLayout, QWidget
from .tuning_ui import ToolDialog, CompareDialog
from .comfort_ui import CurveEditor
from .comfort import valid_points
from .adaptive import CURVES
from .easy_ui import search_key, EasyMixin


class DisplaysDialog(ToolDialog):
    def __init__(self, window):
        super().__init__(window, ("Multiple displays", "الشاشات المتعددة"))
        from .qt_ui import ToggleSwitch, NoWheelSpinBox

        self.resize(640, 720)
        self.snapshot = copy.deepcopy(self.engine.preferences)
        self.profiles = copy.deepcopy(self.snapshot["display_profiles"])
        self.devices = [
            copy.deepcopy(display)
            for display in self.engine.displays
            if display["id"] != self.snapshot["display_target"]
        ]
        self.identity = self.devices[0]["id"] if self.devices else None
        self.enabled = ToggleSwitch(
            window.tr("Control selected additional displays", "التحكم بالشاشات الإضافية المحددة")
        )
        self.enabled.setChecked(self.snapshot["multi_display_enabled"])
        self.box.addWidget(self.enabled)
        self.text(
            "Refresh displays first. Select up to four additional screens; each has independent limits/curve and manual priority. The main selected display still uses Home settings. Start briefly verifies each screen (+5 and restore), then applies targets serially in the same camera cycle. Unsupported/unplugged screens do not redirect to another device.",
            "حدّث قائمة الشاشات أولًا. اختر حتى أربع شاشات إضافية؛ لكل منها حدود ومنحنى وأولوية يدوية مستقلة. تبقى إعدادات الرئيسية للشاشة الأساسية. يُختبر التحكم مؤقتًا بمقدار5ثم الاستعادة، وتُطبق الأهداف بالتسلسل ضمن دورة الكاميرا نفسها. لا يُختار بديل للشاشة غير المدعومة أو المفصولة.",
        )
        self.selected = {}
        for display in self.devices:
            if display["id"] == self.snapshot["display_target"]:
                continue
            check = ToggleSwitch(display["name"])
            check.setChecked(display["id"] in self.snapshot["multi_display_targets"])
            self.selected[display["id"]] = check
            self.box.addWidget(check)
        self.choice = window.combo([display["name"] for display in self.devices], 0, self.switch)
        self.box.addWidget(self.choice)
        self.low = NoWheelSpinBox()
        self.high = NoWheelSpinBox()
        for field in (self.low, self.high):
            field.setRange(0, 100)
            field.setSuffix("%")
            field.setAlignment(
                Qt.AlignmentFlag.AlignAbsolute
                | (
                    Qt.AlignmentFlag.AlignRight
                    if self.engine.language == "ar"
                    else Qt.AlignmentFlag.AlignLeft
                )
            )
        self.text("Minimum / maximum for this display", "أدنى وأعلى سطوع لهذه الشاشة")
        self.box.addWidget(self.low)
        self.box.addWidget(self.high)
        self.keys = tuple(CURVES)
        self.curve = window.combo(
            [window.tr(v[0], v[1]) for v in CURVES.values()], 0, lambda _: None
        )
        self.box.addWidget(self.curve)
        self.editor = CurveEditor(self.snapshot["custom_points"])
        self.box.addWidget(self.editor)
        self.button("Add point", "إضافة نقطة", self.editor.add_point)
        self.button("Remove selected point", "حذف النقطة المحددة", self.editor.remove_point)
        self.text(
            "Point editor applies to Your curve. These additional-screen settings use fixed limits and one curve; the selected main screen retains its power curves.",
            "يخص محرر النقاط «منحناك». تستخدم الشاشات الإضافية هنا حدودًا ثابتة ومنحنى واحدًا؛ وتحتفظ الشاشة الأساسية بمنحنيات الطاقة الخاصة بها.",
        )
        self.button("Save display choices", "حفظ اختيارات الشاشات", self.save)
        self.button("Cancel", "إلغاء", self.reject)
        self.load()
        scroll_tools(self)

    def stash(self):
        if self.identity is None:
            return
        profile = copy.deepcopy(self.profiles.get(self.identity, {}))
        profile.update(
            low=self.low.value(),
            high=self.high.value(),
            brightness_curve=self.keys[self.curve.currentIndex()],
            custom_points=copy.deepcopy(self.editor.points),
            separate_power_curves=False,
            power_profiles=False,
        )
        self.profiles[self.identity] = profile

    def load(self):
        profile = self.profiles.get(self.identity, self.snapshot)
        self.low.setValue(profile.get("low", 10))
        self.high.setValue(profile.get("high", 80))
        self.curve.setCurrentIndex(self.keys.index(profile.get("brightness_curve", "custom")))
        self.editor.points = copy.deepcopy(
            profile.get("custom_points", self.snapshot["custom_points"])
        )
        self.editor.selected = None
        self.editor.update()

    def switch(self, index):
        if not 0 <= index < len(self.devices):
            return
        self.stash()
        self.identity = self.devices[index]["id"]
        self.load()

    def save(self):
        self.stash()
        selected = [identity for identity, check in self.selected.items() if check.isChecked()]
        if len(selected) > 4:
            return
        for profile in self.profiles.values():
            if not profile.get("low", 10) < profile.get("high", 80) or not valid_points(
                profile.get("custom_points", self.snapshot["custom_points"])
            ):
                return
        candidate = copy.deepcopy(self.snapshot)
        candidate.update(
            display_profiles=self.profiles,
            multi_display_enabled=self.enabled.isChecked(),
            multi_display_targets=selected,
        )
        # Primary settings must stay consistent with its existing select-display profile behavior.
        if self.identity == candidate["display_target"]:
            candidate.update(self.profiles[self.identity])
        self.save_candidate(candidate)


def scroll_tools(dialog):
    from PySide6.QtWidgets import QScrollArea

    content = QWidget()
    content.setObjectName("toolContent")
    box = QVBoxLayout(content)
    while dialog.box.count():
        item = dialog.box.takeAt(0)
        if item.widget():
            box.addWidget(item.widget())
        else:
            box.addItem(item)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setWidget(content)
    scroll.setStyleSheet(
        "QScrollArea {border:none;background:#20242b;} QWidget#toolContent {background:#20242b;}"
    )
    dialog.box.addWidget(scroll)


class SuggestionsDialog(ToolDialog):
    def __init__(self, window):
        super().__init__(window, ("Preference suggestions", "اقتراحات التفضيلات"))
        self.text(
            "Evidence stays in this session. Three independent manual adjustments, at least 30s apart and at similar reliable light levels, are required. Nothing changes automatically. Suggestions are separated by camera, main display and power source, and require a custom curve.",
            "تبقى الأدلة في هذه الجلسة فقط. يلزم ثلاثة تعديلات يدوية مستقلة يفصل بينها30ثانية على الأقل، عند قراءات إضاءة موثوقة ومتشابهة. لا يتغير شيء تلقائيًا. تُفصل الاقتراحات حسب الكاميرا والشاشة الأساسية ومصدر الطاقة، وتتطلب منحنى مخصصًا.",
        )
        self.message = self.text("", "")
        self.button("Review suggested curve", "معاينة المنحنى المقترح", self.review)
        self.button("Clear collected evidence", "مسح الأدلة المجمعة", self.clear)
        self.button("Close", "إغلاق", self.reject)

    def review(self):
        points = self.engine.suggested_curve()
        if points is None:
            self.message.setText(
                self.window.tr(
                    "Not enough consistent evidence, or no valid improvement yet.",
                    "لا توجد أدلة متسقة كافية أو تحسين صالح حتى الآن.",
                )
            )
            return
        self.comparison = CompareDialog(self.window, points)
        self.comparison.open()
        self.accept()

    def clear(self):
        from .quality import PreferenceEvidence

        self.engine.preference_evidence = PreferenceEvidence()
        self.message.setText(self.window.tr("Evidence cleared.", "مُسحت الأدلة."))


class HelpDialog(ToolDialog):
    def __init__(self, window):
        super().__init__(window, ("Control status and help", "حالة التحكم والمساعدة"))
        self.message = self.text("", "")
        self.text(
            "Camera: close other camera apps and check Windows camera permissions. External screens: enable DDC/CI in the screen menu and check cable/dock support. Internal screen: update the display driver. A failed restoration requires manual brightness correction.",
            "الكاميرا: أغلق تطبيقات التصوير الأخرى وتحقق من أذونات ويندوز. الشاشة الخارجية: فعّل DDC/CI من قائمة الشاشة وتحقق من دعم الكابل أو المحوّل. الشاشة الداخلية: حدّث برنامج العرض. عند فشل الاستعادة، أعد السطوع يدويًا.",
        )
        self.button("Close", "إغلاق", self.reject)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(1000)
        self.finished.connect(self.timer.stop)
        self.refresh()

    def refresh(self):
        lines = [self.window.brightness_reason()]
        if self.engine.diagnostic in ("camera_error", "display_error", "camera_retry"):
            category = (
                self.engine.health_events[-1]["category"]
                if self.engine.health_events
                else "unknown"
            )
            reasons = {
                "permission_denied": (
                    "Windows denied access. Check the relevant privacy/policy permissions before retrying.",
                    "رفض ويندوز الوصول. تحقق من أذونات الخصوصية أو السياسة المناسبة قبل إعادة المحاولة.",
                ),
                "camera_disconnected": (
                    "The selected camera was disconnected/reordered. Reconnect it and refresh cameras.",
                    "فُصلت الكاميرا المحددة أو تغيّر ترتيبها. أعد توصيلها وحدّث قائمة الكاميرات.",
                ),
                "camera_unavailable": (
                    "Camera unavailable or busy. Close camera apps, check permissions and refresh.",
                    "الكاميرا غير متاحة أو مشغولة. أغلق تطبيقات التصوير وتحقق من الأذونات وحدّث القائمة.",
                ),
                "camera_timeout": (
                    "The camera did not respond in time. Reconnect it and close other camera apps.",
                    "لم تستجب الكاميرا في المهلة. أعد توصيلها وأغلق تطبيقات التصوير الأخرى.",
                ),
                "brightness_verification_failed": (
                    "Requested and measured brightness did not match. Stop and restore brightness manually if needed; check the display driver.",
                    "لم يتطابق السطوع المطلوب والمقاس. أوقف التشغيل وأعد السطوع يدويًا عند الحاجة، وتحقق من برنامج العرض.",
                ),
                "brightness_restore_failed": (
                    "Brightness could not be restored. Restore it manually before restarting automatic mode.",
                    "تعذّرت استعادة السطوع. أعده يدويًا قبل إعادة تشغيل الوضع التلقائي.",
                ),
                "display_unavailable": (
                    "Display unavailable. Check its cable/dock and enable DDC/CI for an external screen.",
                    "الشاشة غير متاحة. تحقق من الكابل أو المحوّل وفعّل DDC/CI للشاشة الخارجية.",
                ),
            }
            lines.append(
                self.window.tr(
                    *reasons.get(
                        category,
                        (
                            "Display control could not finish. Check the driver and connection.",
                            "لم يكتمل التحكم بالشاشة. تحقق من برنامج التشغيل والتوصيل.",
                        ),
                    )
                )
            )
        for identity, status in list(self.engine.secondary_displays.status.items()):
            name = next(
                (d["name"] for d in self.engine.displays if d["id"] == identity),
                self.window.tr("Additional display", "شاشة إضافية"),
            )
            state = status["state"]
            labels = {
                "restored": ("Previous brightness restored", "استُعيد السطوع السابق"),
                "manual_preserved": ("Manual adjustment preserved", "حُفظ التعديل اليدوي"),
                "restore_failed": (
                    "Restoration failed; correct brightness manually",
                    "فشلت الاستعادة؛ أعد السطوع يدويًا",
                ),
                "display_unavailable": (
                    "Disconnected or DDC/CI unavailable",
                    "مفصولة أو DDC/CI غير متاح",
                ),
                "display_control_failed": (
                    "Control failed; check driver/cable/DDC/CI",
                    "فشل التحكم؛ تحقق من برنامج التشغيل والكابل وDDC/CI",
                ),
                "permission_denied": (
                    "Permission denied; change permissions before retrying",
                    "رُفض الإذن؛ غيّر الأذونات قبل إعادة المحاولة",
                ),
                "brightness_verification_failed": (
                    "Readback did not match; check the driver before retrying",
                    "لم تتطابق القراءة؛ تحقق من برنامج التشغيل قبل إعادة المحاولة",
                ),
                "manual_hold": ("Manual brightness has priority", "السطوع اليدوي له الأولوية"),
            }
            lines.append(
                name
                + ": "
                + self.window.tr(
                    *labels.get(
                        state,
                        (
                            "Following curve or waiting for stable light",
                            "اتباع المنحنى أو انتظار ضوء مستقر",
                        ),
                    )
                )
            )
        self.message.setText("\n".join(lines))


class ReviewUiMixin:
    def update_review_ui(self):
        engine = self.engine
        failures = [
            s
            for s in list(engine.secondary_displays.status.values())
            if s["state"]
            in (
                "restore_failed",
                "display_unavailable",
                "display_control_failed",
                "permission_denied",
                "brightness_verification_failed",
            )
        ]
        primary = engine.diagnostic in ("camera_error", "display_error")
        key = (primary, len(failures)) if primary or failures else None
        message = (
            self.tr(
                "Control needs attention. Open Control status and help for steps.",
                "يحتاج التحكم إلى مراجعة. افتح «حالة التحكم والمساعدة» لمعرفة الخطوات.",
            )
            if key
            else ""
        )
        if self.page == "home":
            self.review_alert.setText(message)
        elif hasattr(self, "review_camera_picker"):
            names = engine.device_labels()
            if names != [
                self.review_camera_picker.itemText(i)
                for i in range(self.review_camera_picker.count())
            ]:
                self.review_camera_picker.blockSignals(True)
                self.review_camera_picker.clear()
                self.review_camera_picker.addItems(names)
                self.review_camera_picker.setCurrentIndex(
                    next(
                        (i for i, d in enumerate(engine.devices) if d["id"] == engine.camera_id), -1
                    )
                )
                self.review_camera_picker.blockSignals(False)
            self.review_camera_picker.setEnabled(
                not engine.running
                and not engine.busy
                and not engine.resume_pending
                and engine.trial_original is None
            )
        if (
            key
            and key != getattr(self, "last_control_alert", None)
            and engine.allow_native_notifications
        ):
            from PySide6.QtWidgets import QSystemTrayIcon

            self.tray.showMessage(
                engine.t("app"), message, QSystemTrayIcon.MessageIcon.Warning, 5000
            )
        self.last_control_alert = key

    def review_settings(self, layout):
        from .qt_ui import ToggleSwitch

        layout.addWidget(self.label(self.tr("Camera controls", "أدوات الكاميرا"), True))
        self.review_camera_picker = self.combo(
            self.engine.device_labels(),
            next(
                (i for i, d in enumerate(self.engine.devices) if d["id"] == self.engine.camera_id),
                -1,
            ),
            self.choose_review_camera,
        )
        layout.addWidget(self.review_camera_picker)
        for en, ar, callback in [
            ("Refresh cameras", "تحديث الكاميرات", self.engine.refresh_cameras),
            ("Metering region", "منطقة قياس الضوء", self.region_dialog),
        ]:
            button = QPushButton(self.tr(en, ar))
            button.clicked.connect(callback)
            layout.addWidget(button)
            self.locked.append(button)
        for key, en, ar in [
            (
                "exposure_guard",
                "Wait for camera exposure to settle",
                "انتظار استقرار تعريض الكاميرا",
            ),
            (
                "preference_suggestions",
                "Collect local preference evidence",
                "جمع أدلة التفضيلات محليًا",
            ),
        ]:
            toggle = ToggleSwitch(self.tr(en, ar))
            toggle.setChecked(self.engine.preferences[key])
            if key == "preference_suggestions":
                self.preference_toggle = toggle
            toggle.toggled.connect(lambda value, k=key: self.option_change(k, value))
            layout.addWidget(toggle)
            self.locked.append(toggle)
        layout.addWidget(self.label(self.tr("Display controls", "أدوات الشاشات"), True))
        for en, ar, callback in [
            ("Refresh displays", "تحديث الشاشات", self.engine.refresh_displays),
            (
                "Configure multiple displays",
                "إعداد الشاشات المتعددة",
                lambda: self.open_review(DisplaysDialog),
            ),
        ]:
            button = QPushButton(self.tr(en, ar))
            button.clicked.connect(callback)
            layout.addWidget(button)
            self.locked.append(button)
        layout.addWidget(self.label(self.tr("Preference review", "مراجعة التفضيلات"), True))
        layout.addWidget(self.preference_toggle)
        button = QPushButton(self.tr("Review preference suggestions", "مراجعة اقتراحات التفضيلات"))
        button.clicked.connect(lambda: self.open_review(SuggestionsDialog))
        layout.addWidget(button)
        layout.addWidget(self.label(self.tr("Troubleshooting", "استكشاف الأخطاء"), True))
        button = QPushButton(self.tr("Control status and help", "حالة التحكم والمساعدة"))
        button.clicked.connect(lambda: self.open_review(HelpDialog))
        layout.addWidget(button)

    def choose_review_camera(self, index):
        if not 0 <= index < len(self.engine.devices):
            return
        self.choose_camera(index)
        self.build()

    def open_review(self, kind):
        self.review_dialog = kind(self)
        self.review_dialog.open()

    def organize_settings(self, left, right):
        from .qt_ui import Surface

        self.settings_tabs = None
        EasyMixin.organize_settings(self, left, right)
        titles = {
            "brightness": self.tr("Brightness", "السطوع"),
            "camera": self.tr("Camera", "الكاميرا"),
            "screens": self.tr("Screens", "الشاشات"),
            "appearance": self.tr("Appearance", "المظهر"),
            "updates": self.tr("Updates", "التحديثات"),
            "tools": self.tr("Tools", "الأدوات"),
        }
        categories = {
            self.engine.t("personalize"): "appearance",
            self.tr("Glass transparency", "شفافية الزجاج"): "appearance",
            self.engine.t("check_interval"): "camera",
            self.engine.t("limits"): "brightness",
            self.engine.t("curve"): "brightness",
            self.tr("Comfort and stability", "الراحة والثبات"): "brightness",
            self.tr("Camera controls", "أدوات الكاميرا"): "camera",
            self.tr("Display controls", "أدوات الشاشات"): "screens",
            self.tr("Updates", "التحديثات"): "updates",
            self.tr("Preference review", "مراجعة التفضيلات"): "brightness",
            self.tr("Power saving", "توفير الطاقة"): "camera",
            self.tr("Usage profiles", "ملفات الاستخدام"): "brightness",
        }
        tabs = QTabWidget()
        tabs.setStyleSheet(
            f"QTabWidget::pane {{border:0;background:transparent;}} QTabBar::tab {{background:{self.engine.palette['card']};color:{self.engine.palette['ink']};padding:8px 10px;}} QTabBar::tab:selected {{background:{self.engine.palette['accent']};color:white;}}"
        )
        tabs.setUsesScrollButtons(True)
        pages = {key: Surface(self) for key in titles}
        records = []
        for section, advanced, terms, surface in self.settings_sections:
            heading = section.findChild(QLabel)
            category = categories.get(heading.text() if heading else "", "tools")
            pages[category].layout_box.addWidget(section)
            records.append(
                (section, False if category == "updates" else advanced, terms, pages[category])
            )
        while self.panels.count():
            item = self.panels.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        self.content_layout.removeItem(self.panels)
        self.tab_keys = list(titles)
        for key, page in pages.items():
            page.layout_box.addStretch()
            tabs.addTab(page, titles[key])
        self.settings_search.setAccessibleName(self.tr("Search settings", "البحث في الإعدادات"))
        self.settings_sections = records
        self.settings_tabs = tabs
        self.content_layout.addWidget(tabs)
        self.tab_before_search = getattr(self, "settings_tab_key", "brightness")
        if self.tab_before_search in self.tab_keys:
            tabs.setCurrentIndex(self.tab_keys.index(self.tab_before_search))
        tabs.currentChanged.connect(
            lambda i: setattr(self, "settings_tab_key", self.tab_keys[i]) if i >= 0 else None
        )
        self.filter_settings(self.settings_query)

    def filter_settings(self, text):
        if not getattr(self, "settings_tabs", None):
            return EasyMixin.filter_settings(self, text)
        query = search_key(text.strip())
        previous = getattr(self, "settings_query", "")
        if query and not previous:
            self.tab_before_search = self.tab_keys[self.settings_tabs.currentIndex()]
        self.settings_query = text
        counts = {
            page: 0
            for page in [self.settings_tabs.widget(i) for i in range(self.settings_tabs.count())]
        }
        for section, advanced, terms, page in self.settings_sections:
            show = query in terms if query else not advanced or self.advanced_visible
            section.setVisible(show)
            counts[page] += int(show)
        for i in range(self.settings_tabs.count()):
            self.settings_tabs.setTabVisible(i, counts[self.settings_tabs.widget(i)] > 0)
        self.settings_no_results.setVisible(not sum(counts.values()))
        self.advanced_button.setText(
            self.tr("Hide advanced settings", "إخفاء الإعدادات المتقدمة")
            if self.advanced_visible
            else self.tr("Show advanced settings", "عرض الإعدادات المتقدمة")
        )
        if not query and previous and self.tab_before_search in self.tab_keys:
            self.settings_tabs.setCurrentIndex(self.tab_keys.index(self.tab_before_search))
