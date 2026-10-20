"""Name entry screen (PUK editors, princess naming): Latin letters instead of kana/kanji.

Class 0x2BA180 (notes/survey/names_pools_entry_re.md section 2). Five tabs of cells (pointer
tables to strings; a cell is appended to the text while length < max). Changes:
  - the five cell tables point to ASCII cells in the segment (tab labels: tl/elfstr e3f4ad8..)
  - tab 2 no longer opens the kanji pages (0x2BB3B4)
  - backspace removes one byte (0x2BB60C)
  - the text starts empty when the current name is not ASCII or longer than the field
    (Japanese record names; English names from the name hook can be longer than 8 bytes)
  - cursor x = VWF width of the text (0x2BC124-0x2BC158) instead of (bytes / 2) * 22
'%', '{', '}', '~' and '\\' are left out: they mean something to the message expander.
"""
import struct, sys, os

sys.path.insert(0, os.path.dirname(__file__))
import asm, elfseg
from asm import hi, lo

BLANK = 0x3F4328                     # "  " cell: shown empty, not selectable
UPPER = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
LOWER = UPPER.lower()
DIGITS = '0123456789'
PUNCT = " -'.&!?(),:/+=#*@"          # ' ' = a real space cell
SYMBOLS = "-'.,&!?()[]<>:;/+=#*@$^_\"`|"

def block(chars):
    """One 5 x 10 block (50 cells), padded with blanks."""
    assert len(chars) <= 50
    return list(chars) + [None] * (50 - len(chars))

# (table, cell count) -> cells (None = blank); counts are fixed by the end marker of each table
TABS = [
    (0x3AAAA0, 100, block(UPPER) + block(LOWER)),                  # label "ABC"
    (0x3AAC40, 100, block(LOWER) + block(UPPER)),                  # "abc"
    (0x3AADE0, 50, block(DIGITS + PUNCT)),                         # "123"
    (0x3AAEB0, 70, block(UPPER + ' ' + "-'.") + list(DIGITS) + [None] * 10),   # "Mix"
    (0x3AAFD0, 45, list(SYMBOLS) + [None] * (45 - len(SYMBOLS))),  # "#!?"
]
KANJI_TAB = 0x2BB3B4                 # addiu v0, zero, 2 (tab compare)
BACKSPACE = 0x2BB60C                 # addiu a1, v1, -2
INIT = 0x2BA2F0                      # sw zero, 0x730(s0) (ctor, after max is set at +0xAC)
TRUNCATE = 0x22A490                  # CString truncate(this, length)
CURSOR = 0x2BC124                    # 14 instructions: x = (len / 2) * 22 -> sp+0x40 (stored at 0x2BC164)

def word(elf, va):
    return struct.unpack_from('<I', elf, va - elfseg.VBASE + elfseg.FOFF)[0]

def apply(elf, seg, width_table):
    cells = {}
    for _, n, tab in TABS:
        assert len(tab) == n
        for c in tab:
            if c is not None and c not in cells:
                cells[c] = seg.add(c.encode('ascii') + b'\0', 1)
    for table, n, tab in TABS:
        assert word(elf, table) & 0xFFF00000 == 0x300000 and word(elf, table + 4 * n) == 0, 'cell table %x changed' % table
        elfseg.patch(elf, table, b''.join(struct.pack('<I', cells[c] if c else BLANK) for c in tab))
    assert word(elf, KANJI_TAB) == 0x24020002 and word(elf, BACKSPACE) == 0x2465FFFE and word(elf, INIT) == 0xAE000730
    elfseg.patch(elf, KANJI_TAB, asm.assemble(KANJI_TAB, [('addiu', 'v0', 'zero', 0x63)]))
    elfseg.patch(elf, BACKSPACE, asm.assemble(BACKSPACE, [('addiu', 'a1', 'v1', -1)]))
    code = [                          # s0 = this; v0 is live (lui in the jal delay slot)
        ('addiu', 'sp', 'sp', -16), ('sd', 'ra', 0, 'sp'), ('sd', 'v0', 8, 'sp'),
        ('sw', 'zero', 0x730, 's0'),
        ('lw', 't0', 0xA0, 's0'), ('lw', 't1', -8, 't0'), ('lw', 't2', 0xAC, 's0'),
        ('slt', 'at', 't2', 't1'), ('bnez', 'at', 'clear'), ('nop',),
        'scan:',
        ('lbu', 't3', 0, 't0'), ('beqz', 't3', 'done'), ('andi', 't3', 't3', 0x80),
        ('bnez', 't3', 'clear'), ('nop',),
        ('b', 'scan'), ('addiu', 't0', 't0', 1),
        'clear:',
        ('addiu', 'a0', 's0', 0xA0), ('jal', TRUNCATE), ('or', 'a1', 'zero', 'zero'),
        'done:',
        ('ld', 'v0', 8, 'sp'), ('ld', 'ra', 0, 'sp'), ('jr', 'ra'), ('addiu', 'sp', 'sp', 16)]
    at = seg.reserve(4 * len([l for l in code if not isinstance(l, str)]))
    seg.put(at, asm.assemble(at, code))
    elfseg.patch(elf, INIT, asm.assemble(INIT, [('jal', at)]))
    assert word(elf, CURSOR) == 0x8E2200A0 and word(elf, CURSOR + 0x34) == 0x00021040, 'cursor code changed'
    cursor = [
        ('lw', 't0', 0xA0, 's1'), ('lui', 't1', hi(width_table)), ('or', 't2', 'zero', 'zero'),
        ('addiu', 'a0', 's1', 0x60),
        'loop:',
        ('lbu', 't3', 0, 't0'), ('addu', 't4', 't1', 't3'), ('lbu', 't4', lo(width_table), 't4'),
        ('beqz', 't3', 'end'), ('addiu', 't0', 't0', 1),
        ('b', 'loop'), ('addu', 't2', 't2', 't4'),
        'end:',
        ('addiu', 'v0', 'zero', 0x14), ('sw', 'v0', 0x44, 'sp'), ('or', 'v0', 't2', 'zero')]
    b = asm.assemble(CURSOR, cursor)
    assert len(b) == 14 * 4
    elfseg.patch(elf, CURSOR, b)
