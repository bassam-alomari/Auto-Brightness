# Contributing

Use Python 3.10+ and install the `dev` extra described in the README. Keep camera acquisition, Windows hardware access and pure brightness decisions separate.

Run the unit tests, Ruff checks and package build before opening a pull request. Add meaningful tests for changes to cancellation, restoration, verification or control behavior. Tests must mock hardware rather than changing the contributor's display brightness or opening their webcam.

Describe the user-visible problem, the resulting behavior and how you validated it. Include real hardware details only after running the manual checklist. Do not attach webcam frames or personal calibration files.
