import librosa, numpy as np, json
y, sr = librosa.load('build/music.wav', sr=44100, mono=True)
hop = 256
S = np.abs(librosa.stft(y, n_fft=2048, hop_length=hop))
f = librosa.fft_frequencies(sr=sr, n_fft=2048)
def band_onsets(lo, hi, delta, wait):
    env = librosa.onset.onset_strength(S=librosa.amplitude_to_db(S[(f >= lo) & (f < hi)]), sr=sr, hop_length=hop)
    on = librosa.onset.onset_detect(onset_envelope=env, sr=sr, hop_length=hop, units='time', delta=delta, wait=wait, backtrack=False)
    t = librosa.times_like(env, sr=sr, hop_length=hop)
    strength = np.interp(on, t, env / env.max())
    return on, strength
res = {}
for name, lo, hi, d, w in [('kick', 20, 150, 0.12, 6), ('snare', 1200, 5000, 0.12, 6), ('hat', 7000, 16000, 0.07, 3)]:
    on, st = band_onsets(lo, hi, d, w)
    res[name] = [[round(float(a), 4), round(float(b), 3)] for a, b in zip(on, st)]
    print(name, len(on))
json.dump(res, open('build/perc.json', 'w'))
secs = [(0, 6.4, 'intro'), (6.4, 31.0, 'drop1'), (31.0, 34.46, 'break'), (34.46, 40.69, 'riser'), (40.69, 56.27, 'drop2'), (56.27, 58.8, 'tail')]
for a, b, n in secs:
    print(f"{n:6s}", {k: sum(1 for x in v if a <= x[0] < b) for k, v in res.items()})
print('drop1 first 4s:')
for k in res: print(k, [x[0] for x in res[k] if 6.3 < x[0] < 10.5])
