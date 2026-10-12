# Manual hardware verification for 0.3.0

Tests use synthetic images and mock hardware/registry access. Run these checks on the actual device before claiming measured accuracy or compatibility.

- [ ] Install, launch, select the correct named camera and press Start once.
- [ ] Observe the short brightness verification and restoration.
- [ ] Confirm no dim/bright calibration steps are required.
- [ ] Change room lighting while screen content stays stable; check gradual adaptation.
- [ ] Keep room lighting stable and switch screen content light/dark; check for unwanted feedback.
- [ ] Move your face or introduce an isolated bright patch; check that this does not dominate readings.
- [ ] Record whether exposure metadata is available, along with driver/model details.
- [ ] Adjust brightness manually from Windows; confirm the manual hold and no opposing writes.
- [ ] After the hold, confirm a fresh reference preserves the chosen level in unchanged room lighting.
- [ ] Set manual brightness below 10%; confirm no automatic increase until it is raised.
- [ ] Switch app language/theme explicitly and reopen; verify persistence.
- [ ] Select System, change Windows app color mode and UI-language override; verify live following where Windows exposes the change.
- [ ] Switch keyboard input language only; confirm it is not treated as an intentional UI-language change.
- [ ] Navigate settings by keyboard; check focus, small-window scrolling, Arabic alignment and both color schemes.
- [ ] Enable sign-in launch explicitly, sign out/in and confirm the visible app opens with the camera off.
- [ ] Disable sign-in launch and confirm only this app's registration is removed.
- [ ] Press Stop during capture; confirm capture exits and restoration respects the latest manual choice.
- [ ] Disconnect/reorder cameras; confirm the app stops before capturing another device.
- [ ] Confirm camera indicators turn off between bursts and during manual hold.
- [ ] Check AC/battery intervals and measure total CPU/power use separately from image-analysis timings.

Record failed checks as well as successful ones. Restore brightness manually if restoration cannot be confirmed.
