"""Build a standalone portable app and per-user Windows installer (Python 3.12 x64)."""

from pathlib import Path
import shutil
import subprocess
import sys
import importlib.metadata
import zipfile

project = Path(__file__).resolve().parents[1]
out = project / "dist"
subprocess.run(
    [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--console",
        "--name",
        "AutoBrightness",
        "--distpath",
        str(out),
        "--workpath",
        str(project / "build/frozen"),
        "--specpath",
        str(project / "build"),
        "--paths",
        str(project / "src"),
        "--collect-data",
        "room_brightness",
        "--hidden-import",
        "room_brightness.qt_ui",
        "--hidden-import",
        "room_brightness.qt_engine",
        "--icon",
        str(project / "src/room_brightness/app.ico"),
        "--exclude-module",
        "matplotlib",
        "--exclude-module",
        "scipy",
        "--exclude-module",
        "pandas",
        "--exclude-module",
        "torch",
        "--exclude-module",
        "PyQt5",
        "--exclude-module",
        "PyQt6",
        str(project / "packaging/launcher.py"),
    ],
    check=True,
)
app = out / "AutoBrightness"
# Qt uses the unversioned ICU APIs supplied by Windows. A versioned ICU from
# an unrelated build-tool PATH must not shadow the Windows system library.
for name in ("icuuc.dll", "icudt78.dll"):
    conflicting = app / "_internal" / name
    if conflicting.exists():
        conflicting.unlink()
check = subprocess.run(
    [str(app / "AutoBrightness.exe"), "--self-test"], capture_output=True, text=True, timeout=30
)
if check.returncode or "Desktop smoke check passed" not in check.stdout:
    raise RuntimeError("Standalone app smoke check failed: " + check.stdout + check.stderr)

for name in ("RegisterInstall.ps1", "Uninstall.ps1"):
    shutil.copy2(project / "packaging" / name, app / name)
for name in ("LICENSE", "THIRD_PARTY_NOTICES.md", "README.md", "README.ar.md"):
    shutil.copy2(project / name, app / name)
# Preserve upstream licensing for the runtime and bundled libraries.
licenses = app / "licenses"
for package in (
    "PySide6-Essentials",
    "shiboken6",
    "numpy",
    "opencv-python-headless",
    "Pillow",
    "pystray",
    "pyinstaller",
):
    try:
        distribution = importlib.metadata.distribution(package)
    except importlib.metadata.PackageNotFoundError:
        continue
    for relative in distribution.files or []:
        if any(token in str(relative).lower() for token in ("license", "copying", "notice")):
            source = Path(distribution.locate_file(relative))
            if source.is_file():
                destination = licenses / package / source.name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
for source in (Path(sys.base_prefix) / "LICENSE.txt", Path(sys.base_prefix) / "LICENSE"):
    if source.is_file():
        licenses.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, licenses / "Python-LICENSE.txt")
archive = out / "AutoBrightness-0.6.0-portable.zip"
with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
    for file in app.rglob("*"):
        if file.is_file():
            bundle.write(file, file.relative_to(app))
csc = Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe")
subprocess.run(
    [
        str(csc),
        "/nologo",
        "/target:winexe",
        f"/out:{out / 'AutoBrightness-0.6.0-Setup.exe'}",
        f"/win32icon:{project / 'src/room_brightness/app.ico'}",
        f"/resource:{archive},payload.zip",
        "/reference:System.Windows.Forms.dll",
        "/reference:System.IO.Compression.dll",
        "/reference:System.IO.Compression.FileSystem.dll",
        str(project / "packaging/Installer.cs"),
    ],
    check=True,
)
print("Portable app and Windows installer built.")
