---
name: schizo-edit
description: Make a fast, dark, percussion-locked hype edit (the "schizo edit" style that does numbers on X) from a music track and AI-generated footage. Every kick and snare cuts, every hi-hat moves the camera, no text. Use when the user wants a music-synced edit, a beat-synced montage, an AI hype video, a type-beat visualizer, or says "make an edit like ACCELERATE". Covers music analysis, footage prompts, scene authoring in the engine, rendering, and QC without being able to hear the audio.
---

# schizo-edit

Build a sub-60-second edit where the drums drive every frame. This skill is the distilled
workflow behind ACCELERATE: six versions, one director's notes, and the engine in this repo.

Everything runs from the repo root. Engine: `engine/`. Helpers: `scripts/`. Prompt examples: `prompts/`.

## The house style (learned the hard way, do not relearn it)

These came from real notes on real versions. Treat them as defaults, not suggestions.

**Do**
- Cut on every kick and snare. Make every hi-hat *do something* (camera step, clip skip, exposure pulse).
- Stark black and white, crushed blacks, blown highlights, heavy grain. Red only as a rare accent.
- Real, realistic people in desolate places: running, turning to face the camera, looking up, reaching.
- Strange human motion is gold (people swinging through a jungle like apes beat every sci-fi render).
- One extreme close-up of a real face doing something slightly wrong (a slow smile that doesn't reach the eyes).
- Hook before 7 seconds: the first drop lands early.
- End with a hard cut to black and silence one downbeat early. The hit never lands.

**Don't**
- On-screen text, slogans, year counters, stamps. Zero words is the version that works.
- Glitch fx: RGB split, slice bars, echo trails, tiling. They read as cheap.
- Slow zooms on still images. Animate every still or cut it.
- Screensaver geometry: wireframe spheres, tori, rotating point clouds, glowing orbs held on screen.
- Static or obviously AI-looking people (a kid in front of a TV). Reject them at review.
- Reusing one striking clip too often. Two appearances is plenty.
- Fade-outs.

## Workflow

State this plan to the user, then run it. Show them stills or strips after steps 4, 6 and 7.

### 1. Music: find the bars and the drops
```bash
scripts/make_music.sh path/to/track.mp4    # writes ref/warhorse.wav and build/music.wav
python engine/analyze.py                   # tempo, beat grid, per-second energy (reads ref/warhorse.wav)
python engine/drops.py                     # exact drop times from low-band rises
```
- Pick a sub-60 s structure: **intro (hook) → drop 1 → short break → riser → drop 2 → hard-cut end**.
  Keep drop 1 early. Cut *only on bar lines* (the tempo from analyze.py times 4 beats) so the music
  never stumbles, then edit the two `atrim` ranges in `scripts/make_music.sh` and rerun it.
- Beat trackers love half-time. If the user gives the real BPM, trust it. The engine's `BEAT` constant
  is whatever the tracker returned; it only has to be consistent.
- Then extract the drums: `python engine/perc.py` writes `build/perc.json` (kick 20 to 150 Hz, snare
  1.2 to 5 kHz, hi-hat 7 to 16 kHz onsets).

### 2. Footage: write prompts as JSONL
One JSON object per line: `{"prompt", "model": "kling"|"veo", "name", "duration", "aspect": "16:9"}`,
plus `"image": "assets/img/<still>_0.png"` for image-to-video.

- **People close to camera: Veo 3.1** (4 s, 1080p). Far more real than Kling. About $1.60 a clip.
- **Motion, crowds, environments, animating stills: Kling 2.5 Turbo Pro** (5 s). About $0.35 a clip.
- The realism suffix that works:
  `Documentary realism, shot on 16mm film by a handheld camera, real ordinary people, natural imperfect
  framing, overcast flat light, desolate and eerie, black and white, heavy film grain, no CGI look, no text`
- Describe *motion* in every prompt (running, turning, reaching, swinging, crashing). Static prompts make static clips.
- Budget for 50 to 75 clips so nothing repeats. See `prompts/07`, `08`, `09` for the best examples.

```bash
export FAL_KEY=...                                         # never write this into the repo
python scripts/gen_clips.py prompts/yours.jsonl --dry-run  # payloads + cost estimate, spends nothing
python scripts/gen_clips.py prompts/yours.jsonl --workers 6
```
Confirm the estimated cost with the user before running for real.

### 3. Review the footage before using it
```bash
python engine/prep.py     # extracts frames to assets/vidframes/<name>/ and meta.json
```
Build a contact sheet (first, middle and last frame of each clip) and look at it. Reject clips that are
static, AI-looking, or have garbage in frame. Note clips with film-border artwork: they need a tighter
crop (see the `z *= ...` special cases in `render_frame` in `engine/render3.py`).

### 4. Author the scenes in `engine/render3.py`
Set the section boundaries (seconds) and the beat grid:
- `engine/render3.py`: `DROP1, BREAK, RISER, DROP2, TAIL = ...`
- `engine/render2.py`: `BEAT` (seconds per tracked beat) and `T0` (time of the first drop downbeat).
  `B(n)` is "n beats after the drop" and is how scenes are placed.
- `render3` hands `RISER <= t < DROP2` to the older v3 engine (`render2.py`). For a new track set
  `RISER = DROP2` to turn that off, unless you want the v3 look there.

Then write the scene list. A scene is a time range, a list of items, and a cut mode:
```python
sc(B(8), B(12), [('tunnelrun', 'mono', 2.4), ('robotfactory', 'mono'), ('smileclose', 'thresh', 2.4),
                 ('stairwell', 'crush'), ('treeclimb', 'mono')])
```
- **Item** = `(clip, treatment)` or `(clip, treatment, clip_start_seconds)`. Pin the start when the good
  moment is at a specific point in the clip (the smile, the people on the branch).
- **Treatments**: `mono`, `crush`, `blown`, `thresh`, `lofi` (grades), `contour`, `dots`, `edges`,
  `slit` (generative, from `engine/fxgen.py`), plus `('STRIPS', [clips...])` for a multi-clip strip layout.
  Use the grades most of the time, generative treatments as punctuation.
- **Cut modes**: `'ks'` (kicks + snares, the default for drops), `'all'` (every onset, for intros and
  breaks), `'hats'` (every onset at 75 ms spacing: the last bar before a section change), `'gridN'`
  (N cuts per beat: stutter builds), `'grid1'` (a single held shot).
- Each scene advances one item per cut, cycling. Alternate 2 or 3 subjects per bar so it reads as edited, not random.
- Scene flags: `flash=True` (white frame on the downbeat), `zoomrush=True` (accelerating push-in into the drop).

### 5. Preview fast, then look
```bash
SCALE=0.5 python engine/render3.py stills 6.5 12.7 41.5 57.9   # -> build/stills3/
SCALE=0.5 python engine/render3.py video build/preview.mp4       # ~80 s on 16 cores
python scripts/check_render.py build/preview.mp4 --fps 60 --strip 6.2 4
```
You cannot hear the audio, so verify numerically and visually:
- `check_render.py` prints the median cut-to-drum distance (target under 10 ms), cuts that are off the
  drums (fine only where you built a stutter), and dead-dark stretches (usually a dark clip or a bad crop).
- Read the strips (15 fps tiles) around every section boundary and every place the user commented on.
  Look for: repeats, static shots, crops that cut off faces, anything that breaks the house style.

### 6. Full render and export for X
```bash
python engine/render3.py video build/master.mp4     # 1080p60, ~5 min with 8 workers, ~3 GB RAM
ffmpeg -i build/master.mp4 -c:v libx264 -preset slow -profile:v high -crf 17 -maxrate 25M -bufsize 50M \
       -pix_fmt yuv420p -g 120 -c:a copy -movflags +faststart out/final.mp4
```

### 7. Iterate on notes
Expect several rounds. When the user names a timestamp, find the scene with
`python engine/render3.py plan`, change the items or the treatment, rerender, and show strips of that
moment. When a section is praised, freeze it: render it with the same code and confirm it is
pixel-identical (compare frames with ffmpeg's `psnr` filter; `inf` means identical).

## Pitfalls
- **RAM**: each worker caches frames. 15 workers at full res crashed a 62 GB machine. Keep 8 workers
  and the bounded caches in `render2.load_img` / `load_vframe`.
- **Green tint**: colour splits on 1-bit (threshold or dither) frames turn green after 4:2:0 encoding.
  The engine skips colour splitting on binary frames. Keep it that way.
- **Music fades**: if the ending is a hard cut, make sure `build/music.wav` has no baked-in fade and
  the `afade=t=out:st=...` in `render_video()` in `engine/render3.py` lands exactly on your cut-to-black time.
- **Licensing**: type beats are often "free for non-profit". Credit the producer, don't redistribute the
  audio, and tell the user to get a lease before monetizing.
- **Secrets**: the fal key lives in the environment or an ignored `.env`. Scan before any push.
