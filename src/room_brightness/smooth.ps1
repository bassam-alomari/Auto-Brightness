param([int]$Start,[int]$Target)
$ErrorActionPreference='Stop'
try {
 if($Start -lt 0 -or $Start -gt 100 -or $Target -lt 0 -or $Target -gt 100){throw 'Invalid brightness range'}
 $display=@(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightness | Where-Object Active)
 if($display.Count -ne 1){throw 'Expected one internal display'}
 $id=$display[0].InstanceName
 $method=Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods | Where-Object InstanceName -eq $id
 $actual=[int]$display[0].CurrentBrightness
 if($actual -ne $Start){Write-Output "M $actual"; exit 0}
 # Ask the display provider to fade once over four seconds instead of
 # sending many discrete backlight requests. Support is driver-dependent.
 $result=Invoke-CimMethod -InputObject $method -MethodName WmiSetBrightness -Arguments @{Timeout=[uint32]4;Brightness=[byte]$Target}
 if($null -ne $result.ReturnValue -and $result.ReturnValue -ne 0){throw 'Driver rejected brightness transition'}
 $last=$Start
 $direction=[Math]::Sign($Target-$Start)
 $deadline=[DateTime]::UtcNow.AddSeconds(8)
 do {
  Start-Sleep -Milliseconds 35
  $read=Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightness | Where-Object InstanceName -eq $id
  $actual=[int]$read.CurrentBrightness
  if(($actual-$last)*$direction -lt 0 -or ($actual-$Target)*$direction -gt 0){
   Write-Output "M $actual";exit 0
  }
  if($actual -ne $last){Write-Output "P $actual";$last=$actual}
  if($actual -eq $Target){exit 0}
 } while([DateTime]::UtcNow -lt $deadline)
 throw "Brightness transition readback mismatch: requested $Target received $actual"

} catch {Write-Output ("E "+$_.Exception.Message);exit 1}
