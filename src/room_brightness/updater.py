"""Bounded HTTPS GitHub release downloads, verified before any explicit installation."""

import hashlib
import json
import os
from pathlib import Path
import re
import time
import urllib.request
from urllib.parse import urlsplit

REPOSITORY = "bassam-alomari/Auto-Brightness"
MAX_SIZE = 300 * 1024 * 1024


def trusted(url):
    parsed = urlsplit(url)
    return (
        parsed.scheme == "https"
        and not parsed.username
        and not parsed.password
        and parsed.port in (None, 443)
        and parsed.hostname
        in (
            "api.github.com",
            "github.com",
            "release-assets.githubusercontent.com",
            "objects.githubusercontent.com",
        )
    )


class Redirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not trusted(newurl):
            raise ValueError("Unexpected redirect.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def open_url(url):
    if not trusted(url):
        raise ValueError("Unexpected update URL.")
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "AutoBrightness",
            "Accept": "application/vnd.github+json"
            if "api.github.com" in url
            else "application/octet-stream",
        },
    )
    return urllib.request.build_opener(Redirects()).open(request, timeout=15)


def release_metadata(document, current):
    from .extras import parse_release

    release = parse_release(document, current)
    if release is None:
        return None
    tag = release["version"]
    version = tag.removeprefix("v")
    release["notes"] = str(document.get("body") or "")[:12000]
    release["asset"] = None
    for asset in document.get("assets", [])[:100]:
        if (
            not isinstance(asset, dict)
            or asset.get("name") != f"AutoBrightness-{version}-Setup.exe"
        ):
            continue
        url = f"https://github.com/{REPOSITORY}/releases/download/{tag}/{asset['name']}"
        digest = asset.get("digest", "")
        size = asset.get("size")
        if (
            asset.get("browser_download_url") == url
            and isinstance(digest, str)
            and re.fullmatch(r"sha256:[0-9a-fA-F]{64}", digest)
            and type(size) is int
            and 0 < size <= MAX_SIZE
        ):
            release["asset"] = dict(
                url=url, name=asset["name"], size=size, sha256=digest.split(":")[1].lower()
            )
        break
    return release


def check(current):
    with open_url(f"https://api.github.com/repos/{REPOSITORY}/releases/latest") as response:
        data = response.read(262145)
    if len(data) > 262144:
        raise ValueError("Update response too large.")
    return release_metadata(json.loads(data), current)


def verify_file(path, asset):
    path = Path(path)
    if path.stat().st_size != asset["size"]:
        raise ValueError("Incomplete update file.")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        if stream.read(2) != b"MZ":
            raise ValueError("Invalid Windows executable.")
        stream.seek(0)
        for block in iter(lambda: stream.read(262144), b""):
            digest.update(block)
    if digest.hexdigest() != asset["sha256"]:
        raise ValueError("Update checksum mismatch.")


def download(asset, directory, cancel, progress):
    if (
        not asset
        or not re.fullmatch(r"AutoBrightness-\d+\.\d+\.\d+-Setup\.exe", asset.get("name", ""))
        or not trusted(asset.get("url", ""))
    ):
        raise ValueError("No verifiable installer is published.")
    if (
        type(asset.get("size")) is not int
        or not 0 < asset["size"] <= MAX_SIZE
        or not re.fullmatch(r"[0-9a-f]{64}", asset.get("sha256", ""))
    ):
        raise ValueError("Invalid update metadata.")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / asset["name"]
    temporary = destination.with_suffix(".partial")
    try:
        if destination.is_file():
            try:
                verify_file(destination, asset)
                progress(100)
                return destination
            except ValueError:
                pass
        received = 0
        deadline = time.monotonic() + 900
        if cancel.is_set():
            raise RuntimeError("Download cancelled.")
        with open_url(asset["url"]) as response, temporary.open("wb") as output:
            while True:
                if cancel.is_set() or time.monotonic() > deadline:
                    raise RuntimeError("Download cancelled or timed out.")
                block = response.read(262144)
                if not block:
                    break
                received += len(block)
                if received > asset["size"]:
                    raise ValueError("Update exceeds expected size.")
                output.write(block)
                progress(round(100 * received / asset["size"]))
        verify_file(temporary, asset)
        os.replace(temporary, destination)
        return destination
    finally:
        temporary.unlink(missing_ok=True)


class UpdateClient:
    """Network workers only touch this state; Qt polls it on the GUI thread."""

    def __init__(self, directory):
        import threading

        self.directory = Path(directory) / "updates"
        self.cancel = threading.Event()
        self.busy = False
        self.state = "idle"
        self.release = self.path = None
        self.progress = 0
        self.last_attempt = None
        self.closed = False

    def check(self, version, automatic_download=False):
        import threading

        if self.busy:
            return
        self.busy = True
        self.state = "checking"
        self.last_attempt = time.monotonic()

        def worker():
            try:
                self.release = check(version)
                self.state = "available" if self.release else "current"
                if (
                    self.release is None
                    or self.path
                    and self.path.name != (self.release.get("asset") or {}).get("name")
                ):
                    self.path = None
            except Exception:
                self.state = "check_error"
            finally:
                self.busy = False
            if (
                not self.closed
                and automatic_download
                and self.state == "available"
                and self.release.get("asset")
            ):
                self.download()

        threading.Thread(target=worker, daemon=True).start()

    def download(self):
        import threading

        if self.closed or self.busy or not self.release or not self.release.get("asset"):
            return
        self.busy = True
        self.state = "downloading"
        self.progress = 0
        self.cancel.clear()
        asset = dict(self.release["asset"])

        def worker():
            try:
                self.path = download(
                    asset, self.directory, self.cancel, lambda n: setattr(self, "progress", n)
                )
                self.state = "ready"
            except Exception:
                self.path = None
                self.state = "cancelled" if self.cancel.is_set() else "download_error"
            finally:
                self.busy = False

        threading.Thread(target=worker, daemon=True).start()

    def launch(self):
        import subprocess

        if self.busy or not self.path or not self.release or not self.release.get("asset"):
            raise ValueError("Download a verified installer first.")
        verify_file(self.path, self.release["asset"])
        return subprocess.Popen(
            [str(self.path), "--wait-pid", str(os.getpid()), "--restart"],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
