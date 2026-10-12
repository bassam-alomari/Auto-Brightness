"""Additional opaque themes; glass rendering is kept separate."""

THEME_NAMES = {
    "midnight": ("Midnight blue", "كحلي ليلي"),
    "forest": ("Forest", "أخضر غابة"),
    "violet": ("Violet", "بنفسجي"),
    "sand": ("Warm sand", "رملي دافئ"),
    "rose": ("Soft rose", "وردي هادئ"),
    "oled": ("OLED black", "أسود OLED"),
}
EXTRA_PALETTES = {}
for key, bg, card, ink, muted, line, accent, tint, dark in [
    ("midnight", "#0b1222", "#142137", "#f2f6ff", "#aabbd3", "#2e4260", "#5bafff", "#1c3654", True),
    ("forest", "#0d1915", "#182a22", "#eff8f1", "#a8c3b2", "#345343", "#54c88b", "#203f30", True),
    ("violet", "#171222", "#281e38", "#faf3ff", "#c3b1d8", "#4a365e", "#b88aff", "#3a2850", True),
    ("sand", "#f5f0e7", "#fffaf1", "#352c22", "#756653", "#e2d6c2", "#96672d", "#f1e5cc", False),
    ("rose", "#fff3f5", "#fffafb", "#442931", "#85606e", "#ecd3dc", "#b74676", "#f7dfeb", False),
    ("oled", "#000000", "#101014", "#fafafa", "#b2b2be", "#292931", "#65b6ff", "#14283c", True),
]:
    EXTRA_PALETTES[key] = dict(
        bg=bg,
        card=card,
        ink=ink,
        muted=muted,
        line=line,
        accent=accent,
        tint=tint,
        accent_ink="#ffffff",
        shadow=bg,
        dark=dark,
    )
