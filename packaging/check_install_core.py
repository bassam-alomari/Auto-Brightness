"""Exercise the same C# installation transaction used by the real Windows installer."""

from pathlib import Path
import subprocess

project = Path(__file__).resolve().parents[1]
output = project / "build/validation"
output.mkdir(parents=True, exist_ok=True)
compiler = Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe")
executable = output / "InstallCoreTests.exe"
subprocess.run(
    [
        str(compiler),
        "/nologo",
        f"/out:{executable}",
        str(project / "packaging/InstallCore.cs"),
        str(project / "packaging/InstallCoreTests.cs"),
    ],
    check=True,
)
result = subprocess.run(
    [str(executable), str(output)],
    capture_output=True,
    text=True,
    timeout=60,
    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
)
(output / "install-checks.txt").write_text(result.stdout + result.stderr, encoding="utf-8")
if result.returncode or "INSTALL CORE CHECKS PASSED: 16" not in result.stdout:
    raise RuntimeError("Installation transaction checks failed: " + result.stdout + result.stderr)
print("16 Windows installation transaction checks passed (isolated file-system fixtures).")
