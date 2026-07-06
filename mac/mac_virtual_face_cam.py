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
      grid-template-rows: auto minmax(0, 1fr) auto;
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
    .preview img {
      width: clamp(140px, 34vw, 520px);
      height: auto;
      max-width: calc(100% - 36px);
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
    }
    @media (max-width: 880px) {
      .shell { grid-template-columns: 1fr; }
      .sidebar { border-right: 0; border-bottom: 1px solid rgba(255, 255, 255, 0.08); }
      .stage { padding: 24px; }
      .stage-header { align-items: flex-start; flex-direction: column; }
      .pill-row { justify-content: flex-start; }
      .metrics { grid-template-columns: 1fr; }
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
        <p>Send still images to OBS Virtual Camera.</p>
      </div>
    </section>

    <section class="status-grid" aria-label="Current output">
      <div class="mini-card">
        <span class="eyebrow">Camera</span>
        <strong>OBS Virtual Camera</strong>
      </div>
      <div class="mini-card">
        <span class="eyebrow">Output</span>
        <strong>720p / 30 FPS</strong>
      </div>
    </section>

    <section class="control-card">
      <div class="section-title">
        <h2>Source</h2>
        <span class="eyebrow" id="fileCount">No images selected</span>
      </div>
      <div class="drop-row">
        <input class="file-input" id="files" type="file" accept="image/*" multiple>
        <label class="drop-zone" for="files">
          <span class="icon">+</span>
          <strong>Images</strong>
          <small>Pick one or more files</small>
        </label>

        <input class="file-input" id="folder" type="file" accept="image/*" multiple webkitdirectory>
        <label class="drop-zone" for="folder">
          <span class="icon">/</span>
          <strong>Folder</strong>
          <small>Cycle through a folder</small>
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
          <label class="input-label" for="interval">Interval</label>
          <input id="interval" type="number" min="0.5" max="60" step="0.5" value="3">
        </div>
      </div>
    </section>

    <section class="actions">
      <button id="upload" class="primary">Upload</button>
      <button id="start" class="primary">Start</button>
      <button id="stop" class="danger">Stop</button>
      <button id="refresh">Refresh</button>
    </section>

    <section class="loaded-card">
      <span class="eyebrow">Loaded images</span>
      <strong id="loadedTitle">None</strong>
      <div id="loaded" class="list">Upload images to prepare the camera feed.</div>
    </section>

    <section class="note-card">
      <span class="eyebrow">Setup note</span>
      <strong>OBS is required once</strong>
      <p>Install OBS Studio, start its virtual camera once, then choose OBS Virtual Camera in Zoom, Teams, Chrome, or FaceTime.</p>
    </section>
  </aside>

  <section class="stage">
    <header class="stage-header">
      <div>
        <h2>Live Source</h2>
        <p>Preview the exact image frame that will be sent to your virtual camera.</p>
      </div>
      <div class="pill-row">
        <span class="pill"><span class="dot" id="statusDot"></span><span id="stateLabel">Stopped</span></span>
        <span class="pill" id="sourceLabel">No source</span>
      </div>
    </header>

    <div class="preview-shell">
      <div class="preview" id="preview">
        <div class="empty">
          <div class="empty-mark">+</div>
          <strong>No image selected</strong>
          <span>Choose an image or folder to prepare the camera source.</span>
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
const stateLabel = document.getElementById("stateLabel");
const sourceLabel = document.getElementById("sourceLabel");
const loaded = document.getElementById("loaded");
const loadedTitle = document.getElementById("loadedTitle");
const resolutionMetric = document.getElementById("resolutionMetric");
const fpsMetric = document.getElementById("fpsMetric");

function setStatus(message, tone = "idle") {
  statusEl.innerHTML = `<span class="dot ${tone === "running" ? "ready" : tone === "error" ? "error" : ""}"></span><span>${message}</span>`;
  statusDot.className = `dot ${tone === "running" ? "ready" : tone === "error" ? "error" : ""}`;
  stateLabel.textContent = tone === "running" ? "Running" : tone === "error" ? "Needs attention" : "Stopped";
}

async function api(path, options = {}) {
  const res = await fetch(path, options);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

files.addEventListener("change", () => {
  const list = Array.from(files.files || []);
  fileCount.textContent = list.length ? `${list.length} selected` : "No images selected";
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

function selectedFiles() {
  const direct = Array.from(files.files || []);
  return direct.length ? direct : Array.from(folder.files || []);
}

function showPreview(list) {
  if (!list[0]) return;
  const url = URL.createObjectURL(list[0]);
  preview.innerHTML = "";
  const img = document.createElement("img");
  img.onload = () => URL.revokeObjectURL(url);
  img.src = url;
  preview.appendChild(img);
  sourceLabel.textContent = list.length === 1 ? list[0].name : `${list.length} images`;
}

document.getElementById("upload").addEventListener("click", async () => {
  const list = selectedFiles();
  if (!list.length) {
    setStatus("Choose one or more images first.", "error");
    return;
  }
  const form = new FormData();
  list.forEach(file => form.append("files", file, file.name));
  setStatus("Uploading images...");
  try {
    const data = await api("/api/upload", { method: "POST", body: form });
    loadedTitle.textContent = `${data.count} image(s) ready`;
    loaded.textContent = data.names.join(", ");
    setStatus(`${data.count} image(s) loaded.`);
  } catch (err) {
    setStatus(err.message, "error");
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
    setStatus(`Running: ${data.device || "OBS Virtual Camera"}`, "running");
  } catch (err) {
    setStatus(err.message, "error");
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
    loadedTitle.textContent = data.imageCount ? `${data.imageCount} image(s) ready` : "None";
    loaded.textContent = data.imageCount ? data.imageNames.join(", ") : "Upload images to prepare the camera feed.";
    if (data.running) {
      setStatus(`Running: ${data.device || "OBS Virtual Camera"}`, "running");
    } else if (data.error) {
      setStatus(data.error, "error");
    } else {
      setStatus("Stopped");
    }
  } catch (err) {
    setStatus(err.message, "error");
  }
}

syncMetrics();
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
