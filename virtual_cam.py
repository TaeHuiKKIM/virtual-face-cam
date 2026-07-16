"""Feed an image, image folder, or looping video into a virtual webcam.

Cross-platform: Windows, macOS, Linux (via pyvirtualcam).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path

import cv2
import numpy as np
import pyvirtualcam
from PIL import Image, ImageOps, UnidentifiedImageError

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm"}
MEDIA_EXTS = IMAGE_EXTS | VIDEO_EXTS


def settings_path() -> Path:
    """Return a per-user settings path without requiring administrator access."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "VirtualFaceCam" / "settings.json"


def load_recent_path(config_path: Path | None = None) -> Path | None:
    config = config_path or settings_path()
    try:
        data = json.loads(config.read_text(encoding="utf-8"))
        path = Path(data.get("last_media_path", ""))
    except (OSError, ValueError, TypeError):
        return None
    if path.is_dir() or (path.is_file() and path.suffix.lower() in MEDIA_EXTS):
        return path
    return None


def save_recent_path(path: str | Path, config_path: Path | None = None) -> None:
    config = config_path or settings_path()
    config.parent.mkdir(parents=True, exist_ok=True)
    temp = config.with_suffix(".tmp")
    temp.write_text(
        json.dumps({"last_media_path": str(Path(path).resolve())}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp.replace(config)


def fit_frame(img: Image.Image, width: int, height: int) -> np.ndarray:
    """Resize a Pillow image with letterboxing and return a contiguous RGB frame."""
    img = ImageOps.exif_transpose(img)
    if img.mode == "RGBA":
        background = Image.new("RGB", img.size, (0, 0, 0))
        background.paste(img, mask=img.getchannel("A"))
        img = background
    else:
        img = img.convert("RGB")

    scale = min(width / img.width, height / img.height)
    new_w, new_h = max(1, int(img.width * scale)), max(1, int(img.height * scale))
    resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

    canvas = Image.new("RGB", (width, height), (0, 0, 0))
    x0 = (width - new_w) // 2
    y0 = (height - new_h) // 2
    canvas.paste(resized, (x0, y0))
    return np.asarray(canvas, dtype=np.uint8).copy()


def fit_video_frame(frame: np.ndarray, width: int, height: int) -> np.ndarray:
    """Convert an OpenCV frame to a letterboxed contiguous RGB frame."""
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


def image_files(path: Path) -> list[Path]:
    if path.is_dir():
        files = sorted(f for f in path.iterdir() if f.suffix.lower() in IMAGE_EXTS)
        if not files:
            raise FileNotFoundError(f"폴더에 이미지가 없습니다: {path}")
        return files
    if path.is_file() and path.suffix.lower() in IMAGE_EXTS:
        return [path]
    if path.is_file():
        raise RuntimeError(f"지원하지 않는 이미지 형식입니다: {path.suffix}")
    raise FileNotFoundError(f"경로를 찾을 수 없습니다: {path}")


def load_frames(path: str | Path, width: int, height: int) -> list[np.ndarray]:
    """Load one image or every image in a folder as ready-to-send RGB frames."""
    frames = []
    for file_path in image_files(Path(path)):
        try:
            with Image.open(file_path) as img:
                frames.append(fit_frame(img, width, height))
        except (OSError, UnidentifiedImageError):
            print(f"  건너뜀 (열 수 없음): {file_path}", file=sys.stderr)
    if not frames:
        raise RuntimeError("사용할 수 있는 이미지가 없습니다.")
    return frames


class ImageFrameSource:
    media_type = "images"

    def __init__(self, path: str | Path, width: int, height: int, fps: int, interval: float):
        self.frames = load_frames(path, width, height)
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

    @property
    def item_count(self) -> int:
        return len(self.frames)


class VideoFrameSource:
    media_type = "video"

    def __init__(self, path: str | Path, width: int, height: int, fps: int):
        self.path = Path(path)
        self.width = width
        self.height = height
        self.output_fps = max(1, fps)
        self.capture = cv2.VideoCapture(str(self.path))
        if not self.capture.isOpened():
            self.capture.release()
            raise RuntimeError(f"영상을 열 수 없습니다: {self.path.name}")

        source_fps = float(self.capture.get(cv2.CAP_PROP_FPS))
        self.source_fps = source_fps if math.isfinite(source_fps) and source_fps > 0 else float(fps)
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
            raise RuntimeError(f"영상 프레임을 읽을 수 없습니다: {self.path.name}")
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

    @property
    def item_count(self) -> int:
        return 1


def create_frame_source(
    path: str | Path,
    width: int,
    height: int,
    fps: int,
    interval: float = 3.0,
) -> ImageFrameSource | VideoFrameSource:
    media_path = Path(path)
    if media_path.is_file() and media_path.suffix.lower() in VIDEO_EXTS:
        return VideoFrameSource(media_path, width, height, fps)
    return ImageFrameSource(media_path, width, height, fps, interval)


def preview_image(path: str | Path) -> Image.Image:
    """Return a detached Pillow preview for an image, folder, or video."""
    media_path = Path(path)
    if media_path.is_dir():
        media_path = image_files(media_path)[0]
    if media_path.suffix.lower() in VIDEO_EXTS:
        capture = cv2.VideoCapture(str(media_path))
        try:
            ok, frame = capture.read()
            if not ok or frame is None:
                raise RuntimeError(f"영상 미리보기를 읽을 수 없습니다: {media_path.name}")
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            return Image.fromarray(rgb)
        finally:
            capture.release()
    with Image.open(media_path) as image:
        return ImageOps.exif_transpose(image).convert("RGB").copy()


def main() -> None:
    default_img = Path(__file__).resolve().parent / "assets" / "default_face.jpg"
    parser = argparse.ArgumentParser(
        description="이미지, 이미지 폴더 또는 영상을 가상 웹캠으로 출력합니다.")
    parser.add_argument(
        "path",
        nargs="?",
        default=str(default_img),
        help="이미지·영상 파일 또는 이미지 폴더 경로 (생략 시 기본 이미지)",
    )
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument(
        "--interval",
        type=float,
        default=3.0,
        help="이미지 폴더의 사진을 바꾸는 간격(초). 기본 3초",
    )
    args = parser.parse_args()

    try:
        source = create_frame_source(args.path, args.width, args.height, args.fps, args.interval)
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"오류: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    try:
        cam = pyvirtualcam.Camera(width=args.width, height=args.height, fps=args.fps)
    except Exception as exc:
        source.close()
        print("가상 카메라를 시작할 수 없습니다.", file=sys.stderr)
        print("OBS Studio(가상카메라 드라이버)가 설치되어 있는지 확인하세요.", file=sys.stderr)
        print(f"세부 오류: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    try:
        with cam:
            media_label = "무한 반복 영상" if source.media_type == "video" else f"이미지 {source.item_count}장"
            print(f"가상 카메라 시작: {cam.device}")
            print(f"해상도 {args.width}x{args.height} @ {args.fps}fps, {media_label}")
            print("종료하려면 Ctrl+C")
            try:
                while True:
                    cam.send(source.next_frame())
                    cam.sleep_until_next_frame()
            except KeyboardInterrupt:
                print("\n종료")
    finally:
        source.close()


if __name__ == "__main__":
    main()
