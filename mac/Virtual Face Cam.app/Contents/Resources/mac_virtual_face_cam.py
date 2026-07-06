"""macOS-first browser UI for sending still images to OBS Virtual Camera."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import threading
import time
import webbrowser
from dataclasses import dataclass, field
from email.parser import BytesParser
from email.policy import default as email_policy
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import numpy as np
import pyvirtualcam
from PIL import Image, ImageOps, UnidentifiedImageError


APP_NAME = "Virtual Face Cam"
APP_SUPPORT = Path.home() / "Library" / "Application Support" / "VirtualFaceCamMac"
UPLOAD_ROOT = APP_SUPPORT / "uploads"
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
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


def safe_filename(name: str) -> str:
    base = Path(name).name.strip() or "image"
    stem = re.sub(r"[^A-Za-z0-9._ -]+", "_", base)
    return stem[:120]


class CameraWorker(threading.Thread):
    def __init__(
        self,
        frames: list[np.ndarray],
        width: int,
        height: int,
        fps: int,
        interval: float,
    ) -> None:
        super().__init__(daemon=True)
        self.frames = frames
        self.width = width
        self.height = height
        self.fps = fps
        self.interval = interval
        self.stop_event = threading.Event()
        self.ready = threading.Event()
        self.error: str | None = None
        self.device: str | None = None

    def run(self) -> None:
        try:
            frames_per_image = max(1, int(self.interval * self.fps))
            with pyvirtualcam.Camera(
                width=self.width,
                height=self.height,
                fps=self.fps,
            ) as cam:
                self.device = cam.device
                self.ready.set()
                idx = 0
                count = 0
                while not self.stop_event.is_set():
                    cam.send(self.frames[idx])
                    cam.sleep_until_next_frame()
                    if len(self.frames) > 1:
                        count += 1
                        if count >= frames_per_image:
                            count = 0
                            idx = (idx + 1) % len(self.frames)
        except Exception as exc:  # pyvirtualcam raises backend-specific errors.
            self.error = str(exc)
            self.ready.set()

    def stop(self) -> None:
        self.stop_event.set()


@dataclass
class AppState:
    lock: threading.Lock = field(default_factory=threading.Lock)
    image_paths: list[Path] = field(default_factory=list)
    image_names: list[str] = field(default_factory=list)
    worker: CameraWorker | None = None
    last_error: str | None = None

    def snapshot(self) -> dict:
        with self.lock:
            running = self.worker is not None and self.worker.is_alive() and not self.worker.error
            device = self.worker.device if self.worker else None
            return {
                "running": running,
                "device": device,
                "imageCount": len(self.image_paths),
                "imageNames": self.image_names[:8],
                "error": self.last_error,
            }

    def replace_images(self, paths: list[Path]) -> None:
        with self.lock:
            self.image_paths = paths
            self.image_names = [p.name for p in paths]
            self.last_error = None

    def start_camera(self, width: int, height: int, fps: int, interval: float) -> dict:
        with self.lock:
            if self.worker and self.worker.is_alive():
                return {"ok": True, "message": "Camera is already running."}
            paths = list(self.image_paths)
        if not paths:
            raise RuntimeError("Upload at least one image first.")

        frames = load_frames(paths, width, height)
        worker = CameraWorker(frames, width, height, fps, interval)
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


HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Virtual Face Cam</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f4f6f3;
      --panel: #ffffff;
      --ink: #202322;
      --muted: #69716d;
      --line: #d9dfda;
      --accent: #16745f;
      --accent-ink: #ffffff;
      --danger: #b4233c;
      --stage: #1d2023;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      background: var(--bg);
      color: var(--ink);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    main {
      min-height: 100vh;
      display: grid;
      grid-template-columns: minmax(280px, 360px) 1fr;
    }
    aside {
      background: var(--panel);
      border-right: 1px solid var(--line);
      padding: 22px;
      display: flex;
      flex-direction: column;
      gap: 18px;
    }
    h1 {
      margin: 0;
      font-size: 22px;
      line-height: 1.2;
      letter-spacing: 0;
    }
    p {
      margin: 6px 0 0;
      color: var(--muted);
      line-height: 1.45;
      font-size: 14px;
    }
    label {
      display: block;
      margin-bottom: 6px;
      color: #38413d;
      font-size: 13px;
      font-weight: 600;
    }
    input[type="file"],
    input[type="number"] {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fbfcfb;
      color: var(--ink);
      font: inherit;
      padding: 9px 10px;
    }
    .grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
    }
    button {
      border: 0;
      border-radius: 6px;
      min-height: 40px;
      padding: 0 14px;
      background: #e7ece8;
      color: var(--ink);
      font: 600 14px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      cursor: pointer;
    }
    button.primary { background: var(--accent); color: var(--accent-ink); }
    button.danger { background: var(--danger); color: white; }
    button:disabled { cursor: not-allowed; opacity: 0.55; }
    .actions {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
    }
    .stage {
      background: var(--stage);
      min-width: 0;
      display: grid;
      grid-template-rows: 1fr auto;
    }
    .preview {
      min-height: 360px;
      display: grid;
      place-items: center;
      padding: 28px;
    }
    .preview img {
      max-width: min(860px, 100%);
      max-height: min(72vh, 720px);
      object-fit: contain;
      background: #000;
      border: 1px solid #34393f;
    }
    .empty {
      width: min(620px, 100%);
      aspect-ratio: 16 / 9;
      border: 1px dashed #697078;
      display: grid;
      place-items: center;
      color: #aab1aa;
      text-align: center;
      padding: 20px;
    }
    .status {
      border-top: 1px solid #34393f;
      color: #d8ddd8;
      padding: 14px 18px;
      min-height: 54px;
      font-size: 14px;
      line-height: 1.4;
    }
    .list {
      color: var(--muted);
      font-size: 13px;
      line-height: 1.45;
      word-break: break-word;
    }
    @media (max-width: 760px) {
      main { grid-template-columns: 1fr; }
      aside { border-right: 0; border-bottom: 1px solid var(--line); }
      .preview { min-height: 260px; }
    }
  </style>
</head>
<body>
<main>
  <aside>
    <section>
      <h1>Virtual Face Cam</h1>
      <p>Upload one or more images, then send them to OBS Virtual Camera.</p>
    </section>

    <section>
      <label for="files">Images</label>
      <input id="files" type="file" accept="image/*" multiple>
      <p id="fileCount">No images selected.</p>
    </section>

    <section>
      <label for="folder">Folder</label>
      <input id="folder" type="file" accept="image/*" multiple webkitdirectory>
      <p id="folderCount">No folder selected.</p>
    </section>

    <section class="grid">
      <div>
        <label for="width">Width</label>
        <input id="width" type="number" min="320" max="3840" value="1280">
      </div>
      <div>
        <label for="height">Height</label>
        <input id="height" type="number" min="240" max="2160" value="720">
      </div>
      <div>
        <label for="fps">FPS</label>
        <input id="fps" type="number" min="1" max="60" value="30">
      </div>
      <div>
        <label for="interval">Interval</label>
        <input id="interval" type="number" min="0.5" max="60" step="0.5" value="3">
      </div>
    </section>

    <section class="actions">
      <button id="upload" class="primary">Upload</button>
      <button id="start" class="primary">Start</button>
      <button id="stop" class="danger">Stop</button>
      <button id="refresh">Refresh</button>
    </section>

    <section>
      <label>Loaded images</label>
      <div id="loaded" class="list">None</div>
    </section>

    <section>
      <p>OBS Studio 30 or later must be installed once so macOS registers the virtual camera system extension.</p>
    </section>
  </aside>

  <section class="stage">
    <div class="preview" id="preview">
      <div class="empty">Select an image to preview it here.</div>
    </div>
    <div class="status" id="status">Stopped</div>
  </section>
</main>

<script>
const files = document.getElementById("files");
const folder = document.getElementById("folder");
const fileCount = document.getElementById("fileCount");
const folderCount = document.getElementById("folderCount");
const preview = document.getElementById("preview");
const statusEl = document.getElementById("status");
const loaded = document.getElementById("loaded");

function setStatus(message) {
  statusEl.textContent = message;
}

async function api(path, options = {}) {
  const res = await fetch(path, options);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

files.addEventListener("change", () => {
  const list = Array.from(files.files || []);
  fileCount.textContent = list.length ? `${list.length} selected` : "No images selected.";
  if (list.length) folder.value = "";
  showPreview(list);
});

folder.addEventListener("change", () => {
  const list = Array.from(folder.files || []);
  folderCount.textContent = list.length ? `${list.length} selected from folder` : "No folder selected.";
  if (list.length) files.value = "";
  showPreview(list);
});

function selectedFiles() {
  const direct = Array.from(files.files || []);
  return direct.length ? direct : Array.from(folder.files || []);
}

function showPreview(list) {
  if (list[0]) {
    const url = URL.createObjectURL(list[0]);
    preview.innerHTML = "";
    const img = document.createElement("img");
    img.onload = () => URL.revokeObjectURL(url);
    img.src = url;
    preview.appendChild(img);
  }
}

document.getElementById("upload").addEventListener("click", async () => {
  const list = selectedFiles();
  if (!list.length) return setStatus("Choose one or more images first.");
  const form = new FormData();
  list.forEach(file => form.append("files", file, file.name));
  setStatus("Uploading images...");
  try {
    const data = await api("/api/upload", { method: "POST", body: form });
    loaded.textContent = data.names.join(", ");
    setStatus(`${data.count} image(s) loaded.`);
  } catch (err) {
    setStatus(err.message);
  }
});

document.getElementById("start").addEventListener("click", async () => {
  const body = {
    width: Number(document.getElementById("width").value),
    height: Number(document.getElementById("height").value),
    fps: Number(document.getElementById("fps").value),
    interval: Number(document.getElementById("interval").value)
  };
  setStatus("Starting virtual camera...");
  try {
    const data = await api("/api/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    });
    setStatus(`Running: ${data.device || "OBS Virtual Camera"}`);
  } catch (err) {
    setStatus(err.message);
  }
});

document.getElementById("stop").addEventListener("click", async () => {
  await api("/api/stop", { method: "POST" });
  await refresh();
});

document.getElementById("refresh").addEventListener("click", refresh);

async function refresh() {
  try {
    const data = await api("/api/status");
    loaded.textContent = data.imageCount ? data.imageNames.join(", ") : "None";
    if (data.running) {
      setStatus(`Running: ${data.device || "OBS Virtual Camera"}`);
    } else if (data.error) {
      setStatus(data.error);
    } else {
      setStatus("Stopped");
    }
  } catch (err) {
    setStatus(err.message);
  }
}

setInterval(refresh, 1500);
refresh();
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    server_version = "VirtualFaceCamMac/0.1"

    def log_message(self, fmt: str, *args: object) -> None:
        return

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            body = HTML.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/api/status":
            self.send_json(STATE.snapshot())
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
        shutil.rmtree(UPLOAD_ROOT, ignore_errors=True)
        session_dir = UPLOAD_ROOT / str(int(time.time()))
        session_dir.mkdir(parents=True, exist_ok=True)

        saved: list[Path] = []
        for part in message.iter_parts():
            filename = part.get_filename()
            if not filename:
                continue
            if Path(filename).suffix.lower() not in IMAGE_EXTS:
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

            try:
                with Image.open(out) as img:
                    img.verify()
            except (OSError, UnidentifiedImageError):
                out.unlink(missing_ok=True)
                continue
            saved.append(out)

        if not saved:
            raise RuntimeError("No supported image files were uploaded.")
        STATE.replace_images(saved)
        self.send_json({"ok": True, "count": len(saved), "names": [p.name for p in saved]})

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


def main() -> None:
    args = parse_args()
    APP_SUPPORT.mkdir(parents=True, exist_ok=True)
    try:
        server = ThreadingHTTPServer((args.host, args.port), Handler)
    except OSError:
        if args.port == 0:
            raise
        server = ThreadingHTTPServer((args.host, 0), Handler)
    actual_port = server.server_address[1]
    url = f"http://{args.host}:{actual_port}/"
    print(f"{APP_NAME} running at {url}")
    if not args.no_open:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        STATE.stop_camera()
        server.server_close()


if __name__ == "__main__":
    main()
