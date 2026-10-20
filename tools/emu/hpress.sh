#!/bin/bash
# hpress.sh out.png key ... : press.sh for the headless PCSX2 (virtual pad, no desktop input)
#   keys: X=Circle(confirm) Z=Cross(cancel) S=Triangle A=Square Return=Start BackSpace=Select
#   Q/W=L1/R1 Up/Down/Left/Right; 'w' alone = wait 1s; out.png = /dev/null for no screenshot
D=$(cd "$(dirname "$0")" && pwd); PY="$D/../../.venv/bin/python"
for k in "${@:2}"; do
  case "$k" in
    w) timeout 1 tail -f /dev/null; continue;;
    X) b=Circle;; Z) b=Cross;; S) b=Triangle;; A) b=Square;; Return) b=Start;; BackSpace) b=Select;;
    Q) b=L1;; W) b=R1;; *) b=$k;;
  esac
  "$PY" "$D/vpad.py" hold "$b" 250 >/dev/null; timeout 0.3 tail -f /dev/null
done
timeout 0.5 tail -f /dev/null
[ "$1" = /dev/null ] || "$D/hshot.sh" "$1"
