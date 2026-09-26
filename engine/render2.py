"""v3: percussion-driven edit. Every kick/snare cuts, every hi-hat moves.

usage:
  python render2.py plan                    # print the cut list
  python render2.py stills 7.0 7.1 ...      # preview frames
  python render2.py video out.mp4           # full render (SCALE env for preview res)
"""
import numpy as np, cv2, os, sys, math, json, subprocess, random
from multiprocessing import Pool

cv2.setNumThreads(1)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # repo root
SCALE = float(os.environ.get('SCALE', '1'))
W, H = int(1920 * SCALE) // 2 * 2, int(1080 * SCALE) // 2 * 2
FPS = 60
DUR = 58.8
NF = int(DUR * FPS)
BEAT = 0.77923
T0 = 6.40
def B(b): return T0 + b * BEAT

SEC = [('intro', 0.0, 6.385), ('drop1', 6.385, 31.0), ('break', 31.0, 34.44), ('riser', 34.44, 40.675),
       ('drop2', 40.675, 56.255), ('tail', 56.255, DUR)]
def section(t):
    for n, a, b in SEC:
        if a <= t < b: return n
    return 'tail'

VMETA = json.load(open(f'{ROOT}/assets/vidframes/meta.json'))
PERC = json.load(open(f'{ROOT}/build/perc.json'))

# ------------------------------------------------------------------ sources
from collections import OrderedDict
_img = OrderedDict()
def load_img(name):
    if name in _img:
        _img.move_to_end(name)
    else:
        if len(_img) >= 10: _img.popitem(last=False)
        for ext in ('_0.png', '_0.webp'):
            p = f'{ROOT}/assets/img/{name}{ext}'
            if os.path.exists(p): break
        im = cv2.imread(p)
        h, w = im.shape[:2]
        m = int(w * 0.02)
        im = im[m:h - m, m:w - m]
        h, w = im.shape[:2]
        tw = int(h * 16 / 9)
        if tw <= w:
            x0 = (w - tw) // 2; im = im[:, x0:x0 + tw]
        else:
            th = int(w * 9 / 16); y0 = (h - th) // 2; im = im[y0:y0 + th]
        _img[name] = cv2.resize(im, (int(W * 1.5), int(H * 1.5)), interpolation=cv2.INTER_AREA)
    return _img[name]

_vf = {}
def load_vframe(name, st):
    m = VMETA[name]
    n = m['n']
    fi = int(st * m['fps'])
    period = 2 * (n - 1)
    fi %= period
    if fi >= n: fi = period - fi
    key = (name, fi)
    if key not in _vf:
        if len(_vf) >= 40: _vf.clear()
        im = cv2.imread(f'{ROOT}/assets/vidframes/{name}/{fi + 1:04d}.jpg')
        h, w = im.shape[:2]; mx, my = int(w * 0.035), int(h * 0.035)
        _vf[key] = cv2.resize(im[my:h - my, mx:w - mx], (int(W * 1.2), int(H * 1.2)), interpolation=cv2.INTER_AREA)
    return _vf[key]

def is_vid(name): return name in VMETA

def camera(src, z, px, py, rot):
    hs, ws = src.shape[:2]
    k = z * W / ws
    c, s = math.cos(math.radians(rot)) * k, math.sin(math.radians(rot)) * k
    cx, cy = ws / 2, hs / 2
    tx = W / 2 + px * W - (c * cx - s * cy)
    ty = H / 2 + py * H - (s * cx + c * cy)
    return cv2.warpAffine(src, np.float32([[c, -s, tx], [s, c, ty]]), (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)

# ------------------------------------------------------------------ grades
def lum(x): return x[..., 0] * 0.114 + x[..., 1] * 0.587 + x[..., 2] * 0.299

def lut_from(stops):
    xs = np.linspace(0, 1, len(stops)); t = np.linspace(0, 1, 256)
    return np.stack([np.interp(t, xs, [s[i] for s in stops]) for i in range(3)], -1).astype(np.float32)

LUT = {  # BGR
    'red': lut_from([(0, 0, 0), (0.02, 0.02, 0.4), (0.06, 0.05, 0.95), (0.9, 0.92, 1), (1, 1, 1)]),
    'ir': lut_from([(0, 0, 0), (0.35, 0.0, 0.2), (0.3, 0.0, 0.85), (0.0, 0.45, 1.0), (0.5, 0.95, 1.0), (1, 1, 1)]),
    'steel': lut_from([(0, 0, 0), (0.22, 0.14, 0.1), (0.62, 0.58, 0.55), (1, 1, 1)]),
}
BAYER = np.array([[0, 32, 8, 40, 2, 34, 10, 42], [48, 16, 56, 24, 50, 18, 58, 26], [12, 44, 4, 36, 14, 46, 6, 38],
                  [60, 28, 52, 20, 62, 30, 54, 22], [3, 35, 11, 43, 1, 33, 9, 41], [51, 19, 59, 27, 49, 17, 57, 25],
                  [15, 47, 7, 39, 13, 45, 5, 37], [63, 31, 55, 23, 61, 29, 53, 21]], np.float32) / 64

def g_mono(x, c=1.6, gain=1.0):
    l = lum(x)
    red = np.clip((x[..., 2] - np.maximum(x[..., 0], x[..., 1])) * 2.2, 0, 1)
    g = np.clip(((l * gain) - 0.5) * c + 0.5, 0, 1)
    out = np.repeat(g[..., None], 3, -1)
    out[..., 0] *= 1 - 0.92 * red
    out[..., 1] *= 1 - 0.92 * red
    out[..., 2] = np.maximum(out[..., 2], red * np.clip(g * 1.8, 0, 1))
    return out

def g_lut(x, name, c=1.35):
    l = np.clip((lum(x) - 0.5) * c + 0.5, 0, 1)
    return LUT[name][(l * 255).astype(np.uint8)]

def g_thresh(x, th=0.4):
    return np.repeat((lum(x) > th).astype(np.float32)[..., None], 3, -1)

def g_dither(x, px=3):
    px = max(1, int(px * SCALE))
    l = cv2.resize(lum(x), (W // px, H // px), interpolation=cv2.INTER_AREA)
    l = np.clip((l - 0.5) * 1.5 + 0.5, 0, 1)
    h, w = l.shape
    bm = np.tile(BAYER, (h // 8 + 1, w // 8 + 1))[:h, :w]
    d = (l > bm).astype(np.float32)
    d = cv2.resize(d, (W, H), interpolation=cv2.INTER_NEAREST)
    return np.repeat(d[..., None], 3, -1)

def g_lofi(x):
    l = lum(x)
    out = x * 0.55 + l[..., None] * 0.45
    out = out * 0.78 + 0.09
    out[..., 0] = out[..., 0] * 1.15 + 0.03
    out[..., 2] *= 0.85
    return np.clip(out, 0, 1)

def apply_grade(x, g):
    if g == 'mono': return g_mono(x)
    if g == 'blown': return g_mono(x, c=1.9, gain=1.55)
    if g == 'crush': return g_mono(x, c=2.4, gain=0.8)
    if g == 'thresh': return g_thresh(x)
    if g == 'invert': return 1 - g_mono(x, c=1.8)
    if g == 'dither': return g_dither(x)
    if g == 'lofi': return g_lofi(x)
    if g in LUT: return g_lut(x, g)
    return x

def bloom(x, amt):
    sw, shh = W // 6, H // 6
    small = cv2.resize(np.clip(x - 0.55, 0, 1), (sw, shh), interpolation=cv2.INTER_AREA)
    small = cv2.GaussianBlur(small, (0, 0), 5)
    return x + cv2.resize(small, (W, H), interpolation=cv2.INTER_LINEAR) * amt

YY, XX = np.mgrid[0:H, 0:W].astype(np.float32)
VIG = (1 - 0.6 * np.clip(((XX / W - 0.5) ** 2 + (YY / H - 0.5) ** 2) * 1.8, 0, 1) ** 1.4)[..., None].astype(np.float32)
_grng = np.random.default_rng(11)
GRAIN = [_grng.standard_normal((H, W, 1)).astype(np.float32) for _ in range(8)]

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
        y0 = int(rng.integers(0, H - 4)); h = int(rng.integers(3, max(5, int(70 * SCALE))))
        out[y0:y0 + h] = np.roll(x[y0:y0 + h], int(rng.integers(-amp, amp + 1)), axis=1)
    return out

def tile(x, n):
    s = cv2.resize(x, (W // n, H // n), interpolation=cv2.INTER_AREA)
    return cv2.resize(np.tile(s, (n, n, 1)), (W, H), interpolation=cv2.INTER_NEAREST)

# ------------------------------------------------------------------ events
def merged(times, gap):
    out = []
    for t in sorted(times):
        if not out or t - out[-1] >= gap: out.append(t)
    return out

kicks = [(t, s) for t, s in PERC['kick']]
snares = [(t, s) for t, s in PERC['snare']]
hats = [t for t, s in PERC['hat']]
snare_set = [t for t, _ in snares]
kick_str = {round(t, 3): s for t, s in kicks}

def near(t, arr, tol=0.03):
    return any(abs(t - a) < tol for a in arr)

cut_times = [0.0]
for n, a, b in SEC:
    if n in ('drop1', 'drop2'):
        c = [t for t, _ in kicks + snares if a <= t < b]
        if n == 'drop1':
            c += [t for t in hats if B(29) <= t < b]            # fill into the breakdown
        else:
            c += [t for t in hats if B(60) <= t < b]            # last bar: every hat is a cut
        cut_times += merged([a] + c, 0.075)
    elif n in ('intro', 'break', 'riser'):
        c = [t for t, _ in kicks + snares if a <= t < b] + [t for t in hats if a <= t < b]
        if n == 'riser':  # manufactured stutter build over the last two beats
            c += [B(42) + i * BEAT / 4 for i in range(4)] + [B(43) + i * BEAT / 8 for i in range(8)]
        cut_times += merged([a] + c, 0.12 if n != 'riser' else 0.075)
    else:
        cut_times.append(a)
cut_times = merged(cut_times, 0.06)
cut_times = [t for t in cut_times if t < DUR]

# ------------------------------------------------------------------ shot plan
POOLS = {
    'intro': ['eyeiris', 'lighter', 'faceprojection', 'eniac', 'creationhands', 'murmuration', 'trainrush', 'eyemacro', 'servohand', 'chessrobot2'],
    'drop1': ['robotrun', 'robotarmy', 'robotface', 'robotfactory', 'servercorridor', 'datacenteraerial', 'lightning', 'fiber',
              'chipdie', 'aitemple', 'rocket2', 'trainrush', 'servohand', 'chromeface', 'braincircuit', 'autolab', 'dna',
              'fusion', 'megacity', 'marscity', 'dyson2', 'crowdscreens', 'infinitefaces', 'murmuration', 'faceprojection'],
    'break': ['lonemonolith', 'handorb', 'runnerfield', 'childscreen', 'astronaut'],
    'riser': ['skyeye', 'eyemacro', 'runnerfield', 'eyeiris', 'trainrush', 'faceprojection', 'fallwater', 'lighter', 'murmuration', 'servohand', 'galaxyeye', 'shatter'],
    'drop2': ['cosmicface', 'angel2', 'galaxyeye', 'neuralgalaxy', 'robotrun', 'matrioshka', 'ascend', 'handsraised',
              'fallwater', 'shatter', 'murmuration', 'chromeface', 'astronaut', 'dyson2', 'whitevoid', 'lightning', 'eyeiris', 'fiber'],
    'tail': ['whitevoid'],
}
GRADES = {
    'intro': [('mono', 5), ('crush', 2), ('dither', 1)],
    'drop1': [('mono', 5), ('crush', 2), ('red', 2), ('blown', 2), ('dither', 1), ('thresh', 1)],
    'break': [('lofi', 1)],
    'riser': [('mono', 3), ('crush', 2), ('thresh', 1)],
    'drop2': [('mono', 4), ('blown', 2), ('red', 2), ('ir', 1), ('dither', 1), ('crush', 1), ('steel', 1)],
    'tail': [('blown', 1)],
}
FIRST = {'drop1': 'robotrun', 'drop2': 'cosmicface', 'break': 'lonemonolith', 'riser': 'skyeye', 'tail': 'whitevoid'}

def wpick(rng, items):
    tot = sum(w for _, w in items); r = rng.random() * tot
    for v, w in items:
        r -= w
        if r <= 0: return v
    return items[-1][0]

def build_shots():
    rng = random.Random(1337)
    shots = []
    avail = {k: [] for k in POOLS}
    def draw(sec):
        if not avail[sec]:
            avail[sec] = POOLS[sec][:]; rng.shuffle(avail[sec])
        return avail[sec].pop()
    bar_srcs, cur_bar, k_in_bar = [], None, 0
    for i, t in enumerate(cut_times):
        t1 = cut_times[i + 1] if i + 1 < len(cut_times) else DUR + 1
        sec = section(t)
        dense = (sec == 'drop2' and t >= B(60)) or (sec == 'drop1' and t >= B(29)) or (sec == 'riser' and t >= B(42))
        glen = 1 if dense else (2 if sec in ('intro', 'break', 'riser') else 4)
        bar = (sec, math.floor((t - T0) / (BEAT * glen)))
        is_start = any(abs(t - a) < 1e-6 for n, a, b in SEC)
        if bar != cur_bar or is_start:
            cur_bar, k_in_bar = bar, 0
            nsrc = 3 if dense else (2 if sec in ('intro', 'break') else rng.choice([2, 3, 3]))
            bar_srcs = [draw(sec) for _ in range(nsrc)]
            if is_start and sec in FIRST: bar_srcs[0] = FIRST[sec]
        src = bar_srcs[k_in_bar % len(bar_srcs)]
        k_in_bar += 1
        snare_cut = near(t, snare_set) and not near(t, [k for k, _ in kicks], 0.02)
        g = wpick(rng, GRADES[sec])
        punct = None
        if sec in ('drop1', 'drop2') and snare_cut:
            punct = rng.choice(['invert', 'thresh', 'tile2', 'tile3'] if sec == 'drop2' else ['invert', 'thresh', 'invert'])
        vid = is_vid(src)
        shot = dict(t0=t, t1=t1, src=src, sec=sec, g=g, punct=punct,
                    z=rng.uniform(1.0, 1.25) if vid else rng.uniform(1.0, 1.6),
                    px=rng.uniform(-0.06, 0.06), py=rng.uniform(-0.05, 0.05),
                    rot=rng.choice([0, 0, 0, rng.uniform(-4, 4)]),
                    step=rng.uniform(0.025, 0.06) * rng.choice([1, 1, -1]),
                    vstart=rng.uniform(0, 3.8), speed=rng.uniform(0.9, 2.2),
                    dbl=(sec in ('intro', 'break') and rng.random() < 0.45),
                    bands=(sec == 'drop2' and vid and rng.random() < 0.18),
                    mirror=(sec == 'drop2' and rng.random() < 0.12))
        if src == 'earthcircuits':  # dark clip: keep the planet centered and bright
            shot.update(z=1.0, px=0, py=0, g=rng.choice(['mono', 'blown', 'red']))
        if is_start and sec == 'drop2':
            shot.update(vstart=1.3, speed=1.2, z=1.15, g='mono', punct=None)
        if is_start and sec == 'drop1':
            shot.update(vstart=0.5, speed=1.6, z=1.05, g='mono', punct=None)
        if sec == 'tail':
            shot.update(z=1.0, step=0.03, g='blown', vstart=0)
        shots.append(shot)
    for i, s in enumerate(shots):
        s['prev'] = shots[i - 1]['src'] if i else s['src']
    return shots

SHOTS = build_shots()
SHOT_T = np.array([s['t0'] for s in SHOTS])
HATS = np.array(hats)
KICK_T = np.array([t for t, _ in kicks])
KICK_S = np.array([s for _, s in kicks])

def shot_index(t): return int(np.searchsorted(SHOT_T, t, side='right') - 1)

# ------------------------------------------------------------------ frame
def base_frame(s, t, fi, rng):
    lt = t - s['t0']
    nh = int(((HATS > s['t0'] + 0.02) & (HATS <= t)).sum())  # hats since cut
    last_hat = HATS[HATS <= t][-1] if (HATS <= t).any() else -9
    sec = s['sec']
    moving = sec in ('drop1', 'drop2', 'tail', 'riser')
    # stepped camera: every hat advances zoom and nudges position
    z = s['z'] * ((1 + s['step']) ** nh if moving else (1 + 0.035 * lt))
    hr = random.Random(int(last_hat * 1000) + 7)
    jx = hr.uniform(-0.012, 0.012) if moving and nh else 0
    jy = hr.uniform(-0.012, 0.012) if moving and nh else 0
    # kick punch
    dk = t - KICK_T
    m = (dk >= 0) & (dk < 0.25)
    kp = float((KICK_S[m] * np.exp(-dk[m] / 0.08)).max()) if m.any() and sec in ('drop1', 'drop2', 'tail') else 0.0
    z *= 1 + 0.12 * kp
    shake = 0.012 * kp
    px = s['px'] + jx + rng.uniform(-shake, shake)
    py = s['py'] + jy + rng.uniform(-shake, shake)
    rot = s['rot'] + rng.uniform(-1.5, 1.5) * kp
    src = s['src']
    if is_vid(src):
        st = s['vstart'] + lt * s['speed'] + (nh * 0.12 if moving else 0)  # hats skip clip time forward
        if s['bands']:
            parts = []
            nb = 6
            for bi in range(nb):
                fr = camera(load_vframe(src, st - bi * 0.15), z, px, py, rot)
                parts.append(fr[bi * H // nb:(bi + 1) * H // nb])
            img = np.concatenate(parts, 0)
        else:
            img = camera(load_vframe(src, st), z, px, py, rot)
    else:
        img = camera(load_img(src), z, px, py, rot)
    x = img.astype(np.float32) / 255
    if s['dbl']:
        p = s['prev']
        o = load_vframe(p, s['vstart'] + lt) if is_vid(p) else load_img(p)
        o = camera(o, 1.1 + 0.05 * lt, -s['px'], 0, 0).astype(np.float32) / 255
        x = 1 - (1 - x) * (1 - o * 0.55)  # screen blend
    return x, kp, nh, last_hat

def render_frame(fi, prev):
    t = fi / FPS
    si = shot_index(t)
    s = SHOTS[si]
    rng = np.random.default_rng(fi * 17 + 3)
    x, kp, nh, last_hat = base_frame(s, t, fi, rng)
    sec = s['sec']
    since_cut = t - s['t0']
    g = s['g']
    if s['punct'] and since_cut < 0.07:
        p = s['punct']
        x = apply_grade(x, 'invert' if p == 'invert' else 'thresh' if p == 'thresh' else g)
        if p.startswith('tile'): x = tile(x, int(p[-1]))
    else:
        x = apply_grade(x, g)
    if s['mirror']:
        x[:, W // 2:] = x[:, :W - W // 2][:, ::-1]
    hot = sec in ('drop1', 'drop2')
    # hat jolt: brief exposure pulse + chroma split
    dh = t - last_hat
    hp = math.exp(-dh / 0.035) if 0 <= dh < 0.15 and sec in ('drop1', 'drop2', 'tail', 'riser') else 0
    x = x * (1 + 0.18 * hp)
    # echo trail (datamosh-lite)
    if hot and prev is not None:
        M = cv2.getRotationMatrix2D((W / 2, H / 2), 0.8, 1.03)
        pw = cv2.warpAffine(prev, M, (W, H), borderMode=cv2.BORDER_REFLECT)
        x = np.maximum(x, pw * (0.42 if sec == 'drop2' else 0.3))
    clean = x
    x = bloom(x, 0.9 if g in ('blown', 'mono', 'lofi') else 0.5)
    # flash frames on hard kicks / section starts
    if since_cut < 1.5 / FPS and si > 0 and any(abs(s['t0'] - a) < 1e-6 for n, a, b in SEC if n in ('drop1', 'drop2')):
        x = x * 0.1 + 0.9
    elif hot and kp > 0.85 and since_cut < 1.0 / FPS:
        x = x * 0.45 + 0.55
    # glitch
    if hot and rng.random() < 0.1 + 0.5 * hp:
        x = slice_glitch(x, rng, int(2 + 8 * hp), int(W * 0.08))
    binary = g in ('dither', 'thresh') or (s['punct'] in ('thresh',) and since_cut < 0.07)
    if (hot or sec == 'tail') and not binary:
        x = rgb_split(x, (1 + 10 * hp + 8 * kp) * SCALE)
    # letterbox snaps in drop2 on snare cuts
    if sec == 'drop2' and s['punct'] in ('tile2', 'invert'):
        bh = int(H * 0.12); x[:bh] = 0; x[-bh:] = 0
    x = x * VIG
    x = x + GRAIN[fi % 8] * (0.07 if sec != 'break' else 0.09)
    # tail: burn to white, then to black
    if t > 57.3:
        x = x * max(0.0, 1 - (t - 57.3) / 1.2)
    if t < 0.25:
        x = x * (t / 0.25)
    return np.clip(x, 0, 1), np.clip(clean, 0, 1)

def to8(x): return (x * 255 + 0.5).astype(np.uint8)

def render_chunk(args):
    a, b, path = args
    cmd = ['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-',
           '-c:v', 'libx264', '-preset', 'fast', '-crf', '14', '-pix_fmt', 'yuv420p', path]
    pr = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    prev = None
    for fi in range(max(0, a - 10), b):
        f, prev = render_frame(fi, prev)
        if fi >= a: pr.stdin.write(to8(f).tobytes())
    pr.stdin.close(); pr.wait()
    return path

def render_video(out, workers=8):
    os.makedirs(f'{ROOT}/build/chunks2', exist_ok=True)
    step = math.ceil(NF / workers)
    jobs = [(i * step, min(NF, (i + 1) * step), f'{ROOT}/build/chunks2/c{i:02d}.mp4') for i in range(workers) if i * step < NF]
    with Pool(len(jobs)) as pool:
        paths = pool.map(render_chunk, jobs)
    lst = f'{ROOT}/build/chunks2/list.txt'
    open(lst, 'w').write(''.join(f"file '{p}'\n" for p in paths))
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', lst, '-i', f'{ROOT}/build/music.wav',
                    '-map', '0:v', '-map', '1:a', '-c:v', 'copy', '-af', 'volume=-1.5dB,alimiter=limit=0.8:level=false',
                    '-c:a', 'aac', '-b:a', '256k', '-ar', '48000', '-shortest', '-movflags', '+faststart', out], check=True)
    print('wrote', out)

if __name__ == '__main__':
    mode = sys.argv[1]
    if mode == 'plan':
        for n, a, b in SEC:
            ss = [s for s in SHOTS if s['sec'] == n]
            print(f"{n:6s} {len(ss):3d} cuts  avg {((b - a) / max(1, len(ss))):.2f}s  srcs {len(set(s['src'] for s in ss))}")
        print('total cuts', len(SHOTS))
    elif mode == 'stills':
        os.makedirs(f'{ROOT}/build/stills2', exist_ok=True)
        for ts in sys.argv[2:]:
            fi = int(float(ts) * FPS); prev = None
            for j in range(max(0, fi - 8), fi + 1):
                f, prev = render_frame(j, prev)
            cv2.imwrite(f'{ROOT}/build/stills2/t{float(ts):06.3f}.jpg', to8(f), [cv2.IMWRITE_JPEG_QUALITY, 88])
        print('ok')
    elif mode == 'video':
        render_video(sys.argv[2])
