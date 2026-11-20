$ErrorActionPreference='Stop'
if($PSScriptRoot -ne 'C:\AutoBrightnessInput\packaging'){throw 'Run only in the prepared validation Sandbox'}
$inputRoot='C:\AutoBrightnessInput'
$results='C:\AutoBrightnessResults'
$log=Join-Path $results ('guest-'+(Get-Date -Format yyyyMMdd-HHmmss)+'.txt')
Start-Transcript -LiteralPath $log
try{
 $core=Join-Path $inputRoot 'build\validation\InstallCoreTests.exe'
 & $core $env:TEMP
 if($LASTEXITCODE -ne 0){throw 'Install core checks failed'}
 $app=Join-Path $inputRoot 'dist\AutoBrightness\AutoBrightness.exe'
 & $app --version
 if($LASTEXITCODE -ne 0){throw 'Version check failed'}
 & $app --self-test
 if($LASTEXITCODE -ne 0){throw 'Desktop smoke check failed'}
 @'
AUTOMATED GUEST CHECKS COMPLETE. Remaining manual VM acceptance checks:
1. If build\validation\PreviousSetup.exe exists, install it inside this Sandbox first.
2. Run the current dist\AutoBrightness-*-Setup.exe. Confirm install and open the app.
3. Verify current version, Start-menu/Desktop shortcuts and Windows uninstall registration.
4. Change a harmless preference, Exit, reopen and verify persistence (do not start camera).
5. Update an installed previous copy; verify preferences and previous-version backup.
6. Stop, select Return to previous installed version and confirm. Verify version/shortcuts.
7. Reinstall current, then run Uninstall. Verify app and previous folder removed, preferences retained.
8. Save observations in this results folder. Do not mark these steps passed unless performed.
Network, camera and microphone are disabled. Hardware support/live downloads require separate explicit tests.
'@ | Set-Content -LiteralPath (Join-Path $results 'MANUAL-ACCEPTANCE.txt') -Encoding UTF8
 Write-Output 'Guest smoke/core checks passed. Manual installed-app acceptance remains pending.'
}finally{Stop-Transcript}
