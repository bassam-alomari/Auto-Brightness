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

Download `AutoBrightness-0.7.0-Setup.exe` from the release assets, close any running copy using Exit, and run the installer. It installs under your current account without Python or administrator privileges and creates Desktop and Start menu shortcuts. Remove it through Windows Installed apps; personal preferences are preserved. A portable ZIP is also available: extract it and open `AutoBrightness.exe`.

For developers: `python -m pip install -e ".[windows-build]"` then `python packaging/build_windows.py` on Windows with Python 3.12 x64 builds both packages. The Windows installer workflow also builds them when run manually or on a version tag.



## Setup and tools in 0.3.0

The first-run wizard lets you choose a camera and display, set comfort limits, and explicitly test display control. The test briefly adjusts brightness and restores it. Close the wizard to postpone it, or reopen it from Settings → First setup. Camera capture begins only through Start or Capture preview/Check now.

Choose a metering region in Settings: capture an in-memory full-frame preview and drag a rectangle. Only that region is analyzed; Whole image restores the default. This can reduce interference from a window or face, but remains a camera estimate rather than a lux measurement.

A busy or disconnected camera holds the current brightness and retries after 5, 10, 20, 40, then at most 60 seconds. Camera identity is preserved. Stop cancels the retry; display-control errors remain visible instead of being silently retried.

Export/Import settings uses a versioned JSON file, with a confirmation preview on import. Exports omit camera/display identity, paths, startup registration, and preview frames. Reset restores portable preferences without changing startup/device choices. Undo saved curve change restores up to 20 previous curve point sets, including learned preferences.

Work, Gaming, and Night are built-in usage profiles; save your own named profiles. Stop automatic mode before importing, switching profiles, editing the region, or selecting another display. Optional global shortcuts are Ctrl+Alt+B (start/stop) and Ctrl+Alt+O (open window). If another app owns a shortcut, the option is disabled and explains the conflict.

Check for updates contacts the GitHub releases API only when clicked. It ignores draft/prerelease releases and compares numeric version components. Open release page navigates to the official repository release; downloading and installing stay under your control.

External monitors are listed only if Windows reports brightness capability through DDC/CI and a valid range can be read. Enable DDC/CI in the monitor menu if needed. One selected display is controlled at a time; each stores its own curve, comfort range, and sampling settings. Disconnecting a selected display causes a visible error rather than switching to another display. External transitions use cancellable verified steps and may differ from the internal display fade. Quantized hardware brightness values are respected. Physical external-monitor validation is still required on your equipment. See [Microsoft monitor configuration documentation](https://learn.microsoft.com/en-us/windows/win32/api/highlevelmonitorconfigurationapi/nf-highlevelmonitorconfigurationapi-getmonitorbrightness).

Power saving is optional and initially disabled. After four stable light/brightness cycles, sampling gradually slows, never past the configured AC/battery maximum. A changed or unreliable reading restores the base interval. Each cycle still takes two readings at its midpoint and endpoint. Longer intervals delay detection of new light changes; the effective maximum cannot be shorter than the base interval.


## Recovery and diagnostics in 0.3.1

Changed settings create up to ten local snapshots under the preferences folder, while identical saves create no duplicates. Missing or corrupt current settings recover the newest valid snapshot. Settings → Restore a backup previews available snapshots and asks before applying one. Current camera/display identity and startup registration are preserved, and current preferences are backed up before restoration. If writing fails, imported/profile preferences are not applied to runtime.

Settings → Diagnostic report opens a read-only preview before saving a JSON file. It includes the app version, numerical control settings, up to 60 recent readings, and up to 50 categorized errors from the current session. It excludes images, device names/identifiers, account/file paths, raw error text, and named profiles. Reports are never sent automatically. Camera permission failures stop with an error rather than retrying indefinitely; ordinary busy/disconnected-camera retries remain available.

## Simpler controls in 0.4.0

Settings initially shows the basic sections. Show advanced settings reveals the remaining tools and stability/power options; search finds matching sections even when advanced controls are collapsed. Search tolerates accents and common Arabic letter variations. The toggle and search are retained within the current window session. Clearing search restores the chosen basic/advanced view.

Preview curve takes a snapshot of the selected curve and effective controller limits (or general limits when stopped). Simulate readings from 0 to 255 to see the curve target before confirmation/manual holds, without changing actual screen brightness, preferences, or camera state.

From Home, pause automatic mode for 15, 30, or 60 minutes. The countdown updates while camera/control work is cancelled and current brightness is retained. Resume now ends the pause early. Stop cancels automatic resumption. If the timer expires while locked or sleeping, resumption waits until all pause reasons clear. A detected manual brightness change during the pause gets the normal three-minute priority hold after resume. Pauses are session-only; quitting does not silently resume the camera on the next launch.

## Everyday controls (0.5.0)

After a successful manual brightness adjustment, a reliable reading less than one minute old enables **Save this brightness to my curve**. Saving is explicit; stale readings and curves that would reverse direction are rejected. Stop automatic mode before saving settings. Existing curve undo remains available.

The tray menu offers 15/30/60-minute pauses and Resume now. The main status area explains why brightness is held and counts down manual priority. Narrow windows stack their panels vertically. Settings includes an appearance sample with theme and glass-transparency controls: Cancel leaves settings untouched; Save applies and persists the choice while stopped.

## Calibration and measurement (0.6.0)

Open Settings → Calibration and measurement. All new measurement/response/pause options start disabled to preserve existing curves and defaults.

- **Guided calibration:** stop automatic mode, arrange dim/medium/bright light, capture a reliable reading at each step, and enter your preferred screen brightness (use Windows to try it). The tool never adjusts the display. Readings must increase by at least one level, fall strictly between 12 and 254, and preferred brightness must not decrease. Review the proposed curve against your current curve before explicitly saving. This maps image readings, not lux; camera exposure changes can affect calibration.
- **Compare curves:** a shared 0–255 simulator compares your current curve with any preset or proposed calibration under your configured low/high limits. Saving uses the normal transactional preferences path and preserves undo history. Stability/manual-priority decisions remain separate.
- **Measurement and response:** optional spatial protection rejects the centre and isolated extreme 4×4 tiles inside your chosen metering region, replacing rejected pixels with the retained median before analysis. Requested camera previews darken ignored areas. It cannot identify faces or separate diffuse screen light from room light; it may discard real light. Recalibrate after changing region/protection/camera. Optional directional response uses 1-second upward and 8-second downward fades; hardware drivers determine physical behavior.
- **App pauses:** opt in and enter up to 30 executable basenames (e.g. vlc.exe), one per line. Pause applies while a listed desktop app is in the foreground, checked at 1.5-second intervals; it does not detect video playback or games automatically. Only configured basenames are saved, no titles or use history. A failed foreground query holds the existing pause; other pause reasons and Stop take priority. Disable/clear the rules to remove an application pause. No elevated access is requested.
- **Compatibility:** camera/read check opens the selected camera and reads brightness without writing it. The separate control test explicitly changes by five points and attempts restoration in finally; heed any restoration failure and restore manually. Automatic mode must be stopped. Mock tests do not certify your camera/monitor.
- **Resource usage:** live app process CPU (per logical core, not normalized across cores) and working-set memory, plus cumulative time/CPU from completed camera captures. Failed captures and unrelated child-process work are excluded. Values remain in a bounded in-memory session buffer. Frame analysis is throttled to 150ms with the existing 1.5s warmup and 3s camera budget. Use Adaptive sampling for fewer bursts; actual resource savings depend on hardware.

## Sessions, devices and updates (0.7.0)

Open **Session and updates** from Home or Settings. Stop automatic mode before saving options, undoing preferences or installing.

- Optional remembered automatic mode starts the camera after a normal relaunch/sign-in only when it was previously running and initial setup is complete. This is off by default. Explicit Stop clears continuation; closing via Exit preserves the last intent. Saved camera identity is required; no fallback camera is silently used. Camera/Windows permissions still apply.
- Camera selection remembers each camera's custom curve, preset, metering region and spatial protection (up to twenty identities). First use of a new camera inherits current options. Profiles remain local and are not exported with portable settings.
- Recoverable display-control failures pause rather than switch targets. Exact camera/display discovery plus brightness readback is retried every ten seconds, then the normal reversible control verification runs before automatic mode resumes. Stop cancels recovery and all pending resume. Permission errors do not retry automatically; driver faults may still require manual repair.
- Pause until a selected local HH:mm (next 24 hours, tracked by monotonic countdown) or AC connection (checked every two seconds). If AC is already connected, the condition is immediately satisfied on the next check. Lock/sleep/application pauses must also clear. These pauses are session-local, not persisted across a restart.
- Undo covers up to twenty successful portable-preference changes in the current session. It leaves camera/display identity and sign-in registration untouched. Curve undo and saved backup restoration are still separate options.
- Reduce motion disables switch animations. Standard Qt controls have accessible names/buddies and keyboard focus; the time picker ignores wheel edits. Accessibility is validated through control properties/keyboard behavior, not a full screen-reader certification.

### Integrated updater

Normal desktop launch checks GitHub once, then every 24 hours while open. Disable **Check on opening and daily** for manual checks only. Automatic download starts **off** and never installs automatically. No camera frames/settings are sent to GitHub; the normal HTTPS request reveals the client's network address to GitHub. Tests and smoke checks do not make update requests.

The version must be a newer stable published GitHub Release in `bassam-alomari/Auto-Brightness`, with an asset named `AutoBrightness-X.Y.Z-Setup.exe`, a positive size at most 300 MiB, and GitHub's `sha256:` asset digest. Missing/unverifiable installers remain visible but cannot be downloaded in-app. Only GitHub and its allowed release-asset HTTPS hosts may be followed. Downloads have bounded time/size, a cancel option, a partial temporary file, PE-header and size/hash checks, and atomic promotion only on success. Matching cached downloads are verified and reused. The checksum protects transfer integrity; this is not publisher code signing.

**Install and restart** requires stopped/idle operation, verifies the file again, opens the per-user installer and exits the app normally. The installer asks for confirmation, waits up to two minutes for the previous process, stages files, swaps the app folder and attempts rollback on failure. Settings in LocalAppData/RoomBrightness are preserved. A source/portable user who installs the update moves to the standard installed application; the source checkout is not rewritten. Existing sign-in registration is pointed to the installed executable, preserving opt-outs. Full installation/rollback still depends on Windows file permissions and is not physically exercised by development tests.

Pushing a version tag now runs tests/build and creates or updates that tag's GitHub Release with installer/portable assets. A failed build publishes no new installer. The workflow needs repository Actions permission to write contents. Older releases are kept; simply pushing code without a tag does not publish an update.
