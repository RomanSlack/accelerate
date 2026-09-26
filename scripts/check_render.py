"""QC a render without watching it: cut-to-drum sync, dead-dark stretches, and frame strips to look at.

usage:
  python scripts/check_render.py out.mp4                     # sync + dark report
  python scripts/check_render.py out.mp4 --strip 6.2 4       # also write build/strip_6.2.jpg (15fps, 4s)
"""
import argparse, json, subprocess, numpy as np

def cuts(path):
    err = subprocess.run(['ffmpeg', '-i', path, '-vf', "scale=480:-2,select='gt(scene,0.3)',showinfo", '-an', '-f', 'null', '-'],
                         capture_output=True, text=True).stderr
    return np.array([float(x.split(':')[1]) for x in err.split() if x.startswith('pts_time:')])

def luma(path, fps=10):
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', path, '-vf', f'fps={fps},scale=64:36,format=gray', '-f', 'rawvideo', '-'],
                         capture_output=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, 64 * 36).mean(1)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('video')
    ap.add_argument('--perc', default='build/perc.json')
    ap.add_argument('--fps', type=float, default=60)
    ap.add_argument('--strip', nargs=2, type=float, metavar=('START', 'SECONDS'))
    a = ap.parse_args()

    c = cuts(a.video)
    p = json.load(open(a.perc))
    hits = np.array(sorted(t for k in p for t, _ in p[k]))
    d = np.array([np.min(np.abs(hits - x)) for x in c])
    print(f'{len(c)} cuts | median {np.median(d) * 1000:.1f} ms to nearest drum hit | '
          f'{(d < 1 / a.fps).mean() * 100:.0f}% within one frame')
    off = c[d > 0.05]
    if len(off): print('cuts > 50 ms off the drums:', np.round(off, 2).tolist())

    l = luma(a.video)
    runs, cur = [], []
    for i, v in enumerate(l):
        if v < 18: cur.append(i / 10)
        else:
            if len(cur) >= 4: runs.append((cur[0], cur[-1]))
            cur = []
    print('dark stretches >= 0.4 s (mean luma < 18/255):', runs or 'none')

    if a.strip:
        s, n = a.strip
        out = f'build/strip_{s}.jpg'
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', str(s), '-t', str(n), '-i', a.video, '-vf',
                        "fps=15,scale=200:-2,drawtext=text='%{pts\\:hms}':x=2:y=2:fontsize=14:fontcolor=lime:box=1:boxcolor=black@0.6,"
                        f"tile=12x{int(np.ceil(n * 15 / 12))}", '-frames:v', '1', out], check=True)
        print('wrote', out)

if __name__ == '__main__':
    main()
