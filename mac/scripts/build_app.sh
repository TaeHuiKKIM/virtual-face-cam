#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP="$ROOT/Virtual Face Cam.app"
RES="$APP/Contents/Resources"
MACOS="$APP/Contents/MacOS"

mkdir -p "$RES" "$MACOS"
cp "$ROOT/mac_virtual_face_cam.py" "$RES/mac_virtual_face_cam.py"
cp "$ROOT/requirements.txt" "$RES/requirements.txt"
cp "$ROOT/scripts/launch.sh" "$RES/launch.sh"
cp "$ROOT/scripts/app_executable.sh" "$MACOS/VirtualFaceCam"
chmod +x "$RES/launch.sh"
chmod +x "$MACOS/VirtualFaceCam"

echo "Updated: $APP"
