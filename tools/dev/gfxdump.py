"""Contact sheet of NB10 textures (dev; output is Koei data: keep it out of git).

usage: gfxdump.py ENTRY[.a-b] ... out.png [--scale N] [--grid]
--grid draws a 10 px ruler grid (labels every 50 px) over each texture.
"""
import os, sys
from PIL import Image, ImageDraw
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import tim2

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def entry(k):
    return open(os.path.join(ROOT, 'extract', 'nbx', '%03d.bin' % k), 'rb').read()

def textures(spec):
    e, _, r = spec.partition('.')
    d = entry(int(e))
    n = len(tim2.objects(d))
    if r:
        a, _, b = r.partition('-')
        ids = range(int(a), int(b or a) + 1)
    else:
        ids = range(n)
    for i in ids:
        try:
            t = tim2.Texture(d, i)
        except Exception:
            continue
        if t.w and t.h:
            yield '%s.%d' % (e, i), t

def checker(w, h):
    im = Image.new('RGBA', (w, h), (90, 110, 130, 255))
    dr = ImageDraw.Draw(im)
    for y in range(0, h, 8):
        for x in range((y // 8 % 2) * 8, w, 16):
            dr.rectangle((x, y, x + 7, y + 7), fill=(110, 130, 150, 255))
    return im

def main():
    args = sys.argv[1:]
    scale = 2
    grid = '--grid' in args
    if grid:
        args.remove('--grid')
    if '--scale' in args:
        k = args.index('--scale'); scale = int(args[k + 1]); del args[k:k + 2]
    out = args.pop()
    cells = []
    for spec in args:
        for name, t in textures(spec):
            im = t.image()
            im = im.resize((t.w * scale, t.h * scale), Image.NEAREST)
            bg = checker(im.width, im.height); bg.alpha_composite(im)
            if grid:
                dr = ImageDraw.Draw(bg)
                for x in range(0, t.w, 10):
                    dr.line((x * scale, 0, x * scale, bg.height), fill=(255, 0, 0, 90 if x % 50 else 200))
                for y in range(0, t.h, 10):
                    dr.line((0, y * scale, bg.width, y * scale), fill=(255, 0, 0, 90 if y % 50 else 200))
            cells.append(('%s %dx%d' % (name, t.w, t.h), bg))
    W = max(1200, max(c[1].width for c in cells) + 8)
    x = y = rowh = 0
    pos = []
    for lab, im in cells:
        if x + im.width > W:
            x, y, rowh = 0, y + rowh + 16, 0
        pos.append((x, y))
        x += max(im.width, 70) + 8
        rowh = max(rowh, im.height)
    sheet = Image.new('RGBA', (W, y + rowh + 16), (30, 30, 30, 255))
    dr = ImageDraw.Draw(sheet)
    for (lab, im), (px, py) in zip(cells, pos):
        dr.text((px, py), lab, fill=(255, 255, 0, 255))
        sheet.alpha_composite(im, (px, py + 12))
    sheet.save(out)
    print(out, len(cells), sheet.size)

if __name__ == '__main__':
    main()
