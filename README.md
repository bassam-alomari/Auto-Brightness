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
