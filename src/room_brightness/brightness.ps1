param([ValidateSet('read','set')][string]$Action='read',[int]$Value=40)
$ErrorActionPreference='Stop'
try {
 $b=@(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightness | Where-Object Active)
 if($b.Count -ne 1){throw 'Expected one active internal display'}
 if($Action -eq 'set'){
  if($Value -lt 0 -or $Value -gt 100){throw 'Brightness outside safe range'}
  $m=Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods | Where-Object InstanceName -eq $b[0].InstanceName
  if(!$m){throw 'Brightness control unavailable'}
  $r=Invoke-CimMethod -InputObject $m -MethodName WmiSetBrightness -Arguments @{Timeout=[uint32]1;Brightness=[byte]$Value}
  # Some providers omit ReturnValue. Missing status is not proof of failure
  # or success: always confirm the actual display brightness below.
  if($null -ne $r.ReturnValue -and $r.ReturnValue -ne 0){throw "WmiSetBrightness returned error code $($r.ReturnValue)"}
  $deadline=[DateTime]::UtcNow.AddSeconds(4)
  do {
   Start-Sleep -Milliseconds 200
   $actual=@(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightness | Where-Object InstanceName -eq $b[0].InstanceName)
   if($actual.Count -ne 1 -or $null -eq $actual[0].CurrentBrightness){throw 'Brightness readback unavailable'}
   if([int]$actual[0].CurrentBrightness -eq $Value){
    Write-Output ([int]$actual[0].CurrentBrightness)
    exit 0
   }
  } while([DateTime]::UtcNow -lt $deadline)
  throw "Brightness readback mismatch: requested $Value%, received $($actual[0].CurrentBrightness)%"
 }
 $b=Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightness | Where-Object Active
 Write-Output ([int]$b.CurrentBrightness)
} catch {[Console]::Error.WriteLine($_.Exception.Message);exit 1}
