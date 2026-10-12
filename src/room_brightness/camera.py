"""Read transient camera frames in a cancellable, time-limited child process."""

import subprocess
import json
import base64
import math
import sys
import threading
import time


def camera_sample(index: int, preview=False) -> dict:
    import cv2
    from .metering import analyze_frame, combine_frames
    from .vision import scene_features, vision_score

    cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
    try:
        if not cap.isOpened():
            raise RuntimeError(
                "Camera unavailable. Close video apps and check Windows camera permissions."
            )
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
        started = time.monotonic()
        values = []
        while time.monotonic() - started < 3:
            ok, frame = cap.read()
            if not ok:
                raise RuntimeError("Could not read a camera frame.")
            if time.monotonic() - started >= 1.5:
                if frame.shape[0] > 240 or frame.shape[1] > 320:
                    frame = cv2.resize(frame, (320, 240), interpolation=cv2.INTER_AREA)
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                exposure = cap.get(cv2.CAP_PROP_EXPOSURE)
                features = scene_features(frame)
                measured = analyze_frame(gray, exposure)
                measured.update(features)
                measured["score"] = vision_score(
                    features["illumination_level"], measured["exposure"]
                )
                measured["zones"] = [
                    vision_score(v, measured["exposure"]) for v in features["illumination_zones"]
                ]
                values.append(measured)
            time.sleep(0.06)
        if not values:
            raise RuntimeError("No light measurements received.")
        reading = combine_frames(values)
        reading["scene_signature"] = values[-1]["scene_signature"]
        reading["illumination_level"] = values[-1]["illumination_level"]
        reading["visible_fraction"] = values[-1]["visible_fraction"]
        gain = cap.get(cv2.CAP_PROP_GAIN)
        reading["gain"] = gain if math.isfinite(gain) and gain >= 0 else None
        if preview:
            thumb = cv2.resize(frame, (240, 180), interpolation=cv2.INTER_AREA)
            encoded, png = cv2.imencode(".png", thumb)
            if encoded:
                reading["preview"] = base64.b64encode(png).decode("ascii")
        return reading
    finally:
        cap.release()


def sample(index: int, cancel: threading.Event, timeout: float = 15, preview=False) -> dict:
    if cancel.is_set():
        raise RuntimeError("Stopped.")
    process = subprocess.Popen(
        [sys.executable, "-m", "room_brightness", "--meter", str(index)]
        + (["--preview"] if preview else []),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    captured = []
    reader = None
    if preview:
        # Drain the PNG while the child is running; pipe buffers are small on Windows.
        reader = threading.Thread(
            target=lambda: captured.append(process.communicate()), daemon=True
        )
        reader.start()
    deadline = time.monotonic() + timeout
    try:
        while process.poll() is None:
            if cancel.is_set():
                raise RuntimeError("Stopped.")
            if time.monotonic() > deadline:
                raise RuntimeError("Camera timed out. Refresh the camera list and try again.")
            time.sleep(0.1)
        if reader is not None:
            reader.join(2)
            if not captured:
                raise RuntimeError("Camera output timed out.")
            out, err = captured[0]
        else:
            out, err = process.communicate()
        if process.returncode:
            raise RuntimeError("Could not measure camera light: " + err.strip()[-300:])
        reading = json.loads(out)
        if not isinstance(reading, dict) or not all(
            type(reading.get(key)) in (int, float) and math.isfinite(reading[key])
            for key in ("score", "level", "confidence")
        ):
            raise RuntimeError("Invalid camera measurement.")
        if not 0 <= reading["confidence"] <= 1 or not 0 <= reading["level"] <= 255:
            raise RuntimeError("Invalid camera measurement.")
        zones = reading.get("zones", [])
        if (
            not isinstance(zones, list)
            or len(zones) not in (0, 8)
            or not all(type(value) in (int, float) and math.isfinite(value) for value in zones)
        ):
            raise RuntimeError("Invalid camera measurement zones.")
        if "preview" in reading:
            png = reading["preview"]
            if not isinstance(png, str) or len(png) > 200000:
                raise RuntimeError("Invalid camera preview.")
            try:
                decoded = base64.b64decode(png, validate=True)
                if not decoded.startswith(b"\x89PNG\r\n\x1a\n"):
                    raise ValueError("Not PNG")
            except ValueError as exc:
                raise RuntimeError("Invalid camera preview.") from exc
        return reading
    finally:
        if process.poll() is None:
            process.kill()
            if reader is not None:
                reader.join(2)
            else:
                process.communicate()
