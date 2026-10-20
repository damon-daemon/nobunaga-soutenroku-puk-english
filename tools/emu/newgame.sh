#!/bin/bash
# newgame.sh out.png : from the main menu, start a new game (first scenario,
# first hero, default settings) up to the "game begins" message (msg21 #32)
D=$(dirname "$0")
$D/press.sh /dev/null X w w X w w X w w w X w w w X w w X w w w w || exit 1
$D/press.sh /dev/null w w w w w w Down Down Down Down Down Down Down X || exit 1
timeout 10 tail -f /dev/null
$D/shot.sh "$1"
