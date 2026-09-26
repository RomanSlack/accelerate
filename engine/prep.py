"""Per-frame audio envelopes + video frame extraction for render.py."""
import numpy as np, librosa, os, glob, subprocess, json

FPS = 30
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # repo root

y, sr = librosa.load(f'{ROOT}/build/music.wav', sr=22050, mono=True)
hop = 256
S = np.abs(librosa.stft(y, n_fft=2048, hop_length=hop))
f = librosa.fft_frequencies(sr=sr, n_fft=2048)
t = librosa.times_like(S[0], sr=sr, hop_length=hop)
low = S[f < 130].mean(0)
hi = S[f > 3000].mean(0)
rms = S.mean(0)

nf = int(58.8 * FPS)
ft = np.arange(nf) / FPS
def resample(a):
    return np.interp(ft, t, a)

low_f, hi_f, rms_f = resample(low), resample(hi), resample(rms)
# kick = positive low-band flux, peak-held with decay
flux = np.maximum(0, np.diff(low_f, prepend=low_f[0]))
flux /= np.percentile(flux, 99.5)
kick = np.zeros(nf)
for i in range(nf):
    kick[i] = max(min(flux[i], 1.0), (kick[i - 1] * 0.72) if i else 0)
np.savez(f'{ROOT}/build/env.npz', kick=kick, low=low_f / low_f.max(), hi=hi_f / hi_f.max(), rms=rms_f / rms_f.max())
print('env frames', nf, 'kick>0.5 count', int((kick > 0.5).sum()))

# extract video frames
meta = {}
for mp4 in sorted(glob.glob(f'{ROOT}/assets/vid/*.mp4')):
    name = os.path.basename(mp4).rsplit('_', 1)[0]
    out = f'{ROOT}/assets/vidframes/{name}'
    if not os.path.isdir(out) or not os.listdir(out):
        os.makedirs(out, exist_ok=True)
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', mp4, '-vf', 'scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080',
                        '-q:v', '2', f'{out}/%04d.jpg'], check=True)
    fps = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v', '-show_entries', 'stream=r_frame_rate', '-of', 'csv=p=0', mp4],
                         capture_output=True, text=True).stdout.strip()
    n, d = fps.split('/')
    meta[name] = {'fps': float(n) / float(d), 'n': len(os.listdir(out))}
json.dump(meta, open(f'{ROOT}/assets/vidframes/meta.json', 'w'), indent=1)
print(meta)
