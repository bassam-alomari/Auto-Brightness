"""Exercise the actual bridge with mocked CIM providers; never touch hardware."""

import base64
import os
import subprocess
import unittest

from room_brightness.paths import RESOURCE_DIR


@unittest.skipUnless(os.name == "nt", "Windows PowerShell regression tests")
class PowerShellTests(unittest.TestCase):
    def bridge(self, status, change=True, value=45):
        script = str(RESOURCE_DIR / "brightness.ps1").replace("'", "''")
        mock = """
$script:level=40
function Get-CimInstance {
 param($Namespace,$ClassName)
 if($ClassName -eq 'WmiMonitorBrightnessMethods') {
  return [pscustomobject]@{Active=$true;InstanceName='test-display'}
 }
 return [pscustomobject]@{Active=$true;InstanceName='test-display';CurrentBrightness=$script:level}
}
function Invoke-CimMethod {
 param($InputObject,$MethodName,$Arguments)
 CHANGE
 return STATUS
}
"""
        mock = mock.replace("CHANGE", "$script:level=$Arguments.Brightness" if change else "")
        mock = mock.replace("STATUS", status)
        command = mock + f"\n. '{script}' -Action set -Value {value}"
        encoded = base64.b64encode(command.encode("utf-16-le")).decode("ascii")
        return subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-EncodedCommand",
                encoded,
            ],
            capture_output=True,
            text=True,
            timeout=12,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

    def test_missing_return_property_accepts_confirmed_brightness(self):
        result = self.bridge("([pscustomobject]@{})")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "45")

    def test_null_result_accepts_confirmed_brightness(self):
        result = self.bridge("$null")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_zero_status_accepts_confirmed_brightness(self):
        result = self.bridge("([pscustomobject]@{ReturnValue=0})")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_nonzero_status_is_rejected(self):
        result = self.bridge("([pscustomobject]@{ReturnValue=5})")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("error code 5", result.stderr)
        self.assertNotIn("CategoryInfo", result.stderr)

    def test_missing_status_never_accepts_unchanged_display(self):
        result = self.bridge("([pscustomobject]@{})", change=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("readback mismatch", result.stderr)

    def test_one_percent_step_rejects_old_readback(self):
        result = self.bridge("([pscustomobject]@{})", change=False, value=41)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("readback mismatch", result.stderr)

    def test_one_percent_step_accepts_actual_new_value(self):
        result = self.bridge("([pscustomobject]@{})", value=41)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "41")

    def ramp_bridge(self, start, target):
        script = str(RESOURCE_DIR / "smooth.ps1").replace("'", "''")
        mock = """
$script:level=40
function Get-CimInstance { param($Namespace,$ClassName)
 if($ClassName -eq 'WmiMonitorBrightnessMethods'){return [pscustomobject]@{InstanceName='test'}}
 return [pscustomobject]@{Active=$true;InstanceName='test';CurrentBrightness=$script:level}
}
function Invoke-CimMethod {param($InputObject,$MethodName,$Arguments)
 $script:level=$Arguments.Brightness
 return [pscustomobject]@{ReturnValue=0}
}
"""
        command = mock + f"\n. '{script}' -Start {start} -Target {target}"
        encoded = base64.b64encode(command.encode("utf-16-le")).decode("ascii")
        return subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-EncodedCommand",
                encoded,
            ],
            capture_output=True,
            text=True,
            timeout=12,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

    def test_native_transition_reports_verified_target(self):
        result = self.ramp_bridge(40, 44)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.splitlines(), ["P 44"])

    def test_ramp_preserves_manual_change_before_first_write(self):
        result = self.ramp_bridge(39, 44)
        self.assertEqual(result.stdout.strip(), "M 40")
