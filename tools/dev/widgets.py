"""List the text widgets of a PCSX2 save state and flag text wider than its box.

usage: .venv/bin/python tools/dev/widgets.py SLOT|state.p2s [--all] [--min=80]
  SLOT = slot number of the English build in build/pcsx2h (newest state with that slot).
Text widgets = objects with vtable 0x447440 (x +4, y +8, w +0xC, h +0x10, text CString +0x60);
buttons = vtable 0x4476F0 (text +0xBC, the frame is about w - w/8: vwf.SQUEEZE margin), marked [btn].
Width = VWF width (vwf.widths) of the longest line; SJIS = 22 px. Prints OVER rows only unless --all.
Key-mode builds (ELFSTR_KEYS=1 tools/build.py): keys are measured as their English.
Live objects only roughly: freed widgets stay in RAM, so check the screen too.
"""
import glob, os, struct, sys, zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import elfstr, re, vwf

VTABLES = {0x447440: (0x60, 0), 0x4476F0: (0xBC, 8)}    # vtable: (text CString, margin)
MIN = next((int(a[6:]) for a in sys.argv if a.startswith('--min=')), 1000)   # only rows squeezed below MIN %

def ee_memory(arg):
    if arg.isdigit():
        states = glob.glob(os.path.join(ROOT, 'build/pcsx2h/PCSX2/sstates/SLPM-65455 (*).%02d.p2s' % int(arg)))
        arg = max(states, key=os.path.getmtime)
    with zipfile.ZipFile(arg) as z:          # zstd members: Python >= 3.14
        return z.read('eeMemory.bin')

def width(b, W):
    best = x = 0
    i = 0
    while i < len(b):
        c = b[i]
        if c == 0x0A:
            x = 0; i += 1
        elif c == 0x1B:
            x += 22 if i + 1 < len(b) and b[i + 1] == 0x50 else 0
            i += 3
        elif (0x81 <= c <= 0x9F or 0xE0 <= c <= 0xFC) and i + 1 < len(b):
            x += 22; i += 2
        else:
            x += W[c]; i += 1
        best = max(best, x)
    return best

def main():
    m = ee_memory(sys.argv[1])
    W = vwf.widths()
    rows = elfstr.rows()
    en = elfstr.resolved(elfstr.load_tl(), rows)     # key-mode builds (ELFSTR_KEYS=1) show keys
    for vtable, (field, margin) in VTABLES.items():
        vt = struct.pack('<I', vtable)
        i = m.find(vt)
        while i >= 0:
            if i % 4 == 0:
                x, y, w, h = struct.unpack_from('<4i', m, i + 4)
                w -= w // 8 if margin == 8 else margin
                p = struct.unpack_from('<I', m, i + field)[0]
                t = b''
                if 0 < p < len(m):
                    t = m[p:m.find(b'\0', p, p + 512)]
                key = t.decode('ascii', 'replace')
                if re.fullmatch('[esg][0-9a-f]{6,7}', key) and key in en:
                    t = en[key].encode('ascii') + b'  [' + t + b']'
                    px = width(en[key].encode('ascii'), W)
                else:
                    px = width(t, W)
                over = px > w
                if t and (over or '--all' in sys.argv) and 100 * w // max(px, 1) < MIN:
                    try:
                        s = t.decode('cp932')
                    except UnicodeDecodeError:
                        s = repr(t)
                    print('%08x %3d,%3d %3dx%-3d %4d %3d%% %s %s%s' % (i, x, y, w, h, px, 100 * w // max(px, 1),
                          'OVER' if over else '    ', s.replace('\n', '|'), ' [btn]' if margin else ''))
            i = m.find(vt, i + 1)

if __name__ == '__main__':
    main()
