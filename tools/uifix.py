"""Layout fixes for English found in the emulator pass (phase 6d).

Status bar (council hall / map, 0x211050): the year widget (x 24, 88 px) shows "1534" and
the season widget (x 125) is one kanji wide (22 px), so an English season would be squeezed
to nothing. The season sprintf (0x211234) is replaced by a stub that writes
"<season> <year>" into the year text and leaves the season text empty.
The year box clips at 88 px whatever its width field says (fixed when the widget is created),
so the season is abbreviated here (SEASONS; v1 = season index * 4 at the call). In the era-name mode
the year text is "%s%s" (era, year): it becomes "%s %s".
"""
import os, struct, sys

sys.path.insert(0, os.path.dirname(__file__))
import elfseg
from asm import assemble, hi, lo

SPRINTF = 0x22AB00                       # CString printf(CString *dst, fmt, ...)
STATUS_SEASON = 0x211234                 # jal SPRINTF (a0 = sp+0x2F8 season, a1 "%s", a2 season)
SEASONS = (b'Spr.', b'Sum.', b'Aut.', b'Win.')    # status bar only (box clips at 88 px)
STATUS_ERA = (0x2111C4, 0x2111D4)        # lui a1, 0x3F / addiu a1, a1, -0x1F0 ("%s%s")

def word(elf, va):
    return struct.unpack_from('<I', elf, va - elfseg.VBASE + elfseg.FOFF)[0]

# half-width katakana strings (the elfstr export only takes full-width Japanese): in place
HALFWIDTH = {0x3C2508: (b'\xbf\xb0\xc4', b'Sort'), 0x3C2510: (b'\xcd\xd9\xcc\xdf', b'Help')}   # key guide, 8-byte slots

# pointer words to strings the elfstr export skips (icon codes): repointed to English in the segment
REPOINT = {0x4D9A00: (0x3C2518, b'+\x1bPUPage')}       # key guide "+(D-pad) 頁"

# lui/addiu pairs (a1) of strings shared by two commands: these references get their own English
# (after elfstr, which repoints every reference of a moved string). 軍事 = Diplomacy > Alliance in
# the command tables, but the main-bar command at these sites is Military.
SPLIT = {(0x4162D4, 0x4162E0): b'Military', (0x41823C, 0x418248): b'Military'}
SPLIT_WORDS = {0x3A0A0C: (0x3EC2B0, b'Military')}       # help reference table: the Military topic

# command bar breadcrumb (notes/survey/breadcrumb_re.md): Create 0x28A910 sizes the label widgets through a
# jump table (0x3F1D20, by element type): types 6/7 = level 1/2 labels, 88 x 22 (0x28AD08). Level 1 sits at
# x 16 on a 72 px tab, level 2 at x 76 on a tab ending at ~150: narrower boxes make vwf.SQUEEZE fit them.
CRUMB_TABLE, CRUMB_88, CRUMB_DONE = 0x3F1D20, 0x28AD08, 0x28AD54
CRUMB_W = {6: 56, 7: 72}

def apply(elf, seg):
    for at, (old, new) in REPOINT.items():
        assert word(elf, at) == old, 'pointer %x changed' % at
        elfseg.patch(elf, at, struct.pack('<I', seg.add(new + b'\0')))
    for t, w in CRUMB_W.items():
        assert word(elf, CRUMB_TABLE + 4 * t) == CRUMB_88 and word(elf, CRUMB_88) == 0x24030058, 'breadcrumb sizes changed'
        code = [('addiu', 'v1', 'zero', w), ('addiu', 'v0', 'zero', 22), ('sw', 'v1', 0x618, 'sp'),
                ('j', CRUMB_DONE), ('sw', 'v0', 0x61C, 'sp')]
        at = seg.reserve(4 * len(code))
        seg.put(at, assemble(at, code))
        elfseg.patch(elf, CRUMB_TABLE + 4 * t, struct.pack('<I', at))
    for va, (old, new) in HALFWIDTH.items():
        o = va - elfseg.VBASE + elfseg.FOFF
        assert elf[o:o + 8] == old.ljust(8, b'\0') and len(new) < 8, 'half-width string %x changed' % va
        elf[o:o + 8] = new.ljust(8, b'\0')
    assert word(elf, STATUS_SEASON) == 0x0C000000 | SPRINTF >> 2, 'status bar season changed'
    assert (word(elf, STATUS_ERA[0]), word(elf, STATUS_ERA[1])) == (0x3C05003F, 0x24A5FE10), 'status bar era changed'
    two = seg.add(b'%s %s\0')
    one = seg.add(b'%s\0')
    empty = seg.add(b'\0')
    lui, addiu = assemble(STATUS_ERA[0], [('lui', 'a1', hi(two))]), assemble(STATUS_ERA[1], [('addiu', 'a1', 'a1', lo(two))])
    elfseg.patch(elf, STATUS_ERA[0], lui)
    elfseg.patch(elf, STATUS_ERA[1], addiu)
    short = seg.add(b''.join(struct.pack('<I', 0) for _ in SEASONS))
    seg.put(short, b''.join(struct.pack('<I', seg.add(t + b'\0')) for t in SEASONS))
    code = [
        ('sltiu', 'at', 'v1', 4 * len(SEASONS)),
        ('beqz', 'at', 'keep'),
        ('lui', 'at', hi(short)),
        ('addu', 'at', 'at', 'v1'),
        ('lw', 'a2', lo(short), 'at'),
        'keep:',
        ('addiu', 'sp', 'sp', -16),
        ('sd', 'ra', 0, 'sp'),
        ('sw', 'a0', 8, 'sp'),
        # season CString = "<season> <year>" (a2 = season; year chars at caller sp+0x2FC = a0+4)
        ('lw', 'a3', 4, 'a0'),
        ('lui', 'a1', hi(two)),
        ('jal', SPRINTF),
        ('addiu', 'a1', 'a1', lo(two)),
        # year CString = that text
        ('lw', 'a0', 8, 'sp'),
        ('lw', 'a2', 0, 'a0'),
        ('addiu', 'a0', 'a0', 4),
        ('lui', 'a1', hi(one)),
        ('jal', SPRINTF),
        ('addiu', 'a1', 'a1', lo(one)),
        # season CString = ""
        ('lw', 'a0', 8, 'sp'),
        ('lui', 'a1', hi(empty)),
        ('jal', SPRINTF),
        ('addiu', 'a1', 'a1', lo(empty)),
        ('ld', 'ra', 0, 'sp'),
        ('jr', 'ra'),
        ('addiu', 'sp', 'sp', 16)]
    at = seg.reserve(4 * len([c for c in code if not isinstance(c, str)]))
    seg.put(at, assemble(at, code))
    elfseg.patch(elf, STATUS_SEASON, assemble(STATUS_SEASON, [('jal', at)]))

# help reference tree (0x3A0630, 379 x 16 B: s16 id = index, s16 parent, u32 block 39 page, REF name ptr,
# label ptr). Records are found by id (table + 16 * id); a menu lists the children of a node in table order
# (0x1DAA50). The glossary (node 0xF4) groups its terms by kana row (あ行 ...): the terms are re-sorted by
# English label into the term slots and the 9 row nodes become letter ranges. The REF name -> id map is built
# from the table at run time (0x1D6E50), so links follow their term.
HELP_TABLE, HELP_N, GLOSSARY = 0x3A0630, 379, 0xF4

def cstr(elf, seg, va):
    if va >= seg.base:
        d, o = seg.data, va - seg.base
    else:
        d, o = elf, va - elfseg.VBASE + elfseg.FOFF
    return bytes(d[o:d.index(b'\0', o)])

def glossary(elf, seg):
    rec = lambda i: HELP_TABLE + 16 * i
    par = lambda i: struct.unpack('<hh', elf[rec(i) - elfseg.VBASE + elfseg.FOFF:][:4])
    groups = [i for i in range(HELP_N) if par(i) == (i, GLOSSARY)]
    slots = [i for i in range(HELP_N) if par(i)[1] in groups]
    terms = sorted((tuple(word(elf, rec(i) + k) for k in (4, 8, 12)) for i in slots),
                   key=lambda t: cstr(elf, seg, t[2]).lower())
    labels = [cstr(elf, seg, t[2]) for t in terms]
    assert all(l[:1].isalpha() and l.isascii() for l in labels), 'glossary label not English: %r' % labels
    # cut the sorted list at letter changes into len(groups) runs of about equal size
    firsts = [l[:1].upper() for l in labels]
    cuts, n = [0], len(labels)
    for g in range(1, len(groups)):
        want = round(g * n / len(groups))
        cands = [k for k in range(cuts[-1] + 1, n) if firsts[k] != firsts[k - 1]]
        cuts.append(min(cands, key=lambda k: abs(k - want)))
    cuts.append(n)
    for g, node in enumerate(groups):
        a, b = firsts[cuts[g]], firsts[cuts[g + 1] - 1]
        elfseg.patch(elf, rec(node) + 12, struct.pack('<I', seg.add((a if a == b else a + b'-' + b) + b'\0')))
        for k in range(cuts[g], cuts[g + 1]):
            elfseg.patch(elf, rec(slots[k]), struct.pack('<hhIII', slots[k], node, *terms[k]))

def apply_late(elf, seg):
    """SPLIT, SPLIT_WORDS, glossary: after elfstr.apply."""
    glossary(elf, seg)
    for at, (jp, en) in SPLIT_WORDS.items():
        assert word(elf, at) == jp or word(elf, at) >= elfseg.BASE, 'split word %x changed' % at   # elfstr may have moved it
        elfseg.patch(elf, at, struct.pack('<I', seg.add(en + b'\0')))
    for (lui_va, add_va), en in SPLIT.items():
        a, b = word(elf, lui_va), word(elf, add_va)
        assert a >> 16 == 0x3C05 and b >> 16 == 0x24A5, 'split pair %x changed' % lui_va
        at = seg.add(en + b'\0')
        elfseg.patch(elf, lui_va, assemble(lui_va, [('lui', 'a1', hi(at))]))
        elfseg.patch(elf, add_va, assemble(add_va, [('addiu', 'a1', 'a1', lo(at))]))
