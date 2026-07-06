"""Build a standalone executable with PyInstaller.

Run on the SAME OS you want to build for (PyInstaller does not cross-compile):
    pip install -r requirements.txt pyinstaller
    python build.py

Output:
    Windows -> dist/virtual-face-cam.exe
    macOS   -> dist/virtual-face-cam        (unix executable)
    Linux   -> dist/virtual-face-cam
"""
import platform
import subprocess
import sys

def main():
    gui = "--cli" not in sys.argv
    if gui:
        name = "virtual-face-cam-gui"
        entry = "gui.py"
        window = "--windowed"   # 콘솔 창 없이 GUI만
    else:
        name = "virtual-face-cam"
        entry = "virtual_cam.py"
        window = "--console"

    sep = ";" if platform.system() == "Windows" else ":"
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--name", name,
        "--add-data", f"assets{sep}assets",   # 기본 이미지 번들
        window,
        entry,
    ]
    print("빌드 중:", " ".join(cmd))
    subprocess.check_call(cmd)

    system = platform.system()
    if system == "Windows":
        out = f"dist/{name}.exe"
    elif system == "Darwin" and gui:
        out = f"dist/{name}.app"
    else:
        out = f"dist/{name}"
    print(f"\n완료 → {out}")
    print("이 파일만 배포하면 됩니다 (단, OBS 가상카메라 드라이버는 별도 설치 필요).")
    print("CLI 버전을 빌드하려면: python build.py --cli")


if __name__ == "__main__":
    main()
