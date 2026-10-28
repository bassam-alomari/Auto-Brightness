param([Parameter(Mandatory=$true)][string]$InstallRoot)
$ErrorActionPreference='Stop'
$expected=Join-Path $env:LOCALAPPDATA 'Programs\AutoBrightness'
if([IO.Path]::GetFullPath($InstallRoot) -ne [IO.Path]::GetFullPath($expected)){throw 'Unexpected installation path'}
$app=Join-Path $InstallRoot 'AutoBrightness.exe'
$shell=New-Object -ComObject WScript.Shell
$menu=Join-Path ([Environment]::GetFolderPath('Programs')) 'Auto Brightness.lnk'
$desktop=Join-Path ([Environment]::GetFolderPath('Desktop')) 'Auto Brightness.lnk'
foreach($path in @($menu,$desktop)){
 $link=$shell.CreateShortcut($path);$link.TargetPath=$app;$link.WorkingDirectory=$InstallRoot;$link.IconLocation="$app,0";$link.Save()
}
$key='HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\AutoBrightness'
New-Item -Path $key -Force | Out-Null
$values=@{DisplayName='Auto Brightness';DisplayVersion='0.7.0';Publisher='Auto Brightness';InstallLocation=$InstallRoot;DisplayIcon=$app;UninstallString=('powershell.exe -NoProfile -ExecutionPolicy Bypass -File "'+(Join-Path $InstallRoot 'Uninstall.ps1')+'"')}
foreach($name in $values.Keys){New-ItemProperty -Path $key -Name $name -Value $values[$name] -PropertyType String -Force | Out-Null}
$run='HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
if((Get-ItemProperty -Path $run -Name RoomBrightness -ErrorAction SilentlyContinue).RoomBrightness){Set-ItemProperty -Path $run -Name RoomBrightness -Value ('"'+$app+'" --autostart')}
