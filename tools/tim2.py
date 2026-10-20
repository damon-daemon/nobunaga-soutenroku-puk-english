"""Koei N9GD textures (standard TIM2 inside a 0x30-byte wrapper) in NB10 entries.

Most texture entries are packs: a table of u32 (offset, size) pairs at the start (offsets
16-aligned, the first offset ends the table, trailing zero slots), then the objects.
Entries 30-32 have no table (objects back to back).

N9GD header: 'N9GD', 1 or 8, 0x20, TIM2 offset (0x30; 0xA0 for v8, which adds 8 x 16-byte tile rects), i32 palette ref (-1 = own CLUT, else
index of the object in the same pack whose CLUT is used), 0, display w, h; TIM2 at +0x30:
one picture, 4bpp or 8bpp indexed, 32-bit CLUT (8bpp CLUTs CSM1-swizzled: bits 3/4 of
the index swapped). Palette-only objects (w = h = 0) and borrowed CLUTs exist, so
textures are only ever edited in place: pixels change, every header, size and palette
stays (Taiko 5 froze when a rebuilt texture lost a palette). apply() asserts that.
"""
import struct

def objects(entry):
    """[(offset, size)] of a pack entry (None for entries without a table)."""
    if entry[:4] == b'N9GD':
        return None
    first = struct.unpack_from('<I', entry, 0)[0]
    # table positions are object indexes (palette refs use them): keep zero slots
    return [struct.unpack_from('<II', entry, 8 * i) for i in range(first // 8)]

def _swz(i):
    return (i & ~0x18) | ((i & 8) << 1) | ((i & 0x10) >> 1)

class Texture:
    """One N9GD object of an entry: pix = palette indexes (row-major), pal = [(r, g, b, a)]
    in index order (a = PS2 alpha 0-0x80)."""
    def __init__(self, entry, i):
        objs = objects(entry)
        self.entry, self.i = entry, i
        self.off = objs[i][0] if objs else 0x2000 * i    # 30: 0x2000 stride
        o = self.off
        tim = o + struct.unpack_from('<I', entry, o + 0xC)[0]      # 0x30 (v1) or 0xA0 (v8: + tile rects)
        assert entry[o:o + 4] == b'N9GD' and entry[tim:tim + 4] == b'TIM2', (i, hex(o))
        self.ref = struct.unpack_from('<i', entry, o + 0x10)[0]
        p = tim + 0x10
        tot, clsz, imsz, hsz, clc, pfmt, mip, clt, imt, w, h = struct.unpack_from('<IIIHHBBBBHH', entry, p)
        assert imt in (4, 5) and mip == 1, (i, imt, mip)
        self.w, self.h, self.bpp = w, h, 4 if imt == 4 else 8
        self.img, self.img_size = p + hsz, imsz
        raw = entry[self.img:self.img + imsz]
        if self.bpp == 8:
            self.pix = list(raw[:w * h])
        else:
            self.pix = [v for b in raw for v in (b & 15, b >> 4)][:w * h]
        src = self if clc else Texture(entry, self.ref)
        self.pal = src._palette() if clc else src.pal
        self.clut_type = clt

    def _palette(self):
        o = self.off + struct.unpack_from('<I', self.entry, self.off + 0xC)[0] + 0x10
        tot, clsz, imsz, hsz, clc, pfmt, mip, clt, imt = struct.unpack_from('<IIIHHBBBB', self.entry, o)
        n = 16 if imt == 4 else 256
        c = o + hsz + imsz
        pal = [tuple(self.entry[c + 4 * k:c + 4 * k + 4]) for k in range(n)]
        if imt == 5 and not clt & 0x80:
            pal = [pal[_swz(k)] for k in range(n)]
        return pal

    def get(self, x, y):
        return self.pal[self.pix[y * self.w + x]]

    def idx(self, x, y):
        return self.pix[y * self.w + x]

    def put(self, x, y, i):
        assert 0 <= i < len(self.pal)
        self.pix[y * self.w + x] = i

    def pixels(self):
        """Image bytes (same size as the original)."""
        if self.bpp == 8:
            out = bytes(self.pix)
        else:
            p = self.pix + [0] * (-len(self.pix) % 2)
            out = bytes(p[k] | p[k + 1] << 4 for k in range(0, len(p), 2))
        out += self.entry[self.img + len(out):self.img + self.img_size]
        assert len(out) == self.img_size
        return out

    def image(self, palette=None):
        from PIL import Image
        pal = palette or self.pal
        im = Image.new('RGBA', (self.w, self.h))
        im.putdata([pal[i][:3] + (min(255, pal[i][3] * 2),) for i in self.pix])
        return im

def apply(entry, textures):
    """Entry bytes with the pixels of the edited textures written back in place."""
    e = bytearray(entry)
    for t in textures:
        e[t.img:t.img + t.img_size] = t.pixels()
    assert len(e) == len(entry)
    # headers and palettes unchanged: only image bytes may differ
    spans = sorted((t.img, t.img + t.img_size) for t in textures)
    k = 0
    for a, b in spans:
        assert e[k:a] == entry[k:a]
        k = b
    assert e[k:] == entry[k:]
    return bytes(e)
