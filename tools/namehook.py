"""Name hook: the name records keep their Japanese, the getters show English.

Every screen and message variable reads names through a few per-type getters that
return a heap string (notes/survey/names_*_re.md). The records stay Japanese, so
history events that compare names with Japanese constants, renames, saves and the
random-name pools keep working. At build time a table is generated:

  FNV-1a(kind byte, field, 0xFF, field, ...) -> English string      (sorted by hash)

and the getters are hooked to look up what is in the record:

  kind  key                                   English
  n/f/g person/woman/PUK record: family, family reading, given, given reading
                                              "Family Given" / family / given
  F/G   one part + its reading (pools, generated persons, princesses)
  K     castle name + Japanese suffix         "Kiyosu Castle", "Chusonji", "Iga Village"
  c p r t T o q  castle, province, region, treasure, court title, office, group name
  W     English (title, office, treasure)  its short form: swapped in by text widgets and list
        cells too narrow for the full form (vwf SHORTEN); castle full names -> bare name

No hit -> the record is shown as it is (names the player typed). Callers that copy
a name back into a record or compare it with Japanese constants (RAW_SITES) call the
getter through a wrapper that sets a flag the hooks obey (raw Japanese).

Ninja names are not stored in records (indices into four lists, formatted on demand
"%s%s" in three identical code copies): the 12 pointer tables are repointed to the
English of tl/names/pools.json and the formats become "%s %s".

  namehook.py stats          table size, conflicts, longest names
  namehook.py find TEXT      keys whose English contains TEXT
"""
import collections, json, os, re, struct, sys

sys.path.insert(0, os.path.dirname(__file__))
import asm, elfseg, names, overflow, setup
from asm import hi, lo

POOLS = os.path.join(setup.TL, 'names', 'pools.json')
SHORT_TABLES = ('courttitles', 'offices', 'treasures')   # 'short' forms used by vwf's SHORTEN
UI_SHORT = os.path.join(setup.TL, 'uishort.txt')         # UI English<TAB>short form, also for SHORTEN

def load_ui_short(path=UI_SHORT):
    out = {}
    for n, line in enumerate(open(path, encoding='utf-8').read().splitlines(), 1):
        if line.strip() and not line.startswith('#'):
            en, tab, short = line.partition('\t')
            if not (tab and en and short and short.isascii() and en != short):
                raise ValueError('%s line %d: expected English<TAB>short: %r' % (path, n, line))
            out[en] = short
    return out
ASSIGN, FORMAT = 0x22A1B0, 0x22AB00          # CString = char*; CString::Format(this, fmt, ...)
P32, M32 = 0x01000193, 0xFFFFFFFF

# castle suffix table 0x39F840 (16 x (kanji, kana)) -> English appended to the castle name
SUFFIX_EN = [' Castle', ' Castle', ' Hall', ' Hall', ' Gobo', ' Mido', ' Palace', 'ji', ' Shrine',
             ' Fort', ' Stockade', ' Church', ' Village', '', ' Port', ' Village']
# the castle type shown alone (0x1AE040: Format(out, "%s", suffix))
TYPE_EN = ['Castle', 'Castle', 'Hall', 'Hall', 'Gobo', 'Mido', 'Palace', 'Temple', 'Shrine',
           'Fort', 'Stockade', 'Church', 'Village', 'Town', 'Port', 'Village']
TYPE_SITE = 0x1AE040
SUFFIX_TABLE = 0x39F840             # its kanji pointers are set to Japanese copies in the segment
                                    # (elfstr translates some of the shared strings)
CASTLE_SUFFIX = 26                  # suffix id in the scenario castle record (runtime +0x1F)
WOMEN_REC = (names.TABLES['women'][0] - 26, 70)   # family [9], reading [17], given [9], reading [17]

# ELF name pools: (table, count, kind, stride) of (name ptr, reading ptr) pairs
POOL_TABLES = [(0x3CC630, 2030, 'F'), (0x3D0AC0, 69, 'F'),        # random family names (commoners, court)
               (0x3E0DC0, 3507, 'G'), (0x3E9CE0, 50, 'G'), (0x3E9140, 278, 'G'),  # given: default, court, monks
               (0x3FBD20, 850, 'G'),                               # princess given names (copy 1 of 3)
               (0x39FB10, 15, 'G'), (0x39FB90, 10, 'G'),           # default given names (雑兵 officers)
               (0x3EA290, 1, 'F'), (0x3EA2B0, 1, 'F')]             # 伝令, 雑兵 (name, reading are adjacent)
COURT_NOBLES = (0x39F930, 8)        # (family, given, family reading, given reading) ptrs
CHRISTIAN = (0x3EA120, 30)          # (name, reading) pairs, English from pools.json
RENAMES = (0x3AD8E0, 0x3ADA28)      # event rename / compare constants (name, reading) pairs
POOL_EN = {0x3EA290: 'Messenger', 0x3EA2B0: 'Foot Soldier'}

# ninja: 3 copies x (male epithets, male given, kunoichi epithets, kunoichi given)
NINJA_TABLES = [(0x3BDA10, 0x3BDFB0, 0x3BE440, 0x3BE7F0), (0x3F20A0, 0x3F2640, 0x3F2AD0, 0x3F2E80),
                (0x3F8B30, 0x3F90D0, 0x3F9560, 0x3F9910)]
NINJA_COUNTS = (62, 110, 62, 110)
NINJA_LISTS = ('ninja_epithets', 'ninja_given', 'kunoichi_epithets', 'kunoichi_given')
NINJA_FMT = (0x3BEBC0, 0x3F3220, 0x3F9CB8)

# hooks: (site, original jal target) -> stub
PERSON_HOOKS = {   # record class: (family jal site, given jal site, full-name function)
    'person': (0x12BFF8, 0x12C020, 0x12F0E0),
    'woman': (0x17DB44, 0x17DB6C, 0x17E2F0),
    'puk': (0x1AD154, 0x1AD17C, 0x1AD340),
}
SIMPLE_HOOKS = {0x186DE0: 'q', 0x18BE10: 't', 0x18E220: 'T', 0x288FA0: 'o', 0x18F370: 'p',
                0x134600: 'r', 0x1AF7E0: 'c'}    # jal CString=char* (a1 = record name)
SAVE_COPIES = (0x1C71E8, 0x1C71F8, 0x1C7208)   # jal memcpy(header field, name, n): NUL-terminate
MEMCPY = 0x124DE8
# reading getters (jal CString=char*, a1 = record reading = name + delta): show the English name
READING_HOOKS = {0x18F3C0: ('p', 9), 0x186E30: ('q', 13), 0x18BE60: ('t', 13), 0x1AF830: ('c', 9)}
# person/woman reading props 1/3/61 -> English family/given/full name (sorting, list columns)
PERSON_READING_HOOKS = {'person': (0x12C00C, 0x12C034, 0x12D014), 'woman': (0x17DB58, 0x17DB80, 0x17DD20)}
CASTLE_FULL = 0x1AF88C              # jal Format(out, "%s%s", name, suffix)
GETTERS = {0x12BFA0: 'person', 0x17DAF0: 'woman', 0x1AD100: 'puk', 0x18DF90: 'title', 0x288CE0: 'office'}
# getter calls whose result is written back into a record (strcpy setters) or compared
# with Japanese strings: (image, site); found by a scan (getter jal followed by a setter
# or strcmp within 5 calls) + notes/survey/names_persons_re.md
RAW_SITES = [('e', a) for a in (
    0x129A3C, 0x129A50, 0x129A64, 0x129A78, 0x19D5C8, 0x19D5DC, 0x19D668, 0x19D67C, 0x1BC50C, 0x2A2BA4,
    0x30F8D0, 0x30F8E4, 0x343D68, 0x343D7C, 0x358D60, 0x358DD4, 0x38B07C, 0x3437D4, 0x3437E8, 0x38BD98,
    0x38BDAC, 0x363278, 0x363294)] + [('g', a) for a in (
    0x19C0B34, 0x19C0B48, 0x19C8620, 0x19C8634, 0x19C87C8, 0x19C87DC, 0x19C9354, 0x19C9368, 0x19CCC34,
    0x19CCC48, 0x19CDD48, 0x19CDD5C, 0x19D306C, 0x19D3080, 0x19D3A58, 0x19D3A6C, 0x19D3A80, 0x19D3A94)] + [
    ('s', 0x1A414C8), ('s', 0x1A414DC)]
# full-reading labels next to names (officer screen and two more): the getter call is dropped,
# the label keeps the empty string its CString was initialised with
READING_BLANK = (0x1F1EA8, 0x27BAC8, 0x27D34C)
CASTLE_READING_BLANK = (0x1EF958, 0x332F78)   # castle 0x1D (reading) labels: castle info panel, 0x332F00 screen
CASTLE_READING = 0x1AF8EC           # jal Format(out, "%s%s", reading, suffix kana) in GetFullReading 0x1AF8B0
                                    # (s1 castle, v0 = &suffix table[i].kana) -> English full name (sorting)
OVL_BASE = 0x198A000

def fnv(kind, parts):
    h = ((0x811C9DC5 ^ ord(kind)) * P32) & M32
    for i, p in enumerate(parts):
        if i:
            h = ((h ^ 0xFF) * P32) & M32
        for b in p:
            h = ((h ^ b) * P32) & M32
    return h

def sj(s):
    return s.encode('cp932')

def romaji(kana, given=False):
    r = names.romaji(kana, given)
    return re.sub('bee$', 'bei', r)

# ---------------------------------------------------------------- table

class Table:
    """kind + Japanese parts -> English; first writer wins for pool fallbacks, votes for records."""
    def __init__(self):
        self.votes = collections.defaultdict(collections.Counter)

    def vote(self, kind, parts, en, n=1):
        if en or kind == 's':
            self.votes[(kind, tuple(sj(p) for p in parts))][en] += n

    def fallback(self, kind, parts, en):
        k = (kind, tuple(sj(p) for p in parts))
        if en and k not in self.votes:
            self.votes[k][en] += 1

    def has(self, kind, parts):
        return (kind, tuple(sj(p) for p in parts)) in self.votes

    def resolved(self):
        """{(kind, parts): English}, [(key, Counter)] of keys with more than one English."""
        out, conflicts = {}, []
        for k, c in self.votes.items():
            out[k] = c.most_common(1)[0][0]
            if len(c) > 1:
                conflicts.append((k, c))
        return out, conflicts

def elf_str(elf, va):
    o = va - elfseg.VBASE + elfseg.FOFF
    return elf[o:elf.index(b'\0', o)].decode('cp932')

def elf_word(elf, va):
    return struct.unpack_from('<I', elf, va - elfseg.VBASE + elfseg.FOFF)[0]

def person_en(parts_en):
    return ' '.join(p for p in parts_en if p)

def build_table(elf, scens):
    t = Table()
    jp = names.japanese(scens)
    tls = {k: names.load_tl(k) for k in names.TABLES}
    # persons: exact record keys + part votes
    for i, forms in enumerate(jp['persons']):
        row = tls['persons'].get(i)
        for sk, ((fam, giv), (famr, givr)) in forms.items():
            if not (fam or giv) or row is None:
                continue
            en = names.english(row, sk)
            rec = (fam, famr, giv, givr)
            t.vote('n', rec, person_en(en))
            t.vote('f', rec, en[0])
            t.vote('g', rec, en[1])
            if fam:
                t.vote('F', (fam, famr), en[0])
            if giv:
                t.vote('G', (giv, givr), en[1])
    # women: given from tl/names/women.json, family from the persons' family votes
    fam_en = {k[1]: c.most_common(1)[0][0] for k, c in t.votes.items() if k[0] == 'F'}
    off, size = WOMEN_REC
    for j, scen in enumerate(scens):
        sk = names.SCEN_KEYS[j]
        for i in range(names.TABLES['women'][2]):
            r = scen[off + i * size:off + (i + 1) * size]
            fam, famr, giv, givr = (names.field(r[a:a + n]) for a, n in ((0, 9), (9, 17), (26, 9), (35, 17)))
            row = tls['women'].get(i)
            if not giv or row is None:
                continue
            g_en = names.english(row, sk)
            f_en = fam_en.get((sj(fam), sj(famr))) or (romaji(famr) if famr else '')
            rec = (fam, famr, giv, givr)
            t.vote('n', rec, person_en([f_en, g_en]))
            t.vote('f', rec, f_en)
            t.vote('g', rec, g_en)
            t.vote('G', (giv, givr), g_en)
            if fam:
                t.fallback('F', (fam, famr), f_en)
    # places, items, groups
    simple = {'provinces': 'p', 'regions': 'r', 'treasures': 't', 'courttitles': 'T', 'offices': 'o',
              'kunishu': 'q', 'pirates': 'q', 'bands': 'q'}
    for table, kind in simple.items():
        for i, forms in enumerate(jp[table]):
            row = tls[table].get(i)
            for sk, (nm, _) in forms.items():
                if nm[0] and row is not None:
                    t.vote(kind, (nm[0],), names.english(row, sk))
    # W: English -> short form, for text widgets too narrow for the full form (vwf.SQUEEZE)
    for table in SHORT_TABLES:
        for row in tls[table].values():
            if row.get('short'):
                t.vote('W', (row['en'],), row['short'])
    for en, short in load_ui_short().items():
        t.vote('W', (en,), short)
    off, size, count, _ = names.TABLES['castles']
    suffixes = [(elf_str(elf, elf_word(elf, SUFFIX_TABLE + 8 * k))) for k in range(16)]
    per_castle = collections.defaultdict(lambda: (set(), set()))      # id -> ({(jp, en)}, {suffix ids})
    for j, scen in enumerate(scens):
        sk = names.SCEN_KEYS[j]
        for i in range(count):
            r = scen[off + i * size:off + (i + 1) * size]
            nm = names.field(r[:9])
            row = tls['castles'].get(i)
            if nm and row is not None:
                en = names.english(row, sk)
                t.vote('c', (nm,), en)
                per_castle[i][0].add((nm, en))
                per_castle[i][1].add(r[CASTLE_SUFFIX])
    for k, suf in enumerate(suffixes):
        t.vote('s', (suf,), SUFFIX_EN[k])
        t.vote('S', (suf,), TYPE_EN[k])
    for i, (forms, sufs) in per_castle.items():
        for nm, en in forms:
            for k in sufs:
                tail = SUFFIX_EN[k]
                if tail == 'ji' and en.lower().endswith('ji'):
                    tail = ''
                t.vote('K', (nm, suffixes[k]), en + tail)
                if tail.strip():
                    t.fallback('W', (en + tail,), en)     # too wide: drop the suffix
                    t.fallback('W', (en + tail + ' Army',), en + ' Army')   # "%s Army" (e3befe8)
    # ELF pools: fill parts the records did not name
    for table, n, kind in POOL_TABLES:
        for k in range(n):
            a, b = elf_word(elf, table + 8 * k), elf_word(elf, table + 8 * k + 4)
            if table in POOL_EN:
                a, b = table, table + 8
            nm, rd = elf_str(elf, a), elf_str(elf, b)
            en = POOL_EN.get(table) or romaji(rd, kind == 'G')
            t.fallback(kind, (nm, rd), en)
    tab, n = COURT_NOBLES
    for k in range(n):
        fam, giv, famr, givr = (elf_str(elf, elf_word(elf, tab + 16 * k + 4 * x)) for x in range(4))
        t.fallback('F', (fam, famr), romaji(famr))
        t.fallback('G', (giv, givr), romaji(givr, True))
    pools = json.load(open(POOLS, encoding='utf-8'))
    tab, n = CHRISTIAN
    for k in range(n):
        nm, rd = (elf_str(elf, elf_word(elf, tab + 8 * k + 4 * x)) for x in range(2))
        t.vote('G', (nm, rd), pools['christian'][k], 100)
    for va in range(RENAMES[0], RENAMES[1] - 4, 4):     # (name, reading) pairs, not all 8-aligned
        nm, rd = elf_str(elf, elf_word(elf, va)), elf_str(elf, elf_word(elf, va + 4))
        if not re.fullmatch('[ぁ-ん]+', rd) or re.search('[ぁ-ん]', nm):
            continue
        if not t.has('F', (nm, rd)) and not t.has('G', (nm, rd)) and not t.has('c', (nm,)):
            t.fallback('F', (nm, rd), romaji(rd))
            t.fallback('G', (nm, rd), romaji(rd, True))
    return t

def entries(table):
    """sorted [(hash, kind, parts, English)]; fails on a hash collision of two keys."""
    res, conflicts = table.resolved()
    by_hash = {}
    for (kind, parts), en in res.items():
        h = fnv(kind, parts)
        if h in by_hash and by_hash[h][:2] != (kind, parts):
            raise ValueError('namehook: hash collision %r / %r' % (by_hash[h][:2], (kind, parts)))
        by_hash[h] = (kind, parts, en)
    return sorted((h,) + v for h, v in by_hash.items()), conflicts

# ---------------------------------------------------------------- code

def raw_flag_code(raw, value):
    return [('lui', 't9', hi(raw)), ('sw', value, lo(raw), 't9')]

def tr_code(tab, tab_end):
    """tr: t0 kind, t1..t4 strings (0 ends) -> v0 English or 0. Leaf; keeps a0-a3, s*.
    tr1 / tr2 / tr4rec: shorthands (one string in t1, two in t1/t2, a record at a0)."""
    return [
        'tr4rec:',
        ('addiu', 't1', 'a0', 4), ('addiu', 't2', 'a0', 0xD), ('addiu', 't3', 'a0', 0x1E),
        ('b', 'tr'), ('addiu', 't4', 'a0', 0x27),
        'tr1:',
        ('or', 't2', 'zero', 'zero'),
        'tr2:',
        ('or', 't3', 'zero', 'zero'), ('or', 't4', 'zero', 'zero'),
        'tr:',
        ('lui', 'v0', 0x811C), ('ori', 'v0', 'v0', 0x9DC5),
        ('lui', 't9', P32 >> 16), ('ori', 't9', 't9', P32 & 0xFFFF),
        ('xor', 'v0', 'v0', 't0'), ('mult', 'v0', 'v0', 't9'),
        'tr_str:',
        ('lbu', 't6', 0, 't1'),
        'tr_chr:',
        ('beqz', 't6', 'tr_end'), ('addiu', 't1', 't1', 1),
        ('xor', 'v0', 'v0', 't6'), ('mult', 'v0', 'v0', 't9'),
        ('b', 'tr_chr'), ('lbu', 't6', 0, 't1'),
        'tr_end:',
        ('or', 't1', 't2', 'zero'), ('or', 't2', 't3', 'zero'), ('or', 't3', 't4', 'zero'),
        ('beqz', 't1', 'tr_find'), ('or', 't4', 'zero', 'zero'),
        ('ori', 't6', 'zero', 0xFF), ('xor', 'v0', 'v0', 't6'),
        ('b', 'tr_str'), ('mult', 'v0', 'v0', 't9'),
        'tr_find:',
        ('lui', 't5', hi(tab)), ('addiu', 't5', 't5', lo(tab)),
        ('lui', 't6', hi(tab_end)), ('addiu', 't6', 't6', lo(tab_end)),
        'tr_bs:',
        ('sltu', 'at', 't5', 't6'), ('beqz', 'at', 'tr_miss'), ('subu', 't7', 't6', 't5'),
        ('srl', 't7', 't7', 4), ('sll', 't7', 't7', 3), ('addu', 't7', 't5', 't7'),
        ('lw', 't8', 0, 't7'), ('beq', 't8', 'v0', 'tr_hit'), ('sltu', 'at', 't8', 'v0'),
        ('bnez', 'at', 'tr_right'), ('nop',),
        ('b', 'tr_bs'), ('or', 't6', 't7', 'zero'),
        'tr_right:',
        ('b', 'tr_bs'), ('addiu', 't5', 't7', 8),
        'tr_hit:',
        ('jr', 'ra'), ('lw', 'v0', 4, 't7'),
        'tr_miss:',
        ('jr', 'ra'), ('or', 'v0', 'zero', 'zero'),
    ]

def raw_check(raw, label):
    return [('lui', 'at', hi(raw)), ('lw', 'at', lo(raw), 'at'), ('bnez', 'at', label)]

PUSH = [('addiu', 'sp', 'sp', -16), ('sd', 'ra', 0, 'sp')]
POP = [('ld', 'ra', 0, 'sp'), ('addiu', 'sp', 'sp', 16)]

def part_stub(p, raw, rec_kind, part_kind, off, orig):
    """family / given getter (a0 record, a1 CString*): record key, then part key."""
    return [
        p + ':'] + raw_check(raw, p + '_orig') + [('nop',)] + PUSH + [
        ('ori', 't0', 'zero', ord(rec_kind)), ('jal', 'tr4rec'), ('nop',),
        ('bnez', 'v0', p + '_hit'), ('ori', 't0', 'zero', ord(part_kind)),
        ('addiu', 't1', 'a0', off), ('jal', 'tr2'), ('addiu', 't2', 'a0', off + 9),
        ('bnez', 'v0', p + '_hit'), ('nop',)] + POP + [
        p + '_orig:', ('j', orig), ('nop',),
        p + '_hit:'] + POP + [
        ('or', 'a0', 'a1', 'zero'), ('j', ASSIGN), ('or', 'a1', 'v0', 'zero')]

def full_stub(p, raw, fmt_jp, fmt_sp, orig=None):
    """full name (a0 record, a1 CString*), replaces the whole Format("%s%s", +4, +0x1E) method
    (orig: called through a jal instead, raw goes to orig: the full-reading method)."""
    raw_path = [p + '_raw:', ('j', orig), ('nop',)] if orig else [
        p + '_raw:',
        ('addiu', 'a2', 'a0', 4), ('addiu', 'a3', 'a0', 0x1E),
        ('or', 'a0', 'a1', 'zero'), ('lui', 'a1', hi(fmt_jp)), ('j', FORMAT), ('addiu', 'a1', 'a1', lo(fmt_jp))]
    return [
        p + ':'] + raw_check(raw, p + '_raw') + [('nop',)] + PUSH + [
        ('ori', 't0', 'zero', ord('n')), ('jal', 'tr4rec'), ('nop',),
        ('bnez', 'v0', p + '_hit'), ('ori', 't0', 'zero', ord('F')),
        ('addiu', 't1', 'a0', 4), ('jal', 'tr2'), ('addiu', 't2', 'a0', 0xD),
        ('addiu', 'a2', 'a0', 4), ('movn', 'a2', 'v0', 'v0'),
        ('ori', 't0', 'zero', ord('G')), ('addiu', 't1', 'a0', 0x1E), ('jal', 'tr2'), ('addiu', 't2', 'a0', 0x27),
        ('addiu', 'a3', 'a0', 0x1E), ('movn', 'a3', 'v0', 'v0')] + POP + [
        ('or', 'a0', 'a1', 'zero'), ('lui', 'a1', hi(fmt_sp)), ('j', FORMAT), ('addiu', 'a1', 'a1', lo(fmt_sp))] + raw_path + [
        p + '_hit:'] + POP + [
        ('or', 'a0', 'a1', 'zero'), ('j', ASSIGN), ('or', 'a1', 'v0', 'zero')]

def simple_stub(p, raw, kind, reg='a1', target=ASSIGN, delta=0):
    """jal CString=char* (a0 CString*, a1 Japanese name) -> English if known
    (or another call whose string argument is in reg; the key is the string at reg - delta)."""
    return [
        p + ':'] + raw_check(raw, p + '_go') + [('ori', 't0', 'zero', ord(kind))] + PUSH + [
        ('jal', 'tr1'), ('addiu', 't1', reg, -delta)] + POP + [
        ('movn', reg, 'v0', 'v0'),
        p + '_go:', ('j', target), ('nop',)]

def castle_stub(p, raw):
    """jal Format(a0 out, a1 "%s%s", a2 name, a3 suffix): K(name, suffix), else c(name) + suffix."""
    return [
        p + ':'] + raw_check(raw, p + '_go') + [('nop',)] + PUSH + [
        ('ori', 't0', 'zero', ord('K')), ('or', 't1', 'a2', 'zero'), ('jal', 'tr2'), ('or', 't2', 'a3', 'zero'),
        ('bnez', 'v0', p + '_hit'), ('ori', 't0', 'zero', ord('c')),
        ('jal', 'tr1'), ('or', 't1', 'a2', 'zero'),
        ('movn', 'a2', 'v0', 'v0'), ('ori', 't0', 'zero', ord('s')),
        ('jal', 'tr1'), ('or', 't1', 'a3', 'zero'),
        ('movn', 'a3', 'v0', 'v0')] + POP + [
        p + '_go:', ('j', FORMAT), ('nop',),
        p + '_hit:'] + POP + [
        ('j', ASSIGN), ('or', 'a1', 'v0', 'zero')]

def castle_reading_stub(p, raw, castle_n):
    """CASTLE_READING: not raw -> castle_n with (name s1+5, suffix kanji) instead of the readings."""
    return [
        p + ':'] + raw_check(raw, p + '_go') + [('nop',),
        ('addiu', 'a2', 's1', 5), ('j', castle_n), ('lw', 'a3', -4, 'v0'),
        p + '_go:', ('j', FORMAT), ('nop',)]

def raw_stub(p, raw, getter):
    return [p + ':'] + PUSH + [('ori', 't8', 'zero', 1)] + raw_flag_code(raw, 't8') + [
        ('jal', getter), ('nop',)] + raw_flag_code(raw, 'zero') + [
        ('ld', 'ra', 0, 'sp'), ('jr', 'ra'), ('addiu', 'sp', 'sp', 16)]

def shorten_stub(p):
    """vwf SHORTEN: a0 CString* -> its short form (W) assigned, v0 1; else v0 0."""
    return [p + ':'] + PUSH + [
        ('sw', 'a0', 8, 'sp'), ('lw', 't1', 0, 'a0'),
        ('jal', 'tr1'), ('ori', 't0', 'zero', ord('W')),
        ('beqz', 'v0', p + '_out'), ('lw', 'a0', 8, 'sp'),
        ('jal', ASSIGN), ('or', 'a1', 'v0', 'zero'),
        ('ori', 'v0', 'zero', 1),
        p + '_out:'] + POP + [('jr', 'ra'), ('nop',)]

def memz_stub(p):
    """memcpy(a0, a1, a2), then a0[a2 - 1] = 0 (a cut name instead of one glued to the next field)."""
    return [p + ':'] + PUSH + [
        ('addu', 't0', 'a0', 'a2'), ('jal', MEMCPY), ('sw', 't0', 8, 'sp'),
        ('lw', 't0', 8, 'sp'), ('sb', 'zero', -1, 't0'),
        ('ld', 'ra', 0, 'sp'), ('jr', 'ra'), ('addiu', 'sp', 'sp', 16)]

def jal_target(w, site):
    assert w >> 26 == 3, 'namehook: %#x is not a jal' % site
    return (w & 0x3FFFFFF) << 2 | site & 0xF0000000

def jal(target):
    return struct.pack('<I', 0x0C000000 | (target >> 2) & 0x3FFFFFF)

# ---------------------------------------------------------------- apply

def apply(elf, clean, ovl, seg, scens, shorten=None):
    """Table + stubs into the segment, hooks into the ELF and the overlays ({'s': bytes, 'g': bytes}).
    clean = the unpatched ELF (Japanese strings). Returns (entries, conflicts)."""
    ents, conflicts = entries(build_table(clean, scens))
    raw = seg.reserve(4)
    strings, pos = {}, bytearray()
    def string(s):
        if s not in strings:
            strings[s] = len(pos)
            pos.extend(s.encode('ascii') + b'\0')
        return strings[s]
    for e in ents:
        string(e[3])
    fmt_sp_off = string('%s %s')
    fmt_jp = 0x3B8648
    assert elf_str(clean, fmt_jp) == '%s%s'
    pools = json.load(open(POOLS, encoding='utf-8'))
    for lst in NINJA_LISTS:
        for s in pools[lst]:
            string(s)
    str_base = seg.add(bytes(pos), 4)
    for k in range(16):
        jp = clean[elf_word(clean, SUFFIX_TABLE + 8 * k) - elfseg.VBASE + elfseg.FOFF:]
        jp = jp[:jp.index(b'\0') + 1]
        elfseg.patch(elf, SUFFIX_TABLE + 8 * k, struct.pack('<I', seg.add(jp, 4)))
    tab = seg.add(b''.join(struct.pack('<II', h, str_base + strings[en]) for h, _, _, en in ents), 8)
    tab_end = tab + 8 * len(ents)
    # code
    word = lambda va: elf_word(elf, va)
    code = tr_code(tab, tab_end)
    patches = []                    # (image, site, bytes-producing fn(labels))
    for cls, (fam_site, giv_site, full_fn) in PERSON_HOOKS.items():
        code += part_stub(cls + '_f', raw, 'f', 'F', 4, jal_target(word(fam_site), fam_site))
        code += part_stub(cls + '_g', raw, 'g', 'G', 0x1E, jal_target(word(giv_site), giv_site))
        code += full_stub(cls + '_n', raw, fmt_jp, str_base + fmt_sp_off)
        assert word(full_fn) == 0x0080102D and word(full_fn + 0x10) >> 16 == 0x3C05, 'full name %x changed' % full_fn
        patches += [('e', fam_site, cls + '_f', 'jal'), ('e', giv_site, cls + '_g', 'jal'), ('e', full_fn, cls + '_n', 'j')]
    for cls, sites in PERSON_READING_HOOKS.items():
        f, g, n = (jal_target(word(x), x) for x in sites)
        code += part_stub(cls + '_fr', raw, 'f', 'F', 4, f)
        code += part_stub(cls + '_gr', raw, 'g', 'G', 0x1E, g)
        code += full_stub(cls + '_nr', raw, fmt_jp, str_base + fmt_sp_off, n)
        patches += [('e', sites[0], cls + '_fr', 'jal'), ('e', sites[1], cls + '_gr', 'jal'), ('e', sites[2], cls + '_nr', 'jal')]
    for site, (kind, delta) in READING_HOOKS.items():
        assert jal_target(word(site), site) == ASSIGN, 'reading hook %x changed' % site
        code += simple_stub('r%x' % site, raw, kind, delta=delta)
        patches.append(('e', site, 'r%x' % site, 'jal'))
    for site, kind in SIMPLE_HOOKS.items():
        assert jal_target(word(site), site) == ASSIGN, 'simple hook %x changed' % site
        code += simple_stub('s%x' % site, raw, kind)
        patches.append(('e', site, 's%x' % site, 'jal'))
    assert jal_target(word(CASTLE_FULL), CASTLE_FULL) == FORMAT
    code += castle_stub('castle_n', raw)
    assert jal_target(word(TYPE_SITE), TYPE_SITE) == FORMAT
    code += simple_stub('castle_type', raw, 'S', 'a2', FORMAT)
    patches.append(('e', TYPE_SITE, 'castle_type', 'jal'))
    patches.append(('e', CASTLE_FULL, 'castle_n', 'jal'))
    assert jal_target(word(CASTLE_READING), CASTLE_READING) == FORMAT and word(CASTLE_READING - 0x2C) == 0x0080882D
    code += castle_reading_stub('castle_r', raw, 'castle_n')
    patches.append(('e', CASTLE_READING, 'castle_r', 'jal'))
    code += memz_stub('memz')
    code += shorten_stub('shorten')
    for site in SAVE_COPIES:
        assert jal_target(word(site), site) == MEMCPY, 'save copy %x changed' % site
        patches.append(('e', site, 'memz', 'jal'))
    imgs = {'e': elf, 's': ovl['s'], 'g': ovl['g']}
    def img_word(img, va):
        if img == 'e':
            return word(va)
        return struct.unpack_from('<I', imgs[img], va - OVL_BASE)[0]
    for g in GETTERS:
        code += raw_stub('raw_%x' % g, raw, g)
    for img, site in RAW_SITES:
        g = jal_target(img_word(img, site), site)
        assert g in GETTERS, 'raw site %s%x calls %x' % (img, site, g)
        patches.append((img, site, 'raw_%x' % g, 'jal'))
    n = len([l for l in code if not isinstance(l, str)])
    at = seg.reserve(4 * n)
    seg.put(at, asm.assemble(at, code))
    lab = asm.labels(at, code)
    for img, site, label, op in patches:
        b = jal(lab[label]) if op == 'jal' else asm.assemble(site, [('j', lab[label]), ('nop',)])
        if img == 'e':
            elfseg.patch(elf, site, b)
        else:
            imgs[img][site - OVL_BASE:site - OVL_BASE + len(b)] = b
    if shorten:
        seg.put(shorten, asm.assemble(shorten, [('j', lab['shorten']), ('nop',)]))
    for site in READING_BLANK:
        assert jal_target(word(site), site) == 0x12BFA0 and 0x2405003D in [word(site - 4 * k) for k in range(1, 12)], \
            'reading label %x changed' % site
        elfseg.patch(elf, site, bytes(4))
    for site in CASTLE_READING_BLANK:
        assert jal_target(word(site), site) == 0x1ADF70 and 0x2405001D in [word(site - 4 * k) for k in range(-1, 5)], \
            'castle reading label %x changed' % site
        elfseg.patch(elf, site, bytes(4))
    # ninja lists
    for copy in NINJA_TABLES:
        for lst, t0, n in zip(NINJA_LISTS, copy, NINJA_COUNTS):
            en = pools[lst]
            first = NINJA_TABLES[0][NINJA_LISTS.index(lst)]
            by_jp = {}
            for k in range(len(en)):
                by_jp.setdefault(elf_str(clean, elf_word(clean, first + 8 * k)), en[k])
            for k in range(n):
                jp = elf_str(clean, elf_word(clean, t0 + 8 * k))
                elfseg.patch(elf, t0 + 8 * k, struct.pack('<I', str_base + strings[by_jp[jp]]))
    for va in NINJA_FMT:
        o = va - elfseg.VBASE + elfseg.FOFF
        assert elf[o:o + 8] == b'%s%s\0\0\0\0', 'ninja format %x' % va
        elfseg.patch(elf, va, b'%s %s\0\0\0')
    return ents, conflicts

# ---------------------------------------------------------------- checks / cli

def check_lengths(ents):
    """Fixed buffers downstream of the getters (overflow.py)."""
    errs = []
    for h, kind, parts, en in ents:
        n = len(en) + len(' clan') if kind == 'f' else len(en)
        if kind in 'nf' and n > overflow.SAVE_SLOT:
            errs.append('%s: %r is %d bytes > %d (save slot summary)' % (kind, en, n, overflow.SAVE_SLOT))
        if len(en) > overflow.VAR:
            errs.append('%s: %r is %d bytes > overflow.VAR' % (kind, en, len(en)))
    return errs

def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'stats'
    scens = names.scenarios()
    import iso
    elf = iso.read_file(setup.CLEAN, iso.ELF_NAME)
    ents, conflicts = entries(build_table(elf, scens))
    if cmd == 'stats':
        c = collections.Counter(e[1] for e in ents)
        print('%d entries: %s' % (len(ents), ' '.join('%s %d' % kv for kv in sorted(c.items()))))
        print('%d keys with several English (most common used):' % len(conflicts))
        for (kind, parts), cnt in conflicts[:40]:
            print('  %s %s %s' % (kind, '|'.join(p.decode('cp932') for p in parts), dict(cnt)))
        for e in check_lengths(ents):
            print(e)
        longest = sorted((e for e in ents if e[1] == 'n'), key=lambda e: -len(e[3]))[:5]
        print('longest full names:', [e[3] for e in longest])
    elif cmd == 'find':
        q = sys.argv[2].lower()
        for h, kind, parts, en in ents:
            if q in en.lower():
                print('%08x %s %s -> %s' % (h, kind, '|'.join(p.decode('cp932') for p in parts), en))

if __name__ == '__main__':
    main()
