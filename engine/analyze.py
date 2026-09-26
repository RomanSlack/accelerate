import librosa, numpy as np
y, sr = librosa.load('ref/warhorse.wav', sr=22050, mono=True)
tempo, beats = librosa.beat.beat_track(y=y, sr=sr, units='time')
print('tempo', tempo, 'nbeats', len(beats))
print('first beats', np.round(beats[:12],3))
hop=512
rms = librosa.feature.rms(y=y, hop_length=hop)[0]
t = librosa.times_like(rms, sr=sr, hop_length=hop)
# low-end energy (kick/808)
S = np.abs(librosa.stft(y, hop_length=hop))
f = librosa.fft_frequencies(sr=sr)
low = S[f<150].mean(0); high = S[f>4000].mean(0)
def per_sec(a):
    return [a[(t>=s)&(t<s+1)].mean() for s in range(int(t[-1]))]
r=per_sec(rms); l=per_sec(low); h=per_sec(high)
r=np.array(r)/max(r); l=np.array(l)/max(l); h=np.array(h)/max(h)
for s in range(len(r)):
    print(f"{s:3d}s rms {'#'*int(r[s]*40):40s} low {l[s]:.2f} hi {h[s]:.2f}")
onset = librosa.onset.onset_strength(y=y, sr=sr)
ons = librosa.onset.onset_detect(onset_envelope=onset, sr=sr, units='time')
np.save('beats.npy', beats); np.save('onsets.npy', ons)
