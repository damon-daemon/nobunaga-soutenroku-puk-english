"""Bigger message output buffer (ELF code patch).

Every message expansion goes to one buffer: malloc(0x4B0) at 0x1E96B8 (manager +0x10,
returned by 0x208BB0 as mgr+4), cleared per message (memset 0x4B0 at 0x1E82C8); the
byte writer 0x1E81A0 stops at the limit u16 +0x38 = 0x4AE (0x1E82CC) and the rest of
the message is cut. English help pages exceed 1,198 bytes, so the three immediates
are raised (notes/survey/msg_buffers.md).
"""
import struct

FOFF = 0x100000 - 0x800
SIZE = 0x1000
LIMIT = SIZE - 2            # bytes of text the writer accepts
SITES = {0x1E96B8: (0x24040000, 0x4B0),     # addiu a0, zero, size   (malloc)
         0x1E82C8: (0x24060000, 0x4B0),     # addiu a2, zero, size   (memset)
         0x1E82CC: (0x24030000, 0x4AE)}     # addiu v1, zero, limit

def apply(elf):
    for va, (op, old) in SITES.items():
        o = va - FOFF
        assert struct.unpack_from('<I', elf, o)[0] == op | old, hex(va)
        struct.pack_into('<I', elf, o, op | (LIMIT if old == 0x4AE else SIZE))
