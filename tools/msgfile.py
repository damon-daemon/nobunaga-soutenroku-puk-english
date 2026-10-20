"""Message blocks: NB10 entries 39 and 40.

Entry: u16 count, u32 offsets[count] (from the entry start), then the strings back to
back (each normally ending 05 05 05), then one zero byte. Plain Shift-JIS, no
obfuscation. Strings are never shared.
"""
import struct

BLOCKS = (39, 40)

def strings(data):
    n = struct.unpack_from('<H', data)[0]
    offs = list(struct.unpack_from('<%dI' % n, data, 2))
    end = len(data.rstrip(b'\0'))
    if end < len(data) and data[end - 3:end] != b'\5\5\5':
        end = len(data) - 1             # keep zeros that belong to the last string
    return [data[a:b] for a, b in zip(offs, offs[1:] + [end])]

def pack(strs):
    n = len(strs)
    out, offs = bytearray(), []
    for s in strs:
        offs.append(2 + 4 * n + len(out))
        out += s
    return struct.pack('<H%dI' % n, n, *offs) + bytes(out) + b'\0'
