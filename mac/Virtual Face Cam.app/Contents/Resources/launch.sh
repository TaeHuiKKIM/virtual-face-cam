#!/bin/bash
set -u

APP_DIR="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
APP_SUPPORT="$HOME/Library/Application Support/VirtualFaceCamMac"
VENV="$APP_SUPPORT/.venv"

echo "Virtual Face Cam for macOS"
echo "App files: $APP_DIR"

is_usable_python() {
    "$1" - <<'PY' >/dev/null 2>&1
import sys
if sys.version_info < (3, 10):
    raise SystemExit(1)
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
    echo "[Error] Python 3.10 or later is required."
    echo "Install Python from https://www.python.org/downloads/macos/ or run: brew install python"
    echo ""
    read -n 1 -s -r -p "Press any key to close..."
    exit 1
fi

mkdir -p "$APP_SUPPORT"

if [ ! -x "$VENV/bin/python" ]; then
    "$PYTHON_BIN" -m venv "$VENV" || exit 1
fi

"$VENV/bin/python" -m pip install --upgrade pip >/dev/null || exit 1

if ! "$VENV/bin/python" -c "import pyvirtualcam, numpy, PIL" >/dev/null 2>&1; then
    echo "Installing Python packages..."
    "$VENV/bin/python" -m pip install -r "$APP_DIR/requirements.txt" || exit 1
fi

echo "Opening browser UI..."
"$VENV/bin/python" "$APP_DIR/mac_virtual_face_cam.py"
