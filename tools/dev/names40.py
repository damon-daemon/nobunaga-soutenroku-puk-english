"""Block 40 name-only lines from tl/names (phase 5b).

Block 40 pairs a name line with each description: officers 0-2999 (even = "name {1B}k reading
{1B}H years", odd = bio), other-era heroes 3003-3797 (odd = name), treasures 3799-4717, court
titles 4719-5417 ("name<IDSP>reading"), offices 5419-5567, castles 5569-6067 ("name<IDSP>type").
Static RE (phase 5b) found no code that reads these name lines (every getter adds +1 to the
name-line id), so the format is free: "Family Given 1479-1545" for officers (readings dropped),
the plain English name elsewhere. This writes the English of every name unit no tl file has yet into a batch for `tl.py apply 40`.
Re-run after tl/names changes: `--all` regenerates the units it wrote before (keys listed in
tl/msg40/.names40.json) so they follow tl/names.

usage: .venv/bin/python tools/dev/names40.py [--all] OUT_BATCH   (prints the unmatched names)
"""
import json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import names, tl

IDSP = '\u3000'
RANGES = [(0, 3000, 'persons'), (3003, 3799, 'hero'), (3799, 4719, 'treasures'),
          (4719, 5419, 'courttitles'), (5419, 5569, 'offices'), (5569, 6069, 'castles')]
# Castle-type words after the bare castle name (also what the name hook must print for N / 9):
# temples are written solid (Chusonji), towns bare (Sakai).
CASTLE_TYPE = [('御坊（砦）', ' Gobo (fort)'), ('御坊（寺）', ' Gobo (temple)'), ('御坊', ' Gobo'),
               ('御所', ' Palace'), ('聖堂', ' Church'), ('の村', ' Village'), ('城', ' Castle'),
               ('館', ' Hall'), ('砦', ' Fort'), ('湊', ' Port'), ('寺', 'ji'), ('社', ' Shrine'),
               ('町', ''), ('里', ' Village'), ('', '')]
GEN = os.path.join(tl.tl_dir(40), '.names40.json')
# Block 40 lines that name an officer by a popular name (or a form no table has): jp -> English.
# Lines whose Japanese is a typo or kana variant of their record need nothing here.
EXTRA = {
    '津軽信牧': 'Tsugaru Nobuhira', '小野忠明': 'Ono Tadaaki', '佐野信吉': 'Sano Nobuyoshi',
    '由良泰詮': 'Yura Shigeaki', '服部半蔵': 'Hattori Hanzo', '前田慶次': 'Maeda Keiji',
    '可児才蔵': 'Kani Saizo', '竹中半兵衛': 'Takenaka Hanbei', '山本勘助': 'Yamamoto Kansuke',
    '真田大助': 'Sanada Daisuke', '鬼小島弥太郎': 'Onikojima Yataro', '渡辺勘兵衛': 'Watanabe Kanbei',
    '高田又兵衛': 'Takada Matabei', '本願寺蓮淳': 'Honganji Renjun', '本願寺証恵': 'Honganji Shokei',
    '山中鹿之介': 'Yamanaka Shikanosuke', '黒田官兵衛': 'Kuroda Kanbei', '後藤又兵衛': 'Goto Matabei',
    '母里太兵衛': 'Mori Tahei', '河野通政': 'Kono Michimasa',
    # other-era heroes 3003-3797 not in the scenario tables
    '武田信勝': 'Takeda Nobukatsu', '小笠原長朝': 'Ogasawara Nagatomo', '敷地藤康': 'Shikichi Fujiyasu',
    'でうす': 'Deusu',
}

def load(t):
    return json.load(open(os.path.join(names.SCRIPT_DIR, t + '.json'), encoding='utf-8'))

TABLES = {t: load(t) for t in ('persons', 'treasures', 'courttitles', 'offices', 'castles')}

def en_str(en):
    return ' '.join(en) if isinstance(en, list) else en

def forms(r):
    """{jp: English} of a names record (base + scenario forms)."""
    out = {''.join(r['jp']): en_str(r['tl']['en'])}
    for s, jp in sorted(r.get('jp_scen', {}).items()):
        out.setdefault(''.join(jp), en_str(r['tl'].get(s, r['tl']['en'])))
    return out

def by_jp(t):
    out = {}
    for r in TABLES[t]:
        for jp, en in forms(r).items():
            out.setdefault(jp, en)
    return out

def name_of(t, i, jp, notes):
    """English of record i of table t for the Japanese jp (line i belongs to record i): the
    matching form of that record, else the same Japanese in another record, else the record's
    base English (a typo/kana variant in block 40)."""
    if jp in EXTRA:
        return EXTRA[jp]
    if t == 'hero':
        return by_jp('persons').get(jp)
    f = forms(TABLES[t][i])
    if jp in f:
        return f[jp]
    other = by_jp(t).get(jp)
    en = other or en_str(TABLES[t][i]['tl']['en'])
    notes.append('%s %d: %s -> %s (%s)' % (t, i, jp, en, 'other record' if other else 'record %s' % ''.join(TABLES[t][i]['jp'])))
    return en

def line(kind, i, jp, notes):
    if kind == 'persons':
        m = re.fullmatch(r'(\S+)\s+(\S+)\s+(\S+)～(\S+)', jp)
        en = name_of(kind, i, m.group(1) if m else jp, notes)
        return '%s %s-%s' % (en, m.group(3), m.group(4)) if m else en
    if kind == 'castles':
        jp = jp.replace(IDSP, '').replace(' ', '')
        for w, e in CASTLE_TYPE:
            if jp.endswith(w) and len(jp) > len(w):
                return name_of(kind, i, jp[:len(jp) - len(w)], notes) + e
    return name_of(kind, i, jp.split(IDSP)[0], notes)

def main():
    args = sys.argv[1:]
    regen = '--all' in args
    out_path = [a for a in args if not a.startswith('--')][0]
    tls = tl.expand(40, tl.load_tl(40))
    gen = set(json.load(open(GEN))) if os.path.exists(GEN) else set()
    batch, notes = {}, []
    for a, z, kind in RANGES:
        for e in range(a, z, 2):
            toks, spans = tl.units_of(40, e)
            for u, (x, y) in enumerate(spans):
                key = '%d%s' % (e, '.%d' % u if u else '')
                if (e, u) in tls and not (regen and key in gen):
                    continue
                jp = tl.unit_str(toks[x:y]).strip()
                en = jp and line(kind, (e - a) // 2, jp, notes)
                if en:
                    batch[key] = en
                elif jp:
                    notes.append('MISSING @%s %s' % (key, jp))
    with open(out_path, 'w', encoding='utf-8') as f:
        for k, v in batch.items():
            f.write('@%s\n%s\n' % (k, v))
    if os.path.exists(GEN) or batch:
        json.dump(sorted(gen | set(batch), key=tl.key_order), open(GEN, 'w'))
    print('%d units written to %s' % (len(batch), out_path))
    for x in notes:
        print('  ' + x)

if __name__ == '__main__':
    main()
