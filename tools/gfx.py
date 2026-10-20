"""Redraw Japanese text baked into NB10 textures (tools/tim2.py edits them in place).

Lettering comes from the stroke glyphs of tools/latinfont.py (original drawings) rendered at
any size (ported from Taiko 5 gfx.py); colours are measured from the original texture:

  plate(): light text with a dark outline on a textured plate (tags, buttons, banners on
    a panel): text pixels (brighter than the plate) plus their outline are erased by
    resampling unmasked pixels of the same row, then the English is drawn with the
    original's fill and outline colours.
  banner(): big outlined lettering on transparency (勝利 ...).

tl/gfx.txt: "entry.object<TAB>English" ('|' = line break inside one spot, ';' separates spots
of ITEMS with several boxes). ITEMS gives the kind and boxes; objects not in ITEMS are plates
over the whole texture.
"""
import collections, os, random, sys
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(__file__))
import latinfont, tim2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TL = os.path.join(ROOT, 'tl', 'gfx.txt')
SS = 4

def luma(c):
    return (c[0] * 299 + c[1] * 587 + c[2] * 114) // 1000

class Canvas:
    """Palette helpers around a tim2.Texture."""
    def __init__(self, tex):
        self.t = tex
        self.w, self.h, self.pal = tex.w, tex.h, tex.pal
        self.cache = {}

    def get(self, x, y):
        return self.t.get(x, y)

    def idx(self, x, y):
        return self.t.idx(x, y)

    def put(self, x, y, i):
        self.t.put(x, y, i)

    def index(self, rgb, alpha=0x80):
        """Nearest palette entry to an RGB colour and alpha (0-0x80)."""
        key = tuple(int(round(v)) for v in rgb[:3]) + (int(round(alpha)),)
        if key not in self.cache:
            self.cache[key] = min(range(len(self.pal)), key=lambda i: sum((a - b) ** 2 for a, b in zip(self.pal[i][:3], key[:3]))
                                  + 6 * (self.pal[i][3] - key[3]) ** 2)
        return self.cache[key]

class Stack(Canvas):
    """Textures stacked vertically as one canvas (a 400x80 banner split into two 400x40
    textures with their own palettes): indexes are into the joined palette list; a put
    maps the colour to the nearest entry of the texture that holds the pixel."""
    def __init__(self, texs):
        self.ts = texs
        self.w, self.h = texs[0].w, sum(t.h for t in texs)
        self.pal, self.base, self.y0 = [], [], []
        y = 0
        for t in texs:
            self.base.append(len(self.pal)); self.y0.append(y)
            self.pal += t.pal; y += t.h
        self.cache = {}

    def _at(self, y):
        k = max(i for i in range(len(self.ts)) if self.y0[i] <= y)
        return k, y - self.y0[k]

    def get(self, x, y):
        k, yy = self._at(y)
        return self.ts[k].get(x, yy)

    def idx(self, x, y):
        k, yy = self._at(y)
        return self.base[k] + self.ts[k].idx(x, yy)

    def put(self, x, y, i):
        k, yy = self._at(y)
        t = self.ts[k]
        lo = self.base[k]
        if not lo <= i < lo + len(t.pal):
            c = self.pal[i]
            i = lo + min(range(len(t.pal)), key=lambda j: sum((a - b) ** 2 for a, b in zip(t.pal[j][:3], c[:3])) + 6 * (t.pal[j][3] - c[3]) ** 2)
        t.put(x, yy, i - lo)

# ---------------------------------------------------------------- lettering

def text_masks(text, cap, widths, condense=1.0, spacing=None, descender=None):
    """Coverage images (PIL 'L', SS times the final size) of text drawn with each
    stroke width in widths (px, final scale): wider strokes give the outline layers.
    Returns (images, (w, h), (left, top) of the cap box) at final scale."""
    stroke = widths[0]
    s = (cap - stroke) / latinfont.C
    spacing = stroke * 0.45 if spacing is None else spacing
    pad = max(widths) / 2 + 1
    xs, x = [], pad
    for c in text:
        w, _ = latinfont.GLYPHS[c]
        xs.append(x)
        x += (w * s * condense + stroke + spacing) if c != ' ' else cap * 0.32
    width = x - spacing + pad
    if descender is None:
        descender = any(c in 'gjpqy,;' for c in text)
    height = cap + stroke + 2 * pad + (3 * s if descender else 0)
    base = pad + cap - stroke / 2
    out = []
    for sw in widths:
        im = Image.new('L', (int(width * SS) + 1, int(height * SS) + 1), 0)
        dr = ImageDraw.Draw(im)
        r = sw * SS / 2
        for c, x0 in zip(text, xs):
            for st in latinfont.GLYPHS[c][1]:
                pts = [((x0 + stroke / 2 + px * s * condense) * SS, (base - py * s) * SS) for px, py in st]
                for a, b in zip(pts, pts[1:]):
                    dr.line([a, b], fill=255, width=max(1, round(sw * SS)))
                for px, py in pts:
                    dr.ellipse((px - r, py - r, px + r, py + r), fill=255)
        out.append(im)
    return out, (width, height), (pad, pad)

def fit(lines, cap, box_w, box_h, widths_of, min_cap=5.0, min_condense=0.7):
    """Shrink (condense first, then cap) until every line fits box_w and all lines box_h.
    -> (cap, condense, [(masks, (w, h), (px, py))])"""
    condense = 1.0
    while True:
        r = [text_masks(l, cap, widths_of(cap), condense, descender=False) for l in lines]
        lh = cap + widths_of(cap)[-1]
        tw = max(m[1][0] for m in r) - 2 * (max(widths_of(cap)) / 2 + 1)
        if (tw <= box_w and lh * len(lines) + (len(lines) - 1) * 1 <= box_h + 1) or cap <= min_cap:
            if tw > box_w + 0.5 or lh * len(lines) > box_h + 3:
                raise ValueError('%r does not fit %dx%d' % ('|'.join(lines), box_w, box_h))
            return cap, condense, r
        if condense > min_condense:
            condense *= 0.96
        else:
            cap *= 0.95

# ---------------------------------------------------------------- plates

def _box(cv, box):
    if box == 'auto':
        # the opaque plate of a texture wider than its plate (command banners): columns
        # opaque on the middle row, inset 4 px
        xs = [x for x in range(cv.w) if cv.get(x, cv.h // 2)[3] >= 0x40]
        return (xs[0] + 4, 4, xs[-1] - 4, cv.h - 5)
    return box or (1, 1, cv.w - 2, cv.h - 2)

def plate_style(cv, box, mode='light', grow=2, dilate=4, sens=(24, 0.4), amin=0x40):
    """-> (text mask set, fill rgb, outline rgb, text alpha) for light text with a dark
    outline (mode 'light') or dark text on a light plate ('dark'). amin = alpha of the pixels
    measured (lower for faint, half-transparent art)."""
    x0, y0, x1, y1 = box
    px = [(x, y) for y in range(y0, y1 + 1) for x in range(x0, x1 + 1)]
    L = {p: luma(cv.get(*p)) for p in px}
    A = {p: cv.get(*p)[3] for p in px}
    vals = sorted(L[p] for p in px if A[p] > amin)
    # the plate is the bulk of the pixels; text the bright tail
    med = vals[len(vals) // 2]
    spread = max(6, vals[len(vals) * 2 // 3] - vals[len(vals) // 3])
    hi = vals[int(len(vals) * 0.97)]
    if mode in ('light', 'glow'):
        th = med + max(sens[0], (hi - med) * sens[1])
        core = {p for p in px if L[p] >= th and A[p] > amin}
    else:
        lo = vals[int(len(vals) * 0.03)]
        th = med - max(sens[0], (med - lo) * sens[1])
        core = {p for p in px if L[p] <= th and A[p] > amin}
    # the outline: core neighbours on the opposite side of the plate
    ring = collections.Counter()
    for (x, y) in core:
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                q = (x + dx, y + dy)
                if q in L and q not in core and ((L[q] < med) if mode == 'light' else (L[q] > med)):
                    ring[q] += 1
    if mode == 'glow':
        # dark lettering inside a light glow: the glow is the bright core; the letters'
        # insides are dark like the background, so the mask is the glow grown by dilate px
        dark = {p for p in px if L[p] < med - 8}
        core = {(x, y) for (x, y) in core if any((x + dx, y + dy) in dark for dx in range(-3, 4) for dy in range(-3, 4))}
        mask = set(core)
        for _ in range(dilate):
            mask |= {(x + dx, y + dy) for (x, y) in mask for dx in (-1, 0, 1) for dy in (-1, 0, 1) if (x + dx, y + dy) in L}
        inner = sorted((cv.get(*p) for p in mask - core), key=luma)
        glow = sorted((cv.get(*p) for p in core), key=luma)
        fill, outline = inner[len(inner) // 10], glow[len(glow) * 3 // 4]
        return mask, fill[:3], outline[:3], max(fill[3], outline[3])
    if not core:
        raise ValueError('no lettering found in %r' % (box,))
    fillc = sorted((cv.get(*p) for p in core), key=luma)
    fill = fillc[int(len(fillc) * 0.8)] if mode == 'light' else fillc[len(fillc) // 5]
    outc = sorted((cv.get(*p) for p in ring), key=luma)
    outline = (outc[len(outc) // 4] if mode == 'light' else outc[len(outc) * 3 // 4]) if outc else None
    # erase a bit more than the outline: anti-aliased edges otherwise stay as specks
    mask = set(core) | set(ring)
    for _ in range(grow):
        mask |= {(x + dx, y + dy) for (x, y) in mask for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                 if (x + dx, y + dy) in L and abs(L[x + dx, y + dy] - med) > spread}
    # plus one pixel all round: the inpainting copies from the mask's edge, and faint
    # anti-aliased text edges there grew back into ghosts of the old lettering
    mask |= {(x + dx, y + dy) for (x, y) in mask for dx in (-1, 0, 1) for dy in (-1, 0, 1) if (x + dx, y + dy) in L}
    return mask, fill[:3], outline[:3] if outline else None, fill[3]

def erase(cv, box, mask, seed=0):
    """Inpaint masked pixels from the outside in (onion peel): each pass fills the pixels
    with the most known neighbours by copying a random known pixel within 2 px, so the
    background's local colours and grain continue under the text."""
    x0, y0, x1, y1 = box
    rnd = random.Random(seed)
    todo = {p for p in mask if x0 <= p[0] <= x1 and y0 <= p[1] <= y1}
    near = [(dx, dy) for dx in range(-2, 3) for dy in range(-2, 3) if dx or dy]
    def known(x, y):
        return [(x + dx, y + dy) for dx, dy in near
                if x0 <= x + dx <= x1 and y0 <= y + dy <= y1 and (x + dx, y + dy) not in todo]
    while todo:
        cand = {p: known(*p) for p in todo}
        best = max(len(v) for v in cand.values())
        if best == 0:
            break
        need = max(1, min(best, 8))
        layer = [p for p, v in cand.items() if len(v) >= need]
        for p in layer:
            cv.put(p[0], p[1], cv.idx(*rnd.choice(cand[p])))
        todo -= set(layer)

def draw(cv, box, text, fill, outline, alpha=0x80, cap=None, align='center', bold=0.14, lw=1.0, vshift=0, hshift=0):
    """English (lines split on '|') centred in box, fill + outline colours."""
    x0, y0, x1, y1 = box
    lines = text.split('|')
    bw, bh = x1 - x0 + 1, y1 - y0 + 1
    widths_of = lambda c: [max(1.2, c * bold)] + ([max(1.2, c * bold) + 2 * lw] if outline else [])
    cap = cap or min(bh / len(lines) * 0.62, 22)
    cap = min(cap, bh / len(lines) * 0.75)
    cap, condense, rs = fit(lines, cap, bw - 2, bh, widths_of)
    lh = cap + widths_of(cap)[-1]
    total = lh * len(lines)
    top = y0 + (bh - total) / 2 + vshift
    for k, (masks, (tw, th), (px, py)) in enumerate(rs):
        size = (int(tw) + 1, int(th) + 1)
        layers = [m.resize(size, Image.BOX) for m in masks]
        inkw = tw - 2 * px
        ox = {'center': x0 + (bw - inkw) / 2, 'left': x0 + 1, 'right': x1 - inkw}[align] - px + hshift
        oy = top + k * lh - py + (widths_of(cap)[-1] - widths_of(cap)[0]) / 2
        ox, oy = int(round(ox)), int(round(oy))
        for y in range(size[1]):
            for x in range(size[0]):
                tx, ty = ox + x, oy + y
                if not (x0 <= tx <= x1 and y0 <= ty <= y1):
                    continue
                c = layers[0].getpixel((x, y)) / 255
                e = layers[1].getpixel((x, y)) / 255 if outline else 0
                if c <= 0.04 and e <= 0.08:
                    continue
                base = cv.get(tx, ty)
                col = base[:3]
                if e > 0:
                    col = tuple(p + (q - p) * min(1, e * 1.3) for p, q in zip(col, outline))
                if c > 0:
                    col = tuple(p + (q - p) * min(1, c * 1.15) for p, q in zip(col, fill))
                a = base[3] + (max(alpha, base[3]) - base[3]) * max(c, e)
                cv.put(tx, ty, cv.index(col, a))

def clear(cv, box, text, dark=False, area=None, amin=0x60, outline=True, **kw):
    """Text on transparency: fill/outline = bright/dark opaque colours of the box, which is
    cleared to the most transparent palette entry and redrawn. area(x, y) -> bool limits the
    cleared pixels (a shape inside the box); amin = alpha of the pixels measured."""
    x0, y0, x1, y1 = box
    inside = [(x, y) for y in range(y0, y1 + 1) for x in range(x0, x1 + 1) if area is None or area(x, y)]
    opq = sorted((cv.get(x, y) for x, y in inside if cv.get(x, y)[3] >= amin), key=luma)
    fill, line = opq[len(opq) * 19 // 20], opq[len(opq) // 10]
    if dark:
        fill, line = opq[len(opq) // 20], opq[len(opq) * 9 // 10]
    t = min(range(len(cv.pal)), key=lambda i: cv.pal[i][3])
    for x, y in inside:
        cv.put(x, y, t)
    if text:
        draw(cv, box, text, fill[:3], line[:3] if outline else None,
             max(fill[3], line[3]) if outline else fill[3], **kw)

def plate(cv, text, box=None, mode='light', erase_box=None, style=None, copy=None, **kw):
    """copy = ((sx, y0, y1), (x0, x1)): after erasing, rows y0-y1 of columns x0-x1 become
    copies of column sx (rebuilds a straight rule the old lettering was joined to)."""
    box = _box(cv, box)
    if mode == 'clear':
        return clear(cv, box, text, **kw)
    if mode == 'holes':
        # lettering cut out of a shape (faint menu art): transparent pixels with shape on both
        # sides of their row and column are filled from the shape around them
        x0, y0, x1, y1 = box
        amin = (style or {}).get('amin', 0x18)
        solid = lambda x, y: cv.get(x, y)[3] >= amin
        mask = {(x, y) for y in range(y0, y1 + 1) for x in range(x0, x1 + 1) if not solid(x, y)
                and any(solid(i, y) for i in range(x0, x)) and any(solid(i, y) for i in range(x + 1, x1 + 1))
                and any(solid(x, j) for j in range(y0, y)) and any(solid(x, j) for j in range(y + 1, y1 + 1))}
        assert not text, 'holes: erase only'
        return erase(cv, box, mask)
    boxes = erase_box if isinstance(erase_box, list) else [erase_box or box]
    mask, fill, outline, alpha = plate_style(cv, boxes[0], mode, **(style or {}))
    for b in boxes[1:]:
        mask |= plate_style(cv, b, mode, **(style or {}))[0]
    if mode == 'glow':
        kw.setdefault('lw', 1.4)
    for b in boxes:
        erase(cv, b, mask)
    if copy:
        (sx, cy0, cy1), (cx0, cx1) = copy
        for y in range(cy0, cy1 + 1):
            for x in range(cx0, cx1 + 1):
                cv.put(x, y, cv.idx(sx, y))
    if text:
        draw(cv, box, text, fill, outline, alpha, **kw)

# ---------------------------------------------------------------- banners (Taiko 5)

def _runs(row):
    out, x = [], 0
    while x < len(row):
        if row[x]:
            x0 = x
            while x < len(row) and row[x]:
                x += 1
            out.append((x0, x))
        x += 1
    return out

def banner(cv, text, cap=None, fill_pct=0.5):
    """Replace the lettering of an outlined banner on transparency with text (centred):
    fill rows, outline and outer glow measured from the original."""
    w, h = cv.w, cv.h
    A = [[cv.get(x, y)[3] for x in range(w)] for y in range(h)]
    Lm = [[luma(cv.get(x, y)) for x in range(w)] for y in range(h)]
    solid = [[A[y][x] >= 0x70 for x in range(w)] for y in range(h)]
    ys = [y for y in range(h) if any(solid[y])]
    # outline = solid pixels touching non-solid; fill = solid pixels 2+ px inside
    edge, fillpx = collections.Counter(), collections.defaultdict(list)
    for y in ys:
        for x in range(w):
            if not solid[y][x]:
                continue
            near = [solid[y + dy][x + dx] if 0 <= y + dy < h and 0 <= x + dx < w else False
                    for dx in range(-2, 3) for dy in range(-2, 3)]
            if not all(near[6:9] + near[11:14] + near[16:19]):
                edge[cv.idx(x, y)] += 1
            elif all(near):
                fillpx[y].append(cv.idx(x, y))
    outline = edge.most_common(1)[0][0]
    fill = {y: sorted(v, key=lambda i: luma(cv.pal[i]))[int(len(v) * fill_pct)] for y, v in fillpx.items() if v}
    glow = collections.Counter(cv.idx(x, y) for y in range(h) for x in range(w) if 0 < A[y][x] < 0x70)
    glow_rgb = cv.pal[glow.most_common(1)[0][0]][:3] if glow else None
    transparent = min(range(len(cv.pal)), key=lambda i: cv.pal[i][3])
    y0, y1 = ys[0], ys[-1]
    cap = cap or (y1 - y0 + 1) * 0.7
    condense = 1.0
    while True:
        stroke = max(2.0, cap * 0.16)
        widths = [stroke, stroke + 2 * max(1, cap * 0.06), stroke + 2 * max(2, cap * 0.12)]
        masks, (tw, th), _ = text_masks(text, cap, widths, condense)
        if tw <= w - 4 or cap < 10:
            break
        if condense > 0.8:
            condense *= 0.96
        else:
            cap *= 0.95
    if tw > w - 4:
        raise ValueError('banner %r: %d px wide, texture %d' % (text, tw, w))
    size = (int(tw) + 1, int(th) + 1)
    core, mid, out = (m.resize(size, Image.BOX) for m in masks)
    ox = (w - size[0]) // 2
    oy = (y0 + y1) // 2 - size[1] // 2
    fy = sorted(fill)
    for y in range(h):
        for x in range(w):
            cv.put(x, y, transparent)
    for y in range(size[1]):
        ty = oy + y
        if not 0 <= ty < h:
            continue
        row = fill[min(fy, key=lambda r: abs(r - (y0 + (y1 - y0) * y / size[1])))]
        for x in range(size[0]):
            tx = ox + x
            c, m, o = core.getpixel((x, y)) / 255, mid.getpixel((x, y)) / 255, out.getpixel((x, y)) / 255
            if c > 0.5:
                i = row
            elif m > 0.5:
                i = outline
            elif o > 0.15 and glow_rgb:
                i = cv.index(glow_rgb, o * 0x60)
            else:
                continue
            cv.put(tx, ty, i)

# ---------------------------------------------------------------- items

# (entry, object): (kind, options) ; kind 'plate' (default), 'banner', 'plates' (several
# boxes: options = list of dicts for plate())
GLOW = {'mode': 'glow', 'bold': 0.2}
HELP_PANEL = [{'box': (30, 20, 225, 50), 'align': 'left'}] + [{'box': (101, y, 189, y + 20)} for y in (82, 128, 172, 218)]
STRIP48 = ('plate', {'box': (1, 1, 42, 20)})        # 48x22 labels with a green strip at x 44-47
BLUE = ('plate', {'box': 'auto', 'style': {'sens': (12, 0.2), 'grow': 4}})     # glowing command banners 176x36
def frames(n, h, inner, shifts):
    """plates for an animation strip of n frames h px tall: inner = (x0, y0, x1, y1) of
    frame 0; shifts = {frame: px} for frames where the text slides in/out (None = empty)."""
    out = []
    for k in range(n):
        x0, y0, x1, y1 = inner
        o = {'box': (x0, y0 + k * h, x1, y1 + k * h), 'style': {'grow': 3}}
        if k in shifts:
            if shifts[k] is None:
                o['empty'] = True
            else:
                o['hshift'] = shifts[k]
        out.append(o)
    return out

SEASON_TILES = [{'box': (108 * c + 5, 64 * r + 28, 108 * c + 100, 64 * r + 60), 'erase_box': (108 * c + 4, 64 * r + 26, 108 * c + 44, 64 * r + 61),
                 'align': 'left', 'cap': 15, 'style': {'sens': (16, 0.3), 'grow': 4}} for r in range(2) for c in range(4)]
ITEMS = {
    **{(60, k): ('plates', SEASON_TILES) for k in range(4)},     # 8 animation tiles 108x64 (N9GD v8)
    # title logo: パワーアップキット (letters joined to a zigzag underline) -> English over a
    # straight underline (rows 319-329 copied from its plain part at x 200)
    (51, 0): ('plate', {'mode': 'glow', 'box': (150, 254, 488, 317), 'erase_box': [(146, 251, 492, 318), (146, 243, 252, 260), (335, 234, 492, 260)],
                        'bold': 0.2, 'lw': 2.2, 'cap': 40, 'style': {'dilate': 7},
                        'copy': ((200, 319, 334), (228, 412))}),
    (81, 89): ('stack', {'with': [88], 'kind': 'banner', 'opts': {'fill_pct': 0.85}}),
    (81, 91): ('stack', {'with': [90], 'kind': 'banner', 'opts': {'fill_pct': 0.85}}),
    **{(81, k): ('plate', {'box': (8, 6, 231, 41)}) for k in (69, 70)},
    # Early/Late and Month N tags sit side by side: keep the English inside the Japanese ink extent
    **{(81, k): ('plate', {'mode': 'clear', 'dark': True, 'box': (1, 1, 33, 24)}) for k in (72, 73)},
    **{(81, k): ('plate', {'mode': 'clear', 'dark': True, 'box': (1, 1, 49, 24), 'align': 'right'}) for k in range(74, 86)},
    **{(81, k): ('plate', {'mode': 'clear', 'dark': True}) for k in (86, 87)},
    (82, 52): ('plate', {'mode': 'clear'}),
    **{(84, k): ('plate', {'box': (4, 3, 195, 28)}) for k in range(0, 10)},
    (84, 16): ('plates', frames(6, 56, (6, 6, 97, 49), {0: None, 1: -22, 5: 50})),
    (84, 17): ('plates', frames(6, 56, (6, 6, 97, 49), {0: None, 5: 40})),
    (84, 18): ('plates', frames(6, 56, (6, 6, 97, 49), {})),
    (84, 31): BLUE,
    **{(84, k): ('plate', {'box': (22, 2, 101, 21)}) for k in (38, 39)},
    **{(60, k): ('plate', {'box': (40, 4, 280, 43), 'style': {'sens': (16, 0.3), 'grow': 4}}) for k in range(12, 16)},
    **{(60, k): BLUE for k in range(16, 21)},
    **{(61, k): BLUE for k in range(41, 53)},
    **{(61, k): ('plate', {'box': (4, 4, 171, 31)}) for k in range(22, 37)},
    **{(61, k): ('plate', {'box': (3, 4, 52, 19), 'erase_box': (3, 4, 36, 66), 'mode': 'dark', 'style': {'grow': 3}}) for k in range(37, 41)},
    (61, 58): ('plate', {'box': (15, 2, 57, 19)}),
    (61, 73): ('plates', [{'box': b, 'mode': 'clear'} for b in ((0, 0, 100, 21), (101, 0, 201, 21), (202, 0, 303, 21))]),
    **{(52, k): STRIP48 for k in range(14, 32)},
    **{(57, k): STRIP48 for k in range(10, 19)},
    **{(58, k): STRIP48 for k in range(16, 21)},
    (54, 0): ('plates', [{'box': (226, 20, 258, 40), 'style': {'grow': 3}}, {'box': (470, 20, 503, 40), 'style': {'grow': 3}}]),  # battle header vs / time left
    (58, 14): ('plates', [{'box': (165, 20, 197, 40), 'style': {'grow': 3}}]),  # siege header vs
    (55, 66): ('plates', [{'box': (230, 20, 262, 40), 'style': {'grow': 3}}]),  # siege battle header vs
    **{(54, k): ('plate', {'box': (4, 4, 141, 31), 'style': {'sens': (12, 0.2), 'grow': 4}}) for k in range(50, 54)},
    **{(55, k): ('plate', {'style': {'grow': 4}}) for k in range(68, 71)},
    (53, 11): ('plate', {'box': (1, 1, 46, 22), 'align': 'left'}),
    **{(46, k): ('plates', HELP_PANEL) for k in range(4, 9)},
    **{(50, k): ('plate', {'box': (6, 6, 217, 57), 'erase_box': (4, 4, 219, 59), 'style': {'sens': (10, 0.15), 'grow': 5}}) for k in range(9, 13)},
    (43, 0): ('plate', dict(GLOW, box=(140, 28, 505, 66), align='right')),
    (51, 8): ('plate', dict(GLOW, box=(30, 48, 390, 80), align='left')),
    (51, 76): ('plate', dict(GLOW, box=(70, 28, 511, 64))),
    (51, 77): ('plate', dict(GLOW, box=(0, 28, 60, 64))),
    (51, 7): ('plate', dict(GLOW, box=(4, 2, 476, 38))),
    (51, 96): ('plate', {'box': (8, 3, 327, 22)}),
    (51, 97): ('plates', [{'box': (34, 3, 80, 26)}, {'box': (108, 3, 178, 26)}, {'box': (203, 3, 263, 26)}]),   # game draws colour keys over x ~17-32, 87-107, 183-201 (text starts after them)
    # main-menu illustrations (faint animation frames, right side): 読込 cut out of the load arrow filled
    # (arrow and book stay), 特撰 rising from the chest (drifts and fades: erased in every frame, English
    # in the frames where the kanji are solid), インストール on the HDD-install disc.
    **{(51, k): ('plate', {'mode': 'holes', 'box': (46, 12, 84, 64), 'style': {'amin': 0x20}}) for k in range(22, 28)},
    **{(51, k): ('plate', {'mode': 'dark', 'box': (24, 22, 94, 62), 'cap': 18, 'style': {'grow': 3, 'amin': 0x18}}) for k in range(65, 70)},
    # install disc: the label band inside the rim (ellipse centre (63, 30)), below the hub, left of the dark wedge
    **{(51, k): ('plate', {'mode': 'clear', 'dark': True, 'outline': False, 'amin': 0x20, 'box': (20, 25, 97, 50),
                           'area': lambda x, y: ((x - 63) / 42) ** 2 + ((y - 30) / 19) ** 2 <= 1
                                                and ((x - 64) / 17) ** 2 + ((y - 19) / 8) ** 2 > 1,
                           'cap': 13}) for k in range(46, 52)},
    **{(33, k): ('banner', {}) for k in range(26, 30)},
    **{(34, k): ('plate', {'box': (6, 4, 76, 28)}) for k in range(163, 167)},
    **{(34, k): ('plate', {'box': (4, 4, 52, 28)}) for k in range(256, 264)},
}

def load_tl():
    out = {}
    if os.path.exists(TL):
        for n, line in enumerate(open(TL, encoding='ascii').read().splitlines(), 1):
            if line.strip() and not line.startswith('#'):
                k, _, v = line.partition('\t')
                e, _, t = k.partition('.')
                out[int(e), int(t)] = v
    return out

def redraw(entry, key, text):
    """-> (edited textures, clean textures) for one tl/gfx.txt item."""
    kind, opts = ITEMS.get(key, ('plate', {}))
    ids = [key[1]]
    if kind == 'stack':
        ids += opts['with']
        kind, opts = opts['kind'], opts.get('opts', {})
    texs = [tim2.Texture(entry, i) for i in ids]
    cv = Stack(texs) if len(texs) > 1 else Canvas(texs[0])
    if kind == 'plate':
        plate(cv, text, **opts)
    elif kind == 'banner':
        banner(cv, text, **opts)
    elif kind == 'plates':
        texts = text.split(';')
        if len(texts) == 1:
            texts *= len(opts)
        for o, t in zip(opts, texts):
            o = dict(o)
            if o.pop('empty', False):
                t = ''
            plate(cv, t, **o)
    else:
        raise ValueError(kind)
    return texs, [tim2.Texture(entry, i) for i in ids]

def apply(entry_fn):
    """-> {entry: new bytes}; entry_fn(i) = clean NB10 entry bytes."""
    by_entry = collections.defaultdict(dict)
    for (e, t), text in load_tl().items():
        by_entry[e][t] = text
    out = {}
    for e, items in sorted(by_entry.items()):
        clean = entry_fn(e)
        texs = []
        for t, text in sorted(items.items()):
            try:
                texs += redraw(clean, (e, t), text)[0]
            except ValueError as err:
                raise ValueError('gfx %d.%d: %s' % (e, t, err))
        assert len({x.i for x in texs}) == len(texs), 'gfx %d: a texture is edited twice' % e
        out[e] = tim2.apply(clean, texs)
    return out

def _stacked(texs):
    ims = [t.image() for t in texs]
    out = Image.new('RGBA', (max(i.width for i in ims), sum(i.height for i in ims)))
    y = 0
    for i in ims:
        out.paste(i, (0, y)); y += i.height
    return out

def preview(out, keys=None, scale=3):
    """Before/after sheet of tl/gfx.txt items (dev; Koei data, keep out of git)."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'dev'))
    import gfxdump
    tl = load_tl()
    cells = []
    for (e, t), text in sorted(tl.items()):
        if keys and not any(('%d.%d' % (e, t)).startswith(k) for k in keys):
            continue
        d = gfxdump.entry(e)
        try:
            b, a = redraw(d, (e, t), text)
        except ValueError as err:
            print('%d.%d: %s' % (e, t, err))
            continue
        pair = []
        for x in (a, b):
            im = _stacked(x)
            im = im.resize((im.width * scale, im.height * scale), Image.NEAREST)
            bg = gfxdump.checker(im.width, im.height); bg.alpha_composite(im)
            pair.append(bg)
        cells.append(('%d.%d' % (e, t), pair))
    W = max([1200] + [a.width * 2 + 4 for _, (a, b) in cells])
    x = y = rowh = 0
    pos = []
    for lab, (a, b) in cells:
        cw = a.width + b.width + 4
        if x + cw > W:
            x, y, rowh = 0, y + rowh + 16, 0
        pos.append((x, y))
        x += max(cw, 60) + 10
        rowh = max(rowh, a.height)
    sheet = Image.new('RGBA', (W, y + rowh + 16), (30, 30, 30, 255))
    dr = ImageDraw.Draw(sheet)
    for (lab, (a, b)), (px, py) in zip(cells, pos):
        dr.text((px, py), lab, fill=(255, 255, 0, 255))
        sheet.alpha_composite(a, (px, py + 12))
        sheet.alpha_composite(b, (px + a.width + 4, py + 12))
    sheet.save(out)
    print(out, len(cells))

if __name__ == '__main__':
    # gfx.py preview out.png [key prefixes...] [--scale N]
    a = sys.argv[3:]
    sc = 3
    if '--scale' in a:
        k = a.index('--scale'); sc = int(a[k + 1]); del a[k:k + 2]
    preview(sys.argv[2], a, sc)
