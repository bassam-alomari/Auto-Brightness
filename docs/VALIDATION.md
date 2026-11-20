# Windows validation

## Checks that can run without installing the app

```powershell
python -m ruff check src tests
python -m ruff format --check src tests
python -m unittest discover -s tests -q
python packaging/check_install_core.py
python packaging/build_windows.py
```

The C# fixture executable runs the **same InstallCore.cs transaction used by the real installer**. Its 16 checks exercise real file copies/directory swaps in test-owned directories: first install, update, rollback, incomplete payload, unknown-folder refusal, failed registration rollback, removal and preservation of an external preferences fixture. It does not register shortcuts, modify the user's startup entry or certify GUI installation. Building the installer runs this fixture first, and also checks the frozen application's `--self-test` before packaging.

## Prepared Windows Sandbox session

After building, run:

```powershell
python packaging/prepare_validation.py
```

Optionally stage your previous trusted installer:

```powershell
python packaging/prepare_validation.py --previous-installer "C:\path\to\previous-Setup.exe"
```

The generated `build/validation/AutoBrightness-validation.wsb` maps the project read-only and only `build/sandbox-results` writable. Network, camera, microphone and clipboard redirection are disabled. The guest script runs the file-transaction fixture, frozen version check and desktop smoke check, then writes a manual acceptance checklist. To explicitly start a supported/enabled Windows Sandbox installation:

```powershell
python packaging/prepare_validation.py --launch
```

No Windows feature is installed/enabled automatically. The configuration follows [Microsoft's Windows Sandbox configuration documentation](https://learn.microsoft.com/en-us/windows/security/application-security/application-isolation/windows-sandbox/windows-sandbox-configure-using-wsb-file).

## Manual acceptance inside the disposable guest

1. Install the staged previous version, if supplied. Change a harmless preference and Exit.
2. Install the new version with its actual Setup executable. Verify current version and preserved preferences.
3. Verify Desktop/Start-menu shortcuts, Windows uninstall registration and that an existing startup opt-out remains off.
4. Exit/relaunch. Check settings persistence without starting a camera.
5. Stop and choose Return to previous installed version. Confirm previous version, shortcuts and preferences; new fields may not be understood by the older version. A pre-rollback settings copy is preserved.
6. Reinstall current, then use its uninstaller. Verify current and recognized previous folders/shortcuts/registration removed while preferences remain.
7. Cancel an installer confirmation and verify the existing app remains usable.
8. Save observed results in the writable results folder. Do not mark a step passed without performing it.

These manual GUI/registration checks remain distinct from the automated file-system transaction checks.

## Separate hardware acceptance

Use real supported hardware and explicit camera/display controls to check camera identity, exposure metadata, manual priority, unplug/replug, CIM brightness, DDC/CI support, cancellation and restoration. Each screen needs its own driver/cable support; a VM does not establish physical display compatibility. Additional screens share a camera reading cycle but receive serial, cancellable writes, not physically simultaneous writes. Vendor DDC calls can delay cancellation while the driver is blocked. Additional-screen failures are isolated; failure of the main selected display or shared camera still pauses the common automatic session.

Live GitHub download/install acceptance requires a published stable release asset with its digest and a separately network-enabled test environment. The offline Sandbox configuration deliberately does not perform this test. Unit tests validate corrupt/oversize/cancelled downloads and unexpected URLs without live network access.
