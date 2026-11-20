param([Parameter(Mandatory=$true)][string]$InstallRoot)
$ErrorActionPreference='Stop'
$expected=Join-Path $env:LOCALAPPDATA 'Programs\AutoBrightness'
if([IO.Path]::GetFullPath($InstallRoot) -ne [IO.Path]::GetFullPath($expected)){throw 'Unexpected installation path'}
$app=Join-Path $InstallRoot 'AutoBrightness.exe'
$shell=New-Object -ComObject WScript.Shell
$menu=Join-Path ([Environment]::GetFolderPath('Programs')) 'Auto Brightness.lnk'
$desktop=Join-Path ([Environment]::GetFolderPath('Desktop')) 'Auto Brightness.lnk'
$key='HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\AutoBrightness'
$run='HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
$links=@{}
foreach($path in @($menu,$desktop)){
 $links[$path]=if(Test-Path -LiteralPath $path){[IO.File]::ReadAllBytes($path)}else{$null}
}
$oldKey=Get-Item -LiteralPath $key -ErrorAction SilentlyContinue
$oldValues=@{}
if($oldKey){
 foreach($name in $oldKey.GetValueNames()){
  $oldValues[$name]=@($oldKey.GetValue($name,$null,[Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames),$oldKey.GetValueKind($name))
 }
}
$runKey=Get-Item -LiteralPath $run -ErrorAction SilentlyContinue
$hadRun=$runKey -and $runKey.GetValueNames() -contains 'RoomBrightness'
if($hadRun){
 $oldRun=$runKey.GetValue('RoomBrightness',$null,[Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames)
 $oldRunKind=$runKey.GetValueKind('RoomBrightness')
}
try{
foreach($path in @($menu,$desktop)){
 $link=$shell.CreateShortcut($path);$link.TargetPath=$app;$link.WorkingDirectory=$InstallRoot;$link.IconLocation="$app,0";$link.Save()
}
New-Item -Path $key -Force | Out-Null
$values=@{DisplayName='Auto Brightness';DisplayVersion='0.10.1';Publisher='Auto Brightness';InstallLocation=$InstallRoot;DisplayIcon=$app;UninstallString=('powershell.exe -NoProfile -ExecutionPolicy Bypass -File "'+(Join-Path $InstallRoot 'Uninstall.ps1')+'"')}
foreach($name in $values.Keys){New-ItemProperty -Path $key -Name $name -Value $values[$name] -PropertyType String -Force | Out-Null}
if((Get-ItemProperty -Path $run -Name RoomBrightness -ErrorAction SilentlyContinue).RoomBrightness){Set-ItemProperty -Path $run -Name RoomBrightness -Value ('"'+$app+'" --autostart')}
}catch{
 $failure=$_
 foreach($path in $links.Keys){
  try{
   if($null -ne $links[$path]){[IO.File]::WriteAllBytes($path,[byte[]]$links[$path])}
   elseif(Test-Path -LiteralPath $path){Remove-Item -LiteralPath $path}
  }catch{Write-Warning "Shortcut recovery failed: $_"}
 }
 try{
  $current=Get-Item -LiteralPath $key -ErrorAction SilentlyContinue
  if($current -and $oldKey){
   foreach($name in $current.GetValueNames()){if(!$oldValues.ContainsKey($name)){$current.DeleteValue($name,$false)}}
   foreach($name in $oldValues.Keys){$current.SetValue($name,$oldValues[$name][0],$oldValues[$name][1])}
  }elseif($current){Remove-Item -LiteralPath $key}
 }catch{Write-Warning "Uninstall registration recovery failed: $_"}
 try{if($hadRun){$runKey.SetValue('RoomBrightness',$oldRun,$oldRunKind)}}catch{Write-Warning "Startup registration recovery failed: $_"}
 throw $failure
}
