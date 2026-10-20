"""One-off: seed tl/names/ from the earlier releases' name lists + romanised readings.

A name part takes the spelling of Nobunaga DS 2 / Taiko 5 when the Japanese part and
its reading agree with this game (so all releases agree, incl. irregular spellings);
otherwise the romanised reading of this game. Existing tl rows are kept unless --force.

usage: seed_names.py [table ...] [--force] [--report]
"""
import collections, json, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import names

PROJECTS = os.path.expanduser('~/Projects')
DS2 = os.path.join(PROJECTS, 'nobunaga_ds_2_translation', 'script')
TK5 = os.path.join(PROJECTS, 'taiko_risshiden_5_translation')

def norm(s):
    return names.romaji(s).lower()

def person_refs():
    """Part spellings {(jp part, kind): {kana reading: spelling}} (DS 2) and pair
    spellings {(family, given): [(full kana reading, en, source)]} (Taiko 5, DS 2)."""
    parts = collections.defaultdict(dict)
    pairs = collections.defaultdict(list)
    tl = {r['id']: r for r in json.load(open(os.path.join(TK5, 'tl', 'names_persons.json'), encoding='utf-8'))}
    for r in json.load(open(os.path.join(TK5, 'script', 'names_persons.json'), encoding='utf-8')):
        t = tl.get(r['id'])
        if not t or 'officer' not in r:
            continue
        canon, reading = r['officer']
        for s, jp in r['jp'].items():
            en = t.get(s, t['en'])
            if ''.join(jp) == canon and all(en):
                pairs[tuple(jp)].append((names.hiragana(reading), en, 'tk5'))
    for r in json.load(open(os.path.join(DS2, 'names_officers.json'), encoding='utf-8')):
        for k in (0, 1):
            if r['jp'][k] and r['en'][k]:
                parts[r['jp'][k], k].setdefault(names.hiragana(r['reading'][k]), r['en'][k])
        pairs[tuple(r['jp'])].append((names.hiragana(''.join(r['reading'])), r['en'], 'ds2'))
    return parts, pairs

def person_en(jp, reading, refs):
    """English [family, given] and how each part was found."""
    parts, pairs = refs
    for kana, en, src in pairs.get(tuple(jp), []):
        if kana == ''.join(reading):
            return list(en), src
    out = []
    for k in (0, 1):
        if not jp[k]:
            out.append('')
            continue
        out.append(parts.get((jp[k], k), {}).get(reading[k]) or names.romaji(reading[k], k == 1))
    return out, 'parts'

def seed_persons(jp, report):
    refs = person_refs()
    rows, stats, diff = [], collections.Counter(), []
    for i, forms in enumerate(jp['persons']):
        base = names.common(forms)
        en, src = person_en(base[0], base[1], refs)
        row = {'id': i, 'en': en}
        stats[src] += 1
        for k, v in forms.items():
            if v[0] != base[0]:
                row[k] = person_en(v[0], v[1], refs)[0]
        for kana, ref, s in refs[1].get(base[0], []):
            if ref != en:
                diff.append('%4d %s %s: ours %s, %s %s (%s)' % (i, ''.join(base[0]), ''.join(base[1]),
                                                            ' '.join(en), s, ' '.join(ref), kana))
        rows.append(row)
    if report:
        print(dict(stats))
        print('%d pairs differ from the reference spelling:' % len(diff))
        print('\n'.join(diff))
    return rows

def seed_simple(table, jp, refs=None):
    rows = []
    for i, forms in enumerate(jp[table]):
        if all(names.is_empty(v[0]) for v in forms.values()):
            continue
        def en(v):
            n, r = v[0][0], v[1][0]
            return (refs or {}).get((n, norm(r)), names.romaji(r))
        base = names.common(forms)
        row = {'id': i, 'en': en(base)}
        for k, v in forms.items():
            if v[0] != base[0]:
                row[k] = en(v)
        rows.append(row)
    return rows

def province_refs():
    refs = {}
    for r in json.load(open(os.path.join(DS2, 'names_provinces.json'), encoding='utf-8')):
        refs[r['jp'][0] if isinstance(r['jp'], list) else r['jp'],
             norm(r['reading'][0] if isinstance(r['reading'], list) else r['reading'])] = r['en']
    return refs

# group suffix -> English pattern (glossary: notes/glossary.md "Minor powers")
GROUP_SUFFIX = [('国衆', '%s Gentry'), ('門徒衆', '%s Ikko'), ('衆徒', '%s Monks'), ('社衆', '%s Shrine Men'),
                ('海賊衆', '%s Pirates'), ('村衆', '%s Villagers'), ('町衆', '%s Townsmen'),
                ('信者衆', '%s Christians'), ('衆', '%s Ninja')]
GROUP_FIXED = {'窃忍衆': 'Shinobi Band'}

def seed_groups(table, jp):
    places = {}
    for t in ('provinces', 'castles'):
        for i, forms in enumerate(jp[t]):
            tl = names.load_tl(t).get(i)
            for k, v in forms.items():
                if tl and v[0][0]:
                    places.setdefault(v[0][0], names.english(tl, k))
    def en(v):
        n, r = v[0][0], v[1][0]
        if n in GROUP_FIXED:
            return GROUP_FIXED[n]
        for suf, pat in GROUP_SUFFIX:
            if n.endswith(suf):
                place = n[:-len(suf)]
                return pat % places.get(place, names.romaji(r[:len(r) - len(names.hiragana(
                    {'国衆': 'くにしゅう', '門徒衆': 'もんとしゅう', '衆徒': 'しゅと', '社衆': 'やしろしゅう',
                     '海賊衆': 'かいぞくしゅう', '村衆': 'むらしゅう', '町衆': 'まちしゅう', '信者衆': 'しんじゃしゅう',
                     '衆': 'しゅう'}[suf]))]))
        raise ValueError(n)
    rows = []
    for i, forms in enumerate(jp[table]):
        base = names.common(forms)
        row = {'id': i, 'en': en(base)}
        for k, v in forms.items():
            if v[0] != base[0]:
                row[k] = en(v)
        rows.append(row)
    return rows

def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    force, report = '--force' in sys.argv, '--report' in sys.argv
    jp = names.japanese(names.scenarios())
    seeders = {'persons': lambda: seed_persons(jp, report),
               'women': lambda: seed_simple('women', jp),
               'regions': lambda: seed_simple('regions', jp),
               'provinces': lambda: seed_simple('provinces', jp, province_refs()),
               'castles': lambda: seed_simple('castles', jp),
               'kunishu': lambda: seed_groups('kunishu', jp),
               'pirates': lambda: seed_groups('pirates', jp),
               'bands': lambda: seed_groups('bands', jp)}
    for t in args or seeders:
        if os.path.exists(names.tl_path(t)) and not force:
            print('%s: exists (use --force)' % t)
            continue
        rows = seeders[t]()
        names.write_tl(t, rows)
        print('%s: %d rows' % (t, len(rows)))

if __name__ == '__main__':
    main()
