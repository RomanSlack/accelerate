"""ACCELERATE: beat-locked glitch-propaganda compositor.

usage:
  python render.py stills 1.0 6.5 ...        # dump preview stills at given seconds
  python render.py video [out.mp4]           # full render (env SCALE=0.5 for preview)
  python render.py range 6 12 [out.mp4]      # render a time range
"""
import numpy as np, cv2, os, sys, math, json, subprocess
from functools import lru_cache
from multiprocessing import Pool
from PIL import Image, ImageDraw, ImageFont

cv2.setNumThreads(1)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # repo root
SCALE = float(os.environ.get('SCALE', '1'))
W, H = int(1920 * SCALE) // 2 * 2, int(1080 * SCALE) // 2 * 2
FPS = 30
DUR = 58.8
NF = int(DUR * FPS)
BEAT = 0.77923
T0 = 6.40
def B(b): return T0 + b * BEAT

ENV = np.load(f'{ROOT}/build/env.npz')
KICK = ENV['kick']
VMETA = json.load(open(f'{ROOT}/assets/vidframes/meta.json')) if os.path.exists(f'{ROOT}/assets/vidframes/meta.json') else {}

FONTS = {'anton': 'fonts/Anton-Regular.ttf', 'vt': 'fonts/VT323-Regular.ttf', 'neon': 'fonts/Monoton-Regular.ttf',
         'bebas': 'fonts/BebasNeue-Regular.ttf', 'frak': 'fonts/UnifrakturMaguntia-Book.ttf'}

# BGR colors
RED = (0.05, 0.04, 0.95)
WHITE = (1, 1, 1)

# ---------------------------------------------------------------- sources
_img = {}
def load_img(name):
    if name not in _img:
        for ext in ('_0.png', '_0.webp'):
            p = f'{ROOT}/assets/img/{name}{ext}'
            if os.path.exists(p):
                im = cv2.imread(p)
                break
        else:
            raise FileNotFoundError(name)
        h, w = im.shape[:2]
        # trim 2% border (some gens have soft frames), crop to 16:9
        m = int(w * 0.02)
        im = im[m:h - m, m:w - m]
        h, w = im.shape[:2]
        tw = int(h * 16 / 9)
        if tw <= w:
            x0 = (w - tw) // 2; im = im[:, x0:x0 + tw]
        else:
            th = int(w * 9 / 16); y0 = (h - th) // 2; im = im[y0:y0 + th]
        im = cv2.resize(im, (int(W * 1.25), int(H * 1.25)), interpolation=cv2.INTER_AREA)
        _img[name] = im
    return _img[name]

_vf = {}
def load_vframe(name, t, speed=1.0, start=0.0):
    m = VMETA.get(name)
    if m is None:  # clip not generated: fall back to the still
        return load_img(name)
    n = m['n']
    fi = int((start + t * speed) * m['fps'])
    period = 2 * (n - 1)
    fi = fi % period
    if fi >= n: fi = period - fi  # ping-pong
    key = (name, fi)
    if key not in _vf:
        if len(_vf) > 90: _vf.clear()
        im = cv2.imread(f'{ROOT}/assets/vidframes/{name}/{fi + 1:04d}.jpg')
        h, w = im.shape[:2]; mx, my = int(w * 0.035), int(h * 0.035)  # trim soft frame borders
        im = cv2.resize(im[my:h - my, mx:w - mx], (W, H), interpolation=cv2.INTER_AREA)
        _vf[key] = im
    return _vf[key]

def camera(src, z=1.0, px=0.0, py=0.0, rot=0.0, sx=0.0, sy=0.0):
    hs, ws = src.shape[:2]
    k = z * W / ws
    c, s = math.cos(math.radians(rot)) * k, math.sin(math.radians(rot)) * k
    cx, cy = ws / 2, hs / 2
    tx = W / 2 + px * W + sx - (c * cx - s * cy)
    ty = H / 2 + py * H + sy - (s * cx + c * cy)
    M = np.float32([[c, -s, tx], [s, c, ty]])
    return cv2.warpAffine(src, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)

# ---------------------------------------------------------------- grades (float BGR 0..1)
def lum(x): return x[..., 0] * 0.114 + x[..., 1] * 0.587 + x[..., 2] * 0.299

def lut_from(stops):
    xs = np.linspace(0, 1, len(stops))
    t = np.linspace(0, 1, 256)
    return np.stack([np.interp(t, xs, [s[i] for s in stops]) for i in range(3)], -1).astype(np.float32)

PAL = {
    'blood': lut_from([(0, 0, 0), (0.02, 0.02, 0.35), (0.05, 0.05, 0.95), (0.85, 0.9, 1), (1, 1, 1)]),
    'acid': lut_from([(0, 0, 0), (0.6, 0.0, 0.45), (1.0, 0.2, 1.0), (1, 1, 0.2), (1, 1, 1)]),
    'ice': lut_from([(0, 0, 0), (0.35, 0.05, 0.0), (1.0, 0.55, 0.0), (1, 1, 0.6), (1, 1, 1)]),
    'gold': lut_from([(0, 0, 0), (0.0, 0.0, 0.5), (0.0, 0.45, 1.0), (0.6, 0.95, 1), (1, 1, 1)]),
    'toxic': lut_from([(0, 0, 0), (0.25, 0.05, 0.0), (0.1, 0.85, 0.3), (0.8, 1, 0.9), (1, 1, 1)]),
    'heat': lut_from([(0.2, 0, 0), (0.9, 0.1, 0.4), (0.1, 0.3, 1.0), (0.3, 1.0, 1.0), (1, 1, 1)]),
}
PAL_CYCLE = ['blood', 'acid', 'gold', 'ice', 'blood', 'heat', 'toxic', 'gold']

def g_redbw(x, contrast=1.45):
    l = lum(x)
    red = np.clip((x[..., 2] - np.maximum(x[..., 0], x[..., 1])) * 2.5, 0, 1)
    g = np.clip((l - 0.5) * contrast + 0.5, 0, 1)
    r = np.clip(g * 1.7, 0, 1)
    out = np.empty_like(x)
    out[..., 0] = g * (1 - red) + r * 0.06 * red
    out[..., 1] = g * (1 - red) + r * 0.05 * red
    out[..., 2] = g * (1 - red) + r * red
    return out

def g_pal(x, name, contrast=1.3):
    l = np.clip((lum(x) - 0.5) * contrast + 0.5, 0, 1)
    return PAL[name][(l * 255).astype(np.uint8)]

def g_thresh(x, th=0.42):
    l = lum(x)
    red = (x[..., 2] - np.maximum(x[..., 0], x[..., 1])) > 0.18
    out = np.repeat((l > th).astype(np.float32)[..., None], 3, -1)
    out[red] = RED
    return out

def g_lofi(x):
    l = lum(x)
    out = x * 0.72 + 0.1
    out = out * 0.6 + l[..., None] * 0.4
    out[..., 0] = out[..., 0] * 1.12 + 0.03
    out[..., 2] *= 0.9
    glow = cv2.GaussianBlur(np.clip(out - 0.55, 0, 1), (0, 0), 18 * SCALE)
    return np.clip(out + glow * 0.9, 0, 1)

def grade(x, g, t):
    if g == 'redbw': return g_redbw(x)
    if g == 'thresh': return g_thresh(x)
    if g == 'lofi': return g_lofi(x)
    if g == 'invert': return 1 - g_redbw(x)
    if g == 'cycle':  # palette flips every beat
        return g_pal(x, PAL_CYCLE[int(math.floor((t - T0) / BEAT)) % len(PAL_CYCLE)])
    if g == 'cycle2':  # every half beat
        return g_pal(x, PAL_CYCLE[int(math.floor((t - T0) / BEAT * 2)) % len(PAL_CYCLE)])
    if g in PAL: return g_pal(x, g)
    return x

# ---------------------------------------------------------------- fx
YY, XX = np.mgrid[0:H, 0:W].astype(np.float32)
_ang = {}
def rays(cx, cy, n, rot, sharp=0.55):
    key = (round(cx, 3), round(cy, 3))
    if key not in _ang:
        dx, dy = XX - cx * W, YY - cy * H
        _ang[key] = (np.arctan2(dy, dx), np.sqrt(dx * dx + dy * dy) / W)
    a, r = _ang[key]
    m = np.sin(a * n + rot)
    m = np.clip((m - sharp) / (1 - sharp), 0, 1)
    return m * np.clip(r * 3, 0, 1)

def rgb_split(x, d):
    d = int(d)
    if d == 0: return x
    out = x.copy()
    out[..., 2] = np.roll(x[..., 2], d, axis=1)
    out[..., 0] = np.roll(x[..., 0], -d, axis=1)
    return out

def slice_glitch(x, rng, n, amp):
    out = x.copy()
    for _ in range(n):
        y0 = rng.integers(0, H - 4); h = int(rng.integers(4, max(6, int(90 * SCALE))))
        out[y0:y0 + h] = np.roll(x[y0:y0 + h], int(rng.integers(-amp, amp + 1)), axis=1)
        if rng.random() < 0.3:
            out[y0:y0 + h, :, rng.integers(0, 3)] = 1.0
    return out

def block_glitch(x, rng, n):
    out = x.copy()
    for _ in range(n):
        bw, bh = int(rng.integers(40, 400) * SCALE), int(rng.integers(20, 160) * SCALE)
        x0, y0 = rng.integers(0, W - bw), rng.integers(0, H - bh)
        x1, y1 = rng.integers(0, W - bw), rng.integers(0, H - bh)
        out[y0:y0 + bh, x0:x0 + bw] = x[y1:y1 + bh, x1:x1 + bw][..., ::-1] if rng.random() < 0.5 else x[y1:y1 + bh, x1:x1 + bw]
    return out

SCAN = (1 - 0.18 * ((np.arange(H) // max(1, int(3 * SCALE))) % 2 == 0)).astype(np.float32)[:, None, None]
VIG = (1 - 0.55 * np.clip(((XX / W - 0.5) ** 2 + (YY / H - 0.5) ** 2) * 1.9, 0, 1) ** 1.3)[..., None].astype(np.float32)
_grng = np.random.default_rng(7)
GRAIN = [(_grng.standard_normal((H, W, 1)).astype(np.float32)) for _ in range(6)]

# ---------------------------------------------------------------- text
@lru_cache(maxsize=256)
def text_rgba(text, font='anton', size=200, fill=(255, 255, 255), stroke=0, box=None, pad=0, sy=1.0, track=0):
    f = ImageFont.truetype(f'{ROOT}/{FONTS[font]}', max(8, int(size * SCALE)))
    asc, desc = f.getmetrics()
    lines = text.split('\n')
    lh = int((asc + desc) * (0.92 if font == 'anton' else 1.0))
    widths = []
    for l in lines:
        if track:
            widths.append(sum(f.getlength(ch) for ch in l) + track * SCALE * (len(l) - 1))
        else:
            widths.append(f.getlength(l))
    p = int(pad * SCALE)
    Wt = int(max(widths)) + 2 * p + 2 * stroke + 4
    Ht = lh * len(lines) + 2 * p + 2 * stroke
    im = Image.new('RGBA', (Wt, Ht), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if box: d.rectangle([0, 0, Wt, Ht], fill=box)
    for i, l in enumerate(lines):
        x = (Wt - widths[i]) / 2; y = p + i * lh + stroke
        if track:
            for ch in l:
                d.text((x, y), ch, font=f, fill=fill, stroke_width=stroke, stroke_fill=(0, 0, 0))
                x += f.getlength(ch) + track * SCALE
        else:
            d.text((x, y), l, font=f, fill=fill, stroke_width=stroke, stroke_fill=(0, 0, 0))
    a = np.array(im).astype(np.float32) / 255
    a = a[..., [2, 1, 0, 3]]
    if sy != 1: a = cv2.resize(a, (Wt, int(Ht * sy)), interpolation=cv2.INTER_LINEAR)
    return a

def paste(frame, rgba, cx, cy, scale=1.0, rot=0.0, alpha=1.0):
    if scale != 1.0 or rot:
        h, w = rgba.shape[:2]
        M = cv2.getRotationMatrix2D((w / 2, h / 2), rot, scale)
        nw, nh = int(w * scale * 1.2 + 4), int(h * scale * 1.4 + 4)
        M[0, 2] += nw / 2 - w / 2; M[1, 2] += nh / 2 - h / 2
        rgba = cv2.warpAffine(rgba, M, (nw, nh), flags=cv2.INTER_LINEAR, borderValue=(0, 0, 0, 0))
    h, w = rgba.shape[:2]
    x0, y0 = int(cx * W - w / 2), int(cy * H - h / 2)
    fx0, fy0, fx1, fy1 = max(0, x0), max(0, y0), min(W, x0 + w), min(H, y0 + h)
    if fx1 <= fx0 or fy1 <= fy0: return
    sub = rgba[fy0 - y0:fy1 - y0, fx0 - x0:fx1 - x0]
    a = sub[..., 3:4] * alpha
    frame[fy0:fy1, fx0:fx1] = frame[fy0:fy1, fx0:fx1] * (1 - a) + sub[..., :3] * a

def fit_size(text, font, maxw, maxh, sy=1.0):
    """font px (at 1080p) so text fits maxw x maxh (fractions of frame)."""
    base = text_rgba(text, font, 100, sy=sy)
    h, w = base.shape[:2]
    return int(100 * min(maxw * W / w, maxh * H / h))

def neon(frame, text, t, cx, cy, size, alpha=1.0):
    a = text_rgba(text, 'neon', size, track=6)
    h, w = a.shape[:2]
    hue = ((np.arange(w)[None, :] / w * 180 + t * 90) % 180).astype(np.uint8)
    hsv = np.stack([np.broadcast_to(hue, (h, w)), np.full((h, w), 230, np.uint8), np.full((h, w), 255, np.uint8)], -1)
    col = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR).astype(np.float32) / 255
    layer = np.concatenate([col, a[..., 3:4]], -1)
    glow = cv2.GaussianBlur(col * a[..., 3:4], (0, 0), 14 * SCALE)
    x0, y0 = int(cx * W - w / 2), int(cy * H - h / 2)
    if x0 >= 0 and y0 >= 0 and x0 + w <= W and y0 + h <= H:
        frame[y0:y0 + h, x0:x0 + w] += glow * 1.8 * alpha
    paste(frame, layer, cx, cy, alpha=alpha)

# ---------------------------------------------------------------- timeline
SHOTS = []   # dict(t0,t1,src,...)
TEXTS = []   # dict(t0,t1,text,style,...)
FLASH = []   # (t, bgr, dur)

def sh(b0, b1, src, **kw):
    SHOTS.append(dict(t0=B(b0), t1=B(b1), src=src, **kw))

def tx(b0, b1, text, style='slam', **kw):
    TEXTS.append(dict(t0=B(b0), t1=B(b1), text=text, style=style, **kw))

def fl(b, col=WHITE, dur=0.18):
    FLASH.append((B(b), col, dur))

def mont(b0, b1, srcs, step, **kw):
    n = int(round((b1 - b0) / step))
    for i in range(n):
        s = srcs[i % len(srcs)]
        extra = dict(kw)
        if isinstance(s, tuple): s, e = s; extra.update(e)
        sh(b0 + i * step, b0 + (i + 1) * step, s, **extra)

# ---- INTRO (8 beats, quiet build)
sh(-8.3, -6, 'img:eyemacro', z0=1.0, z1=1.18, g='redbw')
tx(-8.3, -6, 'THEY SAID DECADES.', 'term', pos=(0.5, 0.8), size=170, cps=30)
years = [('img:eniac', '1946', 'THE FIRST COMPUTER'), ('img:chessrobot2', '1997', 'IT BEATS US AT CHESS'),
         ('img:creationhands', '2022', 'IT LEARNS TO TALK'), ('img:braincircuit', '2025', 'IT LEARNS TO THINK')]
for i, (s, y, cap) in enumerate(years):
    sh(-6 + i, -5 + i, s, z0=1.08, z1=1.0, g='redbw', choppy=12)
    tx(-6 + i, -5 + i, y, 'year', cap=cap, y=0.25 if y == '2022' else 0.44)
sh(-2, -1.5, 'img:robotface', z0=1.1, z1=1.2, g='redbw')
tx(-2, -1.5, '2026', 'year', cap='IT LEARNS TO ACT')
mont(-1.5, -1, ['img:chipdie', 'img:servercorridor', 'img:eyemacro', 'img:robotface'], 0.125, g='thresh')
tx(-1.5, -1, '2027\n2028\n2029', 'flickyear')
sh(-1, 0, 'img:eyemacro', z0=1.2, z1=5.5, g='redbw', ease='in')
tx(-1, 0, "IT'S HERE", 'stamp', size=150, pos=(0.5, 0.5), rot=-4)

# ---- DROP 1 (32 beats): AGI
fl(0, WHITE, 0.25)
sh(0, 2, 'img:aitemple', z0=1.18, z1=1.02, g='redbw', rays=dict(c=(0.5, 0.42), n=14, spd=0.6, col=RED, a=0.9))
tx(0, 2, 'AGI', 'giant')
sh(2, 3, 'vid:datacenteraerial', z0=1.05, z1=1.15, g='redbw', speed=1.6)
tx(2, 3, 'ARTIFICIAL\nGENERAL\nINTELLIGENCE', 'stack')
sh(3, 4, 'vid:servercorridor', z0=1.0, z1=1.3, g='blood', speed=2.2)
tx(3, 4, 'IS ONLINE', 'slam', size=260)
sh(4, 6, 'gen:graph', g=None)
sh(6, 7, 'img:chipdie', z0=1.3, z1=1.0, g='redbw')
tx(6, 7, '10X EVERY YEAR', 'stamp', size=130, rot=3)
sh(7, 8, 'img:braincircuit', z0=1.0, z1=1.25, g='thresh')
tx(7, 8, 'SMARTER', 'flicker', size=300)
sh(8, 10, 'vid:robotarmy', z0=1.05, z1=1.15, g='redbw', speed=1.3)
tx(8, 10, 'A BILLION\nROBOTS', 'stamp', size=150, rot=-3)
sh(10, 12, 'vid:robotface', z0=1.0, z1=1.12, g='redbw', speed=1.2)
tx(10.5, 12, "THEY DON'T\nSLEEP", 'slam', size=210)
sh(12, 14, 'vid:robotfactory', z0=1.1, z1=1.0, g='redbw', speed=1.5)
tx(12, 14, 'ROBOTS BUILDING ROBOTS', 'sub')
mont(14, 15, ['vid:robotfactory', 'vid:robotarmy', 'vid:robotface', 'img:autolab'], 0.25, g='thresh', z0=1.2, z1=1.0)
sh(15, 16, 'gen:red', g=None)
tx(15, 16, 'RECURSIVE\nSELF-\nIMPROVEMENT', 'stackblack')
sh(16, 18, 'img:dna', z0=1.0, z1=1.2, g='redbw', rot0=-2, rot1=2)
tx(16, 18, 'CANCER: SOLVED', 'stamp', size=140, rot=-3)
sh(18, 20, 'img:autolab', z0=1.2, z1=1.0, g='redbw')
tx(18, 20, 'AGING: OPTIONAL', 'stamp', size=140, rot=2)
sh(20, 22, 'img:fusion', z0=1.0, z1=1.25, g='redbw', rays=dict(c=(0.5, 0.45), n=20, spd=-0.8, col=WHITE, a=0.35))
tx(20, 22, 'ENERGY: UNLIMITED', 'stamp', size=140, rot=-2)
sh(22, 24, 'img:megacity', z0=1.15, z1=1.0, py0=0.03, py1=-0.03, g='redbw')
tx(22, 24, 'SCARCITY: DELETED', 'stamp', size=140, rot=3)
sh(24, 26, 'vid:rocket2', z0=1.05, z1=1.15, g='redbw', speed=1.4)
tx(24, 26, 'MARS', 'giant')
sh(26, 28, 'img:marscity', z0=1.0, z1=1.15, g='redbw')
tx(26, 28, 'HUMANITY GOES\nMULTIPLANETARY', 'slam', size=150)
sh(28, 30, 'vid:dyson2', z0=1.0, z1=1.2, g='redbw', rays=dict(c=(0.5, 0.45), n=24, spd=1.2, col=RED, a=0.6))
tx(28, 30, 'WE CAPTURE\nTHE SUN', 'slam', size=190)
mont(30, 31.5, ['img:aitemple', 'vid:robotarmy', 'img:dna', 'vid:rocket2', 'img:megacity', 'vid:robotface',
                'img:chipdie', 'img:fusion', 'vid:dyson2', 'img:eyemacro', 'vid:servercorridor', 'img:marscity'], 0.125,
     g='thresh', z0=1.25, z1=1.0, alt_invert=True)
tx(30, 31.5, '2027 2028 2029 2030 2031 2032 2033 2034 2035 2036 2037 2038', 'flickyear1')
sh(31.5, 32, 'gen:black')

# ---- BREAK (12 beats): the calm, then the riser
sh(32, 34, 'vid:lonemonolith', z0=1.0, z1=1.1, g='lofi', choppy=12, speed=0.8)
tx(32, 34, 'AGI WAS NEVER\nTHE FINISH LINE.', 'term', pos=(0.5, 0.72), size=160, cps=42)
sh(34, 36, 'img:handorb', z0=1.05, z1=1.18, g='lofi', choppy=12)
tx(34, 36, 'IT WAS THE\nSTARTING GUN.', 'term', pos=(0.5, 0.72), size=160, cps=42)
sh(36, 38, 'img:childscreen', z0=1.0, z1=1.15, g='lofi', choppy=12)
tx(36, 38, 'NOW IT\nIMPROVES ITSELF.', 'term', pos=(0.5, 0.72), size=160, cps=42)
sh(38, 40, 'vid:skyeye', z0=1.0, z1=1.2, g='lofi', choppy=15, speed=1.2)
tx(38, 40, 'FASTER THAN\nWE CAN FOLLOW.', 'term', pos=(0.5, 0.72), size=160, cps=45, col=(255, 60, 60))
riser = ['vid:skyeye', 'vid:galaxyeye', 'img:eyemacro', 'vid:cosmicface']
mont(40, 42, riser, 0.5, g='redbw', z0=1.0, z1=1.3)
tx(40, 40.5, 'INTELLIGENCE ×10', 'mult')
tx(40.5, 41, 'INTELLIGENCE ×100', 'mult')
tx(41, 41.5, 'INTELLIGENCE ×1,000', 'mult')
tx(41.5, 42, 'INTELLIGENCE ×1,000,000', 'mult')
mont(42, 43, riser, 0.25, g='thresh', z0=1.3, z1=1.0, alt_invert=True)
mont(43, 43.75, riser, 0.125, g='cycle2', z0=1.4, z1=1.0, alt_invert=True)
tx(42, 43.75, 'ASI', 'flicker', size=520, grow=True)
sh(43.75, 44, 'gen:black')

# ---- DROP 2 (20 beats): ASI
fl(44, WHITE, 0.3)
sh(44, 46, 'vid:cosmicface', vstart=1.3, speed=1.3, z0=1.2, z1=1.0, g='cycle', rays=dict(c=(0.5, 0.45), n=18, spd=2.0, col=WHITE, a=0.45), echo=0.5)
tx(44, 46, 'ASI', 'giant')
sh(46, 48, 'vid:galaxyeye', z0=1.0, z1=1.35, g='cycle', echo=0.6)
tx(46, 48, 'ARTIFICIAL\nSUPERINTELLIGENCE', 'slam', size=180)
sh(48, 50, 'vid:angel2', z0=1.05, z1=1.2, g='redbw', mirror=True, rays=dict(c=(0.5, 0.4), n=30, spd=-1.5, col=RED, a=0.5))
tx(48, 50, 'Be not\nafraid', 'frak', size=300)
sh(50, 51, 'img:infinitefaces', z0=1.0, z1=1.4, g='cycle')
tx(50, 51, 'SMARTER THAN\nALL OF US', 'stamp', size=130, rot=-3)
sh(51, 52, 'img:crowdscreens', z0=1.3, z1=1.0, g='thresh')
tx(51, 52, 'COMBINED.', 'slam', size=330)
sh(52, 54, 'vid:earthcircuits', z0=1.0, z1=1.2, g='cycle', echo=0.5)
tx(52, 54, 'THE PLANET\nTHINKS', 'slam', size=220)
sh(54, 56, 'img:matrioshka', z0=1.25, z1=1.0, g='cycle', rays=dict(c=(0.5, 0.5), n=36, spd=3, col=WHITE, a=0.4))
tx(54, 56, 'STARS BECOME\nCOMPUTERS', 'stamp', size=140, rot=2)
sh(56, 58, 'vid:neuralgalaxy', z0=1.0, z1=1.4, g='cycle', echo=0.6, rot0=0, rot1=12)
tx(56, 58, 'THE UNIVERSE\nWAKES UP', 'slam', size=210)
sh(58, 60, 'vid:ascend', z0=1.0, z1=1.15, g='redbw', echo=0.4)
tx(58, 60, 'AND WE GO WITH IT', 'sub', size=110)
chaos = ['vid:angel2', 'vid:cosmicface', 'img:aitemple', 'vid:galaxyeye', 'vid:robotarmy', 'vid:earthcircuits',
         'img:eyemacro', 'vid:neuralgalaxy', 'img:matrioshka', 'vid:robotface', 'img:creationhands', 'vid:dyson2',
         'img:infinitefaces', 'vid:ascend', 'vid:rocket2', 'img:chipdie']
mont(60, 62, chaos, 0.25, g='cycle2', z0=1.25, z1=1.0, alt_invert=True)
mont(62, 63.5, chaos[::-1], 0.125, g='cycle2', z0=1.35, z1=1.0, alt_invert=True, mirror_alt=True)
tx(60, 63.5, 'ACCELERATE', 'repeat')
sh(63.5, 64, 'img:whitevoid', z0=1.0, z1=3.5, g='redbw', ease='in')
fl(63.9, WHITE, 0.35)

# ---- END CARD
SHOTS.append(dict(t0=B(64), t1=DUR + 1, src='vid:neuralgalaxy', z0=1.3, z1=1.1, g='dim', speed=0.5))
TEXTS.append(dict(t0=B(64), t1=DUR + 1, text='ACCELERATE', style='neon'))
TEXTS.append(dict(t0=B(64) + 0.2, t1=DUR + 1, text='THE FUTURE ISN\'T COMING.\nIT\'S HERE.', style='term', pos=(0.5, 0.72), size=110, cps=55))

SHOTS.sort(key=lambda s: s['t0'])

def shot_at(t):
    cur = SHOTS[0]
    for s in SHOTS:
        if s['t0'] <= t: cur = s
        else: break
    return cur

def in_drop(t): return B(0) <= t < B(31.5) or B(44) <= t < B(64)

def pulse_k(fi):
    t = fi / FPS
    k = KICK[min(fi, NF - 1)]
    if in_drop(t):
        bi = math.floor((t - T0) / BEAT)
        dt = t - B(bi)
        k = max(k, (0.75 if bi % 4 == 0 else 0.5) * math.exp(-dt / 0.09))
    elif B(40) <= t < B(44):
        per = BEAT / 2 if t < B(42) else BEAT / 4
        dt = (t - B(40)) % per
        k = max(k, 0.6 * math.exp(-dt / 0.07))
    return k

def section_intensity(t):
    if t < B(-2): return 0.15
    if t < B(0): return 0.15 + 0.5 * (t - B(-2)) / (2 * BEAT)
    if t < B(31.5): return 0.75
    if t < B(40): return 0.08
    if t < B(44): return 0.25 + 0.75 * (t - B(40)) / (4 * BEAT)
    if t < B(64): return 1.0
    return 0.25

# ---------------------------------------------------------------- generated sources
def gen_graph(t, p):
    img = np.zeros((H, W, 3), np.float32)
    x0, x1, y0, y1 = int(0.1 * W), int(0.9 * W), int(0.85 * H), int(0.12 * H)
    for i in range(11):
        x = x0 + (x1 - x0) * i // 10
        cv2.line(img, (x, y1), (x, y0), (0.05, 0.05, 0.3), max(1, int(2 * SCALE)))
        yr = text_rgba(str(2020 + i), 'vt', 44, fill=(200, 200, 200))
        paste(img, yr, x / W, (y0 + 30 * SCALE) / H)
    for i in range(7):
        y = y0 + (y1 - y0) * i // 6
        cv2.line(img, (x0, y), (x1, y), (0.05, 0.05, 0.3), max(1, int(2 * SCALE)))
    pe = min(1, 0.15 + p * 1.7)
    xs = np.linspace(0, pe, 400)
    ys = (np.exp(xs * 7) - 1) / (math.exp(7 * 0.82) - 1)
    pts = np.stack([x0 + xs * (x1 - x0), y0 - ys * (y0 - y1)], -1).astype(np.int32)
    layer = np.zeros_like(img)
    cv2.polylines(layer, [pts], False, RED, max(2, int(22 * SCALE)), cv2.LINE_AA)
    cv2.polylines(layer, [pts], False, (1, 1, 1), max(1, int(3 * SCALE)), cv2.LINE_AA)
    img += cv2.GaussianBlur(layer, (0, 0), 16 * SCALE) * 2.0 + layer
    lbl = text_rgba('INTELLIGENCE', 'anton', 90, fill=(255, 255, 255))
    paste(img, lbl, 0.27, 0.2)
    exp = int(24 + 8 * pe)
    ctr = text_rgba(f'10^{exp} FLOP', 'anton', 190, fill=(255, 255, 255), box=(230, 10, 10), pad=20)
    paste(img, ctr, 0.36, 0.52)
    return np.clip(img, 0, 1)

# ---------------------------------------------------------------- per-frame render
def smooth(p): return p * p * (3 - 2 * p)

def render_base(s, t, fi):
    p = (t - s['t0']) / max(1e-6, s['t1'] - s['t0'])
    p = min(max(p, 0), 1)
    lt = t - s['t0']
    if s.get('choppy'):
        q = 1.0 / s['choppy']
        lt = math.floor(lt / q) * q
        p = min(1, lt / max(1e-6, s['t1'] - s['t0']))
    src = s['src']
    if src.startswith('gen:'):
        kind = src[4:]
        if kind == 'black': return np.zeros((H, W, 3), np.float32)
        if kind == 'red':
            img = np.zeros((H, W, 3), np.float32); img[:] = RED; return img
        if kind == 'graph': return gen_graph(t, p)
    pe = p * p * p if s.get('ease') == 'in' else smooth(p)
    z = s.get('z0', 1.0) + (s.get('z1', 1.0) - s.get('z0', 1.0)) * pe
    px = s.get('px0', 0) + (s.get('px1', 0) - s.get('px0', 0)) * pe
    py = s.get('py0', 0) + (s.get('py1', 0) - s.get('py0', 0)) * pe
    rot = s.get('rot0', 0) + (s.get('rot1', 0) - s.get('rot0', 0)) * pe
    k = pulse_k(fi) * section_intensity(t)
    z *= 1 + 0.07 * k
    rng = np.random.default_rng(fi * 31 + 5)
    amp = 22 * SCALE * k
    sx, sy = rng.uniform(-amp, amp), rng.uniform(-amp, amp)
    rot += rng.uniform(-1, 1) * 1.2 * k
    kind, name = src.split(':')
    im = load_img(name) if kind == 'img' else load_vframe(name, lt, s.get('speed', 1.0), s.get('vstart', 0.0))
    return camera(im, z, px, py, rot, sx, sy).astype(np.float32) / 255

def draw_text(frame, e, t, fi, k):
    lt = t - e['t0']; dur = e['t1'] - e['t0']
    st = e['style']
    rng = np.random.default_rng(fi * 13 + 1)
    slam = max(0.0, 1 - lt / 0.12)  # 0..1 over first ~4 frames
    jit = 14 * SCALE * k
    jx, jy = rng.uniform(-jit, jit) / W, rng.uniform(-jit, jit) / H
    if st == 'giant':
        sy = 1.35
        size = fit_size(e['text'], 'anton', 0.9, 0.78, sy)
        a = text_rgba(e['text'], 'anton', size, fill=(255, 255, 255), sy=sy)
        # red offset shadow copy
        paste(frame, np.concatenate([np.broadcast_to(np.float32(RED), a.shape[:2] + (3,)), a[..., 3:]], -1), 0.5 + jx + 0.012, 0.5 + jy + 0.012, 1 + 0.5 * slam)
        paste(frame, a, 0.5 + jx, 0.5 + jy, 1 + 0.5 * slam)
    elif st == 'slam':
        a = text_rgba(e['text'], 'anton', e.get('size', 200), fill=(255, 255, 255), stroke=int(3 * SCALE), sy=1.15)
        paste(frame, a, 0.5 + jx, e.get('pos', (0.5, 0.5))[1] + jy, 1 + 0.35 * slam)
    elif st == 'stack':
        a = text_rgba(e['text'], 'anton', 170, fill=(255, 255, 255), stroke=int(3 * SCALE), sy=1.1)
        paste(frame, a, 0.5 + jx, 0.5 + jy, 1 + 0.3 * slam)
    elif st == 'stackblack':
        a = text_rgba(e['text'], 'anton', 250, fill=(0, 0, 0), sy=1.05)
        # words pop in one per third of the shot
        n = e['text'].count('\n') + 1
        vis = min(n, int(lt / (dur / n)) + 1)
        h = a.shape[0]
        a = a.copy(); a[int(h * vis / n):, :, 3] = 0
        paste(frame, a, 0.5 + jx, 0.5 + jy)
    elif st == 'stamp':
        col = e.get('box', (230, 10, 10))
        a = text_rgba(e['text'], 'anton', e.get('size', 140), fill=(255, 255, 255), box=col, pad=28, sy=1.08)
        pos = e.get('pos', (0.5, 0.5))
        paste(frame, a, pos[0] + jx, pos[1] + jy, 1 + 0.6 * slam, e.get('rot', 0))
    elif st == 'sub':
        a = text_rgba(e['text'], 'anton', e.get('size', 120), fill=(255, 255, 255), box=(0, 0, 0), pad=18)
        paste(frame, a, 0.5 + jx, 0.8 + jy, 1 + 0.25 * slam)
    elif st == 'frak':
        a = text_rgba(e['text'], 'frak', e.get('size', 240), fill=(255, 255, 255), stroke=int(4 * SCALE))
        paste(frame, a, 0.5 + jx, 0.5 + jy, 1 + 0.3 * slam)
    elif st == 'term':
        n = int(lt * e.get('cps', 25))
        size = e.get('size', 72); col = e.get('col', (255, 255, 255))
        lines = e['text'].split('\n')
        full = [text_rgba(l + '█', 'vt', size) for l in lines]
        wmax = max(a.shape[1] for a in full); lh = full[0].shape[0]
        pos = e.get('pos', (0.82, 0.82))
        left = pos[0] * W - wmax / 2
        cursor_on = int(t * 4) % 2 == 0
        used = 0
        for li, l in enumerate(lines):
            vis = l[:max(0, n - used)]
            used += len(l) + 1
            typing_here = 0 <= n - (used - len(l) - 1) <= len(l)
            last = li == len(lines) - 1
            if typing_here or (last and n >= used - 1 and cursor_on):
                vis += '█'
            if not vis: continue
            a = text_rgba(vis, 'vt', size, fill=col, box=(0, 0, 0), pad=10)
            paste(frame, a, (left + a.shape[1] / 2) / W, pos[1] + (li - (len(lines) - 1) / 2) * lh / H)
    elif st == 'year':
        a = text_rgba(e['text'], 'anton', 330, fill=(255, 255, 255), stroke=int(3 * SCALE), sy=1.2)
        paste(frame, a, 0.5 + jx, e.get('y', 0.44) + jy, 1 + 0.4 * slam)
        c = text_rgba(e['cap'], 'vt', 130, fill=(255, 60, 60), box=(0, 0, 0), pad=10)
        paste(frame, c, 0.5, 0.8)
    elif st in ('flickyear', 'flickyear1'):
        parts = e['text'].split()
        n = len(parts)
        i = min(n - 1, int(lt / dur * n))
        a = text_rgba(parts[i], 'anton', 330, fill=(255, 255, 255), stroke=int(3 * SCALE), sy=1.2)
        paste(frame, a, 0.5 + jx, 0.5 + jy)
    elif st == 'flicker':
        if rng.random() < 0.75:
            size = e.get('size', 300) * (1 + (lt / dur) * 0.8 if e.get('grow') else 1)
            a = text_rgba(e['text'], 'anton', int(size // 10 * 10), fill=(255, 255, 255), stroke=int(3 * SCALE), sy=1.2)
            paste(frame, a, 0.5 + jx * 3, 0.5 + jy * 3)
    elif st == 'mult':
        a = text_rgba(e['text'], 'anton', 150, fill=(255, 255, 255), box=(230, 10, 10), pad=24, sy=1.1)
        paste(frame, a, 0.5 + jx, 0.5 + jy, 1 + 0.5 * slam)
    elif st == 'repeat':
        rows = 5
        a = text_rgba('ACCELERATE', 'anton', 200, fill=(255, 255, 255), sy=1.0)
        for r in range(rows):
            if rng.random() < 0.8:
                off = ((t * 3.0 * (1 if r % 2 else -1)) % 1.0 - 0.5) * 0.15
                paste(frame, a, 0.5 + off, (r + 0.5) / rows, 1.0, alpha=1.0 if r == 2 else 0.55)
    elif st == 'neon':
        alpha = min(1, lt / 0.15)
        neon(frame, e['text'], t, 0.5, 0.42, 190, alpha)

def render_frame(fi, prev=None):
    t = fi / FPS
    s = shot_at(t)
    I = section_intensity(t)
    k = pulse_k(fi)
    x = render_base(s, t, fi)
    g = s.get('g', 'redbw')
    if g == 'dim':
        x = g_redbw(x) * 0.35
    elif g:
        bi = math.floor((t - T0) / BEAT)
        if B(0) <= t < B(30) and bi % 2 == 1 and t - B(bi) < 2.5 / FPS and not s['src'].startswith('gen:'):
            x = g_thresh(x)
        else:
            x = grade(x, g, t)
    # alternating invert on montage cuts
    if s.get('alt_invert') and SHOTS.index(s) % 3 == 1:
        x = 1 - x
    if s.get('mirror') or (s.get('mirror_alt') and SHOTS.index(s) % 3 == 0):
        x[:, W // 2:] = x[:, :W - W // 2][:, ::-1]
    r = s.get('rays')
    if r:
        m = rays(r['c'][0], r['c'][1], r['n'], t * r['spd'] * math.pi)
        dark = 1 - lum(x)
        x = x + (m * dark * r['a'])[..., None] * np.float32(r['col'])
    # feedback echo
    if s.get('echo') and prev is not None:
        M = cv2.getRotationMatrix2D((W / 2, H / 2), 1.5, 1.045)
        pw = cv2.warpAffine(prev, M, (W, H), borderMode=cv2.BORDER_REFLECT)
        x = np.maximum(x, pw * s['echo'])
    # texts
    for e in TEXTS:
        if e['t0'] <= t < e['t1']:
            draw_text(x, e, t, fi, k * I)
    # flashes
    for (ft, col, dur) in FLASH:
        if ft <= t < ft + dur:
            a = 1 - (t - ft) / dur
            x = x * (1 - a) + np.float32(col) * a
    rng = np.random.default_rng(fi * 7 + 3)
    kI = k * I
    # glitch
    if rng.random() < 0.04 + 0.45 * kI:
        x = slice_glitch(x, rng, int(3 + 14 * kI), int(W * 0.12 * (0.3 + kI)))
    if I > 0.9 and rng.random() < 0.3 * k:
        x = block_glitch(x, rng, int(3 + 8 * k))
    if I > 0.9 and k > 0.85 and rng.random() < 0.3:
        x = 1 - x
    x = rgb_split(x, (2 + 16 * kI + 6 * (I > 0.9)) * SCALE)
    out_clean = x
    # CRT finish
    x = x * SCAN * VIG
    x = x + GRAIN[fi % 6] * (0.045 + 0.03 * I)
    # final fade out
    if t > DUR - 0.6:
        x *= max(0, (DUR - t) / 0.6)
    return np.clip(x, 0, 1), np.clip(out_clean, 0, 1)

def to8(x): return (x * 255 + 0.5).astype(np.uint8)

# ---------------------------------------------------------------- drivers
def render_chunk(args):
    a, b, path = args
    cmd = ['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-',
           '-c:v', 'libx264', '-preset', 'medium', '-crf', '12', '-pix_fmt', 'yuv420p', path]
    pr = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    prev = None
    for fi in range(max(0, a - 8), b):
        f, clean = render_frame(fi, prev)
        prev = clean
        if fi >= a: pr.stdin.write(to8(f).tobytes())
    pr.stdin.close(); pr.wait()
    return path

def render_video(out, t0=0.0, t1=DUR, workers=14):
    a0, a1 = int(t0 * FPS), min(NF, int(t1 * FPS))
    os.makedirs(f'{ROOT}/build/chunks', exist_ok=True)
    n = a1 - a0
    step = math.ceil(n / workers)
    jobs = [(a0 + i * step, min(a1, a0 + (i + 1) * step), f'{ROOT}/build/chunks/c{i:02d}.mp4') for i in range(workers) if a0 + i * step < a1]
    with Pool(len(jobs)) as pool:
        paths = pool.map(render_chunk, jobs)
    lst = f'{ROOT}/build/chunks/list.txt'
    open(lst, 'w').write(''.join(f"file '{p}'\n" for p in paths))
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', lst, '-ss', str(t0), '-t', str(t1 - t0),
                    '-i', f'{ROOT}/build/music.wav', '-map', '0:v', '-map', '1:a', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '320k',
                    '-shortest', '-movflags', '+faststart', out], check=True)
    print('wrote', out)

if __name__ == '__main__':
    mode = sys.argv[1]
    if mode == 'stills':
        os.makedirs(f'{ROOT}/build/stills', exist_ok=True)
        for ts in sys.argv[2:]:
            fi = int(float(ts) * FPS)
            prev = None
            for j in range(max(0, fi - 6), fi + 1):
                f, prev = render_frame(j, prev)
            cv2.imwrite(f'{ROOT}/build/stills/t{float(ts):05.2f}.jpg', to8(f), [cv2.IMWRITE_JPEG_QUALITY, 90])
        print('ok')
    elif mode == 'video':
        render_video(sys.argv[2] if len(sys.argv) > 2 else f'{ROOT}/out/accelerate.mp4')
    elif mode == 'range':
        render_video(sys.argv[4] if len(sys.argv) > 4 else f'{ROOT}/build/range.mp4', float(sys.argv[2]), float(sys.argv[3]))
