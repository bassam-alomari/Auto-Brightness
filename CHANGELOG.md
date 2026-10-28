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
