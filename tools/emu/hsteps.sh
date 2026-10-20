#!/bin/bash
# hsteps.sh sheet.png N [key] : N times (press key (default X = Circle), wait 3 s, screenshot),
# then a contact sheet of the N screenshots (4 per row, 320x224 each)
D=$(cd "$(dirname "$0")" && pwd); PY="$D/../../.venv/bin/python"
tmp=$(mktemp -d)
for i in $(seq -w 1 "$2"); do
  "$D/hpress.sh" /dev/null "${3:-X}"; timeout 3 tail -f /dev/null
  "$D/hshot.sh" "$tmp/$i.png"
done
"$PY" - "$1" "$tmp" <<'PY'
import glob, sys
from PIL import Image
fs = sorted(glob.glob(sys.argv[2] + '/*.png'))
rows = (len(fs) + 3) // 4
im = Image.new('RGB', (320 * 4, 224 * rows))
for k, f in enumerate(fs):
    im.paste(Image.open(f).convert('RGB').resize((320, 224)), ((k % 4) * 320, (k // 4) * 224))
im.save(sys.argv[1])
PY
cp "$tmp"/*.png "$(dirname "$1")/" 2>/dev/null; rm -rf "$tmp"
