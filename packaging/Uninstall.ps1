$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Windows.Forms
$target=[IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'Programs\AutoBrightness'))
if([IO.Path]::GetFullPath($PSScriptRoot) -ne $target -or -not (Test-Path -LiteralPath (Join-Path $target '.autobrightness-install'))){throw 'Invalid installation directory'}
if([Windows.Forms.MessageBox]::Show('Remove Auto Brightness? Close the app using Exit first. Your preferences will be preserved.','Uninstall Auto Brightness','YesNo') -ne 'Yes'){exit}
try{
 $exe=Join-Path $target 'AutoBrightness.exe'
 $check=[IO.File]::Open($exe,'Open','ReadWrite','None');$check.Dispose()
 $shell=New-Object -ComObject WScript.Shell
 foreach($path in @((Join-Path ([Environment]::GetFolderPath('Programs')) 'Auto Brightness.lnk'),(Join-Path ([Environment]::GetFolderPath('Desktop')) 'Auto Brightness.lnk'))){
  if(Test-Path -LiteralPath $path){if($shell.CreateShortcut($path).TargetPath -eq $exe){Remove-Item -LiteralPath $path}}
 }
 $run='HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
 $command=(Get-ItemProperty -Path $run -Name RoomBrightness -ErrorAction SilentlyContinue).RoomBrightness
 if($command -and $command.Contains($exe)){Remove-ItemProperty -Path $run -Name RoomBrightness}
 Remove-Item -LiteralPath 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\AutoBrightness' -ErrorAction SilentlyContinue
 Remove-Item -LiteralPath $target -Recurse -Force
 [Windows.Forms.MessageBox]::Show('Auto Brightness was removed.','Auto Brightness') | Out-Null
}catch{[Windows.Forms.MessageBox]::Show('Close Auto Brightness using Exit, then retry. '+$_.Exception.Message,'Uninstall failed') | Out-Null;exit 1}
