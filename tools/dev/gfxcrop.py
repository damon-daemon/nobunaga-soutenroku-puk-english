"""Crops of textures with a 10 px ruler grid (dev). usage: gfxcrop.py out.png E.O:x0,y0,x1,y1[:scale] ..."""
import os, sys
from PIL import Image, ImageDraw
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.dirname(__file__))
import tim2, gfxdump

def crop(e, i, box, sc, tex=None):
    t = tex or tim2.Texture(gfxdump.entry(e), i)
    box = box or (0, 0, t.w, t.h)
    im = t.image().crop(box)
    im = im.resize((im.width * sc, im.height * sc), Image.NEAREST)
    bg = gfxdump.checker(im.width, im.height); bg.alpha_composite(im); dr = ImageDraw.Draw(bg)
    for x in range(box[0] - box[0] % 10, box[2], 10):
        dr.line(((x - box[0]) * sc, 0, (x - box[0]) * sc, bg.height), fill=(255, 0, 0, 200 if x % 50 == 0 else 60))
    for y in range(box[1] - box[1] % 10, box[3], 10):
        dr.line((0, (y - box[1]) * sc, bg.width, (y - box[1]) * sc), fill=(255, 0, 0, 200 if y % 50 == 0 else 60))
    return bg

def sheet(ims, out):
    W = max(i.width for i in ims)
    sh = Image.new('RGBA', (W, sum(i.height + 6 for i in ims)), (30, 30, 30, 255)); y = 0
    for i in ims:
        sh.alpha_composite(i, (0, y)); y += i.height + 6
    sh.save(out); print(out, sh.size)

if __name__ == '__main__':
    ims = []
    for a in sys.argv[2:]:
        k, _, rest = a.partition(':')
        e, o = map(int, k.split('.'))
        parts = rest.split(':') if rest else []
        box = tuple(map(int, parts[0].split(','))) if parts and parts[0] else None
        sc = int(parts[1]) if len(parts) > 1 else 2
        ims.append(crop(e, o, box, sc))
    sheet(ims, sys.argv[1])
