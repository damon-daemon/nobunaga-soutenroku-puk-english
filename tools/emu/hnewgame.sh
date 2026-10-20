#!/bin/bash
# hnewgame.sh image.iso out.png : headless boot -> new game, scenario 1 (1534), first lord
# (Ashikaga), default settings, through the opening event to the council hall (~2 min)
D=$(cd "$(dirname "$0")" && pwd)
"$D/headless.sh" stop >/dev/null; timeout 2 tail -f /dev/null
"$D/headless.sh" "$1"
for i in $(seq 20); do [ -S "$XDG_RUNTIME_DIR/nobu-vpad.sock" ] && break; timeout 1 tail -f /dev/null; done
timeout 35 tail -f /dev/null
"$D/hpress.sh" /dev/null Return w w w Return w w w X w w w X w w w X w w w
"$D/hpress.sh" /dev/null Down Down Down Down Down X
timeout 25 tail -f /dev/null
for i in $(seq 16); do "$D/hpress.sh" /dev/null X w w; done
timeout 5 tail -f /dev/null
"$D/hshot.sh" "$2"
