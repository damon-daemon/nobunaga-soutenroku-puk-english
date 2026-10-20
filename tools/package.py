"""Package a release: release/<Name>_v<version>.zip with the xdelta patch and README.txt.

usage: .venv/bin/python tools/package.py 0.10.0

Run tools/build.py first. README.txt is generated from README.md (the notice, the
"What's translated", "Known issues" and "Credits" sections) plus patching
instructions and checksums of the clean and patched disc images. The disc image is never
packaged.
"""
import hashlib, os, re, sys, textwrap, zipfile, zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TITLE = 'Nobunaga no Yabou: Soutenroku with Power-Up Kit - English Translation'
ZIP_NAME = 'Nobunaga_no_Yabou_Soutenroku_PUK_English'
CLEAN = 'nobunaga_soutenroku_puk.iso'
PATCHED = 'nobunaga_soutenroku_puk_en.iso'
GAME_CODE = 'SLPM-65455'

def sums(path):
    """Checksums, read in chunks (disc images are 1.5 GB)."""
    md5, sha1, crc, n = hashlib.md5(), hashlib.sha1(), 0, 0
    with open(path, 'rb') as f:
        while chunk := f.read(1 << 24):
            md5.update(chunk); sha1.update(chunk); crc = zlib.crc32(chunk, crc); n += len(chunk)
    return [('Size', '{:,} bytes'.format(n)), ('CRC32', '%08X' % (crc & 0xFFFFFFFF)),
            ('MD5', md5.hexdigest()), ('SHA-1', sha1.hexdigest())]

def section(md, name):
    m = re.search(r'^## %s\n(.*?)(?=^## |\Z)' % re.escape(name), md, re.S | re.M)
    return m.group(1).strip() if m else ''

def plain(text):
    """Markdown -> readable plain text (bold, code, links, quotes, tables)."""
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'(?<!\w)\*(.+?)\*(?!\w)', r'\1', text)
    text = re.sub(r'`([^`]*)`', r'\1', text)
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'\1 (\2)', text)
    text = re.sub(r'^> ?', '', text, flags=re.M)
    return text

def heading(t):
    return '%s\n%s\n' % (t, '-' * len(t))

def main():
    if len(sys.argv) != 2:
        sys.exit('usage: tools/package.py VERSION   (e.g. 0.10.0)')
    version = sys.argv[1]
    clean = os.path.join(ROOT, CLEAN)
    built = os.path.join(ROOT, 'build', PATCHED)
    patch = os.path.splitext(built)[0] + '.xdelta'
    for p in (clean, built, patch):
        if not os.path.exists(p):
            sys.exit('missing %s (run tools/build.py first)' % p)
    if os.path.getmtime(patch) < os.path.getmtime(built):
        sys.exit('patch is older than the built image; re-run tools/build.py')
    md = open(os.path.join(ROOT, 'README.md'), encoding='utf-8').read()
    notice = re.search(r'^> \*\*This is a full machine translation.*?(?=\n\n)', md, re.S | re.M)
    patch_name = '%s_v%s.xdelta' % (os.path.splitext(PATCHED)[0], version)
    table = lambda rows: '\n'.join('  %-6s %s' % r for r in rows)

    out = [TITLE, 'Version %s' % version, '=' * max(len(TITLE), 20), '']
    beta = re.search(r'^> \*\*This is a beta.*?(?=\n\n)', md, re.S | re.M)
    for m in (notice, beta):
        if m:
            out += [textwrap.fill(' '.join(plain(m.group(0)).split()), 78), '']
    out += [heading("What's translated"), plain(section(md, "What's translated")), '']
    out += [heading('How to patch'),
            'You need an unmodified image of the Japanese disc (serial %s):' % GAME_CODE, '',
            table(sums(clean)), '',
            'Apply %s to it with an xdelta tool, e.g. Delta Patcher' % patch_name,
            '(https://github.com/marco-calautti/DeltaPatcher), or on the command line:', '',
            '  xdelta3 -d -s %s %s %s' % (CLEAN, patch_name, PATCHED), '',
            'The patched disc image should match:', '', table(sums(built)), '']
    out += [heading('Known issues'), plain(section(md, 'Known issues')), '']
    out += [heading('Credits'), plain(section(md, 'Credits')), '']
    readme = '\n'.join(out).replace('\n\n\n', '\n\n')

    os.makedirs(os.path.join(ROOT, 'release'), exist_ok=True)
    zpath = os.path.join(ROOT, 'release', '%s_v%s.zip' % (ZIP_NAME, version))
    with zipfile.ZipFile(zpath, 'w', zipfile.ZIP_DEFLATED) as z:
        z.write(patch, patch_name)
        z.writestr('README.txt', readme.replace('\n', '\r\n'))
    print('%s (%s, README.txt)' % (zpath, patch_name))

if __name__ == '__main__':
    main()
