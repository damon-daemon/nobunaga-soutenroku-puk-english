"""ISO 9660 + UDF access for the PS2 disc: read files, write a patched copy.

Every file has an ISO directory record and a UDF File Entry (one per file, sectors
273-314, a single short_ad each), and the game itself does not search the file
system: the ELF holds a table of (name, LBA, end LBA, sector count) for the movies,
NB10.NBX, sound and the two overlays (LBA_TABLE). A rebuilt file that still fits its
sectors is rewritten in place; otherwise
  - a small file (<= EVICT_MAX) moves to the free area after the last file,
  - a big one grows in place and the small files after it move instead
    (NB10.NBX is followed by N10.KHD and N10.KBD, 5.4 MB, then the 80 MB N10.ADX).
The ISO record, the UDF File Entry and the ELF table follow every file that changes
place or size; the image size and every untouched sector stay as on the clean disc.
"""
import binascii, os, shutil, struct

SECTOR = 2048
ELF_NAME = 'SLPM_654.55'
ELF_FOFF = 0x100000 - 0x800             # vaddr - file offset of the code/data segment
LBA_TABLE, LBA_COUNT = 0x3A6FF0, 18     # 32-byte records: name ptr, +8 LBA, +0x10 end, +0x18 sectors
EVICT_MAX = 16 << 20

class Record:
    def __init__(self, path, rec_off, lba, size, is_dir):
        self.path, self.rec_off, self.lba, self.size, self.is_dir = path, rec_off, lba, size, is_dir

    @property
    def sectors(self):
        return (self.size + SECTOR - 1) // SECTOR

def _read_dir(f, lba, size, prefix, out):
    f.seek(lba * SECTOR)
    data = f.read(size)
    pos = 0
    while pos < len(data):
        n = data[pos]
        if n == 0:                      # records never cross sectors; skip to next
            pos = (pos // SECTOR + 1) * SECTOR
            continue
        ext, length = struct.unpack_from('<I4xI', data, pos + 2)
        flags, nlen = data[pos + 25], data[pos + 32]
        name = data[pos + 33:pos + 33 + nlen]
        if name not in (b'\0', b'\1'):
            name = name.decode('ascii').split(';')[0]
            rec = Record(prefix + name, lba * SECTOR + pos, ext, length, bool(flags & 2))
            out[rec.path] = rec
            if rec.is_dir:
                _read_dir(f, ext, length, rec.path + '/', out)
        pos += n
    return out

def records(path):
    """{'SLPM_654.55': Record, 'DATA/NB10.NBX': Record, ...}"""
    with open(path, 'rb') as f:
        f.seek(16 * SECTOR)
        pvd = f.read(SECTOR)
        assert pvd[1:6] == b'CD001', 'not an ISO 9660 image'
        ext, length = struct.unpack_from('<I4xI', pvd, 156 + 2)
        return _read_dir(f, ext, length, '', {})

def read_file(path, name, recs=None):
    rec = (recs or records(path))[name]
    with open(path, 'rb') as f:
        f.seek(rec.lba * SECTOR)
        return f.read(rec.size)

# --- UDF ---------------------------------------------------------------------

def _udf_layout(f):
    """(partition start, partition end, {ISO LBA: FE sector}) from the clean image."""
    part = None
    for s in range(32, 48):                             # main volume descriptor sequence
        f.seek(s * SECTOR)
        d = f.read(SECTOR)
        if struct.unpack_from('<H', d)[0] == 5:         # partition descriptor
            start, length = struct.unpack_from('<II', d, 188)
            part = (start, start + length)
    assert part, 'no UDF partition descriptor'
    fes = {}
    for s in range(part[0], part[0] + 64):
        f.seek(s * SECTOR)
        d = f.read(SECTOR)
        if struct.unpack_from('<H', d)[0] != 261 or d[16 + 11] != 5:   # File Entry of a file
            continue
        l_ea, l_ad = struct.unpack_from('<II', d, 168)
        assert l_ad == 8 and d[16 + 18] & 7 == 0, 'FE %d: expected one short_ad' % s
        fes[struct.unpack_from('<I', d, 176 + l_ea + 4)[0] + part[0]] = s
    return part[0], part[1], fes

def _udf_set(f, fe_sector, part_start, lba, size):
    f.seek(fe_sector * SECTOR)
    d = bytearray(f.read(SECTOR))
    l_ea = struct.unpack_from('<I', d, 168)[0]
    struct.pack_into('<QQ', d, 56, size, (size + SECTOR - 1) // SECTOR)
    struct.pack_into('<II', d, 176 + l_ea, size, lba - part_start)
    crc_len = struct.unpack_from('<H', d, 10)[0]
    struct.pack_into('<H', d, 8, binascii.crc_hqx(bytes(d[16:16 + crc_len]), 0))
    d[4] = sum(d[0:4] + d[5:16]) & 0xFF
    f.seek(fe_sector * SECTOR)
    f.write(d)

# --- ELF LBA table -----------------------------------------------------------

def lba_table(elf):
    """{iso name: record file offset} for the ELF's hard-coded file table."""
    out = {}
    for i in range(LBA_COUNT):
        off = LBA_TABLE - ELF_FOFF + 32 * i
        p = struct.unpack_from('<I', elf, off)[0] - ELF_FOFF
        name = elf[p:elf.index(b'\0', p)].decode('ascii').lstrip('\\').split(';')[0]
        out[name.replace('\\', '/').upper()] = off
    return out

def _set_table(elf, off, lba, size):
    n = (size + SECTOR - 1) // SECTOR
    struct.pack_into('<I', elf, off + 8, lba)
    struct.pack_into('<I', elf, off + 0x10, lba + n - 1)
    struct.pack_into('<I', elf, off + 0x18, n)

# --- writer --------------------------------------------------------------------

def _set_record(f, rec, lba, size):
    f.seek(rec.rec_off + 2)
    f.write(struct.pack('<I', lba) + struct.pack('>I', lba) +
            struct.pack('<I', size) + struct.pack('>I', size))

def _write_extent(f, lba, data, clear_sectors):
    f.seek(lba * SECTOR)
    f.write(data)
    pad = clear_sectors * SECTOR - len(data)
    if pad > 0:
        f.write(bytes(pad))

def plan(clean, files, recs=None):
    """Place the changed files: ({name: (lba, sectors)} for every file, [moved names])."""
    recs = recs or records(clean)
    place = {n: (r.lba, r.sectors) for n, r in recs.items() if not r.is_dir}
    with open(clean, 'rb') as f:
        _, part_end, _ = _udf_layout(f)
    free_lba = max(l + k for l, k in place.values())
    moved = []

    def relocate(name, need):
        nonlocal free_lba
        if free_lba + need > part_end:
            raise RuntimeError('%s: no room left on the disc' % name)
        place[name] = (free_lba, need)
        free_lba += need
        moved.append(name)

    for name, data in sorted(files.items(), key=lambda kv: -len(kv[1])):
        lba, have = place[name]
        need = (len(data) + SECTOR - 1) // SECTOR
        if need <= have:
            place[name] = (lba, max(need, 1))
            continue
        if len(data) <= EVICT_MAX and name != ELF_NAME:     # the ELF grows in place (patch size)
            relocate(name, need)
            continue
        blockers = [n for n, (l, k) in place.items() if n != name and l < lba + need and l + k > lba]
        sizes = {n: len(files[n]) if n in files else recs[n].size for n in blockers}
        big = [n for n in blockers if sizes[n] > EVICT_MAX]
        if big:
            raise RuntimeError('%s (%d sectors) would overrun %s: make it smaller'
                               % (name, need, ', '.join(big)))
        for n in blockers:
            relocate(n, max(place[n][1], (sizes[n] + SECTOR - 1) // SECTOR))
        place[name] = (lba, need)
    return place, moved

def write_image(clean, out, files):
    """Copy clean to out and replace files ({iso name: bytes}). Returns moved names.

    The ELF LBA table is patched for every file that moves or changes size (the ELF
    is added to the written files if needed)."""
    recs = records(clean)
    files = {n: d for n, d in files.items() if read_file(clean, n, recs) != d}
    place, moved = plan(clean, files, recs)
    elf = bytearray(files.get(ELF_NAME) or read_file(clean, ELF_NAME, recs))
    for name, off in lba_table(elf).items():
        size = len(files[name]) if name in files else recs[name].size
        _set_table(elf, off, place[name][0], size)
    if bytes(elf) != read_file(clean, ELF_NAME, recs):
        files[ELF_NAME] = bytes(elf)
        assert place[ELF_NAME] == plan(clean, files, recs)[0][ELF_NAME]

    tmp = out + '.part'
    shutil.copyfile(clean, tmp)
    with open(tmp, 'r+b') as f:
        part_start, _, fes = _udf_layout(f)
        for name in moved:                                 # clear old copies first
            _write_extent(f, recs[name].lba, b'', recs[name].sectors)
        for name in sorted(set(files) | set(moved), key=lambda n: place[n][0]):
            lba, k = place[name]
            data = files[name] if name in files else read_file(clean, name, recs)
            clear = max(k, recs[name].sectors) if lba == recs[name].lba else k
            _write_extent(f, lba, data, clear)
            _set_record(f, recs[name], lba, len(data))
            _udf_set(f, fes[recs[name].lba], part_start, lba, len(data))
    os.replace(tmp, out)
    return moved

def verify(out, files):
    """Read every given file back through the ISO tree, the UDF tree (pycdlib) and the
    ELF LBA table; raise on any mismatch."""
    import io, pycdlib
    recs = records(out)
    elf = read_file(out, ELF_NAME, recs)
    table = lba_table(elf)
    iso = pycdlib.PyCdlib()
    iso.open(out)
    try:
        for name, data in files.items():
            assert read_file(out, name, recs) == data, '%s: ISO copy differs' % name
            buf = io.BytesIO()
            iso.get_file_from_iso_fp(buf, udf_path='/' + name)
            assert buf.getvalue() == data, '%s: UDF copy differs' % name
        for name, off in table.items():
            lba, end, n = struct.unpack_from('<I4xI4xI', elf, off + 8)
            r = recs[name]
            assert (lba, end, n) == (r.lba, r.lba + r.sectors - 1, r.sectors), \
                '%s: ELF table (%d, %d, %d) != ISO (%d, %d)' % (name, lba, end, n, r.lba, r.sectors)
    finally:
        iso.close()
