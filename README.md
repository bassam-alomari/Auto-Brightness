# Auto Brightness

A local Windows app that adjusts internal-display brightness from the average of two camera readings. Images stay in memory: no saved photos, recording or uploads. Image brightness is a heuristic, not calibrated room illuminance or a trained AI model.

## Run

1. Install Python 3.10+ and run `Setup.cmd`.
2. Run `Start.cmd`.
3. Choose a camera and press Start. Screen control is verified before automatic operation.

Requires a Windows internal display that supports CIM brightness methods. WMIC is not required. The camera indicator may illuminate during sampling.

## Defaults and controls

- Comfort range: 10–80%; the minimum supports 0% and the maximum supports 100%.
- Pair cycle: 5 seconds on AC, 10 seconds on battery. A reading is requested at the midpoint and another at the endpoint; their image levels are averaged before mapping to brightness. Camera startup and busy work may delay actual sampling. The next cycle begins after the previous brightness transition.
- Glass transparency: 50%.
- Close-to-tray: enabled; choose Exit from the tray menu to quit.
- Open at Windows sign-in: enabled. The first normal launch registers a current-user startup entry. Later opt-outs remain saved. Sign-in opens the window; the camera still requires Start.
- Manual Windows brightness changes take priority and temporarily hold automatic adaptation.

## Curves

Ten persistent presets update both the controller and preview. Your curve is the default: ≤12/255 maps to your floor, 15 to 50%, 20 to 70%, 25 to 90%, and ≥27 to 100%, clamped to the configured limits. Smooth interpolation joins these points.

Additional presets: Linear, Smooth, Gentle, Responsive, Night comfort, Daylight, Balanced, High contrast and Battery saver. These use more sensitive image ranges. Raise the configured maximum to 100% to allow a 100% target.

The app requests a four-second native display transition and verifies the result. Actual fading depends on the display driver. Unsupported writes report an error rather than claiming success. Stop reapplies the current brightness to cancel a pending fade; restoration is optional.

## Appearance and languages

Light, Dark, Liquid Glass, Midnight blue, Forest, Violet, Warm sand, Soft rose and OLED black are available. Glass uses a Windows composition API; its blur and corner appearance depend on the compositor. No desktop capture is performed by the app.

The active Qt interface supports English, Arabic, Spanish, French, German, Portuguese, Simplified Chinese and Hindi. System follows the Windows UI language; manual choices persist. Arabic has Formal, Jordanian, Egyptian and Gulf style options. Formal is the default; dialect-specific user guidance is combined with neutral technical labels. Raw provider errors and obsolete calibration text may fall back to English.

## Development

Install with `python -m pip install -e ".[dev]"`, then run `python -m unittest discover -s tests` on Windows and `ruff check src tests`. Hardware tests require a real compatible display and camera; mocked regression tests do not establish ambient-light accuracy or visual fade quality. See `docs/HARDWARE_TESTING.md`.

The internal Python package, settings directory and startup registry identity retain their original names for upgrade compatibility. Personal preferences are outside the source checkout. MIT licensed; see `LICENSE` and `THIRD_PARTY_NOTICES.md`.


## Comfort controls in 0.2.0

Stability protection is enabled by default: unreliable readings or pairs differing by more than 6 camera units are held, changes of 15 brightness points or more need two consecutive cycles, and changes smaller than 3 points are ignored. The threshold and protection can be changed in Settings. Configured endpoints remain reachable. This adds deliberate confirmation latency.

Choose Calm (8 s), Balanced (4 s), or Fast (1 s) transitions. These durations are driver requests; some displays apply brightness immediately.

Edit your curve by dragging its points; the first endpoint stays at image 12 and the final point stays at 100%. Add/remove intermediate points or reset the original curve. Stop automatic mode before editing. To learn a preference, set brightness manually, take a fresh reading using Check now, then click Save this brightness for this light. Preferences that reverse the curve are rejected.

Optional power profiles have separate brightness limits for AC and battery. When enabled, these override the general limits for automatic control. The chart keeps only the last minute of readings in memory; the light trace uses its own camera-unit scale, while target and screen use 0–100%. Diagnostics explain confirmation, rejected readings, manual holds, and camera/display errors.

The camera is cancelled on Windows lock/suspend and restarted after unlock/resume only if automatic mode was already active. Stop cancels pending automatic resume. Session notifications require a supported Windows desktop session.

## Standalone installation

Download `AutoBrightness-0.2.0-Setup.exe` from the release assets, close any running copy using Exit, and run the installer. It installs under your current account without Python or administrator privileges and creates Desktop and Start menu shortcuts. Remove it through Windows Installed apps; personal preferences are preserved. A portable ZIP is also available: extract it and open `AutoBrightness.exe`.

For developers: `python -m pip install -e ".[windows-build]"` then `python packaging/build_windows.py` on Windows with Python 3.12 x64 builds both packages. The Windows installer workflow also builds them when run manually or on a version tag.

