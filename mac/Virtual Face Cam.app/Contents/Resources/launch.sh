#!/bin/bash
set -u

APP_DIR="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
APP_SUPPORT="$HOME/Library/Application Support/VirtualFaceCamMac"
VENV="$APP_SUPPORT/.venv"
LOG="$APP_SUPPORT/launch.log"

mkdir -p "$APP_SUPPORT"
if [ -f "$LOG" ] && [ "$(stat -f %z "$LOG" 2>/dev/null || printf '0')" -gt 5242880 ]; then
    mv "$LOG" "$APP_SUPPORT/launch-$(date +%Y%m%d-%H%M%S).log"
fi
exec >>"$LOG" 2>&1

export PATH="/opt/homebrew/bin:/usr/local/bin:/Library/Frameworks/Python.framework/Versions/Current/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

echo "Virtual Face Cam for macOS"
echo "App files: $APP_DIR"
echo "PATH: $PATH"

fail() {
    local message="$1"
    echo ""
    echo "[Error] $message"
    /usr/bin/osascript - "$message" "$LOG" <<'APPLESCRIPT' >/dev/null 2>&1 || true
on run argv
    display dialog (item 1 of argv & return & return & "Log: " & item 2 of argv) buttons {"OK"} default button "OK" with icon caution
end run
APPLESCRIPT
    exit 1
}

is_usable_python() {
    "$1" - <<'PY' >/dev/null 2>&1
import sys
if sys.version_info < (3, 10):
    raise SystemExit(1)
PY
}

resolve_command() {
    local cmd="$1"
    if [[ "$cmd" == */* ]]; then
        [ -x "$cmd" ] && printf '%s\n' "$cmd"
        return
    fi
    command -v "$cmd" 2>/dev/null || true
}

find_python() {
    for cmd in \
        "${PYTHON:-}" \
        /opt/homebrew/bin/python3.14 /opt/homebrew/bin/python3.13 /opt/homebrew/bin/python3.12 /opt/homebrew/bin/python3.11 /opt/homebrew/bin/python3.10 /opt/homebrew/bin/python3 \
        /usr/local/bin/python3.14 /usr/local/bin/python3.13 /usr/local/bin/python3.12 /usr/local/bin/python3.11 /usr/local/bin/python3.10 /usr/local/bin/python3 \
        /Library/Frameworks/Python.framework/Versions/3.14/bin/python3 /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 /Library/Frameworks/Python.framework/Versions/3.12/bin/python3 /Library/Frameworks/Python.framework/Versions/3.11/bin/python3 /Library/Frameworks/Python.framework/Versions/3.10/bin/python3 \
        python3.14 python3.13 python3.12 python3.11 python3.10 python3; do
        [ -n "$cmd" ] || continue
        resolved="$(resolve_command "$cmd")"
        [ -n "$resolved" ] || continue
        if is_usable_python "$resolved"; then
            printf '%s\n' "$resolved"
            return 0
        fi
    done
    return 1
}

PYTHON_BIN="$(find_python)"
if [ -z "$PYTHON_BIN" ]; then
    fail "Python 3.10 or later is required. Install Python from https://www.python.org/downloads/macos/ or run: brew install python"
fi

echo "Python: $PYTHON_BIN"

if [ ! -x "$VENV/bin/python" ]; then
    "$PYTHON_BIN" -m venv "$VENV" || fail "Could not create the Python environment."
fi

"$VENV/bin/python" -m pip install --upgrade pip >/dev/null || fail "Could not update pip."

if ! "$VENV/bin/python" -c "import pyvirtualcam, numpy, PIL, cv2" >/dev/null 2>&1; then
    echo "Installing Python packages..."
    "$VENV/bin/python" -m pip install -r "$APP_DIR/requirements.txt" || fail "Could not install Python packages."
fi

echo "Opening browser UI..."
"$VENV/bin/python" "$APP_DIR/mac_virtual_face_cam.py" || fail "Could not start Virtual Face Cam."
