#!/bin/bash
# hshot.sh out.png : screenshot of the headless PCSX2 (tools/emu/headless.sh)
out=$(realpath -m "$1"); rm -f "$out"
# the headless gamescope's socket (gamescope-N; N can be > 0 if an old socket remains)
sock=$(ls -t "$XDG_RUNTIME_DIR" | grep -E '^gamescope-[0-9]+$' | head -1)
GAMESCOPE_WAYLAND_DISPLAY=${sock:-gamescope-0} gamescopectl screenshot "$out" >/dev/null 2>&1
for i in $(seq 1 20); do [ -s "$out" ] && break; timeout 0.25 tail -f /dev/null; done
[ -s "$out" ] || { echo "no screenshot"; exit 1; }
