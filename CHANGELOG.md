# 0.8.0

- Flag repeatedly near-black, nearly textureless camera pairs as possibly covered and hold brightness. The message explicitly allows extreme room darkness; no physical-shutter recognition is claimed. Manual priority and confidence rules remain in force.
- Add opt-in independent full AC/battery curves, preserved per camera and in portable settings. Select the active curve each reading cycle; comparison/calibration saves to the chosen power source when enabled.
- Add a one-minute trial for common brightness limits, a shared curve and cover protection. Runtime changes are not persisted until Keep; expiry/Stop/Exit revert them. Keep/revert stop automatic mode, wait for serialized work and preserve manual-override detection if restoration is deferred by a lock/pause.
- Show last image level, raw curve target, guarded target and current display value separately.
- Add tray quick controls for current brightness, Start/Stop, pause/resume and usage profiles. Single-click opens the panel; double-click opens the main window.
- Keep one recognized previous installed app and provide an explicit local rollback action. Validate installation location/markers, wait for exit, swap directories and re-register the previous version. Preserve a pre-rollback preferences copy; older versions may not understand new fields.
- Add review-before-export problem ZIP containing a redacted diagnostic JSON and issue template. No images, device names, paths, raw errors or automatic upload.

# 0.7.0

- Add default-on checks at normal launch and daily, opt-in automatic download, version/release-note UI, progress/cancel, and explicit install/restart. Only this repository's stable Windows installer asset is accepted, with bounded HTTPS redirects, declared size, PE header and GitHub-provided SHA-256 checks. Recheck the file immediately before launch; failed downloads leave the current app intact.
- Stage installer files on the destination volume, wait for the requesting process to exit, preserve personal data outside the app directory, and attempt directory rollback on installation/registration failure. Actual installer replacement is not exercised by mocked unit tests.
- Publish Windows downloads to tagged GitHub Releases after passing checks/build; require repository Actions write permission.
- Add opt-in remembered automatic operation after launch/sign-in, requiring completed setup and exact camera discovery. Default remains manual Start for camera access. Explicit Stop cancels future continuation.
- Save up to twenty per-camera curve/metering profiles. Do not silently select another camera when a saved identity disappears.
- Wait for the selected display/camera on recoverable display failures and retry read-only discovery every ten seconds; reverify before resuming and respect other pause reasons and Stop. Existing camera-contention retry remains in place.
- Add pause until the next occurrence of a chosen local time, or until AC power is detected. Other pause reasons still block resume.
- Add twenty session-local undo steps for successfully saved portable preferences, preserving device/startup identity; keep curve undo and backup recovery.
- Name standard controls for accessibility, associate nearby labels and support keyboard focus; add opt-in reduced switch motion and prevent wheel edits in the time picker.

# 0.6.0

- Add a three-reading guided calibration with monotonic curve validation, dry comparison and explicit transactional Save; preserve curve undo.
- Add optional spatial rejection of the central image and isolated extreme tiles, with excluded areas darkened in requested previews. This is a heuristic, not face recognition or calibrated lux.
- Add optional directional transitions: brighten in 1s, dim in 8s; retain stability confirmation, limits and manual priority.
- Add opt-in foreground-executable pause rules using basenames only. Preserve lock/sleep/timed reasons and Stop cancellation. Poll at the existing 1.5s environment interval; access failures retain a known pause.
- Compare current and proposed preset/calibrated curves with the same simulated reading before saving, without camera/display writes.
- Add separate read-only camera/display compatibility checks and an explicit reversible display-control test, with restoration failures called out.
- Add bounded in-memory app CPU/working-set and completed-camera capture time/CPU counters. Limit expensive frame analysis to at most one per 150ms while retaining warmup/capture budgets; no preview encoding unless requested.

# 0.5.0

- Offer an explicit save-to-curve action after a successful manual adjustment with a reliable light reading less than one minute old. Expire stale suggestions and preserve curve validation and undo history.
- Add 15/30/60-minute pause and Resume now to the tray menu, with availability updated when opened.
- Show the reason for held brightness in the main status area, including remaining manual-priority time.
- Preview themes and glass transparency in a separate sample without saving or touching hardware; explicitly Save or Cancel.
- Stack panels in narrow windows, lower the minimum window size, and preserve Arabic right-to-left alignment.

# 0.4.0

- Simplify Settings with basic sections, a session-local advanced toggle, and accent/Arabic-tolerant search that reveals matching advanced sections.
- Add a hardware-free curve preview using a snapshot of the current curve and limits; simulated readings never change settings, capture images, or write brightness.
- Add 15/30/60-minute automatic-mode pauses, a countdown, and Resume now. Pausing cancels camera/control work without restoring the old brightness.
- Stop cancels pending timed resume; expiry waits for lock/sleep reasons to clear. Manual brightness changes made during a pause retain priority on resume.

# 0.3.1

- Keep the last ten changed settings snapshots locally and recover the newest valid snapshot when current settings are missing or corrupt.
- Add preview and explicit restoration of backups, preserving camera/display identity and sign-in startup choices.
- Add a reviewable diagnostic JSON report with bounded recent readings and categorized errors; omit images, device names, paths, raw errors, and automatic uploads.
- Stop retrying camera permission failures as if they were temporary camera contention.
- Apply imported/profile settings to runtime only after disk persistence succeeds, and clean up interrupted atomic writes.

# 0.3.0

- Add first-run setup with camera/display selection, comfort limits, and a reversible display-control test.
- Add camera metering-region selection with an in-memory preview and region-aware child sampling.
- Keep brightness during camera contention/disconnection and retry quietly with capped backoff; Stop cancels retries.
- Export/import/reset portable preferences without device identities, startup registration, or local paths.
- Keep up to 20 saved curve revisions and restore the last revision with Undo.
- Add optional global start/stop and open-window keyboard shortcuts with conflict detection and cleanup.
- Add Work, Gaming, Night, and named custom usage profiles.
- Check published GitHub releases on demand and open the validated download page; no automatic installation.
- Support capability-gated DDC/CI external monitors, verified writes, and independent settings per selected display.
- Optionally reduce sampling frequency during stable light/brightness, with configurable AC/battery maximum intervals.

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
