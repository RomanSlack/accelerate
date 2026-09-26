"""Generative treatments: footage in, designed frame out. All return float32 BGR 0..1 at (H, W)."""
import numpy as np, cv2, math
from PIL import Image, ImageDraw, ImageFont
from functools import lru_cache

def gray(x):
    return x[..., 0] * 0.114 + x[..., 1] * 0.587 + x[..., 2] * 0.299

def to3(g): return np.repeat(g[..., None], 3, -1)

def glow(img, sigma, amt):
    h, w = img.shape[:2]
    s = cv2.resize(img, (w // 4, h // 4), interpolation=cv2.INTER_AREA)
    s = cv2.GaussianBlur(s, (0, 0), sigma / 4)
    return img + cv2.resize(s, (w, h), interpolation=cv2.INTER_LINEAR) * amt

# ---------------------------------------------------------------- point cloud
_pc_rand = {}
def pointcloud(g, W, H, yaw=0.0, pitch=0.0, explode=0.0, depth=0.9, step=4, zoom=1.0, thresh=0.1):
    gh, gw = H // step, W // step
    l = cv2.resize(g, (gw, gh), interpolation=cv2.INTER_AREA)
    l = np.clip((l - 0.5) * 2.2 + 0.45, 0, 1)
    ys, xs = np.nonzero(l > thresh)
    v = l[ys, xs]
    key = (gw, gh)
    if key not in _pc_rand:
        _pc_rand[key] = np.random.default_rng(3).standard_normal((gh, gw, 3)).astype(np.float32)
    rnd = _pc_rand[key][ys, xs]
    asp = W / H
    X = (xs / gw - 0.5) * 2 * asp
    Y = (ys / gh - 0.5) * 2
    Z = (v - 0.5) * -depth
    if explode:
        X = X + rnd[:, 0] * explode
        Y = Y + rnd[:, 1] * explode
        Z = Z + rnd[:, 2] * explode
    cy, sy = math.cos(yaw), math.sin(yaw)
    X, Z = X * cy + Z * sy, -X * sy + Z * cy
    cp, sp = math.cos(pitch), math.sin(pitch)
    Y, Z = Y * cp - Z * sp, Y * sp + Z * cp
    d = 3.2
    f = d * H / 2 * zoom
    zz = Z + d
    ok = zz > 0.2
    sx = (X[ok] / zz[ok] * f + W / 2).astype(np.int32)
    sy_ = (Y[ok] / zz[ok] * f + H / 2).astype(np.int32)
    vv = v[ok]
    m = (sx >= 0) & (sx < W) & (sy_ >= 0) & (sy_ < H)
    img = np.bincount(sy_[m] * W + sx[m], weights=vv[m] * 1.4, minlength=W * H).reshape(H, W).astype(np.float32)
    img = cv2.dilate(img, np.ones((2, 2), np.uint8))
    img = glow(np.clip(img, 0, 1), 10, 0.8)
    return to3(np.clip(img, 0, 1.2))

# ---------------------------------------------------------------- contour lines
def contours(g, W, H, n=9, phase=0.0, thick=2, work=480):
    wh = int(work * H / W)
    l = cv2.GaussianBlur(cv2.resize(g, (work, wh), interpolation=cv2.INTER_AREA), (0, 0), 1.6)
    l8 = (np.clip(l, 0, 1) * 255).astype(np.uint8)
    out = np.zeros((H, W), np.float32)
    sc = W / work
    for k in range(n):
        th = int(((k + phase % 1.0) / n) * 230 + 12)
        _, b = cv2.threshold(l8, th, 255, cv2.THRESH_BINARY)
        cs, _ = cv2.findContours(b, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        cs = [(c.astype(np.float32) * sc).astype(np.int32) for c in cs if len(c) > 6]
        cv2.polylines(out, cs, True, 0.35 + 0.65 * k / n, thick, cv2.LINE_AA)
    return to3(glow(out, 8, 0.5))

# ---------------------------------------------------------------- dot matrix / ascii
@lru_cache(maxsize=8)
def disc_atlas(cell, levels=16):
    a = np.zeros((levels, cell, cell), np.float32)
    for i in range(levels):
        r = (cell / 2) * math.sqrt(i / (levels - 1)) * 0.98
        cv2.circle(a[i], (cell // 2, cell // 2), max(0, int(round(r))), 1.0, -1, cv2.LINE_AA)
    return a

RAMP = " .:-=+*#%@"
@lru_cache(maxsize=8)
def glyph_atlas(cell, font_path):
    f = ImageFont.truetype(font_path, int(cell * 1.25))
    a = np.zeros((len(RAMP), cell, cell), np.float32)
    for i, ch in enumerate(RAMP):
        im = Image.new('L', (cell, cell), 0)
        ImageDraw.Draw(im).text((cell / 2, cell / 2), ch, font=f, fill=255, anchor='mm')
        a[i] = np.array(im, np.float32) / 255
    return a

def matrix(g, W, H, cell=14, kind='dots', font_path=None, gain=1.2):
    gw, gh = W // cell, H // cell
    l = np.clip(cv2.resize(g, (gw, gh), interpolation=cv2.INTER_AREA) * gain, 0, 1)
    atlas = disc_atlas(cell) if kind == 'dots' else glyph_atlas(cell, font_path)
    q = (l * (len(atlas) - 1) + 0.5).astype(np.int32)
    tiles = atlas[q]                                  # gh, gw, cell, cell
    img = tiles.transpose(0, 2, 1, 3).reshape(gh * cell, gw * cell)
    out = np.zeros((H, W), np.float32)
    oy, ox = (H - gh * cell) // 2, (W - gw * cell) // 2
    out[oy:oy + gh * cell, ox:ox + gw * cell] = img
    return to3(out)

# ---------------------------------------------------------------- edges
def edges(g, W, H, lo=40, hi=110):
    s = cv2.resize(g, (W // 2, H // 2), interpolation=cv2.INTER_AREA)
    e = cv2.Canny((cv2.GaussianBlur(s, (0, 0), 1.2) * 255).astype(np.uint8), lo, hi)
    e = cv2.resize(e, (W, H), interpolation=cv2.INTER_LINEAR).astype(np.float32) / 255
    return to3(glow(e, 10, 1.2))

# ---------------------------------------------------------------- layouts / masks
def strips(frames, W, H, n, shift=0.0, gutter=6, vertical=True):
    """frames: list of full-size float images; strip i shows frames[i % len]."""
    out = np.zeros((H, W, 3), np.float32)
    L = W if vertical else H
    edges_ = [int(round((i / n + shift / n) * L)) for i in range(n + 1)]
    for i in range(n):
        a, b = max(0, edges_[i] + gutter // 2), min(L, edges_[i + 1] - gutter // 2)
        if b <= a: continue
        src = frames[i % len(frames)]
        if vertical: out[:, a:b] = src[:, a:b]
        else: out[a:b] = src[a:b]
    return out

def iris(x, W, H, r, cx=0.5, cy=0.5, feather=3):
    yy, xx = np.ogrid[:H, :W]
    d = np.sqrt((xx - cx * W) ** 2 + (yy - cy * H) ** 2)
    m = np.clip((r * H - d) / feather, 0, 1).astype(np.float32)
    return x * m[..., None]

def tunnel(x, W, H, phase, levels=6, ratio=0.6, border=0.012):
    """Droste: nested copies shrinking toward center; phase in [0,1) loops seamlessly."""
    out = np.zeros_like(x)
    bw = max(2, int(W * border))
    for k in range(levels):
        s = ratio ** (k + phase - 1)
        w, h = int(W * s), int(H * s)
        if w < 8: break
        img = cv2.resize(x, (w, h), interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_LINEAR)
        x0, y0 = (W - w) // 2, (H - h) // 2
        sx0, sy0 = max(0, -x0), max(0, -y0)
        dx0, dy0 = max(0, x0), max(0, y0)
        cw, ch = min(W - dx0, w - sx0), min(H - dy0, h - sy0)
        out[dy0:dy0 + ch, dx0:dx0 + cw] = img[sy0:sy0 + ch, sx0:sx0 + cw]
        if x0 > 0 and y0 > 0:
            cv2.rectangle(out, (x0, y0), (x0 + w - 1, y0 + h - 1), (0, 0, 0), bw)
    return out

def slitscan(frames, W, H, vertical=True):
    """frames: list of full frames at increasing time offsets; each band from a different time."""
    n = len(frames)
    out = np.zeros((H, W, 3), np.float32)
    L = W if vertical else H
    for i, f in enumerate(frames):
        a, b = i * L // n, (i + 1) * L // n
        if vertical: out[:, a:b] = f[:, a:b]
        else: out[a:b] = f[a:b]
    return out

# ---------------------------------------------------------------- wireframe geometry
def icosphere(sub=1):
    t = (1 + 5 ** 0.5) / 2
    v = [(-1, t, 0), (1, t, 0), (-1, -t, 0), (1, -t, 0), (0, -1, t), (0, 1, t), (0, -1, -t), (0, 1, -t),
         (t, 0, -1), (t, 0, 1), (-t, 0, -1), (-t, 0, 1)]
    f = [(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11), (1, 5, 9), (5, 11, 4), (11, 10, 2), (10, 7, 6), (7, 1, 8),
         (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9), (4, 9, 5), (2, 4, 11), (6, 2, 10), (8, 6, 7), (9, 8, 1)]
    v = [np.array(p, float) / np.linalg.norm(p) for p in v]
    for _ in range(sub):
        cache, nf = {}, []
        def mid(a, b):
            k = (min(a, b), max(a, b))
            if k not in cache:
                m = v[a] + v[b]; v.append(m / np.linalg.norm(m)); cache[k] = len(v) - 1
            return cache[k]
        for a, b, c in f:
            ab, bc, ca = mid(a, b), mid(b, c), mid(c, a)
            nf += [(a, ab, ca), (b, bc, ab), (c, ca, bc), (ab, bc, ca)]
        f = nf
    E = set()
    for a, b, c in f:
        for p, q in ((a, b), (b, c), (c, a)): E.add((min(p, q), max(p, q)))
    return np.array(v), np.array(sorted(E))

def torus(R=1.0, r=0.35, nu=36, nv=14):
    V, E = [], []
    for i in range(nu):
        for j in range(nv):
            u, w = 2 * math.pi * i / nu, 2 * math.pi * j / nv
            V.append(((R + r * math.cos(w)) * math.cos(u), r * math.sin(w), (R + r * math.cos(w)) * math.sin(u)))
            k = i * nv + j
            E.append((k, ((i + 1) % nu) * nv + j)); E.append((k, i * nv + (j + 1) % nv))
    return np.array(V), np.array(E)

GEOM = {'ico': icosphere(2), 'ico1': icosphere(1), 'torus': torus()}
def wire(W, H, shape='ico', yaw=0, pitch=0, roll=0, scale=0.35, cx=0.5, cy=0.5, thick=1, noise=0.0, seed=0):
    V, E = GEOM[shape]
    V = V.copy()
    if noise:
        rng = np.random.default_rng(seed)
        V *= (1 + noise * rng.standard_normal((len(V), 1)))
    for ang, (i, j) in ((yaw, (0, 2)), (pitch, (1, 2)), (roll, (0, 1))):
        c, s = math.cos(ang), math.sin(ang)
        a, b = V[:, i].copy(), V[:, j].copy()
        V[:, i], V[:, j] = a * c + b * s, -a * s + b * c
    d = 3.0
    zz = V[:, 2] + d
    f = scale * H * d
    P = np.stack([V[:, 0] / zz * f + cx * W, V[:, 1] / zz * f + cy * H], -1)
    shade = np.clip(1.3 - (zz - d + 1) / 2, 0.25, 1)
    img = np.zeros((H, W), np.float32)
    Pi = (P * 16).astype(np.int32)
    for a, b in E:
        cv2.line(img, tuple(Pi[a]), tuple(Pi[b]), float((shade[a] + shade[b]) / 2), thick, cv2.LINE_AA, shift=4)
    return to3(glow(img, 8, 0.9))
