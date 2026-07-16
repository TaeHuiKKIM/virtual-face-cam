"""macOS browser UI for sending images or looping video to OBS Virtual Camera."""

from __future__ import annotations

import argparse
import json
import math
import mimetypes
import re
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from dataclasses import dataclass, field
from email.parser import BytesParser
from email.policy import default as email_policy
from http import HTTPStatus
from http.server import HTTPServer
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import numpy as np
import pyvirtualcam
import cv2
from PIL import Image, ImageOps, UnidentifiedImageError


APP_NAME = "Virtual Face Cam"
APP_SUPPORT = Path.home() / "Library" / "Application Support" / "VirtualFaceCamMac"
UPLOAD_ROOT = APP_SUPPORT / "uploads"
SETTINGS_PATH = APP_SUPPORT / "settings.json"
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm"}
MEDIA_EXTS = IMAGE_EXTS | VIDEO_EXTS
MAX_UPLOAD_BYTES = 300 * 1024 * 1024


def fit_frame(img: Image.Image, width: int, height: int) -> np.ndarray:
    """Return a C-contiguous RGB frame letterboxed to width x height."""
    img = ImageOps.exif_transpose(img)
    if img.mode == "RGBA":
        background = Image.new("RGB", img.size, (0, 0, 0))
        background.paste(img, mask=img.getchannel("A"))
        img = background
    else:
        img = img.convert("RGB")

    scale = min(width / img.width, height / img.height)
    new_w = max(1, int(img.width * scale))
    new_h = max(1, int(img.height * scale))
    resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

    canvas = Image.new("RGB", (width, height), (0, 0, 0))
    canvas.paste(resized, ((width - new_w) // 2, (height - new_h) // 2))
    return np.asarray(canvas, dtype=np.uint8).copy()


def load_frames(paths: list[Path], width: int, height: int) -> list[np.ndarray]:
    frames: list[np.ndarray] = []
    for path in paths:
        try:
            with Image.open(path) as img:
                frames.append(fit_frame(img, width, height))
        except (OSError, UnidentifiedImageError):
            continue
    if not frames:
        raise RuntimeError("No readable images were uploaded.")
    return frames


def fit_video_frame(frame: np.ndarray, width: int, height: int) -> np.ndarray:
    if frame.ndim == 2:
        rgb = cv2.cvtColor(frame, cv2.COLOR_GRAY2RGB)
    elif frame.shape[2] == 4:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGRA2RGB)
    else:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    source_h, source_w = rgb.shape[:2]
    scale = min(width / source_w, height / source_h)
    new_w = max(1, int(source_w * scale))
    new_h = max(1, int(source_h * scale))
    interpolation = cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR
    resized = cv2.resize(rgb, (new_w, new_h), interpolation=interpolation)
    canvas = np.zeros((height, width, 3), dtype=np.uint8)
    x0 = (width - new_w) // 2
    y0 = (height - new_h) // 2
    canvas[y0:y0 + new_h, x0:x0 + new_w] = resized
    return np.ascontiguousarray(canvas)


def safe_filename(name: str) -> str:
    base = Path(name).name.strip() or "media"
    stem = re.sub(r"[^A-Za-z0-9._ -]+", "_", base)
    return stem[:120]


class ImageFrameSource:
    def __init__(self, paths: list[Path], width: int, height: int, fps: int, interval: float):
        self.frames = load_frames(paths, width, height)
        self.frames_per_image = max(1, int(interval * fps))
        self.index = 0
        self.frame_count = 0

    def next_frame(self) -> np.ndarray:
        frame = self.frames[self.index]
        if len(self.frames) > 1:
            self.frame_count += 1
            if self.frame_count >= self.frames_per_image:
                self.frame_count = 0
                self.index = (self.index + 1) % len(self.frames)
        return frame

    def close(self) -> None:
        return


class VideoFrameSource:
    def __init__(self, path: Path, width: int, height: int, output_fps: int):
        self.path = path
        self.width = width
        self.height = height
        self.output_fps = max(1, output_fps)
        self.capture = cv2.VideoCapture(str(path))
        if not self.capture.isOpened():
            self.capture.release()
            raise RuntimeError(f"Could not open video: {path.name}")
        source_fps = float(self.capture.get(cv2.CAP_PROP_FPS))
        self.source_fps = (
            source_fps
            if math.isfinite(source_fps) and source_fps > 0
            else float(self.output_fps)
        )
        self.accumulator = 0.0
        self.current_frame = self._read_looped_frame()

    def _reopen(self) -> None:
        self.capture.release()
        self.capture = cv2.VideoCapture(str(self.path))

    def _read_looped_frame(self) -> np.ndarray:
        ok, frame = self.capture.read()
        if not ok:
            self.capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = self.capture.read()
        if not ok:
            self._reopen()
            ok, frame = self.capture.read()
        if not ok or frame is None:
            raise RuntimeError(f"Could not read video frames: {self.path.name}")
        return fit_video_frame(frame, self.width, self.height)

    def next_frame(self) -> np.ndarray:
        frame = self.current_frame
        self.accumulator += self.source_fps
        while self.accumulator >= self.output_fps:
            self.current_frame = self._read_looped_frame()
            self.accumulator -= self.output_fps
        return frame

    def close(self) -> None:
        self.capture.release()


def save_recent_media(paths: list[Path], media_type: str) -> None:
    APP_SUPPORT.mkdir(parents=True, exist_ok=True)
    temp = SETTINGS_PATH.with_suffix(".tmp")
    temp.write_text(
        json.dumps(
            {"mediaType": media_type, "mediaPaths": [str(path.resolve()) for path in paths]},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    temp.replace(SETTINGS_PATH)


class CameraWorker(threading.Thread):
    def __init__(
        self,
        paths: list[Path],
        media_type: str,
        width: int,
        height: int,
        fps: int,
        interval: float,
    ) -> None:
        super().__init__(daemon=True)
        self.paths = paths
        self.media_type = media_type
        self.width = width
        self.height = height
        self.fps = fps
        self.interval = interval
        self.stop_event = threading.Event()
        self.ready = threading.Event()
        self.error: str | None = None
        self.device: str | None = None

    def run(self) -> None:
        source: ImageFrameSource | VideoFrameSource | None = None
        try:
            if self.media_type == "video":
                source = VideoFrameSource(self.paths[0], self.width, self.height, self.fps)
            else:
                source = ImageFrameSource(
                    self.paths, self.width, self.height, self.fps, self.interval
                )
            with pyvirtualcam.Camera(
                width=self.width,
                height=self.height,
                fps=self.fps,
            ) as cam:
                self.device = cam.device
                self.ready.set()
                while not self.stop_event.is_set():
                    cam.send(source.next_frame())
                    cam.sleep_until_next_frame()
        except Exception as exc:  # pyvirtualcam raises backend-specific errors.
            self.error = str(exc)
            self.ready.set()
        finally:
            if source:
                source.close()

    def stop(self) -> None:
        self.stop_event.set()


@dataclass
class AppState:
    lock: threading.Lock = field(default_factory=threading.Lock)
    media_paths: list[Path] = field(default_factory=list)
    media_names: list[str] = field(default_factory=list)
    media_type: str = "images"
    worker: CameraWorker | None = None
    last_error: str | None = None

    def snapshot(self) -> dict:
        with self.lock:
            running = self.worker is not None and self.worker.is_alive() and not self.worker.error
            device = self.worker.device if self.worker else None
            return {
                "running": running,
                "device": device,
                "mediaCount": len(self.media_paths),
                "mediaNames": self.media_names[:8],
                "mediaType": self.media_type,
                "imageCount": len(self.media_paths) if self.media_type == "images" else 0,
                "imageNames": self.media_names[:8] if self.media_type == "images" else [],
                "error": self.last_error,
            }

    def replace_media(self, paths: list[Path], media_type: str, persist: bool = False) -> None:
        with self.lock:
            self.media_paths = paths
            self.media_names = [p.name for p in paths]
            self.media_type = media_type
            self.last_error = None
        if persist:
            save_recent_media(paths, media_type)

    def preview_media(self) -> tuple[Path | None, str]:
        with self.lock:
            if not self.media_paths:
                return None, self.media_type
            return self.media_paths[0], self.media_type

    def start_camera(self, width: int, height: int, fps: int, interval: float) -> dict:
        with self.lock:
            if self.worker and self.worker.is_alive():
                return {"ok": True, "message": "Camera is already running."}
            paths = list(self.media_paths)
            media_type = self.media_type
        if not paths:
            raise RuntimeError("Upload an image or video first.")

        worker = CameraWorker(paths, media_type, width, height, fps, interval)
        with self.lock:
            self.worker = worker
            self.last_error = None
        worker.start()
        worker.ready.wait(timeout=8)

        if worker.error:
            with self.lock:
                self.last_error = worker.error
                self.worker = None
            raise RuntimeError(worker.error)
        return {"ok": True, "device": worker.device}

    def stop_camera(self) -> None:
        with self.lock:
            worker = self.worker
            self.worker = None
        if worker:
            worker.stop()
            worker.join(timeout=2)


STATE = AppState()


class ShutdownController:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.timer: threading.Timer | None = None
        self.server: HTTPServer | None = None
        self.last_seen = 0.0
        self.monitor_started = False

    def cancel(self) -> None:
        with self.lock:
            self._cancel_locked()

    def mark_active(self, server: HTTPServer) -> None:
        with self.lock:
            self.server = server
            self.last_seen = time.monotonic()
            self._cancel_locked()
            if not self.monitor_started:
                self.monitor_started = True
                threading.Thread(target=self._monitor, daemon=True).start()

    def schedule(self, server: HTTPServer, delay: float = 6.0) -> None:
        if STATE.snapshot()["running"]:
            return
        with self.lock:
            self.server = server
            self._cancel_locked()
            self.timer = threading.Timer(delay, self._shutdown, args=(server,))
            self.timer.daemon = True
            self.timer.start()

    def now(self, server: HTTPServer) -> None:
        with self.lock:
            self.server = None
            self._cancel_locked()
        threading.Thread(target=self._shutdown, args=(server,), daemon=True).start()

    def _cancel_locked(self) -> None:
        if self.timer:
            self.timer.cancel()
            self.timer = None

    def _monitor(self) -> None:
        while True:
            time.sleep(3)
            with self.lock:
                server = self.server
                if server is None:
                    self.monitor_started = False
                    return
                if STATE.snapshot()["running"]:
                    self.last_seen = time.monotonic()
                    continue
                if time.monotonic() - self.last_seen <= 16:
                    continue
                self.server = None
                self._cancel_locked()
            self._shutdown(server)
            return

    def _shutdown(self, server: HTTPServer) -> None:
        STATE.stop_camera()
        server.shutdown()


SHUTDOWN = ShutdownController()


FAVICON_SVG = b"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
<defs><linearGradient id="g" x1="8" y1="8" x2="56" y2="56" gradientUnits="userSpaceOnUse"><stop stop-color="#29d17d"/><stop offset="1" stop-color="#17b6d4"/></linearGradient></defs>
<rect width="64" height="64" rx="18" fill="url(#g)"/>
<rect x="15" y="22" width="31" height="20" rx="5" fill="none" stroke="#fff" stroke-width="5"/>
<path d="M46 27l9-5v20l-9-5z" fill="#fff"/>
</svg>"""


def default_image_candidates() -> list[Path]:
    script_dir = Path(__file__).resolve().parent
    return [
        script_dir / "assets" / "default_face.jpg",
        script_dir / "default_face.jpg",
        script_dir.parent / "assets" / "default_face.jpg",
        Path.cwd() / "assets" / "default_face.jpg",
    ]


def load_default_image() -> None:
    for candidate in default_image_candidates():
        if not candidate.is_file():
            continue
        session_dir = UPLOAD_ROOT / "default"
        session_dir.mkdir(parents=True, exist_ok=True)
        out = session_dir / candidate.name
        try:
            if candidate.resolve() != out.resolve():
                shutil.copyfile(candidate, out)
            with Image.open(out) as img:
                img.verify()
        except (OSError, UnidentifiedImageError):
            continue
        STATE.replace_media([out], "images")
        return


def is_readable_video(path: Path) -> bool:
    capture = cv2.VideoCapture(str(path))
    try:
        if not capture.isOpened():
            return False
        ok, frame = capture.read()
        return bool(ok and frame is not None)
    finally:
        capture.release()


def video_poster(path: Path) -> bytes:
    capture = cv2.VideoCapture(str(path))
    try:
        ok, frame = capture.read()
        if not ok or frame is None:
            raise RuntimeError(f"Could not read video preview: {path.name}")
        encoded, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 88])
        if not encoded:
            raise RuntimeError(f"Could not create video preview: {path.name}")
        return buffer.tobytes()
    finally:
        capture.release()


def load_saved_media() -> bool:
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        media_type = data.get("mediaType")
        paths = [Path(value) for value in data.get("mediaPaths", [])]
    except (OSError, ValueError, TypeError):
        return False

    if media_type == "video":
        if (
            len(paths) == 1
            and paths[0].is_file()
            and paths[0].suffix.lower() in VIDEO_EXTS
            and is_readable_video(paths[0])
        ):
            STATE.replace_media(paths, "video")
            return True
        return False

    if media_type != "images" or not paths:
        return False
    readable: list[Path] = []
    for path in paths:
        if not path.is_file() or path.suffix.lower() not in IMAGE_EXTS:
            continue
        try:
            with Image.open(path) as image:
                image.verify()
        except (OSError, UnidentifiedImageError):
            continue
        readable.append(path)
    if not readable:
        return False
    STATE.replace_media(readable, "images")
    return True


def cleanup_old_uploads(keep: Path) -> None:
    if not UPLOAD_ROOT.is_dir():
        return
    for child in UPLOAD_ROOT.iterdir():
        if child == keep or child.name == "default":
            continue
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)


HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Virtual Face Cam</title>
  <link rel="icon" href="/favicon.svg" type="image/svg+xml">
  <style>
    :root {
      color-scheme: dark;
      --bg: #121417;
      --surface: #1b1f24;
      --panel: #20262b;
      --panel-2: #272e35;
      --ink: #f2f5f3;
      --muted: #99a39f;
      --line: #343d43;
      --accent: #29d17d;
      --accent-2: #1c8cff;
      --warning: #f2a33a;
      --danger: #ff5c7a;
      --shadow: 0 24px 80px rgba(0, 0, 0, 0.34);
    }
    * { box-sizing: border-box; }
    html,
    body {
      height: 100%;
    }
    body {
      margin: 0;
      min-height: 100vh;
      background:
        radial-gradient(circle at 12% 8%, rgba(41, 209, 125, 0.16), transparent 28%),
        radial-gradient(circle at 86% 12%, rgba(28, 140, 255, 0.14), transparent 30%),
        var(--bg);
      color: var(--ink);
      font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", sans-serif;
    }
    button,
    input {
      font: inherit;
    }
    .shell {
      min-height: 100vh;
      display: grid;
      grid-template-columns: minmax(320px, 390px) minmax(0, 1fr);
    }
    .sidebar {
      border-right: 1px solid rgba(255, 255, 255, 0.08);
      background: rgba(24, 29, 33, 0.84);
      backdrop-filter: blur(24px);
      padding: 24px;
      display: flex;
      flex-direction: column;
      gap: 18px;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 13px;
      min-width: 0;
    }
    .logo {
      width: 48px;
      height: 48px;
      border-radius: 14px;
      background: linear-gradient(135deg, var(--accent), #17b6d4);
      display: grid;
      place-items: center;
      box-shadow: 0 12px 30px rgba(41, 209, 125, 0.24);
      flex: 0 0 auto;
    }
    .logo::before {
      content: "";
      width: 23px;
      height: 16px;
      border: 3px solid #fff;
      border-radius: 5px;
      box-shadow: 13px 0 0 -5px #fff;
    }
    h1 {
      margin: 0;
      font-size: 21px;
      line-height: 1.16;
      letter-spacing: 0;
    }
    p {
      margin: 4px 0 0;
      color: var(--muted);
      line-height: 1.45;
      font-size: 13px;
    }
    .status-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
    }
    .mini-card,
    .control-card,
    .loaded-card,
    .note-card {
      border: 1px solid rgba(255, 255, 255, 0.08);
      background: rgba(255, 255, 255, 0.045);
      border-radius: 14px;
    }
    .mini-card {
      padding: 13px;
      min-width: 0;
    }
    .eyebrow {
      display: block;
      color: var(--muted);
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.02em;
      margin-bottom: 4px;
    }
    .mini-card strong,
    .loaded-card strong,
    .note-card strong {
      display: block;
      font-size: 14px;
      line-height: 1.25;
    }
    .control-card {
      padding: 14px;
    }
    .section-title {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 10px;
    }
    .section-title h2 {
      margin: 0;
      font-size: 13px;
      letter-spacing: 0;
    }
    .file-input {
      position: absolute;
      width: 1px;
      height: 1px;
      opacity: 0;
      pointer-events: none;
    }
    .drop-row {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
    }
    .drop-zone {
      min-height: 92px;
      border: 1px dashed rgba(255, 255, 255, 0.18);
      border-radius: 12px;
      padding: 13px;
      cursor: pointer;
      background: rgba(255, 255, 255, 0.04);
      transition: border-color 0.15s ease, background 0.15s ease, transform 0.15s ease;
    }
    .drop-zone:hover {
      background: rgba(255, 255, 255, 0.07);
      border-color: rgba(41, 209, 125, 0.72);
      transform: translateY(-1px);
    }
    .drop-zone strong {
      display: block;
      font-size: 14px;
      margin-top: 7px;
    }
    .drop-zone small {
      display: block;
      margin-top: 4px;
      color: var(--muted);
      line-height: 1.3;
    }
    .icon {
      width: 30px;
      height: 30px;
      border-radius: 9px;
      display: grid;
      place-items: center;
      background: rgba(41, 209, 125, 0.14);
      color: var(--accent);
      font-weight: 900;
    }
    .settings-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
    }
    label.input-label {
      display: block;
      color: var(--muted);
      font-size: 11px;
      font-weight: 700;
      margin-bottom: 6px;
    }
    input[type="number"] {
      width: 100%;
      border: 1px solid rgba(255, 255, 255, 0.10);
      border-radius: 10px;
      background: rgba(9, 12, 14, 0.64);
      color: var(--ink);
      padding: 10px 11px;
      outline: none;
    }
    input[type="number"]:focus {
      border-color: rgba(28, 140, 255, 0.86);
      box-shadow: 0 0 0 3px rgba(28, 140, 255, 0.16);
    }
    .actions {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
    }
    button {
      border: 0;
      border-radius: 11px;
      min-height: 43px;
      padding: 0 14px;
      background: rgba(255, 255, 255, 0.09);
      color: var(--ink);
      font-weight: 750;
      cursor: pointer;
      transition: transform 0.15s ease, filter 0.15s ease, opacity 0.15s ease;
    }
    button:hover { transform: translateY(-1px); filter: brightness(1.08); }
    button:disabled { cursor: not-allowed; opacity: 0.55; transform: none; }
    button.primary {
      background: linear-gradient(135deg, var(--accent), #17b6d4);
      color: #06120d;
    }
    button.danger { background: rgba(255, 92, 122, 0.18); color: #ffdce4; }
    button.danger:disabled {
      background: rgba(255, 255, 255, 0.08);
      color: var(--muted);
    }
    button.secondary {
      background: rgba(255, 255, 255, 0.07);
      color: var(--muted);
    }
    #quit {
      grid-column: 1 / -1;
    }
    body[data-state="running"] #start {
      background: rgba(255, 255, 255, 0.08);
      color: var(--muted);
    }
    body[data-state="running"] #stop {
      background: linear-gradient(135deg, #ff5c7a, #ff8a4d);
      color: #fff;
      box-shadow: 0 12px 28px rgba(255, 92, 122, 0.22);
    }
    .loaded-card,
    .note-card {
      padding: 14px;
    }
    .list {
      margin-top: 8px;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.45;
      word-break: break-word;
    }
    .stage {
      min-width: 0;
      padding: 34px;
      display: grid;
      grid-template-rows: auto minmax(0, 1fr) auto auto;
      gap: 22px;
    }
    .stage-header {
      display: flex;
      align-items: end;
      justify-content: space-between;
      gap: 18px;
    }
    .stage-header h2 {
      margin: 0;
      font-size: clamp(34px, 4vw, 54px);
      line-height: 1;
      letter-spacing: 0;
    }
    .stage-header p {
      font-size: 15px;
      margin-top: 10px;
    }
    .pill-row {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }
    .pill {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      min-height: 38px;
      padding: 0 12px;
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.06);
      color: var(--muted);
      font-size: 13px;
      font-weight: 700;
      white-space: nowrap;
    }
    .dot {
      width: 8px;
      height: 8px;
      border-radius: 999px;
      background: var(--muted);
    }
    .dot.ready { background: var(--accent); box-shadow: 0 0 18px rgba(41, 209, 125, 0.7); }
    .dot.error { background: var(--danger); }
    .dot.busy { background: var(--warning); box-shadow: 0 0 18px rgba(242, 163, 58, 0.6); }
    body[data-state="running"] #statePill {
      border-color: rgba(41, 209, 125, 0.42);
      background: rgba(41, 209, 125, 0.12);
      color: #d9ffe9;
    }
    body[data-state="busy"] #statePill {
      border-color: rgba(242, 163, 58, 0.42);
      background: rgba(242, 163, 58, 0.12);
      color: #ffe9bf;
    }
    body[data-state="error"] #statePill {
      border-color: rgba(255, 92, 122, 0.42);
      background: rgba(255, 92, 122, 0.12);
      color: #ffdce4;
    }
    .preview-shell {
      min-height: 390px;
      display: grid;
      place-items: center;
    }
    .preview {
      width: min(980px, 100%);
      aspect-ratio: 16 / 9;
      border-radius: 28px;
      background: #030405;
      border: 1px solid rgba(255, 255, 255, 0.10);
      box-shadow: var(--shadow);
      overflow: hidden;
      position: relative;
      display: grid;
      place-items: center;
      transition: border-color 0.18s ease, box-shadow 0.18s ease;
    }
    .preview::before,
    .preview::after {
      position: absolute;
      top: 18px;
      z-index: 2;
      color: rgba(255, 255, 255, 0.76);
      font-size: 12px;
      font-weight: 800;
    }
    .preview::before { content: "OBS Virtual Camera"; left: 22px; }
    .preview::after { content: "1280 x 720"; right: 22px; }
    body[data-state="running"] .preview {
      border-color: rgba(41, 209, 125, 0.62);
      box-shadow: var(--shadow), 0 0 0 1px rgba(41, 209, 125, 0.24), 0 0 46px rgba(41, 209, 125, 0.12);
    }
    body[data-state="running"] .preview::before {
      content: "LIVE - OBS Virtual Camera";
      color: #dcffeb;
    }
    body[data-state="running"] .preview::after {
      content: "SENDING";
      right: 18px;
      top: 16px;
      min-height: 24px;
      display: inline-flex;
      align-items: center;
      padding: 0 10px;
      border-radius: 999px;
      background: var(--accent);
      color: #06120d;
      box-shadow: 0 0 22px rgba(41, 209, 125, 0.34);
    }
    .preview img {
      width: clamp(140px, 34vw, 520px);
      height: auto;
      max-width: calc(100% - 36px);
      object-fit: contain;
      background: #000;
    }
    .preview video {
      width: 100%;
      height: 100%;
      object-fit: contain;
      background: #000;
    }
    .empty {
      text-align: center;
      color: rgba(255, 255, 255, 0.72);
      display: grid;
      gap: 12px;
      place-items: center;
      padding: 22px;
    }
    .empty-mark {
      width: 90px;
      height: 90px;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.09);
      display: grid;
      place-items: center;
      color: rgba(255, 255, 255, 0.68);
      font-size: 42px;
      font-weight: 800;
    }
    .empty strong {
      font-size: 20px;
    }
    .metrics {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 14px;
    }
    .metric {
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: 16px;
      background: rgba(255, 255, 255, 0.055);
      padding: 15px;
      min-width: 0;
    }
    .metric span {
      display: block;
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      margin-bottom: 5px;
    }
    .metric strong {
      display: block;
      font-size: 18px;
      overflow-wrap: anywhere;
    }
    .status {
      min-height: 48px;
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: 16px;
      background: rgba(255, 255, 255, 0.055);
      color: var(--muted);
      padding: 14px 16px;
      font-size: 14px;
      line-height: 1.35;
      display: flex;
      align-items: center;
      gap: 10px;
      transition: border-color 0.18s ease, background 0.18s ease, color 0.18s ease;
    }
    body[data-state="running"] .status {
      border-color: rgba(41, 209, 125, 0.42);
      background: rgba(41, 209, 125, 0.10);
      color: #d9ffe9;
    }
    body[data-state="error"] .status {
      border-color: rgba(255, 92, 122, 0.42);
      background: rgba(255, 92, 122, 0.10);
      color: #ffdce4;
    }
    .live-dock {
      position: sticky;
      bottom: 18px;
      z-index: 20;
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(180px, 220px) 112px;
      gap: 12px;
      align-items: center;
      padding: 12px;
      border: 1px solid rgba(255, 255, 255, 0.10);
      border-radius: 18px;
      background: rgba(24, 29, 33, 0.92);
      backdrop-filter: blur(24px);
      box-shadow: 0 22px 60px rgba(0, 0, 0, 0.32);
    }
    .live-dock strong {
      display: block;
      font-size: 15px;
      line-height: 1.25;
      overflow-wrap: anywhere;
    }
    .live-dock button {
      min-height: 54px;
      font-size: 16px;
      border-radius: 13px;
    }
    .big-action.danger {
      background: linear-gradient(135deg, #ff5c7a, #ff8a4d);
      color: #fff;
      box-shadow: 0 12px 28px rgba(255, 92, 122, 0.22);
    }
    @media (max-width: 880px) {
      .shell { grid-template-columns: 1fr; }
      .sidebar { border-right: 0; border-bottom: 1px solid rgba(255, 255, 255, 0.08); }
      .stage { padding: 24px; }
      .stage-header { align-items: flex-start; flex-direction: column; }
      .pill-row { justify-content: flex-start; }
      .metrics { grid-template-columns: 1fr; }
      .live-dock { grid-template-columns: 1fr; }
    }
    @media (min-width: 881px) and (max-height: 920px) {
      body {
        overflow: hidden;
      }
      .shell {
        height: 100vh;
        min-height: 0;
        grid-template-columns: minmax(300px, 365px) minmax(0, 1fr);
        overflow: hidden;
      }
      .sidebar {
        min-height: 0;
        overflow: hidden;
        padding: 16px;
        gap: 10px;
      }
      .logo {
        width: 40px;
        height: 40px;
        border-radius: 12px;
      }
      .logo::before {
        width: 20px;
        height: 13px;
        border-width: 3px;
      }
      h1 { font-size: 19px; }
      p { font-size: 12px; line-height: 1.35; }
      .mini-card,
      .loaded-card,
      .note-card,
      .control-card {
        border-radius: 12px;
      }
      .mini-card,
      .control-card,
      .loaded-card {
        padding: 10px;
      }
      .note-card {
        display: none;
      }
      .eyebrow {
        font-size: 10px;
        margin-bottom: 3px;
      }
      .mini-card strong,
      .loaded-card strong {
        font-size: 13px;
      }
      .section-title {
        margin-bottom: 8px;
      }
      .drop-row,
      .settings-grid,
      .actions {
        gap: 8px;
      }
      .drop-zone {
        min-height: 70px;
        padding: 10px;
      }
      .drop-zone strong {
        font-size: 13px;
        margin-top: 5px;
      }
      .drop-zone small {
        font-size: 12px;
        line-height: 1.25;
      }
      .icon {
        width: 26px;
        height: 26px;
        border-radius: 8px;
      }
      label.input-label {
        font-size: 10px;
        margin-bottom: 4px;
      }
      input[type="number"] {
        padding: 8px 10px;
      }
      button {
        min-height: 38px;
      }
      .list {
        margin-top: 5px;
        font-size: 12px;
        line-height: 1.3;
      }
      .stage {
        height: 100vh;
        min-height: 0;
        padding: 20px;
        gap: 12px;
        overflow: hidden;
      }
      .stage-header {
        align-items: center;
      }
      .stage-header h2 {
        font-size: 38px;
      }
      .stage-header p {
        display: none;
      }
      .pill {
        min-height: 34px;
        font-size: 12px;
      }
      .preview-shell {
        min-height: 0;
      }
      .preview {
        width: min(850px, calc((100vh - 340px) * 16 / 9), 100%);
        border-radius: 22px;
      }
      .preview::before,
      .preview::after {
        top: 14px;
        font-size: 11px;
      }
      .preview::before { left: 18px; }
      .preview::after { right: 18px; }
      body[data-state="running"] .preview::after {
        top: 12px;
        right: 14px;
      }
      .preview img {
        width: clamp(120px, 28vw, 440px);
      }
      .metrics {
        gap: 10px;
      }
      .metric {
        border-radius: 13px;
        padding: 10px 12px;
      }
      .metric span {
        font-size: 11px;
      }
      .metric strong {
        font-size: 16px;
      }
      .status {
        min-height: 40px;
        border-radius: 13px;
        padding: 9px 12px;
        font-size: 13px;
      }
      .live-dock {
        bottom: 0;
        grid-template-columns: minmax(0, 1fr) 180px 92px;
        border-radius: 14px;
        padding: 9px;
        gap: 10px;
      }
      .live-dock strong {
        font-size: 14px;
      }
      .live-dock button {
        min-height: 46px;
        font-size: 15px;
        border-radius: 11px;
      }
    }
  </style>
</head>
<body>
<main class="shell">
  <aside class="sidebar">
    <section class="brand">
      <div class="logo" aria-hidden="true"></div>
      <div>
        <h1>Virtual Face Cam</h1>
        <p>Send photos or a looping video to OBS Virtual Camera.</p>
      </div>
    </section>

    <section class="status-grid" aria-label="Current output">
      <div class="mini-card">
        <span class="eyebrow">Camera</span>
        <strong id="cameraValue">Ready</strong>
      </div>
      <div class="mini-card">
        <span class="eyebrow">Output</span>
        <strong>720p / 30 FPS</strong>
      </div>
    </section>

    <section class="control-card">
      <div class="section-title">
        <h2>Source</h2>
        <span class="eyebrow" id="fileCount">Saved source ready</span>
      </div>
      <div class="drop-row">
        <input class="file-input" id="files" type="file" accept="image/*,video/*" multiple>
        <label class="drop-zone" for="files">
          <span class="icon">+</span>
          <strong>Photos / Video</strong>
          <small>Photos or one looping video</small>
        </label>

        <input class="file-input" id="folder" type="file" accept="image/*" multiple webkitdirectory>
        <label class="drop-zone" for="folder">
          <span class="icon">/</span>
          <strong>Folder</strong>
          <small>Cycle through its photos</small>
        </label>
      </div>
      <p id="folderCount">No folder selected.</p>
    </section>

    <section class="control-card">
      <div class="section-title">
        <h2>Frame Settings</h2>
        <span class="eyebrow">Fit mode</span>
      </div>
      <div class="settings-grid">
        <div>
          <label class="input-label" for="width">Width</label>
          <input id="width" type="number" min="320" max="3840" value="1280">
        </div>
        <div>
          <label class="input-label" for="height">Height</label>
          <input id="height" type="number" min="240" max="2160" value="720">
        </div>
        <div>
          <label class="input-label" for="fps">FPS</label>
          <input id="fps" type="number" min="1" max="60" value="30">
        </div>
        <div>
          <label class="input-label" for="interval">Photo interval</label>
          <input id="interval" type="number" min="0.5" max="60" step="0.5" value="3">
        </div>
      </div>
    </section>

    <section class="actions">
      <button id="upload" class="primary">Upload</button>
      <button id="start" class="primary">Start</button>
      <button id="stop" class="danger">Stop</button>
      <button id="refresh">Refresh</button>
      <button id="quit" class="secondary">Quit App</button>
    </section>

    <section class="loaded-card">
      <span class="eyebrow">Saved source</span>
      <strong id="loadedTitle">None</strong>
      <div id="loaded" class="list">Your latest upload will return on the next launch.</div>
    </section>

    <section class="note-card">
      <span class="eyebrow">Setup note</span>
      <strong>OBS is required once</strong>
      <p>Install OBS Studio once to register the camera extension. Then press Start here and choose OBS Virtual Camera in Zoom, Teams, Chrome, or FaceTime.</p>
    </section>
  </aside>

  <section class="stage">
    <header class="stage-header">
      <div>
        <h2>Live Source</h2>
        <p>Preview the photo source or endlessly looping video sent to your virtual camera.</p>
      </div>
      <div class="pill-row">
        <span class="pill" id="statePill"><span class="dot" id="statusDot"></span><span id="stateLabel">Ready</span></span>
        <span class="pill" id="sourceLabel">No source</span>
      </div>
    </header>

    <div class="preview-shell">
      <div class="preview" id="preview">
        <div class="empty">
          <div class="empty-mark">+</div>
          <strong>No media selected</strong>
          <span>Choose photos, a photo folder, or one video.</span>
        </div>
      </div>
    </div>

    <section class="metrics" aria-label="Output settings">
      <div class="metric">
        <span>Resolution</span>
        <strong id="resolutionMetric">1280 x 720</strong>
      </div>
      <div class="metric">
        <span>Frame Rate</span>
        <strong id="fpsMetric">30 FPS</strong>
      </div>
      <div class="metric">
        <span>Camera Name</span>
        <strong>OBS Virtual Camera</strong>
      </div>
    </section>

    <div class="status" id="status"><span class="dot"></span><span>Stopped</span></div>

    <section class="live-dock" aria-label="Camera controls">
      <div>
        <span class="eyebrow">Camera Control</span>
        <strong id="dockStatus">Ready to start</strong>
      </div>
      <button id="mainToggle" class="primary big-action">Start Live</button>
      <button id="dockQuit" class="secondary">Quit</button>
    </section>
  </section>
</main>

<script>
const files = document.getElementById("files");
const folder = document.getElementById("folder");
const fileCount = document.getElementById("fileCount");
const folderCount = document.getElementById("folderCount");
const preview = document.getElementById("preview");
const statusEl = document.getElementById("status");
const statusDot = document.getElementById("statusDot");
const statePill = document.getElementById("statePill");
const stateLabel = document.getElementById("stateLabel");
const sourceLabel = document.getElementById("sourceLabel");
const loaded = document.getElementById("loaded");
const loadedTitle = document.getElementById("loadedTitle");
const resolutionMetric = document.getElementById("resolutionMetric");
const fpsMetric = document.getElementById("fpsMetric");
const cameraValue = document.getElementById("cameraValue");
const uploadBtn = document.getElementById("upload");
const startBtn = document.getElementById("start");
const stopBtn = document.getElementById("stop");
const quitBtn = document.getElementById("quit");
const mainToggle = document.getElementById("mainToggle");
const dockQuit = document.getElementById("dockQuit");
const dockStatus = document.getElementById("dockStatus");
const settingInputs = ["width", "height", "fps", "interval"].map(id => document.getElementById(id));
const intervalInput = document.getElementById("interval");
let previewKey = "";
let localPreviewUrl = "";
let isQuitting = false;
let latestState = { running: false, mediaCount: 0, mediaType: "images" };

function setStatus(message, tone = "idle") {
  const dotTone = tone === "running" ? "ready" : tone === "error" ? "error" : tone === "busy" ? "busy" : "";
  document.body.dataset.state = tone;
  statePill.className = `pill ${tone}`;
  statusEl.innerHTML = `<span class="dot ${dotTone}"></span><span>${message}</span>`;
  statusDot.className = `dot ${dotTone}`;
  stateLabel.textContent = tone === "running" ? "Live" : tone === "error" ? "Needs attention" : tone === "busy" ? "Working" : "Ready";
}

async function api(path, options = {}) {
  const res = await fetch(path, options);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

files.addEventListener("change", () => {
  const list = Array.from(files.files || []);
  fileCount.textContent = list.length ? selectionLabel(list) : "Saved source ready";
  if (list.length) {
    folder.value = "";
    folderCount.textContent = "No folder selected.";
  }
  showPreview(list);
});

folder.addEventListener("change", () => {
  const list = Array.from(folder.files || []);
  folderCount.textContent = list.length ? `${list.length} selected from folder` : "No folder selected.";
  if (list.length) {
    files.value = "";
    fileCount.textContent = `${list.length} selected`;
  }
  showPreview(list);
});

["width", "height", "fps"].forEach(id => {
  document.getElementById(id).addEventListener("input", syncMetrics);
});

function syncMetrics() {
  resolutionMetric.textContent = `${document.getElementById("width").value} x ${document.getElementById("height").value}`;
  fpsMetric.textContent = `${document.getElementById("fps").value} FPS`;
}

function applyControls(data) {
  latestState = data;
  const hasMedia = Boolean(data.mediaCount);
  const running = Boolean(data.running);
  uploadBtn.disabled = Boolean(data.running);
  startBtn.disabled = Boolean(data.running) || !hasMedia;
  stopBtn.disabled = !data.running;
  settingInputs.forEach(input => input.disabled = Boolean(data.running));
  intervalInput.disabled = Boolean(data.running) || data.mediaType === "video";
  cameraValue.textContent = running ? "Live to OBS" : hasMedia ? "Ready" : "Waiting";
  startBtn.textContent = running ? "Running" : "Start";
  stopBtn.textContent = running ? "Stop Live" : "Stop";
  mainToggle.disabled = !running && !hasMedia;
  mainToggle.textContent = running ? "Stop Live" : "Start Live";
  mainToggle.className = running ? "danger big-action" : "primary big-action";
  dockStatus.textContent = running ? "Live to OBS Virtual Camera" : hasMedia ? "Ready to start" : "Choose photos or a video";
}

function selectedFiles() {
  const direct = Array.from(files.files || []);
  return direct.length ? direct : Array.from(folder.files || []);
}

function isVideoFile(file) {
  return file.type.startsWith("video/") || /\.(mp4|mov|m4v|avi|mkv|webm)$/i.test(file.name);
}

function selectionLabel(list) {
  if (list.length === 1 && isVideoFile(list[0])) return "1 looping video";
  return `${list.length} photo${list.length === 1 ? "" : "s"} selected`;
}

function showPreview(list) {
  if (!list[0]) return;
  if (localPreviewUrl) URL.revokeObjectURL(localPreviewUrl);
  const url = URL.createObjectURL(list[0]);
  localPreviewUrl = url;
  previewKey = `local:${list.map(file => file.name).join("|")}`;
  preview.innerHTML = "";
  if (isVideoFile(list[0])) {
    const video = document.createElement("video");
    video.src = url;
    video.autoplay = true;
    video.loop = true;
    video.muted = true;
    video.playsInline = true;
    video.onloadeddata = () => video.play().catch(() => {});
    preview.appendChild(video);
  } else {
    const img = document.createElement("img");
    img.onload = () => {
      URL.revokeObjectURL(url);
      if (localPreviewUrl === url) localPreviewUrl = "";
    };
    img.src = url;
    preview.appendChild(img);
  }
  sourceLabel.textContent = list.length === 1 ? list[0].name : `${list.length} photos`;
}

function showServerPreview(names, mediaType) {
  const key = `server:${mediaType}:${names.join("|")}`;
  if (!names.length || previewKey === key) return;
  if (localPreviewUrl) {
    URL.revokeObjectURL(localPreviewUrl);
    localPreviewUrl = "";
  }
  previewKey = key;
  preview.innerHTML = "";
  if (mediaType === "video") {
    const video = document.createElement("video");
    video.src = `/api/media?key=${encodeURIComponent(key)}`;
    video.poster = `/api/video-poster?key=${encodeURIComponent(key)}`;
    video.autoplay = true;
    video.loop = true;
    video.muted = true;
    video.playsInline = true;
    preview.appendChild(video);
  } else {
    const img = document.createElement("img");
    img.src = `/api/preview?key=${encodeURIComponent(key)}&t=${Date.now()}`;
    preview.appendChild(img);
  }
  sourceLabel.textContent = names.length === 1 ? names[0] : `${names.length} photos`;
}

document.getElementById("upload").addEventListener("click", async () => {
  const list = selectedFiles();
  if (!list.length) {
    setStatus("Choose photos or one video first.", "error");
    return;
  }
  const form = new FormData();
  list.forEach(file => form.append("files", file, file.name));
  setStatus("Saving media for this and future launches...", "busy");
  try {
    const data = await api("/api/upload", { method: "POST", body: form });
    loadedTitle.textContent = data.mediaType === "video" ? "Looping video ready" : `${data.count} photo(s) ready`;
    loaded.textContent = data.names.join(", ");
    applyControls({ running: false, mediaCount: data.count, mediaType: data.mediaType });
    showServerPreview(data.names, data.mediaType);
    setStatus(data.mediaType === "video" ? "Video saved and ready to loop." : `${data.count} photo(s) saved.`);
  } catch (err) {
    setStatus(err.message, "error");
  }
});

async function startCamera() {
  const body = {
    width: Number(document.getElementById("width").value),
    height: Number(document.getElementById("height").value),
    fps: Number(document.getElementById("fps").value),
    interval: Number(document.getElementById("interval").value)
  };
  setStatus("Starting virtual camera...", "busy");
  startBtn.disabled = true;
  uploadBtn.disabled = true;
  mainToggle.disabled = true;
  try {
    await api("/api/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    });
    await refresh();
  } catch (err) {
    setStatus(err.message, "error");
    await refresh();
  }
}

async function stopCamera() {
  setStatus("Stopping virtual camera...", "busy");
  stopBtn.disabled = true;
  mainToggle.disabled = true;
  try {
    await api("/api/stop", { method: "POST" });
    await refresh();
  } catch (err) {
    setStatus(err.message, "error");
    await refresh();
  }
}

document.getElementById("start").addEventListener("click", startCamera);
document.getElementById("stop").addEventListener("click", stopCamera);

document.getElementById("refresh").addEventListener("click", refresh);

function quitApp() {
  isQuitting = true;
  setStatus("Closing app...", "busy");
  navigator.sendBeacon("/api/quit", new Blob([], { type: "text/plain" }));
  document.body.dataset.state = "busy";
  setTimeout(() => {
    statusEl.innerHTML = `<span class="dot busy"></span><span>App closed. Open Virtual Face Cam.app to start again.</span>`;
  }, 300);
}

quitBtn.addEventListener("click", quitApp);
dockQuit.addEventListener("click", quitApp);

mainToggle.addEventListener("click", () => {
  if (latestState.running) {
    stopCamera();
  } else {
    startCamera();
  }
});

function pingServer() {
  if (isQuitting) return;
  fetch("/api/ping", { method: "POST", keepalive: true }).catch(() => {});
}

window.addEventListener("pagehide", () => {
  if (isQuitting) return;
  if (latestState.running) return;
  navigator.sendBeacon("/api/client-close", new Blob([], { type: "text/plain" }));
});

window.addEventListener("beforeunload", () => {
  if (isQuitting) return;
  if (latestState.running) return;
  navigator.sendBeacon("/api/client-close", new Blob([], { type: "text/plain" }));
});

async function refresh() {
  try {
    const data = await api("/api/status");
    applyControls(data);
    loadedTitle.textContent = data.mediaCount
      ? data.mediaType === "video" ? "Looping video ready" : `${data.mediaCount} photo(s) ready`
      : "None";
    loaded.textContent = data.mediaCount ? data.mediaNames.join(", ") : "Upload photos or a video to prepare the camera feed.";
    if (data.mediaCount && !selectedFiles().length) {
      fileCount.textContent = data.mediaNames[0] === "default_face.jpg"
        ? "Default ready"
        : data.mediaType === "video" ? "Recent video restored" : `${data.mediaCount} recent photo(s)`;
      showServerPreview(data.mediaNames, data.mediaType);
    } else if (!data.mediaCount && !selectedFiles().length) {
      fileCount.textContent = "No media selected";
    }
    if (data.running) {
      setStatus(`Live: sending frames to ${data.device || "OBS Virtual Camera"}.`, "running");
    } else if (data.error) {
      setStatus(data.error, "error");
    } else if (data.mediaCount) {
      setStatus(data.mediaType === "video" ? "Looping video ready. Press Start to send." : `${data.mediaCount} photo(s) ready. Press Start to send.`);
    } else {
      setStatus("Stopped");
    }
  } catch (err) {
    setStatus(err.message, "error");
  }
}

syncMetrics();
pingServer();
setInterval(pingServer, 4000);
setInterval(refresh, 1500);
refresh();
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    server_version = "VirtualFaceCamMac/0.2"

    def log_message(self, fmt: str, *args: object) -> None:
        return

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            SHUTDOWN.mark_active(self.server)
            body = HTML.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/api/status":
            SHUTDOWN.mark_active(self.server)
            self.send_json(STATE.snapshot())
            return
        if path == "/api/preview":
            SHUTDOWN.mark_active(self.server)
            self.send_preview()
            return
        if path == "/api/media":
            SHUTDOWN.mark_active(self.server)
            self.send_media()
            return
        if path == "/api/video-poster":
            SHUTDOWN.mark_active(self.server)
            self.send_video_poster()
            return
        if path in {"/favicon.svg", "/favicon.ico"}:
            self.send_favicon()
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            if path == "/api/upload":
                self.handle_upload()
            elif path == "/api/start":
                self.handle_start()
            elif path == "/api/stop":
                STATE.stop_camera()
                self.send_json({"ok": True})
            elif path == "/api/ping":
                SHUTDOWN.mark_active(self.server)
                self.send_json({"ok": True})
            elif path == "/api/client-close":
                self.send_json({"ok": True})
                SHUTDOWN.schedule(self.server)
            elif path == "/api/quit":
                self.send_json({"ok": True})
                SHUTDOWN.now(self.server)
            else:
                self.send_error(HTTPStatus.NOT_FOUND)
        except Exception as exc:
            STATE.last_error = str(exc)
            self.send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def handle_upload(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            raise RuntimeError("No upload body received.")
        if length > MAX_UPLOAD_BYTES:
            raise RuntimeError("Upload is too large.")

        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            raise RuntimeError("Expected multipart/form-data upload.")

        body = self.rfile.read(length)
        message = BytesParser(policy=email_policy).parsebytes(
            b"Content-Type: " + content_type.encode("utf-8") + b"\r\n\r\n" + body
        )

        STATE.stop_camera()
        session_dir = UPLOAD_ROOT / str(time.time_ns())
        session_dir.mkdir(parents=True, exist_ok=True)

        saved_images: list[Path] = []
        saved_videos: list[Path] = []
        for part in message.iter_parts():
            filename = part.get_filename()
            if not filename:
                continue
            extension = Path(filename).suffix.lower()
            if extension not in MEDIA_EXTS:
                continue
            data = part.get_payload(decode=True)
            if not data:
                continue

            out = session_dir / safe_filename(filename)
            suffix = out.suffix
            counter = 1
            while out.exists():
                out = session_dir / f"{out.stem}-{counter}{suffix}"
                counter += 1
            out.write_bytes(data)

            if extension in VIDEO_EXTS:
                if is_readable_video(out):
                    saved_videos.append(out)
                else:
                    out.unlink(missing_ok=True)
                continue
            try:
                with Image.open(out) as img:
                    img.verify()
            except (OSError, UnidentifiedImageError):
                out.unlink(missing_ok=True)
                continue
            saved_images.append(out)

        if saved_videos and (saved_images or len(saved_videos) > 1):
            shutil.rmtree(session_dir, ignore_errors=True)
            raise RuntimeError("Choose one video by itself, or choose one or more photos.")
        if saved_videos:
            saved = saved_videos
            media_type = "video"
        elif saved_images:
            saved = saved_images
            media_type = "images"
        else:
            shutil.rmtree(session_dir, ignore_errors=True)
            raise RuntimeError("No supported photo or video files were uploaded.")

        STATE.replace_media(saved, media_type, persist=True)
        cleanup_old_uploads(session_dir)
        self.send_json(
            {
                "ok": True,
                "count": len(saved),
                "names": [path.name for path in saved],
                "mediaType": media_type,
            }
        )

    def handle_start(self) -> None:
        params = self.read_json()
        width = clamp_int(params.get("width"), 320, 3840, 1280)
        height = clamp_int(params.get("height"), 240, 2160, 720)
        fps = clamp_int(params.get("fps"), 1, 60, 30)
        interval = clamp_float(params.get("interval"), 0.5, 60.0, 3.0)
        self.send_json(STATE.start_camera(width, height, fps, interval))

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def send_preview(self) -> None:
        path, media_type = STATE.preview_media()
        if path is None or not path.is_file() or media_type != "images":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        body = path.read_bytes()
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_media(self) -> None:
        path, media_type = STATE.preview_media()
        if path is None or not path.is_file() or media_type != "video":
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        size = path.stat().st_size
        start = 0
        end = max(0, size - 1)
        status = HTTPStatus.OK
        range_header = self.headers.get("Range")
        if range_header:
            match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header.strip())
            if not match:
                self.send_error(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                return
            start_text, end_text = match.groups()
            if start_text:
                start = int(start_text)
                if end_text:
                    end = min(int(end_text), size - 1)
            elif end_text:
                suffix_length = min(int(end_text), size)
                start = size - suffix_length
            if start >= size or start > end:
                self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                self.send_header("Content-Range", f"bytes */{size}")
                self.end_headers()
                return
            status = HTTPStatus.PARTIAL_CONTENT

        content_length = end - start + 1
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(content_length))
        if status == HTTPStatus.PARTIAL_CONTENT:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()

        remaining = content_length
        try:
            with path.open("rb") as source:
                source.seek(start)
                while remaining:
                    chunk = source.read(min(1024 * 1024, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            return

    def send_video_poster(self) -> None:
        path, media_type = STATE.preview_media()
        if path is None or not path.is_file() or media_type != "video":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        body = video_poster(path)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_favicon(self) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "image/svg+xml")
        self.send_header("Cache-Control", "public, max-age=86400")
        self.send_header("Content-Length", str(len(FAVICON_SVG)))
        self.end_headers()
        self.wfile.write(FAVICON_SVG)

    def send_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def clamp_int(value: object, lo: int, hi: int, fallback: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return fallback
    return max(lo, min(hi, number))


def clamp_float(value: object, lo: float, hi: float, fallback: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return max(lo, min(hi, number))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-open", action="store_true")
    return parser.parse_args()


def open_browser(url: str) -> None:
    if sys.platform == "darwin":
        subprocess.Popen(["open", url])
        return
    webbrowser.open(url)


def main() -> None:
    args = parse_args()
    APP_SUPPORT.mkdir(parents=True, exist_ok=True)
    if not load_saved_media():
        load_default_image()
    try:
        server = ThreadingHTTPServer((args.host, args.port), Handler)
    except OSError:
        if args.port == 0:
            raise
        server = ThreadingHTTPServer((args.host, 0), Handler)
    actual_port = server.server_address[1]
    url = f"http://{args.host}:{actual_port}/"
    print(f"{APP_NAME} running at {url}", flush=True)
    if not args.no_open:
        threading.Timer(0.4, lambda: open_browser(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        STATE.stop_camera()
        server.server_close()


if __name__ == "__main__":
    main()
