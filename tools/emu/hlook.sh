#!/bin/bash
# hlook.sh out.png key ... : hpress.sh, then save state slot 9 and list the text widgets
# whose English is wider than their box (tools/dev/widgets.py)
D=$(cd "$(dirname "$0")" && pwd); PY="$D/../../.venv/bin/python"
"$D/hpress.sh" "$@"
rm -f "$D/../../build/pcsx2h/PCSX2/sstates/"*.09.p2s
"$PY" "$D/pine.py" save 9
last=-1
for i in $(seq 1 40); do
  timeout 0.5 tail -f /dev/null
  f=$(ls "$D/../../build/pcsx2h/PCSX2/sstates/"*.09.p2s 2>/dev/null | head -1)
  [ -n "$f" ] || continue
  s=$(stat -c %s "$f"); [ "$s" = "$last" ] && break; last=$s
done
"$PY" "$D/../dev/widgets.py" 9 ${MIN:+--min=$MIN}
