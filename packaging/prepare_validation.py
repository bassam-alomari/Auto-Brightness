"""Prepare an offline WSB validation package; opening the VM is an explicit --launch action."""

import argparse
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET

project = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--previous-installer", type=Path)
parser.add_argument("--launch", action="store_true")
args = parser.parse_args()
subprocess.run(
    [__import__("sys").executable, str(project / "packaging/check_install_core.py")], check=True
)
results = project / "build/sandbox-results"
results.mkdir(parents=True, exist_ok=True)
if args.previous_installer:
    previous = args.previous_installer.resolve(strict=True)
    if previous.suffix.lower() != ".exe":
        raise ValueError("Expected a Windows installer.")
    shutil.copy2(previous, project / "build/validation/PreviousSetup.exe")
config = ET.Element("Configuration")
for key, value in [
    ("VGpu", "Disable"),
    ("Networking", "Disable"),
    ("ClipboardRedirection", "Disable"),
    ("VideoInput", "Disable"),
    ("AudioInput", "Disable"),
]:
    ET.SubElement(config, key).text = value
folders = ET.SubElement(config, "MappedFolders")
for host, guest, readonly in [
    (project, r"C:\AutoBrightnessInput", "true"),
    (results, r"C:\AutoBrightnessResults", "false"),
]:
    folder = ET.SubElement(folders, "MappedFolder")
    for key, value in [("HostFolder", str(host)), ("SandboxFolder", guest), ("ReadOnly", readonly)]:
        ET.SubElement(folder, key).text = value
command = ET.SubElement(config, "LogonCommand")
ET.SubElement(
    command, "Command"
).text = r"powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\AutoBrightnessInput\packaging\GuestValidation.ps1"
path = project / "build/validation/AutoBrightness-validation.wsb"
ET.ElementTree(config).write(path, encoding="utf-8", xml_declaration=True)
print("Prepared:", path)
print(
    "Source mapping is read-only; only sandbox-results is writable. Network/camera/microphone are disabled."
)
if args.launch:
    sandbox = shutil.which("WindowsSandbox.exe")
    if not sandbox:
        raise RuntimeError(
            "Windows Sandbox is not installed/enabled. Configuration was prepared; no VM was launched."
        )
    subprocess.Popen([sandbox, str(path)])
