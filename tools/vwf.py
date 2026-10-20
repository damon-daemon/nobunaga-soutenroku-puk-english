"""Proportional Latin text (VWF): new half-width glyphs and the advances that use them.

The game has one text size (22 px rows). Half-width characters (0x20-0x7F, 0xA2-0xDF)
come from one 176x352 4bpp sheet, NB10 entry 36 object 3023: cell = code, 11x22
(x0 = (code & 15) * 11, y0 = (code >> 4) * 22); the label draw loop always advances 11.
The glyph palette (objects 3024-3032, one per text colour, chosen by code) is a ramp
with a baked drop shadow: 0 clear, 1/2/3 black shadow (alpha), 4/5 dark shadow,
6-F body from dark to white.

Changes:
- sheet cells 0x20-0x7E are redrawn with tools/latinfont.py ('msg', ink from column 0)
  plus a drop shadow; kana cells stay; size and palettes unchanged (in-place patch);
- W = 256-byte width table in the English segment: Latin = latinfont advance, kana and
  SJIS lead bytes 11 (lead + trail = 22), control bytes 0;
- label draw 0x2497A0: the half-width advance (0x24988C `b 0x249994` / 0x249890
  `addiu s1,s1,11`, code in s6) jumps to a stub adding W[code]; the bounding box
  (+0x28, used to centre and size labels) follows from s1;
- rich-text layout 0x26E5B0 (help pages): `addiu s4,s4,11` per byte at 0x26E708
  (byte at s1; s4 = x used for link-button positions and auto-wrap) becomes a call to
  a stub adding W[byte]; the SJIS trail +11 at 0x26E724 stays.
- text measures (notes/survey/label_scale.md): a label is shown inside a view whose size
  comes from a measure at 11 px per byte, and the view scales the label's bbox to it
  (labels looked stretched 1.38x). 0x22E8A0 (out[2] = width, lines * 22; 14 callers incl.
  the text widget SetText path) and 0x2637F0 (key-guide bar: units, callers * 11) are
  replaced by stubs measuring like the label loop (1B P x = 22, other 1B y z = 0, SJIS
  pair 22, else W[byte]); the guide bar callers drop their * 11.
- text wider than its widget box / list column (SQUEEZE, LIST_SQUEEZE) is squeezed to fit;
  text widgets and list cells first try its short form (namehook 'W', via SHORTEN).
""" 
import os, struct, sys

sys.path.insert(0, os.path.dirname(__file__))
import elfseg, latinfont
from asm import assemble, hi, lo

ENTRY, SHEET = 36, 3023
CELL_W, CELL_H, SHEET_W = 11, 22, 176
LABEL_ADV, LABEL_DONE = 0x24988C, 0x249994
RICH_ADV = 0x26E708
BODY = [0x6, 0x7, 0x8, 0xA, 0xC, 0xD, 0xE, 0xF]      # by brightness (palette 3024)
SHADOW_OFFSETS = ((1, 2), (2, 1), (2, 2), (3, 2))    # (dx, dy) of the drop shadow
TRIM_LEFT = {'j': 2}

def obj_offset(entry, i):
    """Byte offset of object i of a pack-table entry."""
    return struct.unpack_from('<I', entry, 8 * i)[0]

def glyph_cells():
    """{code: [[index]]} 11x22 palette indices of the new Latin glyphs, and {code: advance}."""
    font = latinfont.render('msg')
    top = latinfont.SIZES['msg'][5]
    cells, adv = {}, {}
    for c, (rows, a) in font.items():
        if c in TRIM_LEFT:
            # the descender hook of j sits 3 px left of the stem: a gap after the previous letter
            # ('Ho jo'); keep a short hook and move the glyph left
            n = TRIM_LEFT[c]
            rows, a = [r[n:] + [0] * n for r in rows], a - n
        # column 0 stays blank: a sprite also samples one texel of the next cell, so ink
        # in column 0 showed as a bar after the previous cell's glyph ('h' + space -> 'h|').
        # Shifting every glyph keeps the spacing (only the first glyph moves 1 px).
        b = [[0] + [v / top for v in r[:-1]] for r in rows]
        out = []
        for y in range(CELL_H):
            row = []
            for x in range(CELL_W):
                v = b[y][x]
                s = max((b[y - dy][x - dx] for dx, dy in SHADOW_OFFSETS if y - dy >= 0 and x - dx >= 0), default=0)
                if v >= 0.5:
                    i = BODY[min(len(BODY) - 1, 2 + int((v - 0.5) / 0.5 * (len(BODY) - 2)))]
                elif v >= 0.25 and s < 0.3:
                    i = BODY[1]
                elif s >= 0.6:
                    i = 0x5
                elif s >= 0.3 or v >= 0.25:
                    i = 0x3 if s < 0.45 else 0x4
                elif s >= 0.1 or v >= 0.1:
                    i = 0x1
                else:
                    i = 0
                row.append(i)
            out.append(row)
        cells[ord(c)] = out
        adv[ord(c)] = a
    return cells, adv

def widths():
    """256-byte advance table."""
    _, adv = glyph_cells()
    t = bytearray(256)
    for c, a in adv.items():
        t[c] = a
    for c in list(range(0xA2, 0xE0)) + list(range(0x81, 0xA0)) + list(range(0xE0, 0xFD)):
        t[c] = CELL_W
    return bytes(t)

def sheet(entry):
    """Entry 36 bytes with the Latin cells of the half-width sheet redrawn."""
    e = bytearray(entry)
    o = obj_offset(e, SHEET)
    assert e[o:o + 4] == b'N9GD' and e[o + 0x30:o + 0x34] == b'TIM2'
    assert struct.unpack_from('<HH', e, o + 0x30 + 16 + 0x14) == (SHEET_W, 352)
    img = o + 0x70
    cells, _ = glyph_cells()
    for code, rows in cells.items():
        x0, y0 = (code & 15) * CELL_W, (code >> 4) * CELL_H
        for y, row in enumerate(rows):
            for x, v in enumerate(row):
                p = (y0 + y) * SHEET_W + x0 + x
                k = img + p // 2
                e[k] = (e[k] & 0x0F) | (v << 4) if p & 1 else (e[k] & 0xF0) | v
    assert len(e) == len(entry)
    return bytes(e)

def _measure(table, p, x, mx, c, t1, t2, lines=None):
    """Shared loop text: p ptr, x line width, mx max, c byte, t1/t2 temps; lines optional."""
    L = lambda s: s + ('_l' if lines else '_b')
    out = [
        ('addu', x, 'zero', 'zero'), ('addu', mx, 'zero', 'zero')]
    if lines: out += [('addu', lines, 'zero', 'zero'), ('lbu', c, 0, p), ('beqz', c, L('done')), ('nop',)]
    out += [
        L('loop') + ':',
        ('lbu', c, 0, p),
        ('beqz', c, L('eol')),
        ('addiu', t1, 'zero', 0x0A),
        ('beq', c, t1, L('newline')),
        ('addiu', t1, 'zero', 0x1B),
        ('beq', c, t1, L('esc')),
        ('sltiu', t1, c, 0x81),
        ('bnez', t1, L('single')),
        ('sltiu', t1, c, 0xA0),
        ('bnez', t1, L('lead')),
        ('sltiu', t1, c, 0xE0),
        ('bnez', t1, L('single')),
        ('sltiu', t1, c, 0xFD),
        ('beqz', t1, L('single')),
        ('nop',),
        L('lead') + ':',
        ('lbu', t2, 1, p),
        ('sltiu', t1, t2, 0x40),
        ('bnez', t1, L('single')),
        ('sltiu', t1, t2, 0xFD),
        ('beqz', t1, L('single')),
        ('addiu', t1, 'zero', 0x7F),
        ('beq', t2, t1, L('single')),
        ('nop',),
        ('addiu', x, x, 22),
        ('b', L('loop')),
        ('addiu', p, p, 2),
        L('single') + ':',
        ('lui', t1, hi(table)),
        ('addu', t1, t1, c),
        ('lbu', t1, lo(table), t1),
        ('addu', x, x, t1),
        ('b', L('loop')),
        ('addiu', p, p, 1),
        L('esc') + ':',
        ('lbu', t2, 1, p),
        ('addiu', t1, 'zero', 0x50),
        ('bne', t2, t1, L('loop')),
        ('addiu', p, p, 3),
        ('b', L('loop')),
        ('addiu', x, x, 22),
        L('newline') + ':',
        ('sltu', t1, mx, x),
        ('movn', mx, x, t1)]
    if lines: out += [('addiu', lines, lines, 1)]
    out += [
        ('addiu', p, p, 1),
        ('lbu', c, 0, p),
        ('bnez', c, L('loop')),
        ('addu', x, 'zero', 'zero'),
        ('b', L('done')),
        ('nop',),
        L('eol') + ':',
        ('sltu', t1, mx, x),
        ('movn', mx, x, t1)]
    if lines: out += [('addiu', lines, lines, 1)]
    out += [L('done') + ':']
    return out


MEASURE_A, MEASURE_B = 0x22E8A0, 0x2637F0
# jal MEASURE_A sites of widget layouts (widget register, margin px): text widget relayout
# 0x23D290 (s3), button-like widget 0x234760 (s4, box - 4, two measures), button 0x23E4A0 (s3,
# vtable 0x4476F0: its frame is narrower than the box: margin 8 = box / 8, 74 -> 65, 46 -> 41)
PROPORTIONAL = {8}                   # margins that mean box / margin
# text widgets also swap a too-wide text for its short form (namehook 'W': court titles, offices,
# treasures) through SHORTEN(a0 CString*) -> v0 1 if replaced; CString field of the widget (or None)
SQUEEZE = [(0x23D324, 's3', 0, 0x60), (0x234788, 's4', 4, None), (0x23486C, 's4', 4, None), (0x23E4DC, 's3', 8, 0xBC)]
# list row layouts (fixed / scrolling columns): jal GetWidth sites, text area in fp / 0xC0(sp)
GET_WIDTH = 0x243760
LIST_SQUEEZE = [(0x23339C, 'fp'), (0x233ACC, 0xC0)]
# list cell text creation 0x233D20(row, col): the column width is saved at entry (0x233D4C
# `lw s3, 0x24(a0)`, a1 = col * 4), the cell text (CString at the caller's 0xBC(sp)) is
# shortened at its measure 0x233E6C when wider than the column's text area (width - 8)
CELL_ENTRY, CELL_MEASURE = 0x233D4C, 0x233E6C
# (vaddr, old word, new instruction or None = nop): the guide-bar callers of 0x2637F0 use px
GUIDE = [(0x263C0C, 0x00621021, None), (0x264140, 0x00022080, ('addu', 'a0', 'v0', 'zero')),
         (0x264148, 0x00822021, None), (0x26414C, 0x00042040, None), (0x264150, 0x00822021, None),
         (0x264290, 0x00624021, ('addu', 't0', 'v0', 'zero'))]

def apply(elf, seg):
    """Width table + stubs into the segment, hooks into the ELF. Returns (width table address,
    SHORTEN slot: 8 bytes returning 0 that namehook turns into a jump to its routine)."""
    table = seg.add(widths(), 4)
    shorten = seg.add(assemble(0, [('jr', 'ra'), ('or', 'v0', 'zero', 'zero')]), 4)
    cellw = seg.reserve(4)
    label = seg.add(bytes(24), 4)
    seg.put(label, assemble(label, [
        ('andi', 't9', 's6', 0xFF),
        ('lui', 'at', hi(table)),
        ('addu', 'at', 'at', 't9'),
        ('lbu', 't9', lo(table), 'at'),
        ('j', LABEL_DONE),
        ('addu', 's1', 's1', 't9'),
    ]))
    rich = seg.add(bytes(24), 4)
    seg.put(rich, assemble(rich, [
        ('lbu', 't9', 0, 's1'),
        ('lui', 'at', hi(table)),
        ('addu', 'at', 'at', 't9'),
        ('lbu', 't9', lo(table), 'at'),
        ('jr', 'ra'),
        ('addu', 's4', 's4', 't9'),
    ]))
    def word(va):
        return struct.unpack_from('<I', elf, va - elfseg.VBASE + elfseg.FOFF)[0]
    assert word(LABEL_ADV) == 0x10000041 and word(LABEL_ADV + 4) == 0x2631000B, 'label advance changed'
    assert word(RICH_ADV) == 0x2694000B, 'rich advance changed'
    elfseg.patch(elf, LABEL_ADV, assemble(LABEL_ADV, [('j', label), ('nop',)]))
    elfseg.patch(elf, RICH_ADV, assemble(RICH_ADV, [('jal', rich)]))
    # measures: A may write only a0-a3, t0-t3, v1; B only v0, v1, a0-a3 (callers keep others live)
    code_a = _measure(table, 'a1', 't0', 't1', 'v1', 'a2', 'a3', lines='t2') + [
        ('sll', 'a2', 't2', 4), ('sll', 'a3', 't2', 2), ('addu', 'a2', 'a2', 'a3'),
        ('sll', 'a3', 't2', 1), ('addu', 'a2', 'a2', 'a3'),          # lines * 22
        ('sw', 't1', 0, 'a0'),
        ('jr', 'ra'),
        ('sw', 'a2', 4, 'a0')]
    code_b = _measure(table, 'a0', 'a1', 'v0', 'v1', 'a2', 'a3') + [('jr', 'ra'), ('nop',)]
    for site, old, code in ((MEASURE_A, (0x27BDFFD0, 0xFFBF0010), code_a), (MEASURE_B, (0x0000102D, 0x2406001B), code_b)):
        assert (word(site), word(site + 4)) == old, 'measure %x changed' % site
        at = seg.add(bytes(4 * len([l for l in code if not isinstance(l, str)])), 4)
        seg.put(at, assemble(at, code))
        elfseg.patch(elf, site, assemble(site, [('j', at), ('nop',)]))
    for va, old, ins in GUIDE:
        assert word(va) == old, 'guide bar %x changed' % va
        elfseg.patch(elf, va, assemble(va, [ins or ('nop',)]))
    # widgets whose layout measures the text and places it in their box (+0xC = width): text
    # wider than the box minus the margin is measured as that width, so the view squeezes it to
    # fit instead of clipping it (the Japanese always fits)
    for site, reg, margin, field in SQUEEZE:
        assert word(site) == 0x0C000000 | MEASURE_A >> 2, 'squeeze site %x changed' % site
        less = ([('srl', 'at', 'v1', 3), ('subu', 'v1', 'v1', 'at')] if margin in PROPORTIONAL
                else [('addiu', 'v1', 'v1', -margin)])
        wider = [                   # v0 = measured width > v1 = box - margin > 0, else -> done
            ('lw', 'a0', 8, 'sp'),
            ('lw', 'v0', 0, 'a0'),
            ('lw', 'v1', 0xC, reg)] + less + [
            ('slt', 'at', 'v1', 'v0'),
            ('beqz', 'at', 'done'),
            ('slt', 'at', 'zero', 'v1'),
            ('beqz', 'at', 'done'),
            ('nop',)]
        swap = [] if field is None else [
            ('jal', shorten),
            ('addiu', 'a0', reg, field),
            ('beqz', 'v0', 'clamp'),
            ('lw', 'a0', 8, 'sp'),
            ('lw', 'a1', field, reg),
            ('jal', MEASURE_A),
            ('or', 'a2', 'zero', 'zero')] + wider + [
            'clamp:',
            ('lw', 'a0', 8, 'sp'),
            ('lw', 'v1', 0xC, reg)] + less
        code = [
            ('addiu', 'sp', 'sp', -16),
            ('sd', 'ra', 0, 'sp'),
            ('jal', MEASURE_A),
            ('sw', 'a0', 8, 'sp')] + wider + swap + [
            ('sw', 'v1', 0, 'a0'),
            'done:',
            ('ld', 'ra', 0, 'sp'),
            ('jr', 'ra'),
            ('addiu', 'sp', 'sp', 16)]
        at = seg.reserve(4 * len([c for c in code if not isinstance(c, str)]))
        seg.put(at, assemble(at, code))
        elfseg.patch(elf, site, assemble(site, [('jal', at)]))
    # list rows (notes/survey/list_widget.md): the cell text view's width (GetWidth) is clamped
    # to the column's text area - 8 and written back to the view (+0xC), so the view squeezes
    # the label instead of the clip rect cutting it off. Text area: fp, or 0xC0(sp) of the caller.
    for site, area in LIST_SQUEEZE:
        assert (word(site), word(site + 4)) == (0x0C000000 | GET_WIDTH >> 2, 0), 'list site %x changed' % site
        load = ('addu', 't0', 'fp', 'zero') if area == 'fp' else ('lw', 't0', area, 'sp')
        code = [
            load,
            ('addiu', 't0', 't0', -8),
            ('addiu', 'sp', 'sp', -16),
            ('sd', 'ra', 0, 'sp'),
            ('sw', 'a0', 8, 'sp'),
            ('jal', GET_WIDTH),
            ('sw', 't0', 12, 'sp'),
            ('lw', 'a0', 8, 'sp'),
            ('lw', 't0', 12, 'sp'),
            ('slt', 'at', 't0', 'v0'),
            ('beqz', 'at', 'done'),
            ('slt', 'at', 'zero', 't0'),
            ('beqz', 'at', 'done'),
            ('nop',),
            ('sw', 't0', 0xC, 'a0'),
            ('addu', 'v0', 't0', 'zero'),
            'done:',
            ('ld', 'ra', 0, 'sp'),
            ('jr', 'ra'),
            ('addiu', 'sp', 'sp', 16)]
        at = seg.reserve(4 * len([c for c in code if not isinstance(c, str)]))
        seg.put(at, assemble(at, code))
        elfseg.patch(elf, site, assemble(site, [('jal', at)]))
    # list cells: column width at entry, short form at the cell text measure
    assert word(CELL_ENTRY) == 0x8C930024 and word(CELL_MEASURE) == 0x0C000000 | MEASURE_A >> 2, 'list cell changed'
    code = [
        ('lw', 's3', 0x24, 'a0'),   # the replaced instruction; v1 (delay slot load) stays live
        ('lw', 't9', 0xB8, 's3'),
        ('addu', 't9', 't9', 'a1'),
        ('lw', 't9', 0, 't9'),
        ('lw', 't9', 0xC, 't9'),
        ('lui', 'at', hi(cellw)),
        ('jr', 'ra'),
        ('sw', 't9', lo(cellw), 'at')]
    at = seg.reserve(4 * len(code))
    seg.put(at, assemble(at, code))
    elfseg.patch(elf, CELL_ENTRY, assemble(CELL_ENTRY, [('jal', at)]))
    code = [
        ('addiu', 'sp', 'sp', -16),
        ('sd', 'ra', 0, 'sp'),
        ('jal', MEASURE_A),
        ('sw', 'a0', 8, 'sp'),
        ('lw', 'a0', 8, 'sp'),
        ('lw', 'v0', 0, 'a0'),
        ('lui', 'at', hi(cellw)),
        ('lw', 'v1', lo(cellw), 'at'),
        ('addiu', 'v1', 'v1', -8),
        ('slt', 'at', 'v1', 'v0'),
        ('beqz', 'at', 'done'),
        ('slt', 'at', 'zero', 'v1'),
        ('beqz', 'at', 'done'),
        ('nop',),
        ('jal', shorten),
        ('addiu', 'a0', 'sp', 16 + 0xBC),
        ('beqz', 'v0', 'done'),
        ('lw', 'a0', 8, 'sp'),
        ('lw', 'a1', 16 + 0xBC, 'sp'),
        ('jal', MEASURE_A),
        ('or', 'a2', 'zero', 'zero'),
        'done:',
        ('ld', 'ra', 0, 'sp'),
        ('jr', 'ra'),
        ('addiu', 'sp', 'sp', 16)]
    at = seg.reserve(4 * len([c for c in code if not isinstance(c, str)]))
    seg.put(at, assemble(at, code))
    elfseg.patch(elf, CELL_MEASURE, assemble(CELL_MEASURE, [('jal', at)]))
    return table, shorten

if __name__ == '__main__':
    cells, adv = glyph_cells()
    for ch in 'Ai':
        print(ch, adv[ord(ch)])
        for r in cells[ord(ch)]:
            print(''.join('.123456789ABCDEF'[v] for v in r))
