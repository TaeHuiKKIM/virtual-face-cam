"""Feed a static image (or a folder of images) into a virtual webcam.

Cross-platform: Windows, macOS, Linux (via pyvirtualcam).
"""
import argparse
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import pyvirtualcam

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def fit_frame(img, width, height):
    """Resize keeping aspect ratio, letterboxed onto a width x height canvas (RGB)."""
    h, w = img.shape[:2]
    scale = min(width / w, height / h)
    new_w, new_h = max(1, int(w * scale)), max(1, int(h * scale))
    # 확대할 땐 LANCZOS4(선명), 축소할 땐 AREA(모아레 방지)
    interp = cv2.INTER_LANCZOS4 if scale > 1 else cv2.INTER_AREA
    resized = cv2.resize(img, (new_w, new_h), interpolation=interp)

    canvas = np.zeros((height, width, 3), dtype=np.uint8)
    y0 = (height - new_h) // 2
    x0 = (width - new_w) // 2
    canvas[y0:y0 + new_h, x0:x0 + new_w] = resized
    return cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB)


def load_frames(path, width, height):
    """Load one image or every image in a folder, as ready-to-send RGB frames."""
    p = Path(path)
    if p.is_dir():
        files = sorted(f for f in p.iterdir() if f.suffix.lower() in IMAGE_EXTS)
        if not files:
            raise FileNotFoundError(f"폴더에 이미지가 없습니다: {path}")
    elif p.is_file():
        files = [p]
    else:
        raise FileNotFoundError(f"경로를 찾을 수 없습니다: {path}")

    frames = []
    for f in files:
        img = cv2.imread(str(f))
        if img is None:
            print(f"  건너뜀 (열 수 없음): {f}", file=sys.stderr)
            continue
        frames.append(fit_frame(img, width, height))
    if not frames:
        raise RuntimeError("사용할 수 있는 이미지가 없습니다.")
    return frames


def main():
    parser = argparse.ArgumentParser(
        description="정적 이미지(또는 이미지 폴더)를 가상 웹캠으로 출력합니다.")
    parser.add_argument("path", help="이미지 파일 또는 이미지가 든 폴더 경로")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--interval", type=float, default=3.0,
                        help="폴더일 때 이미지를 바꾸는 간격(초). 기본 3초")
    args = parser.parse_args()

    try:
        frames = load_frames(args.path, args.width, args.height)
    except (FileNotFoundError, RuntimeError) as e:
        print(f"오류: {e}", file=sys.stderr)
        sys.exit(1)

    frames_per_image = max(1, int(args.interval * args.fps))

    try:
        cam = pyvirtualcam.Camera(width=args.width, height=args.height, fps=args.fps)
    except Exception as e:
        print("가상 카메라를 시작할 수 없습니다.", file=sys.stderr)
        print("OBS Studio(가상카메라 드라이버)가 설치되어 있는지 확인하세요.", file=sys.stderr)
        print(f"세부 오류: {e}", file=sys.stderr)
        sys.exit(1)

    with cam:
        print(f"가상 카메라 시작: {cam.device}")
        print(f"해상도 {args.width}x{args.height} @ {args.fps}fps, 이미지 {len(frames)}장")
        print("종료하려면 Ctrl+C")
        idx, count = 0, 0
        try:
            while True:
                cam.send(frames[idx])
                cam.sleep_until_next_frame()
                if len(frames) > 1:
                    count += 1
                    if count >= frames_per_image:
                        count = 0
                        idx = (idx + 1) % len(frames)
        except KeyboardInterrupt:
            print("\n종료")


if __name__ == "__main__":
    main()
