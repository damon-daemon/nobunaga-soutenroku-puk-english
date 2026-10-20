"""Scenario titles and the scenario preview tables (NB10 entry 41).

Scenario files (NB10 5-16): title [21] at +0x2C and again at +0x18F (each followed by an
intro [334], still Japanese: not seen on screen yet). Entry 41 = 12 titles [21] (in
chronological order), then per scenario (same order) 250 castle names with suffix [13],
250 castle lord names [18] and 250 clan names "X家" [11]. English from
tl/names/scenario_titles.json and the name hook table (namehook.py), cut to the fields.

  scenarios.py check     report preview strings without English
"""
import json, os, struct, sys

sys.path.insert(0, os.path.dirname(__file__))
import namehook, names, setup

TITLES = os.path.join(setup.TL, 'names', 'scenario_titles.json')
TITLE_AT, TITLE_LEN = (0x2C, 0x18F), 21
PREVIEW = 41
CASTLES, CASTLE_LEN = 0xFC, 13
LORDS, LORD_LEN = 0xFC + 3000 * 13, 18
CLANS, CLAN_LEN = LORDS + 3000 * 18, 11
CLAN = '家'

def field(b, at, n):
    return b[at:at + n].split(b'\0')[0].decode('cp932')

def put(b, at, n, s):
    e = s.encode('ascii')
    assert len(e) < n, s
    b[at:at + n] = e + bytes(n - len(e))

def maps(table):
    """Japanese preview strings -> English: castle with suffix, lord full name, family."""
    res, _ = table.resolved()
    castle, lord, family = {}, {}, {}
    for (kind, parts), en in res.items():
        jp = [p.decode('cp932') for p in parts]
        if kind == 'K':
            castle[jp[0] + jp[1]] = (en, res.get(('c', parts[:1]), en))
        elif kind == 'n':
            lord.setdefault(jp[0] + jp[2], en)
        elif kind in 'fF' and len(jp) in (2, 4):
            family.setdefault(jp[0], en)
    return castle, lord, family

def fit_castle(full, bare):
    return full if len(full) < CASTLE_LEN else bare[:CASTLE_LEN - 1]

def fit_lord(en):
    if len(en) < LORD_LEN:
        return en
    fam, _, giv = en.partition(' ')
    return (fam + ' ' + giv[:1] + '.')[:LORD_LEN - 1]

def fit_clan(fam):
    return fam + ' clan' if len(fam) + 5 < CLAN_LEN else fam[:CLAN_LEN - 1]

def apply(scens, preview, table):
    """scens: [bytearray] of the 12 scenario files (changed in place); returns the new entry 41
    and the list of strings left in Japanese."""
    titles = json.load(open(TITLES, encoding='utf-8'))
    jp_titles = {}
    for j, s in enumerate(scens):
        key = names.SCEN_KEYS[j]
        jp_titles[field(s, TITLE_AT[0], TITLE_LEN)] = key
        for at in TITLE_AT:
            put(s, at, TITLE_LEN, titles[key])
    out = bytearray(preview)
    castle, lord, family = maps(table)
    missing = []
    for i in range(12):
        jp = field(preview, i * TITLE_LEN, TITLE_LEN)
        put(out, i * TITLE_LEN, TITLE_LEN, titles[jp_titles[jp]])
    for k in range(3000):
        for base, n, conv in ((CASTLES, CASTLE_LEN, lambda s: castle.get(s) and fit_castle(*castle[s])),
                              (LORDS, LORD_LEN, lambda s: lord.get(s) and fit_lord(lord[s])),
                              (CLANS, CLAN_LEN, lambda s: s.endswith(CLAN) and s[:-1] in family
                               and fit_clan(family[s[:-1]]))):
            jp = field(preview, base + k * n, n)
            if not jp:
                continue
            en = conv(jp)
            if en:
                put(out, base + k * n, n, en)
            else:
                missing.append(jp)
    return bytes(out), missing

def main():
    import iso, nbx
    recs = iso.records(setup.CLEAN)
    elf = iso.read_file(setup.CLEAN, iso.ELF_NAME, recs)
    archive = iso.read_file(setup.CLEAN, nbx.NAME, recs)
    scens = [bytearray(nbx.entry(archive, elf, k)) for k in names.SCENARIOS]
    table = namehook.build_table(elf, [bytes(s) for s in scens])
    _, missing = apply(scens, nbx.entry(archive, elf, PREVIEW), table)
    print('%d preview strings without English%s' % (len(missing), ': ' + ' '.join(sorted(set(missing))) if missing else ''))

if __name__ == '__main__':
    main()
