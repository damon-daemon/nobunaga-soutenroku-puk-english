#!/bin/bash
# usage: press.sh out.png key ...   keys: X=Circle(confirm) Z=Cross(cancel) S=Triangle A=Square
#   Return=Start BackSpace=Select Q/W=L1/R1 Up/Down/Left/Right; 'w' alone = wait 1s
#   out.png = /dev/null for no screenshot
CLASS=$(hyprctl clients -j | python3 -I -c "import json,sys; print([w['class'] for w in json.load(sys.stdin) if w['class'] == 'AppRun' or 'pcsx2' in w['class'].lower()][0])")
hyprctl dispatch "hl.dsp.focus({ window = \"class:$CLASS\" })" >/dev/null
timeout 0.3 tail -f /dev/null
if ! hyprctl activewindow -j | grep -q "\"class\": \"$CLASS\""; then echo "focus is not on $CLASS; aborting" >&2; exit 1; fi
for k in "${@:2}"; do
  if [ "$k" = w ]; then timeout 1 tail -f /dev/null; continue; fi
  hyprctl activewindow -j | grep -q "\"class\": \"$CLASS\"" || { echo "focus lost; aborting" >&2; exit 1; }
  case "$k" in X|Z|S|A|Q|W) k=${k,,};; esac
  wtype -P "$k" -s 300 -p "$k"; timeout 0.4 tail -f /dev/null
done
timeout 0.5 tail -f /dev/null
[ "$1" = /dev/null ] || $(dirname "$0")/shot.sh "$1"
