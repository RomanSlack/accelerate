import librosa, numpy as np
y, sr = librosa.load('ref/warhorse.wav', sr=22050, mono=True)
hop=128
S=np.abs(librosa.stft(y,n_fft=2048,hop_length=hop)); f=librosa.fft_frequencies(sr=sr,n_fft=2048)
low=S[f<120].mean(0); t=librosa.times_like(low,sr=sr,hop_length=hop)
low=low/low.max()
for a,b in [(5,7.5),(30,32.5),(55,57.5),(43,45),(92,94.5)]:
    m=(t>=a)&(t<b); idx=np.where(m)[0]
    d=np.diff(low[idx]); j=idx[np.argmax(d)]
    print(f"window {a}-{b}: max low rise at {t[j]:.3f}  ; first>0.3 at", t[idx[np.argmax(low[idx]>0.3)]] if (low[idx]>0.3).any() else None)
# kick onsets in drop1
on=librosa.onset.onset_detect(onset_envelope=librosa.onset.onset_strength(y=y,sr=sr,hop_length=hop,fmax=150),sr=sr,hop_length=hop,units='time')
print('low onsets 5-35:', np.round(on[(on>5)&(on<35)],2))
print('low onsets 42-60:', np.round(on[(on>42)&(on<60)],2))
