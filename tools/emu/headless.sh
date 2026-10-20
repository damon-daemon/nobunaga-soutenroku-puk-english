#!/bin/bash
# headless.sh image.iso : run PCSX2 on a disc image inside a headless gamescope (no window
# on the desktop) with a virtual gamepad (tools/emu/vpad.py, seen only by game-controller
# readers); drive it with vpad.py press ..., inspect it with tools/emu/pine.py.
# Stop: tools/emu/headless.sh stop
# Output size: HW/HH (default 640x448; e.g. HW=2560 HH=1792 with upscaling to check it).
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
PY="$ROOT/.venv/bin/python"
if [ "$1" = stop ]; then
  pkill -x gamescope; pkill -x gamescopereaper; "$PY" "$ROOT/tools/emu/vpad.py" stop 2>/dev/null; exit 0
fi
[ -d "$ROOT/build/pcsx2h/PCSX2/inis" ] || "$PY" "$ROOT/tools/emu/datapath.py" --headless
[ -S "$XDG_RUNTIME_DIR/nobu-vpad.sock" ] || ("$PY" "$ROOT/tools/emu/vpad.py" serve >/dev/null 2>&1 &)
timeout 1 tail -f /dev/null
(env -u WAYLAND_DISPLAY QT_QPA_PLATFORM=xcb gamescope --backend headless -W ${HW:-640} -H ${HH:-448} -- \
  ~/.local/bin/pcsx2-v2.4.0-linux-appimage-x64-Qt.AppImage -datapath "$ROOT/build/pcsx2h" -batch -fastboot -fullscreen \
  -- "$(realpath "$1")" > "$ROOT/build/pcsx2h/headless.log" 2>&1 &)
