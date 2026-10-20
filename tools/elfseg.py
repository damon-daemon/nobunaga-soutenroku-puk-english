"""English data segment: code and data the patches need, loaded at the end of the BSS.

The ELF has four PT_LOAD program headers; the last (at _end = 0x1AE3800, after the
overlay region 0x198A000) is empty. Filling it makes the loader place our bytes right
after the overlay region. The heap starts at _end, so it is moved past the segment:

  0x10006C/0x100074  lui/addiu a0 = _end   SetupHeap syscall (0x3D): heap start
  0x39A8D4           word = _end           libkernel sbrk's heap pointer (sbrk 0x10DF60)

0x10000C/0x100014 (BSS clear end) stays: the BSS still ends at 0x1AE3800. The clear loop
(sq, then compare, then step) stores once more at the end address: the segment's
first 16 bytes are zeroed at boot, so they are kept as padding (PAD).
The heap (and so the segment) must stay below the stack (0x1F20000-0x1F90000).
"""
import struct, sys, os

sys.path.insert(0, os.path.dirname(__file__))
import asm

BASE = 0x1AE3800
FOFF, VBASE = 0x800, 0x100000
HEAP_SITES = [(0x10006C, 0x100074, 'a0')]
HEAP_WORDS = [0x39A8D4]
LOAD = 3                                  # index of the empty PT_LOAD
PAD = 16                                  # zeroed by crt0's BSS clear (see above)

class Segment:
    def __init__(self, base=BASE):
        self.base, self.data = base, bytearray(PAD)

    @property
    def end(self):
        return self.base + len(self.data)

    def add(self, b, align=4):
        self.data.extend(bytes(-len(self.data) % align))
        addr = self.end
        self.data.extend(b)
        return addr

    def reserve(self, n, align=4):
        """Address of n zero bytes (filled later with put)."""
        return self.add(bytes(n), align)

    def put(self, addr, b):
        o = addr - self.base
        assert 0 <= o and o + len(b) <= len(self.data)
        self.data[o:o + len(b)] = b

def patch(elf, vaddr, b):
    o = vaddr - VBASE + FOFF
    elf[o:o + len(b)] = b

def apply(elf, seg):
    """Append the segment to the ELF file, point the empty PT_LOAD at it, move the heap.
    Returns the new heap start."""
    phoff = struct.unpack_from('<I', elf, 0x1C)[0]
    phnum = struct.unpack_from('<H', elf, 0x2C)[0]
    assert phnum == LOAD + 1
    at = phoff + 32 * LOAD
    p = struct.unpack_from('<8I', elf, at)
    assert p[0] == 1 and p[2] == BASE and p[4] == 0 and p[5] == 0, 'PT_LOAD %d is not the empty one at _end' % LOAD
    if len(seg.data) <= PAD:
        return BASE
    elf.extend(bytes(-len(elf) % 0x80))
    off = len(elf)
    elf.extend(seg.data)
    size = len(seg.data)
    struct.pack_into('<8I', elf, at, 1, off, BASE, BASE, size, size, 7, 0x10)
    end = (BASE + size + 0xFF) & ~0xFF
    for lui, addiu, reg in HEAP_SITES:
        patch(elf, lui, asm.assemble(lui, [('lui', reg, asm.hi(end))]))
        patch(elf, addiu, asm.assemble(addiu, [('addiu', reg, reg, asm.lo(end))]))
    for va in HEAP_WORDS:
        o = va - VBASE + FOFF
        assert elf[o:o + 4] == struct.pack('<I', BASE)
        patch(elf, va, struct.pack('<I', end))
    return end
