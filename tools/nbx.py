"""DATA/NB10.NBX, the main archive: entries and the table of contents in the ELF.

The TOC is in the ELF at vaddr 0x3A6B70: 142 x (u32 byte offset, u32 size) plus a
final (file size, file size). Offsets are 2048-aligned and back to back. The reader
(0x24FA50) uses the size only as "entry present" and, unless the caller passes a
size, reads offset[i+1] - offset[i] bytes, so entries must stay in order with no
slack: a grown entry shifts every later one (the archive grows in place on the disc,
see iso.py).
"""
import struct

NAME = 'DATA/NB10.NBX'
TOC, COUNT = 0x3A6B70, 142
ELF_FOFF = 0x100000 - 0x800
ALIGN = 2048

def toc(elf):
    """[(offset, size)] for the 142 entries."""
    return [struct.unpack_from('<II', elf, TOC - ELF_FOFF + 8 * i) for i in range(COUNT)]

def entries(nbx, elf):
    return [nbx[o:o + s] for o, s in toc(elf)]

def entry(nbx, elf, i):
    o, s = toc(elf)[i]
    return nbx[o:o + s]

def pack(items):
    """Archive bytes and TOC [(offset, size)] for a list of entry bytes."""
    out, table = bytearray(), []
    for data in items:
        table.append((len(out), len(data)))
        out += data
        out += bytes(-len(out) % ALIGN)
    return bytes(out), table

def apply(nbx, elf, changes):
    """Rebuild the archive with {entry index: bytes}; writes the new TOC into elf
    (bytearray) and returns the new archive bytes."""
    items = entries(nbx, elf)
    for i, data in changes.items():
        items[i] = bytes(data)
    out, table = pack(items)
    for i, (o, s) in enumerate(table):
        struct.pack_into('<II', elf, TOC - ELF_FOFF + 8 * i, o, s)
    struct.pack_into('<II', elf, TOC - ELF_FOFF + 8 * COUNT, len(out), len(out))
    return out
