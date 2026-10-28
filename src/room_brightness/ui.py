"""Bilingual desktop UI with guided setup and persistent user preferences."""

import ctypes
import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from .brightness import brightness, set_checked, verify_control, smooth_to
from .tuning import transition_duration
from .camera import sample
from .adaptive import AdaptiveController, curve_target
from .widgets import RoundedCard, RoundedButton, PALETTES
from . import startup
from .themes import THEME_NAMES
import time
from .devices import list_devices
from .i18n import text, LANGUAGES
from .paths import DATA_DIR
from .settings import load_settings, resolve_language, resolve_theme, save_settings

BG = "#f3f6fb"
INK = "#182b49"
MUTED = "#64748b"
BLUE = "#2563eb"
LINE = "#e2e8f0"


class Power(ctypes.Structure):
    _fields_ = [
        ("ac", ctypes.c_ubyte),
        ("flag", ctypes.c_ubyte),
        ("percent", ctypes.c_ubyte),
        ("reserved", ctypes.c_ubyte),
        ("life", ctypes.c_uint32),
        ("full", ctypes.c_uint32),
    ]


class App:
    def __init__(self, root, discover=True):
        self.root = root
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.busy = self.running = self.verified = False
        self.operation = ""
        self.original = self.controller = self.timer = self.save_timer = None
        self.preferences = load_settings(DATA_DIR)
        self.language = resolve_language(self.preferences["language"])
        self.theme = resolve_theme(self.preferences["theme"])
        self.palette = PALETTES[self.theme]
        self.tray_icon = None
        self.last_meter = None
        self.preview_enabled = False
        self.manual_value = tk.IntVar(value=50)
        self.view = "home"
        self.display_value = tk.StringVar(value="—")
        self.language_mode = tk.StringVar(value=self.preferences["language"])
        self.startup_choice = tk.BooleanVar(value=startup.is_enabled())
        self.preferences["startup"] = self.startup_choice.get()
        self.screen_timer = None
        self.language_choice = tk.StringVar()
        self.camera = tk.IntVar(value=self.preferences["camera_index"])
        self.camera_label = tk.StringVar(value=self.t("finding"))
        self.low = tk.IntVar(value=self.preferences["low"])
        self.high = tk.IntVar(value=self.preferences["high"])
        self.interval_ac = tk.IntVar(value=self.preferences["interval_ac"])
        self.interval_battery = tk.IntVar(value=self.preferences["interval_battery"])
        self.restore = tk.BooleanVar(value=self.preferences["restore"])
        self.dark = self.preferences["dark"]
        self.light = self.preferences["bright"]
        self.calibration_camera = self.camera.get() if self.dark is not None else None
        self.calibration_id = self.preferences["calibration_id"]
        self.camera_id = self.preferences["camera_id"]
        self.devices = []
        self.status = tk.StringVar()
        self.status_title = tk.StringVar()
        self.status_state = ("auto_ready", "auto_welcome", {})
        self.error_details = ""
        root.configure(bg=BG)
        root.geometry(f"960x{min(800, max(600, root.winfo_screenheight() - 110))}")
        root.minsize(780, 600)
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure(
            "Modern.TCombobox",
            padding=9,
            font=("Segoe UI", 11),
            fieldbackground="white",
            background="white",
            bordercolor=LINE,
            arrowcolor=MUTED,
        )
        style.map(
            "Modern.TCombobox",
            fieldbackground=[("readonly", "white")],
            foreground=[("readonly", INK)],
            selectbackground=[("readonly", "white")],
            selectforeground=[("readonly", INK)],
        )
        style.configure("Modern.Horizontal.TScale", background="white", troughcolor=LINE)
        self.status_dock = tk.Frame(root, bg=BG)
        self.status_dock.pack(side="bottom", fill="x", padx=28, pady=12)
        scroll_area = tk.Frame(root, bg=BG)
        self.scroll_area = scroll_area
        scroll_area.pack(side="top", fill="both", expand=True)
        self.canvas = tk.Canvas(scroll_area, bg=BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(scroll_area, orient="vertical", command=self.canvas.yview)
        scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.content = tk.Frame(self.canvas, bg=BG)
        self.window = self.canvas.create_window((0, 0), window=self.content, anchor="nw")
        self.content.bind(
            "<Configure>", lambda event: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        self.canvas.bind(
            "<Configure>", lambda event: self.canvas.itemconfigure(self.window, width=event.width)
        )
        root.bind(
            "<MouseWheel>", lambda event: self.canvas.yview_scroll(-int(event.delta / 120), "units")
        )
        self.build()
        root.protocol("WM_DELETE_WINDOW", self.request_close)
        root.bind("<Unmap>", self.on_minimize)
        self.poll_timer = root.after(80, self.poll)
        self.environment_timer = root.after(1500, self.sync_environment)
        self.discovery_timer = root.after(120, self.refresh_cameras) if discover else None

    def t(self, key, **values):
        return text(
            self.language, key, _dialect=self.preferences.get("arabic_dialect", "msa"), **values
        )

    def label(self, parent, key, bold=False, size=10, **kwargs):
        label = tk.Label(
            parent,
            text=self.t(key),
            bg=parent.cget("bg"),
            fg=self.palette["ink"] if bold else self.palette["muted"],
            font=("Segoe UI", size, "bold" if bold else "normal"),
            anchor="e" if self.language == "ar" else "w",
            justify="right" if self.language == "ar" else "left",
            **kwargs,
        )
        if "wraplength" in kwargs:
            label.bind(
                "<Configure>", lambda event: label.configure(wraplength=max(100, event.width - 4))
            )
        return label

    def card(self, parent):
        surface = RoundedCard(parent, self.palette)
        return surface

    def button(self, parent, key, action, primary=False):
        return RoundedButton(parent, self.t(key), action, self.palette, primary=primary)

    def build(self):
        if hasattr(self, "language_menu"):
            self.language_menu.destroy()
            del self.language_menu
        for holder in (self.content, self.status_dock):
            for child in holder.winfo_children():
                child.destroy()
        p = self.palette
        self.root.title(self.t("app"))
        self.root.configure(bg=p["bg"])
        self.content.configure(bg=p["bg"])
        self.canvas.configure(bg=p["bg"])
        self.status_dock.configure(bg=p["bg"])
        self.scroll_area.configure(bg=p["bg"])
        style = ttk.Style(self.root)
        style.configure(
            "Modern.TCombobox",
            fieldbackground=p["card"],
            background=p["card"],
            foreground=p["ink"],
            arrowcolor=p["muted"],
            bordercolor=p["line"],
            padding=8,
        )
        style.map(
            "Modern.TCombobox",
            fieldbackground=[("disabled", p["line"]), ("readonly", p["card"])],
            foreground=[("disabled", p["muted"]), ("readonly", p["ink"])],
            selectbackground=[("readonly", p["card"])],
            selectforeground=[("readonly", p["ink"])],
        )
        style.configure("Modern.Horizontal.TScale", background=p["card"], troughcolor=p["line"])
        style.configure(
            "Vertical.TScrollbar",
            background=p["line"],
            troughcolor=p["bg"],
            arrowcolor=p["muted"],
            bordercolor=p["bg"],
        )
        self.root.option_add("*TCombobox*Listbox.background", p["card"])
        self.root.option_add("*TCombobox*Listbox.foreground", p["ink"])
        self.buttons = []
        self.settings_widgets = []
        header = tk.Frame(self.content, bg=p["bg"], padx=28, pady=22)
        header.pack(fill="x")
        nav = tk.Frame(header, bg=p["bg"])
        nav.pack(side="left" if self.language == "ar" else "right")
        self.language_button = self.button(nav, "language", self.open_language_menu)
        self.language_button.configure(width=110)
        self.language_button.pack(side="left", padx=4)
        self.button(nav, "home" if self.view == "settings" else "settings", self.toggle_view).pack(
            side="left", padx=4
        )
        names = tk.Frame(header, bg=p["bg"])
        names.pack(side="right" if self.language == "ar" else "left", fill="x", expand=True)
        self.label(names, "app", bold=True, size=22, wraplength=460).pack(fill="x")
        self.label(names, "simple_subtitle", wraplength=460).pack(fill="x", pady=(6, 0))
        body = tk.Frame(self.content, bg=p["bg"], padx=28)
        body.pack(fill="x")
        first, second = (1, 0) if self.language == "ar" else (0, 1)
        body.columnconfigure(first, weight=5, uniform="body")
        body.columnconfigure(second, weight=4, uniform="body")
        if self.view == "home":
            hero = self.card(body)
            hero.grid(
                row=0, column=first, sticky="nsew", padx=(8, 0) if self.language == "ar" else (0, 8)
            )
            self.label(hero.inner, "automatic", bold=True, size=16).pack(fill="x")
            self.label(hero.inner, "screen_level").pack(fill="x", pady=(24, 0))
            metric = tk.Frame(hero.inner, bg=p["card"])
            metric.pack(fill="x", pady=(0, 18))
            tk.Label(
                metric,
                textvariable=self.display_value,
                bg=p["card"],
                fg=p["ink"],
                font=("Segoe UI", 62, "bold"),
            ).pack(side="right" if self.language == "ar" else "left")
            tk.Label(metric, text="%", bg=p["card"], fg=p["muted"], font=("Segoe UI", 25)).pack(
                side="right" if self.language == "ar" else "left", padx=10, pady=(25, 0)
            )
            self.label(hero.inner, "one_click", wraplength=400).pack(fill="x", pady=(0, 24))
            actions = tk.Frame(hero.inner, bg=p["card"])
            actions.pack(fill="x")
            self.start_button = self.button(actions, "start_simple", self.start, primary=True)
            self.start_button.pack(
                side="right" if self.language == "ar" else "left", fill="x", expand=True
            )
            self.buttons.append(self.start_button)
            stop = self.button(actions, "stop", self.stop)
            stop.configure(width=90)
            stop.pack(side="left" if self.language == "ar" else "right", padx=8)
            camera = self.card(body)
            camera.grid(
                row=0,
                column=second,
                sticky="nsew",
                padx=(0, 8) if self.language == "ar" else (8, 0),
            )
            self.label(camera.inner, "camera", bold=True, size=16).pack(fill="x")
            self.label(camera.inner, "camera_help", wraplength=300).pack(fill="x", pady=(10, 18))
            self.camera_box = ttk.Combobox(
                camera.inner,
                textvariable=self.camera_label,
                values=self.device_labels(),
                state="readonly",
                style="Modern.TCombobox",
            )
            self.camera_box.pack(fill="x")
            self.camera_box.bind("<<ComboboxSelected>>", self.select_camera)
            self.refresh_button = self.button(camera.inner, "refresh", self.refresh_cameras)
            self.refresh_button.pack(fill="x", pady=(14, 20))
            self.settings_widgets.extend([self.camera_box, self.refresh_button])
            self.label(camera.inner, "privacy", bold=True).pack(fill="x", pady=(12, 4))
            self.label(camera.inner, "privacy_help", wraplength=300).pack(fill="x")
            self.label(camera.inner, "live_meter", bold=True).pack(fill="x", pady=(18, 5))
            self.meter_label = tk.Label(camera.inner, bg=p["card"], fg=p["muted"], wraplength=300)
            self.meter_label.pack(fill="x")
            self.update_meter()
            ttk.Scale(hero.inner, from_=10, to=100, variable=self.manual_value).pack(
                fill="x", pady=(20, 6)
            )
            self.manual_button = self.button(hero.inner, "manual_set", self.apply_manual)
            self.manual_button.pack(fill="x")
            self.label(hero.inner, "manual_tip", wraplength=380).pack(fill="x", pady=(6, 0))

        else:
            personal = self.card(body)
            personal.grid(
                row=0, column=first, sticky="nsew", padx=(8, 0) if self.language == "ar" else (0, 8)
            )
            self.label(personal.inner, "personalize", bold=True, size=16).pack(fill="x")
            self.label(personal.inner, "personalize_help", wraplength=390).pack(
                fill="x", pady=(6, 20)
            )
            self.label(personal.inner, "language", bold=True).pack(fill="x", pady=(0, 6))
            choices = [self.t("system"), "English", "العربية"]
            self.language_choice.set(
                choices[("auto", "en", "ar").index(self.preferences["language"])]
            )
            language = ttk.Combobox(
                personal.inner,
                textvariable=self.language_choice,
                values=choices,
                state="readonly",
                style="Modern.TCombobox",
            )
            language.pack(fill="x")
            language.bind(
                "<<ComboboxSelected>>",
                lambda event: self.change_language(("auto", "en", "ar")[language.current()]),
            )
            self.label(personal.inner, "appearance", bold=True).pack(fill="x", pady=(18, 6))
            appearance = ttk.Combobox(
                personal.inner,
                values=[
                    self.t("system"),
                    self.t("light_mode"),
                    self.t("dark_mode"),
                    self.t("glass_mode"),
                ],
                state="readonly",
                style="Modern.TCombobox",
            )
            appearance.current(("auto", "light", "dark", "glass").index(self.preferences["theme"]))
            appearance.pack(fill="x")
            appearance.bind(
                "<<ComboboxSelected>>",
                lambda event: self.change_theme(
                    ("auto", "light", "dark", "glass")[appearance.current()]
                ),
            )
            checkbox = tk.Checkbutton(
                personal.inner,
                text=self.t("startup"),
                variable=self.startup_choice,
                command=self.toggle_startup,
                bg=p["card"],
                fg=p["ink"],
                activebackground=p["card"],
                selectcolor=p["card"],
                font=("Segoe UI", 10),
                wraplength=370,
                justify="right" if self.language == "ar" else "left",
            )
            checkbox.pack(fill="x", pady=(24, 6))
            self.label(personal.inner, "startup_help", wraplength=390).pack(fill="x")
            for key in ("minimize_tray", "close_tray"):
                var = tk.BooleanVar(value=self.preferences[key])
                tk.Checkbutton(
                    personal.inner,
                    text=self.t(key),
                    variable=var,
                    bg=p["card"],
                    fg=p["ink"],
                    selectcolor=p["card"],
                    command=lambda k=key, v=var: self.set_tray_option(k, v.get()),
                ).pack(fill="x", pady=6)
            self.label(personal.inner, "check_interval", bold=True).pack(fill="x", pady=(20, 6))
            self.label(personal.inner, "interval_help", wraplength=390).pack(fill="x")
            for key, var in [("on_ac", self.interval_ac), ("on_battery", self.interval_battery)]:
                self.label(personal.inner, key).pack(fill="x", pady=(12, 4))
                choice = ttk.Combobox(
                    personal.inner,
                    values=[5, 10, 15, 30, 60, 90, 120, 300, 600],
                    textvariable=var,
                    state="readonly",
                    style="Modern.TCombobox",
                )
                choice.pack(fill="x")
                choice.bind("<<ComboboxSelected>>", lambda event: self.interval_changed())

            comfort = self.card(body)
            comfort.grid(
                row=0,
                column=second,
                sticky="nsew",
                padx=(0, 8) if self.language == "ar" else (8, 0),
            )
            self.label(comfort.inner, "limits", bold=True, size=16).pack(fill="x")
            self.label(comfort.inner, "limits_help", wraplength=300).pack(fill="x", pady=(6, 18))
            for key, var, minimum, maximum in [
                ("minimum", self.low, 0, 95),
                ("maximum", self.high, 15, 100),
            ]:
                row = tk.Frame(comfort.inner, bg=p["card"])
                row.pack(fill="x", pady=(9, 4))
                self.label(row, key).pack(side="right" if self.language == "ar" else "left")
                label = tk.Label(row, bg=p["card"], fg=p["accent"], font=("Segoe UI", 12, "bold"))
                label.pack(side="left" if self.language == "ar" else "right")
                if key == "minimum":
                    self.low_label = label
                else:
                    self.high_label = label
                slider = ttk.Scale(
                    comfort.inner,
                    from_=minimum,
                    to=maximum,
                    variable=var,
                    command=lambda value, kind=key: self.range_changed(kind, value),
                    style="Modern.Horizontal.TScale",
                )
                slider.pack(fill="x", pady=(0, 18))
                self.settings_widgets.append(slider)
            restore = tk.Checkbutton(
                comfort.inner,
                text=self.t("restore_new"),
                variable=self.restore,
                command=self.persist,
                bg=p["card"],
                fg=p["muted"],
                activebackground=p["card"],
                selectcolor=p["card"],
                font=("Segoe UI", 10),
                wraplength=300,
                justify="right" if self.language == "ar" else "left",
            )
            restore.pack(fill="x", pady=12)
            self.settings_widgets.append(restore)
            self.label(comfort.inner, "curve", bold=True).pack(fill="x", pady=(18, 6))
            self.label(comfort.inner, "curve_help", wraplength=300).pack(fill="x")
            response = ttk.Combobox(
                comfort.inner,
                values=[self.t(k) for k in ("gentle", "balanced", "responsive")],
                state="readonly",
                style="Modern.TCombobox",
            )
            response.current(
                ("gentle", "balanced", "responsive").index(self.preferences["sensitivity"])
            )
            response.pack(fill="x", pady=8)
            response.bind(
                "<<ComboboxSelected>>", lambda event: self.change_curve(response.current())
            )
            self.curve_canvas = tk.Canvas(
                comfort.inner, height=130, bg=p["card"], highlightthickness=0
            )
            self.curve_canvas.pack(fill="x")
            self.curve_canvas.bind("<Configure>", lambda event: self.draw_curve())
            self.update_readings()
        footer = tk.Frame(self.content, bg=p["bg"], padx=30, pady=22)
        footer.pack(fill="x")
        self.label(footer, "about_short").pack(fill="x", pady=(0, 6))
        self.label(footer, "saved").pack(fill="x")
        self.label(footer, "meter_note").pack(fill="x", pady=(5, 0))
        status = self.card(self.status_dock)
        status.pack(fill="x")
        tk.Label(
            status.inner,
            textvariable=self.status_title,
            bg=p["card"],
            fg=p["ink"],
            font=("Segoe UI", 12, "bold"),
            anchor="e" if self.language == "ar" else "w",
        ).pack(fill="x")
        desc = tk.Label(
            status.inner,
            textvariable=self.status,
            bg=p["card"],
            fg=p["muted"],
            font=("Segoe UI", 10),
            anchor="e" if self.language == "ar" else "w",
            justify="right" if self.language == "ar" else "left",
            wraplength=800,
        )
        desc.pack(fill="x", pady=(6, 0))
        desc.bind("<Configure>", lambda event: desc.configure(wraplength=max(100, event.width - 4)))
        self.details_button = self.button(status.inner, "details", self.show_details)
        self.render_status()
        self.update_controls()
        self.apply_title_theme()

    def device_labels(self):
        labels = []
        for device in self.devices:
            name = device["name"]
            total = sum((item["name"] == name for item in self.devices))
            number = sum((item["name"] == name for item in self.devices[: len(labels) + 1]))
            labels.append(f"{name} ({number})" if total > 1 else name)
        return labels

    def selected_device(self):
        return next((item for item in self.devices if item["id"] == self.camera_id), None)

    def change_language(self, mode):
        if mode not in LANGUAGES:
            return
        self.preferences["language"] = mode
        self.language = resolve_language(mode)
        self.persist()
        self.build()

    def persist(self):
        device = self.selected_device()
        self.preferences.update(
            low=self.low.get(),
            high=self.high.get(),
            restore=self.restore.get(),
            interval_ac=self.interval_ac.get(),
            interval_battery=self.interval_battery.get(),
            camera_index=self.camera.get(),
            camera_id=self.camera_id,
            camera_name=device["name"] if device else self.preferences["camera_name"],
            calibration_id=self.calibration_id,
            dark=self.dark,
            bright=self.light,
        )
        try:
            save_settings(DATA_DIR, self.preferences)
            return True
        except OSError as exc:
            self.error_details = str(exc)
            self.set_status("error", "error_settings")
            return False

    def range_changed(self, kind, value):
        number = round(float(value))
        if kind == "minimum":
            self.low.set(max(0, min(95, number)))
            if self.high.get() <= self.low.get():
                self.high.set(self.low.get() + 1)
        else:
            self.high.set(max(15, min(100, number)))
            if self.low.get() >= self.high.get():
                self.low.set(self.high.get() - 1)
        self.update_readings()
        if hasattr(self, "curve_canvas") and self.curve_canvas.winfo_exists():
            self.draw_curve()
        if self.save_timer is not None:
            self.root.after_cancel(self.save_timer)
        self.save_timer = self.root.after(250, self.flush_preferences)

    def flush_preferences(self):
        self.save_timer = None
        self.persist()

    def update_readings(self):
        if self.view == "settings":
            self.low_label.config(text=f"{self.low.get()}%")
            self.high_label.config(text=f"{self.high.get()}%")

    def set_status(self, title, description, **values):
        self.status_state = (title, description, values)
        self.render_status()

    def render_status(self):
        title, description, values = self.status_state
        self.status_title.set(self.t(title))
        self.status.set(self.t(description, **values))
        if self.error_details:
            self.details_button.pack(anchor="e" if self.language == "ar" else "w", pady=(8, 0))
        else:
            self.details_button.pack_forget()

    def show_details(self):
        messagebox.showinfo(self.t("details"), self.error_details, parent=self.root)

    def update_controls(self):
        disabled = self.busy or self.running
        for button in self.buttons:
            button.config(state="disabled" if disabled else "normal")
        for widget in self.settings_widgets:
            widget.config(state="disabled" if disabled else "normal")
        if self.view == "home":
            self.camera_box.config(state="disabled" if disabled or not self.devices else "readonly")

    def work(self, function, done, operation):
        if self.busy:
            return
        self.busy = True
        self.operation = operation
        self.update_controls()

        def worker():
            try:
                self.events.put((done, function(), None))
            except Exception as exc:
                self.events.put((done, None, str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def poll(self):
        try:
            done, result, error = self.events.get_nowait()
            if done == "tray":
                result()
                self.poll_timer = self.root.after(80, self.poll)
                return
            if done == "progress":
                self.display_value.set(str(result))
                self.poll_timer = self.root.after(80, self.poll)
                return
            operation = self.operation
            self.busy = False
            if error:
                if (
                    self.cancel.is_set()
                    and operation in ("measure", "control", "observe")
                    and (not self.running)
                ):
                    self.finish_stop()
                else:
                    self.handle_error(operation, error)
            else:
                done(result)
            self.update_controls()
        except queue.Empty:
            pass
        self.poll_timer = self.root.after(80, self.poll)

    def handle_error(self, operation, error):
        self.running = self.verified = False
        self.cancel.set()
        self.error_details = error
        key = {
            "test": "error_test",
            "measure": "error_camera",
            "devices": "no_camera_help",
            "control": "error_control",
            "restore": "error_restore",
        }.get(operation, "error_control")
        if operation == "control" and "camera" in error.lower():
            key = "error_camera"
        self.set_status("error", key)
        if operation == "devices":
            self.devices = []
            self.camera_label.set(self.t("no_camera"))
        if self.restore.get() and self.original is not None and (operation != "restore"):
            old, self.original = (self.original, None)
            self.work(
                lambda: self.restore_target(old), lambda _: self.set_status("error", key), "restore"
            )

    def refresh_cameras(self):
        self.discovery_timer = None
        if self.busy or self.running:
            return
        self.cancel.clear()
        self.error_details = ""
        self.camera_label.set(self.t("finding"))

        def done(devices):
            if self.cancel.is_set():
                self.finish_stop()
                return
            self.devices = devices
            if self.view == "home":
                self.camera_box.config(values=self.device_labels())
            if not devices:
                self.camera_label.set(self.t("no_camera"))
                self.set_status("no_camera", "no_camera_help")
                return
            device = next((item for item in devices if item["id"] == self.camera_id), devices[0])
            self.choose_device(device)
            self.set_status("auto_ready", "auto_welcome")

        self.work(list_devices, done, "devices")

    def select_camera(self, event=None):
        position = self.camera_box.current()
        if 0 <= position < len(self.devices):
            self.choose_device(self.devices[position])

    def choose_device(self, device):
        changed = device["id"] != self.camera_id
        self.camera_id = device["id"]
        self.camera.set(device["index"])
        self.camera_label.set(self.device_labels()[self.devices.index(device)])
        if changed:
            self.controller = None
        self.persist()

    def verify(self, start_after=False):
        if self.busy or self.running:
            return
        self.controller = None
        self.verified = False
        self.cancel.clear()
        self.error_details = ""
        self.set_status("testing", "test_help")

        def test():
            old = brightness()
            self.original = old
            return verify_control(brightness, original=old)

        def done(old):
            if self.cancel.is_set():
                self.finish_stop()
                return
            self.verified = True
            self.display_value.set(str(old))
            if start_after:
                self.controller = AdaptiveController(
                    self.low.get(),
                    self.high.get(),
                    sensitivity=self.curve_sensitivity(),
                    mapping="image",
                    image_curve=self.preferences.get("brightness_curve", "custom"),
                    protect_dim=self.preferences.get("protect_dim", True),
                    expected=old,
                )
                self.running = True
                self.set_status("learning", "learning_help")
                if getattr(self.root, "qt_native", False):
                    self.begin_pair_cycle()
                else:
                    self.tick()
                self.screen_timer = self.root.after(15000, self.watch_screen)
            else:
                self.set_status("verified", "verified_help", value=old)

        self.work(test, done, "test")

    def start(self):
        if self.busy or self.running:
            return
        if not self.selected_device():
            self.set_status("no_camera", "no_camera_help")
            return
        if not self.persist():
            return
        self.verify(start_after=True)

    def begin_pair_cycle(self):
        power = Power()
        ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(power))
        seconds = self.interval_ac.get() if power.ac == 1 else self.interval_battery.get()
        seconds = getattr(self, "cycle_seconds", seconds)
        self.pair_first = None
        self.pair_deadline = time.monotonic() + seconds
        self.timer = self.root.after(round(seconds * 500), self.tick)

    def interval_changed(self):
        self.persist()
        if self.running and self.timer is not None:
            self.root.after_cancel(self.timer)
            power = Power()
            ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(power))
            seconds = self.interval_ac.get() if power.ac == 1 else self.interval_battery.get()
            if getattr(self.root, "qt_native", False):
                self.begin_pair_cycle()
            else:
                self.timer = self.root.after(seconds * 1000, self.tick)

    def tick(self):
        self.timer = None
        if not self.running:
            return
        if self.busy:
            self.timer = self.root.after(250, self.tick)
            return
        remaining = self.controller.hold_until - time.monotonic()
        if remaining > 0:
            self.set_status("manual_hold", "manual_help", seconds=round(remaining))
            self.timer = self.root.after(15000, self.tick)
            return
        device = self.selected_device()

        def update():
            devices = list_devices()
            chosen = next((item for item in devices if item["id"] == device["id"]), None)
            if chosen is None or chosen["index"] != device["index"]:
                raise RuntimeError(
                    "Selected camera disconnected or reordered. Refresh cameras and try again."
                )
            reading = sample(
                device["index"],
                self.cancel,
                preview=self.preview_enabled,
                region=self.preferences.get("meter_region"),
                **({"protection": True} if self.preferences.get("spatial_protection") else {}),
            )
            if hasattr(self, "performance"):
                self.performance.capture(reading)
            if self.cancel.is_set():
                return None
            if getattr(self.root, "qt_native", False):
                first = getattr(self, "pair_first", None)
                if first is None:
                    return {"pair_half": reading}
                from .metering import average_pair

                reading = average_pair(first, reading)
            current = brightness()
            now = time.monotonic()
            was_anchor = self.controller.needs_anchor
            wanted = self.controller.update(reading, current, now)
            manual = now < self.controller.hold_until
            if manual:
                self.original = current
            if wanted != current and (not self.cancel.is_set()):
                fresh = brightness()
                if self.controller.observe(fresh, time.monotonic()):
                    current = fresh
                    self.original = current
                    manual = True
                else:
                    try:
                        actual = current
                        if getattr(self.root, "qt_native", False):

                            def progress(value):
                                self.controller.committed(value)
                                self.events.put(("progress", value, None))

                            if "transition_speed" in self.preferences:
                                actual, manual = smooth_to(
                                    current,
                                    wanted,
                                    self.cancel,
                                    progress,
                                    duration=transition_duration(self.preferences, current, wanted),
                                )
                            else:
                                actual, manual = smooth_to(current, wanted, self.cancel, progress)
                            if manual:
                                self.controller.observe(actual, time.monotonic())
                                self.original = actual
                        else:
                            # Ramp independently of camera timing; each write is verified.
                            while actual != wanted and not self.cancel.is_set():
                                fresh = brightness()
                                if self.controller.observe(fresh, time.monotonic()):
                                    actual = fresh
                                    self.original = fresh
                                    manual = True
                                    break
                                step = actual + (1 if wanted > actual else -1)
                                confirmed = set_checked(step)
                                self.controller.committed(confirmed)
                                if confirmed == actual:
                                    break  # A driver may quantize supported brightness levels.
                                reached = (wanted - actual) * (wanted - confirmed) <= 0
                                actual = confirmed
                                self.events.put(("progress", actual, None))
                                if reached or self.cancel.wait(0.12):
                                    break
                    except RuntimeError:
                        raise
                    current = actual
                    if not manual:
                        self.controller.committed(actual)
            return dict(
                current=current,
                reason=self.controller.reason,
                manual=manual,
                quality=reading["confidence"],
                anchor=was_anchor,
                level=reading.get("level", 0),
                exposure=reading.get("exposure"),
                exposure_corrected=reading.get("exposure_corrected", False),
                gain=reading.get("gain"),
                preview=reading.get("preview") if self.preview_enabled else None,
                target=wanted,
                pair_levels=reading.get("pair_levels"),
            )

        def done(result):
            if not self.running:
                self.finish_stop()
                return
            if result and "pair_half" in result:
                self.pair_first = result["pair_half"]
                remaining = max(
                    0, getattr(self, "pair_deadline", time.monotonic()) - time.monotonic()
                )
                self.timer = self.root.after(max(1, round(remaining * 1000)), self.tick)
                return
            if result:
                self.last_meter = result
                self.update_meter()
                self.display_value.set(str(result["current"]))
                if result["manual"]:
                    self.set_status("manual_hold", "manual_help", seconds=180)
                elif result.get("reason") == "scene_changed":
                    self.set_status("vision_hold", "scene_changed_help")
                elif result.get("reason") == "protected":
                    self.set_status("vision_hold", "protected_help")
                elif result["quality"] < 0.35:
                    self.set_status("unstable", "unstable_help")
                else:
                    self.set_status("watching", "watching_help")
            power = Power()
            ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(power))
            interval = self.interval_ac.get() if power.ac == 1 else self.interval_battery.get()
            if result and result.get("reason") in ("confirming_dim", "confirming_light"):
                interval = min(interval, 5)
            if getattr(self.root, "qt_native", False):
                self.begin_pair_cycle()
            else:
                self.timer = self.root.after(1000 * interval, self.tick)

        self.work(update, done, "control")

    def stop(self):
        if self.screen_timer is not None:
            self.root.after_cancel(self.screen_timer)
            self.screen_timer = None
        if self.timer is not None:
            self.root.after_cancel(self.timer)
            self.timer = None
        self.running = self.verified = False
        self.cancel.set()
        self.set_status("stopping", "stopping_help")
        if not self.busy:
            self.finish_stop()

    def finish_stop(self):
        if self.busy:
            return
        self.verified = False
        if self.restore.get() and self.original is not None:
            old, self.original = (self.original, None)
            self.work(
                lambda: self.restore_target(old),
                lambda value: self.set_status("stopped", "restored_help", value=value),
                "restore",
            )
        else:
            self.original = None
            self.set_status("stopped", "stopped_help")
            self.update_controls()

    def restore_target(self, previous):
        # A user may move the Windows slider just before Stop or a camera error,
        # before the periodic observer has seen it. Never overwrite that choice.
        if self.controller is not None:
            current = brightness()
            if self.controller.observe(current, time.monotonic()):
                return current
        return set_checked(previous)

    def close(self):
        if self.tray_icon is not None:
            self.tray_icon.stop()
            self.tray_icon = None
        self.root.after_cancel(self.environment_timer)
        if self.discovery_timer is not None:
            self.root.after_cancel(self.discovery_timer)
            self.discovery_timer = None
        if self.save_timer is not None:
            self.root.after_cancel(self.save_timer)
            self.save_timer = None
        self.persist()
        self.stop()

        def wait():
            if self.busy:
                self.root.after(100, wait)
            else:
                self.root.after_cancel(self.poll_timer)
                self.root.destroy()

        self.root.after(150, wait)

    def toggle_view(self):
        self.view = "settings" if self.view == "home" else "home"
        self.build()
        self.canvas.yview_moveto(0)

    def open_language_menu(self):
        if hasattr(self, "language_menu"):
            self.language_menu.destroy()
        menu = tk.Menu(
            self.root,
            tearoff=False,
            bg=self.palette["card"],
            fg=self.palette["ink"],
            activebackground=self.palette["accent"],
            activeforeground=self.palette["accent_ink"],
        )
        self.language_menu = menu
        self.language_mode.set(self.preferences["language"])
        for label, mode in [(self.t("system"), "auto"), ("English", "en"), ("العربية", "ar")]:
            menu.add_radiobutton(
                label=label,
                value=mode,
                variable=self.language_mode,
                command=lambda value=mode: self.change_language(value),
            )
        try:
            menu.tk_popup(
                self.language_button.winfo_rootx(), self.language_button.winfo_rooty() + 46
            )
        finally:
            if menu.winfo_exists():
                menu.grab_release()

    def change_theme(self, mode):
        if mode not in ("auto", "light", "dark", "glass", *THEME_NAMES):
            return
        self.preferences["theme"] = mode
        self.theme = resolve_theme(mode)
        self.palette = PALETTES[self.theme]
        self.persist()
        self.build()

    def sync_environment(self):
        language = resolve_language(self.preferences["language"])
        theme = resolve_theme(self.preferences["theme"])
        if (language, theme) != (self.language, self.theme):
            self.language, self.theme = (language, theme)
            self.palette = PALETTES[theme]
            if not self.devices:
                self.camera_label.set(self.t("no_camera"))
            self.build()
        self.environment_timer = self.root.after(1500, self.sync_environment)

    def apply_title_theme(self):
        self.root.attributes("-alpha", 0.97 if self.theme == "glass" else 1.0)
        try:
            get_parent = ctypes.windll.user32.GetParent
            get_parent.argtypes = [ctypes.c_void_p]
            get_parent.restype = ctypes.c_void_p
            hwnd = get_parent(ctypes.c_void_p(self.root.winfo_id()))
            value = ctypes.c_int(self.theme == "dark")
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                ctypes.c_void_p(hwnd), 20, ctypes.byref(value), 4
            )
        except (AttributeError, OSError):
            pass

    def toggle_startup(self):
        desired = self.startup_choice.get()
        try:
            startup.set_enabled(desired)
        except OSError as exc:
            self.startup_choice.set(not desired)
            self.error_details = str(exc)
            self.set_status("error", "startup_error")
            return
        self.preferences["startup"] = desired
        self.persist()

    def watch_screen(self):
        self.screen_timer = None
        if not self.running:
            return
        if self.busy:
            self.screen_timer = self.root.after(3000, self.watch_screen)
            return

        def done(current):
            if not self.running:
                self.finish_stop()
                return
            self.display_value.set(str(current))
            if self.controller.observe(current, time.monotonic()):
                self.original = current
                self.set_status("manual_hold", "manual_help", seconds=180)
            power = Power()
            ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(power))
            self.screen_timer = self.root.after(
                15000 if power.ac == 1 else 30000, self.watch_screen
            )

        self.work(brightness, done, "observe")

    def curve_sensitivity(self):
        return {"gentle": 0.55, "balanced": 1.0, "responsive": 1.8}[self.preferences["sensitivity"]]

    def change_curve(self, index):
        self.preferences["sensitivity"] = ("gentle", "balanced", "responsive")[index]
        if self.controller:
            self.controller.sensitivity = self.curve_sensitivity()
        self.persist()
        self.draw_curve()

    def draw_curve(self):
        canvas = self.curve_canvas
        canvas.delete("all")
        width = max(250, canvas.winfo_width())
        points = []
        for i in range(101):
            value = curve_target(
                (i - 50) / 25,
                (self.low.get() + self.high.get()) / 2,
                self.low.get(),
                self.high.get(),
                self.curve_sensitivity(),
            )
            points.extend((15 + (width - 30) * i / 100, 110 - value))
        canvas.create_line(*points, fill=self.palette["accent"], width=3, smooth=True)
        canvas.create_text(
            20, 120, text=str(self.low.get()) + "%", fill=self.palette["muted"], anchor="w"
        )
        canvas.create_text(
            width - 20, 120, text=str(self.high.get()) + "%", fill=self.palette["muted"], anchor="e"
        )

    def update_meter(self):
        if hasattr(self, "meter_label") and self.meter_label.winfo_exists():
            self.meter_label.configure(
                text=self.t(
                    "meter_values",
                    level=round(self.last_meter["level"]),
                    quality=str(round(self.last_meter["quality"] * 100)) + "%",
                    target=self.last_meter["target"],
                )
                if self.last_meter
                else "—"
            )

    def apply_manual(self):
        if self.running or self.busy:
            messagebox.showinfo(self.t("app"), self.t("manual_tip"))
            return
        value = max(0, min(100, round(self.manual_value.get())))
        self.work(
            lambda: set_checked(value),
            lambda actual: self.display_value.set(str(actual)),
            "control",
        )

    def set_tray_option(self, key, value):
        self.preferences[key] = value
        self.persist()

    def on_minimize(self, event):
        if (
            event.widget == self.root
            and self.root.state() == "iconic"
            and self.preferences["minimize_tray"]
        ):
            self.hide_to_tray()

    def request_close(self):
        if self.preferences["close_tray"]:
            self.hide_to_tray()
        else:
            self.close()

    def show_from_tray(self):
        self.root.deiconify()
        self.root.lift()
        if self.tray_icon:
            self.tray_icon.stop()
            self.tray_icon = None

    def hide_to_tray(self):
        if self.tray_icon:
            return
        try:
            import pystray
            from PIL import Image, ImageDraw

            image = Image.new("RGB", (64, 64), "#2563eb")
            ImageDraw.Draw(image).ellipse((16, 16, 48, 48), fill="white")

            def dispatch(action):
                return lambda icon, item: self.events.put(("tray", action, None))

            icon = pystray.Icon(
                "RoomBrightness",
                image,
                self.t("app"),
                pystray.Menu(
                    pystray.MenuItem(self.t("show"), dispatch(self.show_from_tray), default=True),
                    pystray.MenuItem(self.t("stop"), dispatch(self.stop)),
                    pystray.MenuItem(self.t("exit"), dispatch(self.close)),
                ),
            )
            self.tray_icon = icon

            def ready(active_icon):
                try:
                    active_icon.visible = True
                    self.events.put(
                        (
                            "tray",
                            lambda: self.root.withdraw() if self.tray_icon is active_icon else None,
                            None,
                        )
                    )
                except Exception:
                    self.events.put(("tray", failed, None))

            def failed():
                if self.tray_icon is icon:
                    icon.stop()
                    self.tray_icon = None
                    self.root.deiconify()
                    messagebox.showinfo(self.t("app"), self.t("tray_missing"))

            def run_icon():
                try:
                    icon.run(setup=ready)
                except Exception:
                    self.events.put(("tray", failed, None))

            threading.Thread(target=run_icon, daemon=True).start()
        except Exception:
            self.root.deiconify()
            messagebox.showinfo(self.t("app"), self.t("tray_missing"))
