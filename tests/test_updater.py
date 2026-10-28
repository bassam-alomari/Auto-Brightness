import copy
import hashlib
import io
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from room_brightness.updater import (
    release_metadata,
    download,
    verify_file,
    UpdateClient,
    trusted,
    Redirects,
)


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.data = b"MZ" + b"installer fixture" * 100
        self.asset = dict(
            name="AutoBrightness-0.8.0-Setup.exe",
            url="https://github.com/bassam-alomari/Auto-Brightness/releases/download/v0.8.0/AutoBrightness-0.8.0-Setup.exe",
            size=len(self.data),
            sha256=hashlib.sha256(self.data).hexdigest(),
        )
        self.document = dict(
            tag_name="v0.8.0",
            html_url="https://github.com/bassam-alomari/Auto-Brightness/releases/tag/v0.8.0",
            body="Notes",
            assets=[
                dict(
                    name=self.asset["name"],
                    browser_download_url=self.asset["url"],
                    size=len(self.data),
                    digest="sha256:" + self.asset["sha256"],
                )
            ],
        )

    def test_only_new_stable_own_repo_asset_with_digest_is_downloadable(self):
        release = release_metadata(self.document, "0.7.0")
        self.assertEqual(release["asset"], self.asset)
        self.assertIsNone(release_metadata(self.document, "0.8.0"))
        for changed in (
            dict(digest=None),
            dict(browser_download_url="https://evil.example/app.exe"),
            dict(size=0),
        ):
            bad = copy.deepcopy(self.document)
            bad["assets"][0].update(changed)
            self.assertIsNone(release_metadata(bad, "0.7.0")["asset"])
        self.assertIsNone(release_metadata(dict(self.document, prerelease=True), "0.7.0"))

    def test_download_atomic_verified_and_cached_without_network(self):
        with tempfile.TemporaryDirectory() as folder:
            progress = []
            with patch("room_brightness.updater.open_url", return_value=io.BytesIO(self.data)):
                path = download(self.asset, folder, threading.Event(), progress.append)
            verify_file(path, self.asset)
            self.assertEqual(progress[-1], 100)
            with patch("room_brightness.updater.open_url") as network:
                self.assertEqual(
                    download(self.asset, folder, threading.Event(), progress.append), path
                )
                network.assert_not_called()

    def test_corrupt_or_oversize_download_does_not_replace_existing_file(self):
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / self.asset["name"]
            destination.write_bytes(b"previous")
            for data in (b"MZbroken", self.data + b"overflow"):
                with patch("room_brightness.updater.open_url", return_value=io.BytesIO(data)):
                    with self.assertRaises(ValueError):
                        download(self.asset, folder, threading.Event(), lambda n: None)
                self.assertEqual(destination.read_bytes(), b"previous")
                self.assertFalse(destination.with_suffix(".partial").exists())

    def test_cancel_and_bad_redirect_do_not_launch_installer(self):
        with tempfile.TemporaryDirectory() as folder:
            cancel = threading.Event()
            cancel.set()
            with (
                self.assertRaises(RuntimeError),
                patch("room_brightness.updater.open_url") as network,
            ):
                download(self.asset, folder, cancel, lambda n: None)
            network.assert_not_called()
            client = UpdateClient(folder)
            with patch("subprocess.Popen") as launch, self.assertRaises(ValueError):
                client.launch()
            launch.assert_not_called()
        for url in (
            "http://github.com/a",
            "https://github.com.evil/a",
            "https://user@github.com/a",
            "https://github.com:444/a",
        ):
            self.assertFalse(trusted(url))
        with self.assertRaises(ValueError):
            Redirects().redirect_request(None, None, 302, "", {}, "https://evil.example/a")

    def test_install_rechecks_digest_and_uses_explicit_wait_and_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            client = UpdateClient(folder)
            client.release = release_metadata(self.document, "0.7.0")
            client.path = Path(folder) / self.asset["name"]
            client.path.write_bytes(self.data)
            with patch("subprocess.Popen") as launch:
                client.launch()
                self.assertIn("--wait-pid", launch.call_args.args[0])
                self.assertIn("--restart", launch.call_args.args[0])
                client.path.write_bytes(b"tampered")
                with self.assertRaises(ValueError):
                    client.launch()
                self.assertEqual(launch.call_count, 1)
