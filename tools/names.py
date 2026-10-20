"""Names: Japanese from the scenario files on the disc, English from tl/names/.

The twelve scenario files (NB10 entries 5-16 = scenarios s1-s12, SCEDAT00-11) all
have the same layout; each table is a run of fixed-size records with a name field
and a full-width hiragana reading field (TABLES below). The same record can be named
differently per scenario (石川信直 / 南部信直, 稲葉山 / 岐阜), so the tl files are keyed
by record index with optional per-scenario overrides:

  tl/names/persons.json  {"id": 13, "en": ["Nanbu", "Nobunao"], "s1": ["Ishikawa", "Nobunao"], ...}
  tl/names/castles.json  {"id": 78, "en": "Gifu", "s1": "Kawate", "s2": "Inabayama", ...}

"en" is the form used in most scenarios, "sN" only where another Japanese name is used.
An optional "short" is a cut form for fixed-size fields when "en" is longer than
the Japanese field (bytes - 1, see TABLES), e.g. a treasure name copied into a record.

  names.py export   -> script/names/<table>.json (per id: Japanese per scenario,
                       readings, romanised reading, current English)
  names.py check    -> validate tl/names/ against the disc
  names.py find X   -> rows whose Japanese, reading or English contain X (all tables;
                       uses script/names/, run export first)
"""
import collections, json, os, re, sys, unicodedata

sys.path.insert(0, os.path.dirname(__file__))
import iso, nbx, overflow, setup

ROOT = setup.ROOT
TL_DIR = os.path.join(setup.TL, 'names')
SCRIPT_DIR = os.path.join(setup.SCRIPT, 'names')
SCENARIOS = range(5, 17)            # NB10 entries; scenario sN = entry N + 4
SCEN_KEYS = ['s%d' % (k - 4) for k in SCENARIOS]

# table: (offset, record size, count, [(name offset, size, reading offset, size)])
# One name part except persons (family, given). Readings are full-width hiragana.
TABLES = {
    'regions':     (0x5A8, 19, 11, [(0, 5, 5, 14)]),
    'provinces':   (0x679, 39, 64, [(0, 9, 9, 17)]),
    'castles':     (0x103A, 56, 250, [(0, 9, 9, 17)]),        # incl. temples, ports, churches
    'persons':     (0x46E9, 122, 1990, [(0, 9, 9, 17), (0x1A, 9, 0x23, 17)]),   # id at +0x78
    'women':       (0x3FB5F, 70, 210, [(0, 9, 9, 17)]),        # +0x2C family [9] (birth clan, not unique)
    'kunishu':     (0x4EABF, 460, 64, [(0, 13, 13, 31)]),      # 国衆 / 門徒衆 local powers
    'pirates':     (0x55DBF, 461, 16, [(0, 13, 13, 31)]),
    'bands':       (0x57A8F, 307, 20, [(0, 13, 13, 31)]),      # 村衆, 町衆, ninja 衆
    'treasures':   (0x6B011, 61, 460, [(0, 13, 13, 31)]),
    'courttitles': (0x72AE5, 45, 350, [(0, 13, 13, 25)]),
    'offices':     (0x7686B, 38, 75, [(0, 11, 11, 21)]),
}
PERSON_PARTS = 2

def field(b):
    return b.split(b'\0')[0].decode('cp932', 'replace')

def table_rows(scen, table):
    """[[(name, reading) per part]] of one scenario file."""
    off, size, count, parts = TABLES[table]
    out = []
    for i in range(count):
        r = scen[off + i * size:off + (i + 1) * size]
        out.append([(field(r[a:a + n]), field(r[b:b + m])) for a, n, b, m in parts])
    return out

def scenarios(path=setup.CLEAN):
    recs = iso.records(path)
    elf = iso.read_file(path, iso.ELF_NAME, recs)
    archive = iso.read_file(path, nbx.NAME, recs)
    return [nbx.entry(archive, elf, k) for k in SCENARIOS]

def japanese(scens):
    """{table: [{scenario key: (names tuple, readings tuple)}]}."""
    out = {}
    for t in TABLES:
        per = [table_rows(s, t) for s in scens]
        out[t] = [{k: (tuple(p[0] for p in per[j][i]), tuple(p[1] for p in per[j][i]))
                   for j, k in enumerate(SCEN_KEYS)} for i in range(TABLES[t][2])]
    return out

def common(forms):
    """Most frequent value of {scenario: value} (earliest scenario on a tie)."""
    c = collections.Counter(forms.values())
    best = max(c.values())
    return next(v for v in forms.values() if c[v] == best)

# ---------------------------------------------------------------- romanisation

KANA = {
    'きゃ': 'kya', 'きゅ': 'kyu', 'きょ': 'kyo', 'しゃ': 'sha', 'しゅ': 'shu', 'しょ': 'sho',
    'ちゃ': 'cha', 'ちゅ': 'chu', 'ちょ': 'cho', 'にゃ': 'nya', 'にゅ': 'nyu', 'にょ': 'nyo',
    'ひゃ': 'hya', 'ひゅ': 'hyu', 'ひょ': 'hyo', 'みゃ': 'mya', 'みゅ': 'myu', 'みょ': 'myo',
    'りゃ': 'rya', 'りゅ': 'ryu', 'りょ': 'ryo', 'ぎゃ': 'gya', 'ぎゅ': 'gyu', 'ぎょ': 'gyo',
    'じゃ': 'ja', 'じゅ': 'ju', 'じょ': 'jo', 'ぢゃ': 'ja', 'ぢゅ': 'ju', 'ぢょ': 'jo',
    'びゃ': 'bya', 'びゅ': 'byu', 'びょ': 'byo', 'ぴゃ': 'pya', 'ぴゅ': 'pyu', 'ぴょ': 'pyo',
    'てぃ': 'ti', 'でぃ': 'di', 'ふぁ': 'fa', 'ふぃ': 'fi', 'ふぇ': 'fe', 'ふぉ': 'fo',
    'うぃ': 'wi', 'うぇ': 'we', 'うぉ': 'wo', 'しぇ': 'she', 'じぇ': 'je', 'ちぇ': 'che',
    'あ': 'a', 'い': 'i', 'う': 'u', 'え': 'e', 'お': 'o',
    'か': 'ka', 'き': 'ki', 'く': 'ku', 'け': 'ke', 'こ': 'ko',
    'さ': 'sa', 'し': 'shi', 'す': 'su', 'せ': 'se', 'そ': 'so',
    'た': 'ta', 'ち': 'chi', 'つ': 'tsu', 'て': 'te', 'と': 'to',
    'な': 'na', 'に': 'ni', 'ぬ': 'nu', 'ね': 'ne', 'の': 'no',
    'は': 'ha', 'ひ': 'hi', 'ふ': 'fu', 'へ': 'he', 'ほ': 'ho',
    'ま': 'ma', 'み': 'mi', 'む': 'mu', 'め': 'me', 'も': 'mo',
    'や': 'ya', 'ゆ': 'yu', 'よ': 'yo', 'ら': 'ra', 'り': 'ri', 'る': 'ru', 'れ': 're', 'ろ': 'ro',
    'わ': 'wa', 'ゐ': 'i', 'ゑ': 'e', 'を': 'o', 'ん': 'n', 'ゔ': 'vu',
    'が': 'ga', 'ぎ': 'gi', 'ぐ': 'gu', 'げ': 'ge', 'ご': 'go',
    'ざ': 'za', 'じ': 'ji', 'ず': 'zu', 'ぜ': 'ze', 'ぞ': 'zo',
    'だ': 'da', 'ぢ': 'ji', 'づ': 'zu', 'で': 'de', 'ど': 'do',
    'ば': 'ba', 'び': 'bi', 'ぶ': 'bu', 'べ': 'be', 'ぼ': 'bo',
    'ぱ': 'pa', 'ぴ': 'pi', 'ぷ': 'pu', 'ぺ': 'pe', 'ぽ': 'po',
    'ぁ': 'a', 'ぃ': 'i', 'ぅ': 'u', 'ぇ': 'e', 'ぉ': 'o',
}

def hiragana(s):
    """Half-width / full-width katakana -> hiragana."""
    s = unicodedata.normalize('NFKC', s)
    return ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in s)

def syllables(kana):
    out, i = [], 0
    while i < len(kana):
        if kana[i] == 'っ' and i + 1 < len(kana):
            nxt = KANA.get(kana[i + 1:i + 3]) or KANA.get(kana[i + 1], '')
            out.append('t' if nxt.startswith('ch') else nxt[:1])
            i += 1
        elif kana[i:i + 2] in KANA:
            out.append(KANA[kana[i:i + 2]])
            i += 2
        elif kana[i] == 'ー':
            out.append('')
            i += 1
        else:
            out.append(KANA.get(kana[i], kana[i]))
            i += 1
    return out

def romaji(kana, given=False):
    """Hepburn romanisation of a reading with long vowels written short, as in
    Taiko 5 and Nobunaga DS 2 (Hojo Ujiyasu, Yuki, Choin): ou/oo -> o and uu -> u
    when the second vowel is its own kana, except that a vowel after an already long
    vowel starts a new word (おおうち Ouchi), ou before e stays (いのうえ Inoue, しょうえ
    Shoue, but とうえもん Toemon) and a given name ending in u + うじ (氏) keeps it
    (かずうじ Kazuuji; not ぜんつうじ Zentsuji)."""
    syl = syllables(hiragana(kana))
    out, long_ = '', False
    for j, s in enumerate(syl):
        nxt = syl[j + 1] if j + 1 < len(syl) else ''
        prev = out[-1:] if out else ''
        rest = ''.join(syl[j + 1:])
        if not long_ and s == 'u' and prev in ('o', 'u'):
            keep = (prev == 'o' and nxt[:1] == 'e' and not rest.startswith('emon')
                    or given and prev == 'u' and rest == 'ji' and 'y' not in out[-3:]
                    and out[-3:] not in ('shu', 'chu') and out[-2:] != 'ju')
            if not keep:
                long_ = True
                continue
        if not long_ and s == 'o' and prev == 'o':
            long_ = True
            continue
        long_ = False
        out += s
    return out.capitalize()

# ---------------------------------------------------------------- tl

def tl_path(table):
    return os.path.join(TL_DIR, table + '.json')

def load_tl(table):
    p = tl_path(table)
    if not os.path.exists(p):
        return {}
    return {r['id']: r for r in json.load(open(p, encoding='utf-8'))}

def write_tl(table, rows):
    """One row per line, keys in a fixed order (stable diffs)."""
    order = ['id', 'en', 'short'] + SCEN_KEYS
    lines = []
    for r in sorted(rows, key=lambda r: r['id']):
        r = {k: r[k] for k in order if k in r} | {k: v for k, v in r.items() if k not in order}
        lines.append(json.dumps(r, ensure_ascii=False))
    os.makedirs(TL_DIR, exist_ok=True)
    with open(tl_path(table), 'w', encoding='utf-8') as f:
        f.write('[\n' + ',\n'.join(lines) + '\n]\n')

def english(row, scen_key):
    """English for one scenario (list for persons, str otherwise)."""
    return row.get(scen_key, row['en'])

def is_empty(names):
    return not any(names)

def check(jp=None, quiet=False):
    """Validate tl/names/: every non-empty record has English, overrides only where
    the Japanese differs from the common form, no Japanese in tl. Returns errors."""
    if jp is None:
        jp = japanese(scenarios())
    errs = []
    for t, rows in jp.items():
        tl = load_tl(t)
        if not tl and not os.path.exists(tl_path(t)):
            errs.append('%s: tl/names/%s.json missing' % (t, t))
            continue
        nparts = len(TABLES[t][3])
        for i, forms in enumerate(rows):
            names = {k: v[0] for k, v in forms.items()}
            if all(is_empty(v) for v in names.values()):
                continue
            r = tl.get(i)
            if r is None:
                errs.append('%s %d: no English' % (t, i))
                continue
            base = common(names)
            for k, v in r.items():
                if k in ('id', 'short'):
                    continue
                if k != 'en' and k not in SCEN_KEYS:
                    errs.append('%s %d: unknown key %r' % (t, i, k))
                    continue
                vals = v if isinstance(v, list) else [v]
                if len(vals) != nparts or not all(isinstance(x, str) for x in vals):
                    errs.append('%s %d %s: expected %d string(s)' % (t, i, k, nparts))
                    continue
                if any(re.search(r'[^\x20-\x7e]', x) for x in vals):
                    errs.append('%s %d %s: non-ASCII %r' % (t, i, k, v))
                if any(x != x.strip() or not x for x in vals if base != ('',) * nparts):
                    if not (t == 'persons' and any(not p for p in base)):
                        errs.append('%s %d %s: empty or padded %r' % (t, i, k, v))
            field_max = TABLES[t][3][0][1] - 1
            for k, v in r.items():
                if k == 'id' or not isinstance(v, (str, list)):
                    continue
                n = len(' '.join(v)) if isinstance(v, list) else len(v)
                if k != 'short' and n > overflow.VAR:
                    errs.append('%s %d %s: %d bytes > overflow.VAR %d ({02} variable buffer model)'
                                % (t, i, k, n, overflow.VAR))
            if t != 'persons':
                if 'short' in r and len(r['short']) > field_max:
                    errs.append('%s %d: short %r is %d bytes > field %d' % (t, i, r['short'], len(r['short']), field_max))
            for k in SCEN_KEYS:
                if names[k] != base and k not in r:
                    errs.append('%s %d: %s is named differently (%s) but has no %s'
                                % (t, i, k, ''.join(names[k]), k))
    if not quiet:
        for e in errs[:50]:
            print(e)
        if len(errs) > 50:
            print('... %d errors' % len(errs))
    return errs

def export(jp=None):
    """script/names/<table>.json: Japanese per scenario + readings + English."""
    if jp is None:
        jp = japanese(scenarios())
    os.makedirs(SCRIPT_DIR, exist_ok=True)
    for t, rows in jp.items():
        tl = load_tl(t)
        out = []
        for i, forms in enumerate(rows):
            names = {k: v for k, v in forms.items()}
            base = common(names)
            row = {'id': i, 'jp': list(base[0]), 'reading': list(base[1]),
                   'romaji': [romaji(x, k == 1) for k, x in enumerate(base[1])]}
            other = {k: list(v[0]) for k, v in names.items() if v != base}
            if other:
                row['jp_scen'] = other
            if i in tl:
                row['tl'] = tl[i]
            out.append(row)
        with open(os.path.join(SCRIPT_DIR, t + '.json'), 'w', encoding='utf-8') as f:
            json.dump(out, f, ensure_ascii=False, indent=0)

def find(q):
    ql = q.lower()
    for t in TABLES:
        p = os.path.join(SCRIPT_DIR, t + '.json')
        tl = load_tl(t)
        for r in json.load(open(p, encoding='utf-8')):
            t_row = tl.get(r['id'], {})
            jp = [''.join(r['jp'])] + [''.join(v) for v in r.get('jp_scen', {}).values()]
            en = json.dumps({k: v for k, v in t_row.items() if k != 'id'}, ensure_ascii=False)
            if any(q in x for x in jp) or q in ''.join(r['reading']) or ql in en.lower():
                scen = ' ' + ' '.join('%s:%s' % (k, ''.join(v)) for k, v in r['jp_scen'].items()) if 'jp_scen' in r else ''
                print('%-11s %4d %s (%s)%s -> %s' % (t, r['id'], ''.join(r['jp']), ''.join(r['reading']), scen, en))

def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'check'
    if cmd == 'find':
        return find(sys.argv[2])
    jp = japanese(scenarios())
    if cmd == 'export':
        export(jp)
    errs = check(jp)
    if errs:
        sys.exit(1)
    print('names ok')

if __name__ == '__main__':
    main()
