# 0.2.0

- Ignore unreliable or disagreeing light readings; require two cycles for large brightness changes and ignore small differences.
- Add calm, balanced, and fast transitions, requested through the Windows display driver.
- Add a draggable custom curve editor with add/remove points and reset.
- Save an explicitly confirmed manual brightness preference into the custom curve, with monotonic validation.
- Add separate optional AC and battery brightness limits.
- Pause camera/control work while locked or sleeping, and resume only if automatic mode was previously active.
- Add a rolling one-minute light, target, and actual-brightness chart, plus clearer diagnostic explanations.
- Package a standalone Windows portable app and per-user installer, desktop/Start menu shortcuts, and uninstaller.

# 0.1.0

First public release of Auto Brightness.

- Adjust screen brightness from the average of two camera light readings, with smooth transitions and configurable brightness limits.
- Default custom curve: image 15 → 50%, 20 → 70%, 25 → 90%, and 27 → 100%; readings of 12 or less use the configured minimum.
- Include ten brightness curves, multiple themes, glass transparency, and the new app logo.
- Support English, Arabic with dialect options, Spanish, French, German, Portuguese, Chinese, and Hindi.
- Default sampling intervals: five seconds on AC power and ten seconds on battery.
- Include system-tray controls, optional launch at Windows sign-in, setup scripts, documentation, and automated checks.
