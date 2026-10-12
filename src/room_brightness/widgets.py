"""Rounded native Tk components; no additional UI framework or background renderer."""

import tkinter as tk
from .themes import EXTRA_PALETTES

PALETTES = {
    "glass": dict(
        bg="#dde8f3",
        card="#f1f6fc",
        ink="#152d46",
        muted="#4b647c",
        line="#ffffff",
        accent="#166acb",
        tint="#dcecf9",
        accent_ink="#ffffff",
        shadow="#c4d5e7",
        glass=True,
    ),
    "light": dict(
        bg="#f5f5f7",
        card="#ffffff",
        ink="#1d1d1f",
        muted="#606067",
        line="#e5e5e9",
        accent="#0071e3",
        tint="#eaf3ff",
        accent_ink="#ffffff",
        shadow="#e9e9ee",
    ),
    "dark": dict(
        bg="#101014",
        card="#1c1c22",
        ink="#f5f5f7",
        muted="#ababba",
        line="#33333c",
        accent="#2997ff",
        tint="#18334b",
        accent_ink="#071623",
        shadow="#08080b",
    ),
}


PALETTES.update(EXTRA_PALETTES)


def rounded(canvas, x, y, span, height, radius, **kwargs):
    width = span
    radius = min(radius, width / 2, height / 2)
    points = [
        x + radius,
        y,
        x + width - radius,
        y,
        x + width,
        y,
        x + width,
        y + radius,
        x + width,
        y + height - radius,
        x + width,
        y + height,
        x + width - radius,
        y + height,
        x + radius,
        y + height,
        x,
        y + height,
        x,
        y + height - radius,
        x,
        y + radius,
        x,
        y,
    ]
    return canvas.create_polygon(points, smooth=True, splinesteps=32, **kwargs)


class RoundedCard(tk.Canvas):
    def __init__(self, parent, palette, **kwargs):
        super().__init__(parent, bg=palette["bg"], highlightthickness=0, height=200, **kwargs)
        self.palette = palette
        self.inner = tk.Frame(self, bg=palette["card"])
        self.item = self.create_window(24, 24, window=self.inner, anchor="nw")
        self.bind("<Configure>", self.resize)
        self.inner.bind("<Configure>", self.resize)

    def resize(self, event=None):
        width = max(80, self.winfo_width())
        self.itemconfigure(self.item, width=max(40, width - 48))
        height = self.inner.winfo_reqheight() + 48
        if int(float(self.cget("height"))) != height:
            super().configure(height=height)
        self.delete("surface")
        rounded(
            self,
            1,
            3,
            width - 2,
            height - 4,
            22,
            fill=self.palette["shadow"],
            outline="",
            tags="surface",
        )
        rounded(
            self,
            1,
            0,
            width - 2,
            height - 4,
            22,
            fill=self.palette["card"],
            outline=self.palette["line"],
            width=1,
            tags="surface",
        )
        if self.palette.get("glass"):
            self.create_line(25, 2, width - 25, 2, fill="#ffffff", width=2, tags="surface")
            self.create_line(5, 24, 5, height - 28, fill="#ffffff", width=1, tags="surface")
            self.create_line(
                28, height - 7, width - 28, height - 7, fill="#d6e3f0", width=1, tags="surface"
            )
        self.tag_lower("surface")


class RoundedButton(tk.Canvas):
    def __init__(self, parent, label, action, palette, primary=False, width=180):
        super().__init__(
            parent,
            width=width,
            height=46,
            bg=parent.cget("bg"),
            highlightthickness=0,
            takefocus=1,
            cursor="hand2",
        )
        self.label, self.action, self.palette, self.primary = label, action, palette, primary
        self.enabled, self.hover = True, False
        self.bind("<Configure>", lambda event: self.draw())
        self.bind("<Enter>", lambda event: self.over(True))
        self.bind("<Leave>", lambda event: self.over(False))
        self.bind("<Button-1>", self.activate)
        self.bind("<space>", self.activate)
        self.bind("<Return>", self.activate)
        self.bind("<FocusIn>", lambda event: self.draw())
        self.bind("<FocusOut>", lambda event: self.draw())
        self.draw()

    def over(self, active):
        self.hover = active
        self.draw()

    def activate(self, event=None):
        if self.enabled:
            self.focus_set()
            self.action()
        return "break"

    def configure(self, cnf=None, **kwargs):
        if "text" in kwargs:
            self.label = kwargs.pop("text")
        if "state" in kwargs:
            self.enabled = kwargs.pop("state") != "disabled"
            super().configure(cursor="hand2" if self.enabled else "arrow")
        result = super().configure(cnf, **kwargs)
        self.draw()
        return result

    config = configure

    def cget(self, key):
        if key == "state":
            return "normal" if self.enabled else "disabled"
        if key == "text":
            return self.label
        return super().cget(key)

    def draw(self):
        if not hasattr(self, "palette"):
            return
        self.delete("all")
        width, height = self.winfo_width(), 46
        if width <= 1:
            width = int(float(super().cget("width")))
        fill = self.palette["accent"] if self.primary else self.palette["tint"]
        color = self.palette["accent_ink"] if self.primary else self.palette["accent"]
        if not self.enabled:
            fill, color = self.palette["line"], self.palette["muted"]
        if self.hover and self.enabled and not self.primary:
            fill = self.palette["line"]
        rounded(
            self,
            1,
            1,
            width - 2,
            height - 2,
            14,
            fill=fill,
            outline=self.palette["accent"] if self.focus_get() == self else "",
            width=2,
        )
        if self.palette.get("glass") and self.enabled:
            self.create_line(
                18, 5, width - 18, 5, fill="#9dc4ef" if self.primary else "#ffffff", width=1
            )
        self.create_text(
            width / 2, height / 2, text=self.label, fill=color, font=("Segoe UI", 11, "bold")
        )
