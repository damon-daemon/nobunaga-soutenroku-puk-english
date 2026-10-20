#!/bin/bash
# shot.sh out.png : PCSX2 screenshot hotkey (F8) -> raw game frame, copied to out.png
ROOT=$(cd "$(dirname "$0")/../.." && pwd); SNAPS="$ROOT/build/pcsx2/PCSX2/snaps"
mkdir -p "$SNAPS"; before=$(ls -t "$SNAPS" 2>/dev/null | head -1)
wtype -P F8 -s 300 -p F8
for i in $(seq 1 20); do
  timeout 0.3 tail -f /dev/null
  new=$(ls -t "$SNAPS" | head -1); [ -n "$new" ] && [ "$new" != "$before" ] && break
done
f="$SNAPS/$(ls -t "$SNAPS" | head -1)"; prev=-1
for i in $(seq 1 20); do               # wait until PCSX2 has finished writing the PNG
  timeout 0.3 tail -f /dev/null; size=$(stat -c %s "$f"); [ "$size" = "$prev" ] && break; prev=$size
done
cp "$f" "$1"
