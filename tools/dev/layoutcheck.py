"""Static check of UI layout records against the English (phase 6d).

Layout records (0x1C bytes: text ptr, flags 0x20-0x2F, 0, x | y << 16, w | h << 16, style,
colour) in the ELF and both overlays give the box of a label. A label wider than its box is
squeezed to fit (vwf.SQUEEZE); this lists the records whose English is squeezed below a ratio.

usage: .venv/bin/python tools/dev/layoutcheck.py [min %, default 80] [--all]
"""
import os, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import elfstr, vwf

def records():
    """[(tag, record vaddr, text vaddr, x, y, w, h)]"""
    out = []
    for tag, data, base in zip('esg', elfstr.clean_files(), (0x100000 - 0x800, 0x198A000, 0x198A000)):
        lo = 0x800 if tag == 'e' else 0x80
        for o in range(lo, len(data) - 0x1C, 4):
            p, fl, z, xy, wh = struct.unpack_from('<5I', data, o)
            w, h = wh & 0xFFFF, wh >> 16
            if z or not 0x20 <= fl <= 0x2F or not (4 <= w <= 640 and 4 <= h <= 448):
                continue
            if not (base + lo <= p < base + len(data)):
                continue
            out.append((tag, o + base, p, xy & 0xFFFF, xy >> 16, w, h))
    return out

def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    limit = int(args[0]) if args else 80
    W = vwf.widths()
    rows = {r['key']: r for r in elfstr.rows()}
    tl = elfstr.resolved(elfstr.load_tl(), list(rows.values()))
    seen = set()
    out = []
    for tag, rec, p, x, y, w, h in records():
        key = '%s%x' % (tag, p)
        en = tl.get(key)
        if not en:
            continue
        px = max(sum(W[ord(c)] for c in line) for line in en.split('\n'))
        ratio = 100 * w // max(px, 1)
        if ratio < limit or ('--all' in sys.argv and px > w):
            out.append((ratio, key, rec, x, y, w, px, en, rows[key]['jp'] if key in rows else ''))
    for ratio, key, rec, x, y, w, px, en, jp in sorted(out):
        print('%3d%% %-9s rec %x  %3d,%3d w %3d  en %3d  %s  (%s)' % (ratio, key, rec, x, y, w, px, en.replace('\n', '|'), jp))
    print(len(out), 'records')

if __name__ == '__main__':
    main()
