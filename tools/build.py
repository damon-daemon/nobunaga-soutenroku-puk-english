"""Rebuild the disc image with the translation and produce a patch.

usage: .venv/bin/python tools/build.py [clean.iso] [out.iso]
"""
import os, subprocess, sys

sys.path.insert(0, os.path.dirname(__file__))
import elfseg, elfstr, gfx, iso, nameentry, namehook, names, scenarios, uifix, vwf, msgbuf, msgfile, nbx, overflow, setup, tl

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'build', 'nobunaga_soutenroku_puk_en.iso')
OVERLAYS = ('SEIRYAKU.BIN', 'GUNRYAKU.BIN')
FIXED = (nbx.NAME,) + OVERLAYS          # must stay where they are (patch size; overlays can't grow)

def elfstr_keys():
    """Debug build (env ELFSTR_KEYS=1): every translated ELF/overlay string shows its own key
    (e3bf278 ...) to find which entry a label on screen comes from. None = normal build."""
    if not os.environ.get('ELFSTR_KEYS'):
        return None
    rows = elfstr.rows()
    en = elfstr.resolved(elfstr.load_tl(), rows)
    room = {r['key']: r['room'] for r in rows}
    # format strings keep their English (conversions must match); keys that don't fit a slot
    # that can't move (ambiguous overlay addresses) keep their English too
    return {k: (v if '%' in v or room.get(k, 99) < len(k) else k) for k, v in en.items()}

def build_files(clean, recs):
    """{iso name: bytes} of every rebuilt file."""
    elf = bytearray(iso.read_file(clean, iso.ELF_NAME, recs))
    archive = iso.read_file(clean, nbx.NAME, recs)
    ovl = {name: bytearray(iso.read_file(clean, name, recs)) for name in OVERLAYS}
    clean_code = (bytes(elf),) + tuple(bytes(ovl[n]) for n in OVERLAYS)
    seg = elfseg.Segment()
    msgbuf.apply(elf)
    widths, shorten = vwf.apply(elf, seg)
    nameentry.apply(elf, seg, widths)
    uifix.apply(elf, seg)
    try:
        nstr, moved = elfstr.apply(elf, ovl[OVERLAYS[0]], ovl[OVERLAYS[1]], clean_code, seg, elfstr_keys())
    except ValueError as e:
        sys.exit('elfstr:\n%s' % e)
    uifix.apply_late(elf, seg)
    scens = [nbx.entry(archive, elf, k) for k in names.SCENARIOS]
    try:
        ents, _ = namehook.apply(elf, clean_code[0], {'s': ovl[OVERLAYS[0]], 'g': ovl[OVERLAYS[1]]}, seg, scens, shorten)
    except (ValueError, AssertionError) as e:
        sys.exit('namehook: %s' % e)
    bad = namehook.check_lengths(ents)
    if bad:
        sys.exit('namehook:\n%s' % '\n'.join(bad[:20]))
    changes = {vwf.ENTRY: vwf.sheet(nbx.entry(archive, elf, vwf.ENTRY))}    # NB10 entry -> bytes
    scen_en = [bytearray(s) for s in scens]
    changes[scenarios.PREVIEW], missing = scenarios.apply(
        scen_en, nbx.entry(archive, elf, scenarios.PREVIEW), namehook.build_table(clean_code[0], scens))
    changes.update({k: bytes(s) for k, s in zip(names.SCENARIOS, scen_en)})
    try:
        tex = gfx.apply(lambda k: nbx.entry(archive, elf, k))
    except (ValueError, AssertionError) as e:
        sys.exit('gfx: %s' % e)
    assert not set(tex) & set(changes), set(tex) & set(changes)
    changes.update(tex)
    english, bad = tl.build_all(quiet=True)
    if bad:
        sys.exit('tl/ has %d errors (run tools/tl.py check)' % len(bad))
    for n in msgfile.BLOCKS:
        if english[n]:
            changes[n] = tl.block_bytes(n, english[n])
    growth = sum(len(changes[n]) - nbx.toc(elf)[n][1] for n in changes)
    if growth > overflow.HEAP_GROWTH:
        sys.exit('message blocks grew by %d bytes > %d (heap budget, overflow.py)' % (growth, overflow.HEAP_GROWTH))
    archive = nbx.apply(archive, elf, changes)
    heap = elfseg.apply(elf, seg)
    print('elfstr %d strings (%d moved); %d name keys; segment %d bytes, heap starts at %#x' % (nstr, moved, len(ents), len(seg.data), heap))
    files = {iso.ELF_NAME: bytes(elf), nbx.NAME: archive}
    for name in OVERLAYS:
        assert len(ovl[name]) == len(clean_code[1 + OVERLAYS.index(name)])
        files[name] = bytes(ovl[name])
    return files

def write(clean, out, files):
    """Write the image, check it and make the xdelta patch next to it."""
    os.makedirs(os.path.dirname(out), exist_ok=True)
    moved = iso.write_image(clean, out, files)
    print('rebuilt %s%s' % (out, ' (moved: %s)' % ', '.join(moved) if moved else ''))
    if set(moved) & set(FIXED):
        sys.exit('%s moved on the disc: make it smaller' % ', '.join(set(moved) & set(FIXED)))
    files = dict(files)
    files[iso.ELF_NAME] = iso.read_file(out, iso.ELF_NAME)     # with the patched LBA table
    iso.verify(out, files)
    patch = os.path.splitext(out)[0] + '.xdelta'
    try:
        subprocess.run(['xdelta3', '-e', '-f', '-9', '-S', 'djw', '-B', str(1 << 30), '-s', clean, out, patch], check=True)
        print('patch %s (%d bytes)' % (patch, os.path.getsize(patch)))
    except FileNotFoundError:
        print('xdelta3 not installed; skipped patch')
    return moved

def main():
    clean = sys.argv[1] if len(sys.argv) > 1 else setup.CLEAN
    out = sys.argv[2] if len(sys.argv) > 2 else OUT
    files = build_files(clean, iso.records(clean))
    write(clean, out, files)

if __name__ == '__main__':
    main()
