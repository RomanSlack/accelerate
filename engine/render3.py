"""v4: designed scenes + generative treatments, percussion-driven. Break/riser reuse v3 (render2) untouched.

usage:
  python render3.py stills 7.0 12.5 ...
  python render3.py video out.mp4
"""
import os, sys, math, subprocess, random
import numpy as np, cv2
import render2 as R
import fxgen as fx

W, H, FPS, NF, DUR, BEAT = R.W, R.H, R.FPS, R.NF, R.DUR, R.BEAT
B = R.B
DROP1, BREAK, RISER, DROP2, TAIL = 6.385, 31.0, 34.44, 40.675, 56.255
KICKS = np.array([t for t, _ in R.kicks]); KSTR = np.array([s for _, s in R.kicks])
SNARES = np.array(R.snare_set)
HATS = R.HATS
ONSETS = np.array(sorted(set(np.round(np.concatenate([KICKS, SNARES, HATS]), 3))))

def merged(ts, gap):
    out = []
    for t in sorted(ts):
        if not out or t - out[-1] >= gap: out.append(t)
    return out

# ------------------------------------------------------------------ scenes
SCENES = []
def sc(t0, t1, seq, cuts='ks', **kw):
    if cuts == 'ks':
        ev = [t for t in np.concatenate([KICKS, SNARES]) if t0 + 0.05 < t < t1]
        ct = merged([t0] + ev, 0.075)
    elif cuts == 'all':
        ct = merged([t0] + [t for t in ONSETS if t0 + 0.05 < t < t1], 0.12)
    elif cuts == 'hats':
        ct = merged([t0] + [t for t in ONSETS if t0 + 0.04 < t < t1], 0.075)
    elif cuts == 'grid1':
        ct = [t0]
    elif cuts.startswith('grid'):
        div = int(cuts[4:]); n = int(round((t1 - t0) / (BEAT / div)))
        ct = [t0 + i * BEAT / div for i in range(n)]
    SCENES.append(dict(t0=t0, t1=t1, seq=seq, cut_t=np.array(ct), **kw))

WIRE_ICO = dict(shape='ico', scale=0.42, cy=0.46)
WIRE_TORUS = dict(shape='torus', scale=0.62, cy=0.47)

# --- INTRO: a man alone in a field turns to face us; the machine wakes up (cut on the plucks)
sc(0.0, B(-4), [('eyemacroV', 'mono'), ('fieldturn', 'mono'), ('smokeprofile', 'mono'), ('eyemacroV', 'contour'),
                ('inkbloom', 'crush'), ('fieldturn', 'contour')], cuts='all')
sc(B(-4), B(-1), [('creationhandsV', 'mono'), ('braincircuitV', 'edges'), ('overpass', 'crush'), ('chipdieV', 'dots'),
                  ('creationhandsV', 'contour'), ('parkinglot', 'mono')], cuts='all')
sc(B(-1), DROP1, [('eyemacroV', 'mono'), ('fieldturn', 'thresh'), ('eyemacroV', 'thresh'), ('smokeprofile', 'edges')],
   cuts='grid8', zoomrush=True)

# --- DROP 1: the machine rises, people run
sc(DROP1, B(4), [('jungleswing', 'mono'), ('vineswarm', 'crush'), ('aitempleV', 'mono'), ('canopyleap', 'mono', 0.3),
                 ('jungleswing', 'edges'), ('branchcatch', 'mono'), ('vineswarm', 'mono')], flash=True)
sc(B(4), B(8), [('STRIPS', ['servercorridor', 'fiber', 'chipdieV', 'datacenteraerial', 'lightning'])])
sc(B(8), B(12), [('tunnelrun', 'mono', 2.4), ('robotfactory', 'mono'), ('smileclose', 'thresh', 2.4), ('stairwell', 'crush'),
                 ('treeclimb', 'mono'), ('tunnelrun', 'edges', 1.5)])
sc(B(12), B(16), [('robotarmy', 'dots'), ('highwayrun', 'mono'), ('jungleflee', 'mono'), ('forestlights', 'crush'),
                  ('robotarmy', 'mono'), ('horse', 'contour')])
sc(B(16), B(20), [('dnaV', 'mono'), ('kidsrun', 'mono'), ('braincircuitV', 'edges'), ('inkbloom', 'contour'),
                  ('kidsrun', 'crush'), ('dnaV', 'dots')])
sc(B(20), B(24), [('fusionV', 'mono'), ('platform', 'mono'), ('waves', 'mono'), ('fusionV', 'contour'),
                  ('bikekid', 'crush'), ('cctvrun', 'thresh')])
sc(B(24), B(28), [('rocket2', 'mono'), ('horse', 'slit'), ('birdsflight', 'mono'), ('vineswarm', 'crush'),
                  ('rocket2', 'edges'), ('birdsflight', 'contour')])
sc(B(28), B(29), [('highwayrun', 'mono'), ('megacityV', 'mono'), ('forestlights', 'crush')])
RECAP1 = [('aitempleV', 'mono'), ('jungleswing', 'mono'), ('canopyleap', 'thresh', 0.6), ('tunnelrun', 'thresh'), ('dnaV', 'dots'),
          ('kidsrun', 'mono'), ('fusionV', 'contour'), ('rocket2', 'crush'), ('robotarmy', 'dots'), ('stairwell', 'mono'),
          ('birdsflight', 'edges'), ('highwayrun', 'thresh'), ('megacityV', 'mono'), ('chipdieV', 'contour')]
sc(B(29), BREAK, RECAP1, cuts='hats')

# --- BREAK: desolate stillness (riser after it is v3, untouched)
sc(BREAK, RISER, [('parkinglot', 'lofi'), ('rooftop', 'lofi'), ('emptymall', 'lofi'), ('overpass', 'lofi'),
                  ('platform', 'lofi')], cuts='all')

# --- DROP 2: superintelligence arrives; everyone looks up
sc(DROP2, B(48), [('cosmicface', 'mono'), ('smileclose', 'mono', 0.3), ('cosmicface', 'contour'), ('smileclose', 'mono', 1.2),
                  ('plazalook', 'mono', 2.3), ('smileclose', 'crush', 2.0), ('cosmicface', 'thresh'), ('smileclose', 'mono', 2.6)],
   flash=True, first_vstart=1.3)
sc(B(48), B(52), [('angel2', 'mono'), ('plazalook', 'mono'), ('galaxyeye', 'contour'), ('angel2', 'edges'),
                  ('branchcatch', 'crush'), ('galaxyeye', 'dots')])
sc(B(52), B(56), [('neuralgalaxy', 'mono'), ('dancer', 'slit'), ('rooftop', 'mono'), ('neuralgalaxy', 'dots'),
                  ('murmuration', 'mono'), ('dancer', 'edges')])
sc(B(56), B(60), [('reachsmoke', 'mono'), ('ascend', 'mono'), ('kidsrun', 'crush'), ('reachsmoke', 'dots'),
                  ('corridorwalk', 'slit'), ('ascend', 'contour'), ('tunnelrun', 'mono')])
RECAP2 = [('vineswarm', 'mono'), ('angel2', 'mono'), ('plazalook', 'thresh'), ('galaxyeye', 'contour'), ('jungleswing', 'edges'),
          ('reachsmoke', 'dots'), ('neuralgalaxy', 'thresh'), ('plazalook', 'mono', 2.4), ('highwayrun', 'contour'),
          ('ascend', 'mono'), ('tunnelrun', 'edges'), ('aitempleV', 'mono'), ('fieldturn', 'contour'), ('fusionV', 'dots'),
          ('eyemacroV', 'thresh'), ('kidsrun', 'mono')]
sc(B(60), TAIL, RECAP2, cuts='hats')

# --- ENDING: he has turned to face us. barrage of every face. hard cut to black + silence on the next downbeat.
sc(TAIL, B(65), [('fieldturn', 'mono')], cuts='grid1', first_vstart=2.6, speed=0.5)
BARRAGE = [('plazalook', 'mono'), ('smileclose', 'mono', 2.5), ('tunnelrun', 'mono'), ('angel2', 'contour'),
           ('kidsrun', 'crush'), ('robotface', 'mono'), ('parkinglot', 'mono'), ('eyemacroV', 'thresh'),
           ('highwayrun', 'edges'), ('galaxyeye', 'mono'), ('fieldturn', 'contour'), ('branchcatch', 'mono'),
           ('rooftop', 'mono'), ('dancer', 'edges'), ('platform', 'thresh'), ('aitempleV', 'mono')]
sc(B(65), B(66), BARRAGE, cuts='grid8')
FACES = [('fieldturn', 'thresh'), ('smileclose', 'thresh', 2.8), ('tunnelrun', 'thresh'), ('robotface', 'mono'),
         ('plazalook', 'thresh'), ('eyemacroV', 'mono'), ('cctvrun', 'thresh'), ('platform', 'mono')]
sc(B(66), B(66.875), FACES, cuts='grid16')
sc(B(66.875), B(67), [('fieldturn', 'mono')], cuts='grid1', first_vstart=3.6)
sc(B(67), DUR + 1, [('BLACK', None)], cuts='grid1')

SC_T = np.array([s['t0'] for s in SCENES])

# ------------------------------------------------------------------ frame
def cut_params(si, ci):
    r = random.Random(si * 1009 + ci * 31 + 7)
    return dict(vstart=r.uniform(0.2, 3.6), speed=r.uniform(0.9, 1.8), z=r.uniform(1.0, 1.18),
                step=r.uniform(0.02, 0.045) * r.choice([1, 1, -1]), px=r.uniform(-0.04, 0.04), py=r.uniform(-0.03, 0.03),
                vertical=r.random() < 0.6, nstrips=r.choice([3, 4, 5]))

def footage(clip, st, z, px, py):
    return R.camera(R.load_vframe(clip, st), z, px, py, 0).astype(np.float32) / 255

def mono(x): return R.g_mono(x)

def treat(kind, x, t, tc, nh, nhs, kp, s, p, clip, st):
    if kind == 'mono': return R.g_mono(x)
    if kind == 'crush': return R.g_mono(x, c=2.4, gain=0.8)
    if kind == 'blown': return R.g_mono(x, c=1.9, gain=1.55)
    if kind == 'thresh': return R.g_thresh(x)
    if kind == 'lofi': return R.g_lofi(x)
    g = fx.gray(R.g_mono(x, c=1.3))
    if kind == 'contour': return fx.contours(g, W, H, n=9, phase=0.08 * nhs + (t - tc) * 0.5, thick=max(1, int(2 * R.SCALE)))
    if kind == 'dots': return fx.matrix(g, W, H, cell=max(6, int([12, 16, 20][nhs % 3] * R.SCALE)), kind='dots', gain=1.3)
    if kind == 'edges': return fx.edges(g, W, H)
    if kind in ('pc', 'blownpc'):
        explode = 0.025 * kp
        if kind == 'blownpc':
            prog = max(0.0, (t - s['t0'] - 0.9) / 1.4)
            explode = 0.35 * prog ** 1.6
            g = fx.gray(R.g_mono(x, c=1.9, gain=1.3))
        yaw = s.get('yaw0', 0.3) + 0.06 * nhs + 0.25 * math.sin((t - s['t0']) * 1.3)
        return fx.pointcloud(g, W, H, yaw=yaw, pitch=0.12, explode=explode, thresh=0.22, zoom=1 + 0.015 * nh,
                             step=max(2, int(4 * R.SCALE)))
    if kind == 'iris':
        r = 0.3 + 0.06 * kp + 0.012 * nh
        return fx.iris(R.g_mono(x), W, H, r, feather=3)
    if kind == 'slit':
        n = 18
        frames = [R.g_mono(footage(clip, st - k * 0.045, p['z'], p['px'], p['py'])) for k in range(n)]
        return fx.slitscan(frames, W, H, vertical=p['vertical'])
    raise ValueError(kind)

def render_frame(fi):
    t = fi / FPS
    if RISER <= t < DROP2:
        return R.render_frame(fi, None)[0]
    si = int(np.searchsorted(SC_T, t, side='right') - 1)
    s = SCENES[si]
    ci = int(np.searchsorted(s['cut_t'], t, side='right') - 1)
    tc = s['cut_t'][ci]
    item = s['seq'][ci % len(s['seq'])]
    p = cut_params(si, ci)
    nh = int(((HATS > tc + 0.02) & (HATS <= t)).sum())
    nhs = int(((HATS > s['t0'] + 0.02) & (HATS <= t)).sum())
    in_drop = DROP1 <= t < BREAK or DROP2 <= t < TAIL
    dk = t - KICKS; m = (dk >= 0) & (dk < 0.25)
    kp = float((KSTR[m] * np.exp(-dk[m] / 0.08)).max()) if (m.any() and in_drop) else 0.0
    z = p['z'] * (1 + p['step']) ** nh * (1 + 0.06 * kp)
    if s.get('zoomrush'):
        z *= 1 + 1.6 * ((t - s['t0']) / (s['t1'] - s['t0'])) ** 2
    lr = random.Random(int(t * 1000) // 97)
    px, py = p['px'] + lr.uniform(-0.004, 0.004) * kp, p['py'] + lr.uniform(-0.004, 0.004) * kp
    vstart = s['first_vstart'] if (ci == 0 and 'first_vstart' in s) else p['vstart']
    if len(item) > 2: vstart = item[2]
    st = vstart + (t - tc) * s.get('speed', p['speed']) + nh * 0.1
    if item[0] == 'BLACK':
        return np.zeros((H, W, 3), np.float32)
    if item[0] in ('kidsrun',):
        z *= 1.1
    if item[0] in ('jungleswing', 'branchcatch'):
        z *= 1.2
    if item[0] == 'smileclose':  # crop film sprockets, center the face
        z *= 1.3; px -= 0.05
    if item[0] == 'STRIPS':
        clips = item[1]
        frames = [mono(footage(clips[(j + ci) % len(clips)], p['vstart'] + j * 0.7 + (t - tc) * p['speed'] + nh * 0.1,
                                1.08 * (1 + p['step']) ** nh, 0, 0)) for j in range(p['nstrips'])]
        shift = ((0.22 * nh) % 1.0) - 0.5
        x = fx.strips(frames, W, H, p['nstrips'], shift=shift, gutter=max(2, int(14 * R.SCALE)), vertical=True)
    else:
        clip, kind = item[0], item[1]
        x = footage(clip, st, z, px, py)
        x = treat(kind, x, t, tc, nh, nhs, kp, s, p, clip, st)
    w = s.get('wire')
    if w and ci % 2 == 0:
        wf = fx.wire(W, H, w['shape'], yaw=0.09 * nhs + (t - s['t0']) * 0.35, pitch=0.9 + 0.2 * math.sin(t), roll=0.1 * nhs,
                     scale=w['scale'] * (1 + 0.1 * kp), cy=w['cy'], thick=max(1, int(2 * R.SCALE)))
        x = x * 0.75 + wf * 0.9
    # every onset nudges exposure (hats in drops, plucks in intro)
    last = ONSETS[ONSETS <= t]
    dh = t - last[-1] if len(last) else 9
    x = x * (1 + (0.18 if in_drop else 0.1) * math.exp(-dh / 0.035))
    x = R.bloom(x, 0.6)
    if s.get('flash') and t - s['t0'] < 2.0 / FPS:
        x = x * 0.1 + 0.9
    x = x * R.VIG + R.GRAIN[fi % 8] * 0.07
    if t < 0.25: x *= t / 0.25
    return np.clip(x, 0, 1)

def to8(x): return (x * 255 + 0.5).astype(np.uint8)

def render_chunk(args):
    a, b, path = args
    cmd = ['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-',
           '-c:v', 'libx264', '-preset', 'fast', '-crf', '14', '-pix_fmt', 'yuv420p', path]
    pr = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for fi in range(a, b):
        pr.stdin.write(to8(render_frame(fi)).tobytes())
    pr.stdin.close(); pr.wait()
    return path

def render_video(out, workers=8):
    from multiprocessing import Pool
    d = f'{R.ROOT}/build/chunks3'; os.makedirs(d, exist_ok=True)
    step = math.ceil(NF / workers)
    jobs = [(i * step, min(NF, (i + 1) * step), f'{d}/c{i:02d}.mp4') for i in range(workers) if i * step < NF]
    with Pool(len(jobs)) as pool:
        paths = pool.map(render_chunk, jobs)
    open(f'{d}/list.txt', 'w').write(''.join(f"file '{p}'\n" for p in paths))
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', f'{d}/list.txt', '-i', f'{R.ROOT}/build/music.wav',
                    '-map', '0:v', '-map', '1:a', '-c:v', 'copy', '-af', 'volume=-1.5dB,alimiter=limit=0.8:level=false,afade=t=out:st=58.585:d=0.02',
                    '-c:a', 'aac', '-b:a', '256k', '-ar', '48000', '-shortest', '-movflags', '+faststart', out], check=True)
    print('wrote', out)

if __name__ == '__main__':
    mode = sys.argv[1]
    if mode == 'plan':
        for s in SCENES: print(f"{s['t0']:6.2f}-{s['t1']:6.2f} cuts {len(s['cut_t']):3d} items {len(s['seq'])}")
        print('total cuts', sum(len(s['cut_t']) for s in SCENES))
    elif mode == 'stills':
        os.makedirs(f'{R.ROOT}/build/stills3', exist_ok=True)
        for ts in sys.argv[2:]:
            cv2.imwrite(f'{R.ROOT}/build/stills3/t{float(ts):06.3f}.jpg', to8(render_frame(int(float(ts) * FPS))), [cv2.IMWRITE_JPEG_QUALITY, 88])
        print('ok')
    elif mode == 'video':
        render_video(sys.argv[2])
