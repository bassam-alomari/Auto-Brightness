param([Parameter(Mandatory=$true)][int]$WaitPid)
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Windows.Forms
$root=[IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'Programs\AutoBrightness'))
$previous=$root+'-previous'
$swap=$root+'-rollback-'+[Guid]::NewGuid().ToString('N')
try {
 foreach($folder in @($root,$previous)){
  if(-not (Test-Path -LiteralPath (Join-Path $folder '.autobrightness-install'))){throw 'Recognized app backup not found'}
  if((Get-Item -LiteralPath $folder).Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'Linked installation folders are not supported'}
 }
 $process=Get-Process -Id $WaitPid -ErrorAction SilentlyContinue
 if($process){Wait-Process -Id $WaitPid -Timeout 120 -ErrorAction Stop}
 $settings=Join-Path $env:LOCALAPPDATA 'RoomBrightness\settings.json'
 if(Test-Path -LiteralPath $settings){Copy-Item -LiteralPath $settings -Destination ($settings+'.before-rollback') -Force}
 [IO.Directory]::Move($root,$swap)
 try{[IO.Directory]::Move($previous,$root)}catch{[IO.Directory]::Move($swap,$root);throw}
 [IO.Directory]::Move($swap,$previous)
 try{
  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root 'RegisterInstall.ps1') -InstallRoot $root
  if($LASTEXITCODE -ne 0){throw 'Could not register the previous version'}
 }catch{
  [IO.Directory]::Move($root,$swap)
  [IO.Directory]::Move($previous,$root)
  [IO.Directory]::Move($swap,$previous)
  throw
 }
 Start-Process -FilePath (Join-Path $root 'AutoBrightness.exe') -WorkingDirectory $root -WindowStyle Hidden
}catch{[Windows.Forms.MessageBox]::Show(('Rollback could not finish. Your app folders have been preserved. '+$_.Exception.Message),'Auto Brightness') | Out-Null}
