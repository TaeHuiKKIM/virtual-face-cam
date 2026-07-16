#!/bin/bash
# 더블클릭 실행용 (최초 1회: 우클릭 > 열기 로 Gatekeeper 허용 필요할 수 있음)
cd "$(dirname "$0")"

echo "Virtual Face Cam 준비 중..."

pause_and_exit() {
    echo ""
    read -n 1 -s -r -p "아무 키나 누르면 종료합니다..."
    echo ""
    exit 1
}

is_usable_python() {
    "$1" - <<'PY' >/dev/null 2>&1
import sys
if sys.version_info < (3, 10):
    raise SystemExit(1)
import tkinter
PY
}

find_python() {
    for cmd in "${PYTHON:-}" python3.14 python3.13 python3.12 python3.11 python3.10 python3; do
        [ -n "$cmd" ] || continue
        if command -v "$cmd" >/dev/null 2>&1 && is_usable_python "$cmd"; then
            command -v "$cmd"
            return 0
        fi
    done
    return 1
}

PYTHON_BIN="$(find_python)"
if [ -z "$PYTHON_BIN" ]; then
    echo ""
    echo "[오류] Python 3.10 이상과 Tkinter가 필요합니다."
    echo ""
    echo "Homebrew Python을 쓰는 경우 Tkinter가 별도 패키지라 GUI가 실행되지 않을 수 있습니다."
    if command -v python3 >/dev/null 2>&1; then
        TK_FORMULA="$(python3 - <<'PY' 2>/dev/null
import sys
print(f"python-tk@{sys.version_info.major}.{sys.version_info.minor}")
PY
)"
        [ -n "$TK_FORMULA" ] && echo "설치 예: brew install $TK_FORMULA"
    fi
    echo "또는 https://www.python.org/downloads/macos/ 에서 Python 3.12/3.13을 설치하세요."
    pause_and_exit
fi

echo "사용 Python: $PYTHON_BIN"

VENV=".venv-mac"
if [ ! -x "$VENV/bin/python" ]; then
    "$PYTHON_BIN" -m venv "$VENV" || pause_and_exit
fi

if ! "$VENV/bin/python" -c "import tkinter" >/dev/null 2>&1; then
    echo "기존 macOS 가상환경을 다시 만듭니다..."
    rm -rf "$VENV"
    "$PYTHON_BIN" -m venv "$VENV" || pause_and_exit
fi

"$VENV/bin/python" -m pip install --upgrade pip >/dev/null || pause_and_exit

if ! "$VENV/bin/python" -c "import pyvirtualcam, numpy, PIL, cv2, tkinter" >/dev/null 2>&1; then
    echo "필요한 패키지를 설치합니다. 잠시만 기다려 주세요..."
    "$VENV/bin/python" -m pip install -r requirements.txt || pause_and_exit
fi

"$VENV/bin/python" gui.py
