#!/bin/bash
# run.sh image.iso : (re)start PCSX2 on a disc image with the test data folder (build/pcsx2)
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
pkill -x AppRun; pkill -x pcsx2-qt; timeout 2 tail -f /dev/null
[ -d "$ROOT/build/pcsx2/PCSX2/inis" ] || "$ROOT/.venv/bin/python" "$ROOT/tools/emu/datapath.py"
(~/.local/bin/pcsx2-v2.4.0-linux-appimage-x64-Qt.AppImage -datapath "$ROOT/build/pcsx2" -batch -fastboot -- "$(realpath "$1")" >/dev/null 2>&1 &)
for i in $(seq 1 60); do
  hyprctl clients -j | grep -qE '"class": "(AppRun|pcsx2)' && break; timeout 0.5 tail -f /dev/null
done
timeout 3 tail -f /dev/null
