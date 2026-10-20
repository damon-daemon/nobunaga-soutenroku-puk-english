"""Strings of the ELF and the two overlays (menu labels, help lines, system messages ...).

tl/elfstr/*.txt: "key<TAB>English" lines, key = e<vaddr> (ELF), s<vaddr> (SEIRYAKU.BIN) or
g<vaddr> (GUNRYAKU.BIN) in hex; \\n = newline; ASCII text; English "-" = keep the
Japanese (debug logs never shown); '#' starts a comment line. A string without English
takes the English of another string with the same Japanese (translation memory).
English that fits the
string's slot (its bytes plus the compiler's zero padding) is written in place.
Longer English goes into the English data segment (elfseg.py) and every reference
is repointed:
  - 32-bit data words equal to the address (pointer tables) in the same image (and,
    for an ELF string, in the overlays),
  - lui/addiu (or load/store) pairs in the code that build the address, when that lui
    has no other user (else the pair cannot be changed alone: shorten the English).
An overlay address seen from the ELF is ambiguous (both overlays load at 0x198A000):
such a reference blocks moving the string.
A string with no reference found must fit its slot. printf conversions must match.

Not covered here (later tools): the name pools and name-entry dictionaries
(NAME_RANGES, names), the name-entry character grid (GRID).

  elfstr.py export            -> script/elfstr.json (every candidate, with flags)
  elfstr.py show [KEY KEY] [--todo]   strings to translate between two keys
  elfstr.py stats | check
"""
import collections, json, os, re, struct, sys

sys.path.insert(0, os.path.dirname(__file__))
import elfseg

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TL = os.path.join(ROOT, 'tl', 'elfstr')
SCRIPT = os.path.join(ROOT, 'script', 'elfstr.json')
FMT = re.compile(rb'%[-+ #0]*\d*(?:\.\d+)?[hl]?[diouxXcsfeEgGp%]')
OVL_BASE = 0x198A000

class Image:
    """One loaded file: data[foff + (va - base)] for va in [base, end)."""

    def __init__(self, tag, name, data, base, foff, end, code, words):
        self.tag, self.name, self.data = tag, name, data
        self.base, self.foff, self.end = base, foff, end
        self.code, self.words = code, words          # [(lo, hi)] ranges

    def f(self, va):
        assert self.base <= va < self.end, '%s %x' % (self.tag, va)
        return va - self.base + self.foff

    def w(self, va):
        return struct.unpack_from('<I', self.data, self.f(va))[0]

    def put(self, va, b):
        o = self.f(va)
        self.data[o:o + len(b)] = b

def images(elf, sei, gun):
    """[ELF, SEIRYAKU, GUNRYAKU] images over the given (mutable) file bytes."""
    out = [Image('e', 'SLPM_654.55', elf, 0x100000, 0x800, 0x100000 + 0x3DA200,
                 [(0x100000, 0x39C000), (0x402A80, 0x43FCB0)],      # code, static constructors
                 [(0x398000, 0x402A80), (0x43FCB0, 0x4DA200)])]
    for tag, name, b in (('s', 'SEIRYAKU.BIN', sei), ('g', 'GUNRYAKU.BIN', gun)):
        text, end = struct.unpack_from('<I', b, 0xC)[0], struct.unpack_from('<I', b, 0x18)[0]
        code_end = OVL_BASE + 0x80 + text
        out.append(Image(tag, name, b, OVL_BASE, 0, OVL_BASE + len(b), [(OVL_BASE + 0x80, code_end)], [(code_end, end)]))
    return out

def _s16(x):
    return x - 0x10000 if x & 0x8000 else x

def _writes(w):
    """Register written by instruction w (None if none / unknown)."""
    op = w >> 26
    if op in (0, 0x1C):
        return (w >> 11) & 31
    if op in (0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F, 0x1A, 0x1B, 0x1E, 0x37) or 0x20 <= op <= 0x27:
        return (w >> 16) & 31
    if op == 0x03:
        return 31
    return None

def _is_jump(w):
    op = w >> 26
    return op in (2, 3) or (op == 0 and (w & 0x3F) in (8, 9))

def code_pairs(img):
    """({target: [(lui va, user va)]}, {lui va: number of users}) for the image's code.
    A lui register is followed until it is overwritten or a jump's delay slot ends;
    any other read of it counts as a user too (so such a lui is never changed)."""
    pairs, users = collections.defaultdict(list), collections.Counter()
    lui, end_after = {}, None
    for va in (a for lo, hi in img.code for a in range(lo, hi, 4)):
        w = img.w(va)
        op, rs, rt, imm = w >> 26, (w >> 21) & 31, (w >> 16) & 31, w & 0xFFFF
        if op == 0x0F:
            lui[rt] = (imm << 16, va)
        else:
            if rs in lui and (op in (0x09, 0x0D) or 0x20 <= op <= 0x3F):
                t = (lui[rs][0] + (imm if op == 0x0D else _s16(imm))) & 0xFFFFFFFF
                pairs[t].append((lui[rs][1], va))
                users[lui[rs][1]] += 1
                if 0x28 <= op <= 0x3F and rt in lui and rt != rs:     # stores the lui value
                    users[lui[rt][1]] += 2
            else:
                for r in {rs, rt}:
                    if r in lui:
                        users[lui[r][1]] += 2
            wr = _writes(w)
            if wr in lui:
                del lui[wr]
        if end_after is not None and va >= end_after:
            lui.clear()
            end_after = None
        if _is_jump(w):
            end_after = va + 4
    return pairs, users

def data_words(img, lo, hi):
    """{value: [vaddr]} of the aligned words of the image's data pointing into [lo, hi)."""
    out = collections.defaultdict(list)
    for va in (a for lo, hi in img.words for a in range(lo, hi - 3, 4)):
        v = img.w(va)
        if lo <= v < hi:
            out[v].append(va)
    return out

class Refs:
    """Every reference to a string of each image, by image tag."""

    def __init__(self, imgs):
        self.imgs = {i.tag: i for i in imgs}
        self.code = {i.tag: code_pairs(i) for i in imgs}
        self.words = {i.tag: data_words(i, 0x100000, 0x1AE3800) for i in imgs}

    def of(self, tag, va):
        """(code pairs [(img tag, lui, user)], data words [(img tag, at)], blockers [text])."""
        code, data, block = [], [], []
        if tag == 'e':
            srcs = ['e', 's', 'g']
        else:
            srcs = [tag]
            if self.code['e'][0].get(va) or self.words['e'].get(va):
                block.append('referenced from the ELF (ambiguous overlay address)')
        for s in srcs:
            for l, u in self.code[s][0].get(va, []):
                code.append((s, l, u))
                if self.code[s][1][l] != 1:
                    block.append('lui %s:%x has other users' % (s, l))
            for at in self.words[s].get(va, []):
                data.append((s, at))
        return code, data, block

def slot(img, va):
    """(Japanese bytes, room) of the string at va: room = bytes up to the next 8-byte
    boundary after its NUL (the compiler's padding; zeros beyond it may be constants),
    and never past the next non-zero byte, minus one for the NUL."""
    b = img.data
    o = img.f(va)
    assert b[o - 1] == 0 or va % 4 == 0, '%s%x is not the start of a string' % (img.tag, va)
    e = b.index(b'\0', o)
    k = e
    while k < len(b) and b[k] == 0:
        k += 1
    end = min(k, (va + (e - o) + 1 + 7) // 8 * 8 - va + o)
    return bytes(b[o:e]), end - o - 1

def parse_key(k):
    return k[0], int(k[1:], 16)

def load_tl(d=TL):
    """{key: English} of every tl/elfstr file ('-' entries included)."""
    out = {}
    for fn in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        if not fn.endswith('.txt'):
            continue
        path = os.path.join(d, fn)
        for n, line in enumerate(open(path, encoding='utf-8').read().splitlines(), 1):
            if line.strip() and not line.startswith('#'):
                k, tab, v = line.partition('\t')
                if not (tab and re.fullmatch('[esg][0-9a-f]+', k)):
                    raise ValueError('%s line %d: expected key<TAB>English: %r' % (fn, n, line))
                if k in out:
                    raise ValueError('%s line %d: %s given twice' % (fn, n, k))
                out[k] = v.replace('\\n', '\n')
    return out

def resolved(tl, rows):
    """{key: English} to write: explicit English, else translation memory by Japanese;
    '-' entries dropped. rows = export rows (key, jp, ui)."""
    jp = {r['key']: r['jp'] for r in rows}
    mem = {}
    for k, v in tl.items():
        if v != '-' and k in jp:
            mem.setdefault(jp[k], v)
    out = {k: v for k, v in tl.items() if v != '-'}
    for r in rows:
        if r['ui'] and r['key'] not in tl and r['jp'] in mem:
            out[r['key']] = mem[r['jp']]
    return out

def encode(en):
    return en.encode('ascii')

def apply(elf, sei, gun, clean, seg, tl=None):
    """Write tl/elfstr into elf/sei/gun (bytearrays); clean = (elf, sei, gun) bytes.
    Returns (strings, moved)."""
    cimgs = images(*[bytearray(b) for b in clean])
    tl = resolved(load_tl() if tl is None else tl, survey(cimgs))
    if not tl:
        return 0, 0
    imgs = {i.tag: i for i in images(elf, sei, gun)}
    refs = Refs(cimgs)
    ctag = {i.tag: i for i in cimgs}
    errors, moved = [], 0
    for key, en in sorted(tl.items()):
        tag, va = parse_key(key)
        jp, room = slot(ctag[tag], va)
        try:
            b = encode(en)
        except UnicodeEncodeError:
            errors.append('elfstr %s: not ASCII: %r' % (key, en))
            continue
        if FMT.findall(b) != FMT.findall(jp):
            errors.append('elfstr %s: conversions %s, Japanese has %s' % (key, FMT.findall(b), FMT.findall(jp)))
            continue
        if len(b) <= room:
            imgs[tag].put(va, b + bytes(room + 1 - len(b)))
            continue
        code, data, block = refs.of(tag, va)
        if not code and not data:
            errors.append('elfstr %s: %d bytes, room %d and no reference to repoint' % (key, len(b), room))
            continue
        if block:
            errors.append('elfstr %s: %d bytes, room %d; %s' % (key, len(b), room, '; '.join(block)))
            continue
        new = seg.add(b + b'\0', 1)
        for s, at in data:
            imgs[s].put(at, struct.pack('<I', new))
        for s, l, u in code:
            lw, uw = ctag[s].w(l), ctag[s].w(u)
            assert (imgs[s].w(l), imgs[s].w(u)) == (lw, uw), 'elfstr %s: code at %x/%x already patched' % (key, l, u)
            hi = (new + 0x8000) >> 16
            lo = (new - (hi << 16)) & 0xFFFF
            if uw >> 26 == 0x0D:                                  # ori: unsigned low half
                hi, lo = new >> 16, new & 0xFFFF
            imgs[s].put(l, struct.pack('<I', (lw & 0xFFFF0000) | hi))
            imgs[s].put(u, struct.pack('<I', (uw & 0xFFFF0000) | lo))
        moved += 1
    if errors:
        raise ValueError('\n'.join(errors))
    return len(tl), moved

# ---------------------------------------------------------------- survey

JP = re.compile('[぀-ヿ一-鿿！-～　-〿]')

def _is_text(b):
    i, jp = 0, 0
    while i < len(b):
        c = b[i]
        if 0x81 <= c <= 0x9F or 0xE0 <= c <= 0xFC:
            if i + 1 >= len(b) or not (0x40 <= b[i + 1] <= 0xFC and b[i + 1] != 0x7F):
                return False
            jp += 1
            i += 2
            continue
        if 0xA1 <= c <= 0xDF:
            jp += 1
        elif not (0x20 <= c < 0x7F or c in (0x0A, 0x1B, 0x09)):
            return False
        i += 1
    return jp > 0

def candidates(img):
    """[(vaddr, bytes)] of the Shift-JIS strings in the image's data (mostly Japanese)."""
    out, b = [], img.data
    for lo, hi in img.words:
        out += _scan(img, img.f(lo), img.f(hi - 1) + 1)
    return out

def _scan(img, o, hi):
    out, b = [], img.data
    while o < hi:
        if b[o] == 0:
            o += 1
            continue
        e = b.index(b'\0', o)
        # a string starts after a NUL or, right after a pointer word, at a 4-aligned address
        starts = [o] if b[o - 1] == 0 else []
        starts += [p for p in range(o + 1, e) if (p - img.foff + img.base) % 4 == 0]
        for p in starts:
            s = bytes(b[p:e])
            if _is_text(s):
                t = s.decode('cp932', 'replace')
                fw = len(JP.findall(t))
                if '�' not in t and fw >= 1 and (fw * 2 >= len(t) * 0.5 or FMT.search(s)):
                    out.append((p - img.foff + img.base, s))
                break
        o = e + 1
    return out

# name pools / dictionaries (kanji + kana reading pairs; ninja epithets, princess and
# generated given names, name-entry dictionaries): handled with the names, not here
NAME_RANGES = {'e': [(0x3BD7A8, 0x3BE7E8), (0x3C2F50, 0x3E0DB8), (0x3E7B58, 0x3EA120), (0x3F1E38, 0x3F2E78),
                     (0x3F6560, 0x3F6930), (0x3F88C8, 0x3F9908), (0x3FA108, 0x3FBD18), (0x3FF270, 0x400E80)],
               's': [], 'g': [(0x1AB4AA8, 0x1AB66B8)]}
GRID = ('e', 0x3F4208, 0x3F4AD8)        # name-entry character grid (kana, letters, symbols)
_FMT_S = re.compile(r'%[-+ #0]*\d*[hl]?[dsxuc]')
# likely debug output (never shown): workers still see these, flagged
DEBUG = re.compile(r'Algo|－.*処理|処理$|\*\*\*|===|<<|>>|\$\$|->|Phase|Buffer|Error|[:：]%d|（[ア-ンａ-ｚＡ-Ｚ]）|^\s')

def _junk(t):
    """One kanji + ASCII bytes: an instruction or float that looks like text."""
    rest = _FMT_S.sub('', t)
    return len(JP.findall(t)) == 1 and len(rest) > 1 and all(c.isascii() for c in rest if not JP.match(c))

def survey(imgs):
    """[row] of every referenced candidate string: key, tag, va, room, code, data, block,
    jp (text), ui (to translate), debug (flag), kind."""
    refs = Refs(imgs)
    rows = []
    for img in imgs:
        for va, s in candidates(img):
            jp, room = slot(img, va)
            code, data, block = refs.of(img.tag, va)
            t = jp.decode('cp932')
            if not code and not data:
                kind = 'noref'
            elif any(lo <= va < hi for lo, hi in NAME_RANGES[img.tag]):
                kind = 'name'
            elif img.tag == GRID[0] and GRID[1] <= va < GRID[2]:
                kind = 'grid'
            elif _junk(t):
                kind = 'junk'
            else:
                kind = 'ui'
            rows.append({'key': '%s%x' % (img.tag, va), 'tag': img.tag, 'va': va, 'room': room,
                         'code': len(code), 'data': len(data), 'block': block, 'jp': t,
                         'ui': kind == 'ui', 'debug': kind == 'ui' and bool(DEBUG.search(t) or t.endswith('\n')),
                         'kind': kind})
    return rows

def clean_files():
    d = os.path.join(ROOT, 'extract')
    return [open(os.path.join(d, n), 'rb').read() for n in ('SLPM_654.55', 'SEIRYAKU.BIN', 'GUNRYAKU.BIN')]

def export():
    rows = survey(images(*[bytearray(b) for b in clean_files()]))
    os.makedirs(os.path.dirname(SCRIPT), exist_ok=True)
    json.dump(rows, open(SCRIPT, 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
    return rows

def rows():
    if not os.path.exists(SCRIPT):
        export()
    return json.load(open(SCRIPT, encoding='utf-8'))

def _order(key):
    return ('esg'.index(key[0]), int(key[1:], 16))

def show(lo=None, hi=None, todo=False):
    """Print the strings to translate in [lo, hi] (keys), address order:
    key  room  M (movable if the English is longer) / F (fixed: must fit room)  D (debug?)  Japanese  => English"""
    tl = load_tl()
    rs = [r for r in rows() if r['ui']]
    res = resolved(tl, rs)
    for r in rs:
        if lo and _order(r['key']) < _order(lo) or hi and _order(r['key']) > _order(hi):
            continue
        en = tl.get(r['key'])
        if todo and en is not None:
            continue
        mark = '' if en is not None else '[tm] ' + res[r['key']] if r['key'] in res else ''
        print('%s\t%d\t%s%s\t%s%s' % (r['key'], r['room'], 'F' if r['block'] else 'M', ' D' if r['debug'] else '',
                                    r['jp'].replace('\n', '\\n'), '\t=> ' + (en.replace('\n', '\\n') if en is not None else mark) if en is not None or mark else ''))

def stats():
    tl = load_tl()
    rs = [r for r in rows() if r['ui']]
    res = resolved(tl, rs)
    done = sum(r['key'] in tl or r['key'] in res for r in rs)
    print('ui strings %d: done %d (%d explicit, %d kept Japanese "-"), todo %d; debug-flagged %d'
          % (len(rs), done, sum(r['key'] in tl and tl[r['key']] != '-' for r in rs), sum(tl.get(r['key']) == '-' for r in rs),
             len(rs) - done, sum(r['debug'] for r in rs)))
    keys = {r['key'] for r in rs}
    stray = [k for k in tl if k not in keys]
    if stray:
        print('keys not in the ui list:', ' '.join(stray[:20]))

_W = None

def px(t):
    """Pixel width of a line: English with the proportional font (latinfont 'msg', the
    planned VWF), Japanese 22 per full-width and 11 per half-width character."""
    global _W
    if _W is None:
        import latinfont
        _W = {c: g[1] for c, g in latinfont.render('msg').items()}
    return max(sum(_W.get(c, 11) if c.isascii() else 11 if '\uff61' <= c <= '\uff9f' else 22 for c in line)
               for line in t.split('\n'))

def wide(tl=None):
    """[(key, en px, jp px, en, jp)] of English wider than its Japanese (labels may be clipped)."""
    tl = load_tl() if tl is None else tl
    out = []
    for r in rows():
        en = tl.get(r['key'])
        if r['ui'] and en and en != '-' and px(en) > px(r['jp']):
            out.append((r['key'], px(en), px(r['jp']), en, r['jp']))
    return out

def check():
    """Dry-run apply on the clean files; prints errors. True if clean."""
    clean = clean_files()
    try:
        n, moved = apply(*[bytearray(b) for b in clean], clean, elfseg.Segment())
    except ValueError as e:
        print(e)
        return False
    print('elfstr: %d strings OK (%d moved to the segment)' % (n, moved))
    w = wide()
    if w:
        print('%d strings wider than the Japanese (may be clipped; shorten labels where possible):' % len(w))
        for k, a, b, en, jp in w:
            print('  %s %d > %d px  %s  (%s)' % (k, a, b, en.replace('\n', '\\n'), jp.replace('\n', '\\n')))
    return True

if __name__ == '__main__':
    a = sys.argv[1:]
    if a == ['export']:
        print(len(export()), 'strings ->', SCRIPT)
    elif a and a[0] == 'show':
        todo = '--todo' in a
        a = [x for x in a[1:] if x != '--todo']
        show(a[0] if a else None, a[1] if len(a) > 1 else None, todo)
    elif a == ['stats']:
        stats()
    elif a == ['check']:
        sys.exit(0 if check() else 1)
    else:
        print(__doc__)
