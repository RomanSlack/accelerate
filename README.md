<div align="center">

<img src="docs/img/hero_drop1.gif" width="100%" alt="First drop: figures swinging through a dark jungle, cut on the drums">

# ACCELERATE

**A beat-locked video compositor and the 58-second AGI edit made with it.**

`232 cuts` · `8.3 ms median sync to the drums` · `75 AI-generated clips` · `6 iterations`

</div>

---

## Overview

ACCELERATE is a Python engine that cuts video to percussion. It detects kick, snare and hi-hat onsets
in a track and assigns each one an on-screen action, so the edit is driven by the drums rather than
placed by hand. The repo contains the engine, every generation prompt, a Claude Code skill that
packages the full workflow, and a record of the six iterations it took to reach the final cut.

The edit was produced with [Claude Code](https://claude.com/claude-code) (Claude Opus 5.5), which wrote
the engine, rendered each version and reviewed the output frame by frame, with creative direction from
[@RomanSlack](https://github.com/RomanSlack).

<table>
<tr>
<td width="50%"><img src="docs/img/grin_drop2.gif" alt="Second drop"></td>
<td width="50%"><img src="docs/img/people.gif" alt="Figures running through empty locations"></td>
</tr>
<tr>
<td align="center"><sub>Second drop</sub></td>
<td align="center"><sub>First drop, cut on kicks and snares</sub></td>
</tr>
</table>

## Claude Code skill

The workflow is packaged as a Claude Code skill in
[`.claude/skills/schizo-edit/`](.claude/skills/schizo-edit/SKILL.md). It covers the style guide derived
from the iterations, music analysis, prompt recipes, scene authoring, rendering, and render QC.

```bash
git clone https://github.com/RomanSlack/accelerate && cd accelerate
claude    # the skill is available automatically inside this repo
# > make a schizo edit to path/to/track.mp4 about <topic>
```

To use it outside this repo: `cp -r .claude/skills/schizo-edit ~/.claude/skills/`.

## Percussion sync

<img src="docs/img/beatmap.png" width="100%" alt="Kick, snare and hi-hat onsets above the cut points of the final edit">

| Onset | Band | On-screen action |
|---|---|---|
| Kick | 20 to 150 Hz | Hard cut, zoom punch, light camera shake |
| Snare | 1.2 to 5 kHz | Hard cut, often to a different treatment of the same subject |
| Hi-hat | 7 to 16 kHz | Camera step, clip time skip, exposure pulse (no cut) |
| Final bar of a section | all | Every onset becomes a cut |

Onsets are detected per band with `librosa` ([`engine/perc.py`](engine/perc.py)). Scenes are defined as
ordered `(clip, treatment)` lists and advance on each onset ([`engine/render3.py`](engine/render3.py)).
Measured on the final render with ffmpeg scene detection: median 8.3 ms from a cut to the nearest
onset, 85% within one frame at 60 fps.

## Iterations

<img src="docs/img/evolution.jpg" width="100%" alt="The same eight timestamps across all six versions">

The same eight timestamps across every version. Full feedback and changes per round are in
[docs/DIRECTORS_NOTES.md](docs/DIRECTORS_NOTES.md).

| Version | Feedback | Change |
|---|---|---|
| v1 → v2 | Text too small on mobile (internal review) | Larger text |
| v2 → v3 | Remove text; make the entire edit move with the percussion | All text removed; cuts generated from drum onsets; 60 fps |
| v3 → v4 | Remove glitch effects and slow zooms on stills; keep the 34 to 41 s section | Effects and stills removed; stills animated; generative treatment library; 34 to 41 s preserved exactly |
| v4 → v5 | More realistic people in desolate settings; replace static AI-looking shots and the ending | Realistic footage of people (Veo 3.1); new hard-cut ending |
| v5 → v6 | Replace wireframe geometry and the point-cloud face; reduce repeated footage | Jungle sequence on the first drop; live-action facial close-up; repeats reduced |

## Treatments

Each clip can be rendered through any of these. Snares switch between them. All run at roughly
10 to 30 ms per 1080p frame in NumPy/OpenCV ([`engine/fxgen.py`](engine/fxgen.py)).

<img src="docs/img/treatments.jpg" width="100%" alt="One clip rendered through twelve treatments">

## Final edit

<img src="docs/img/filmstrip.jpg" width="100%" alt="Contact sheet of the final edit at two frames per second">

## Footage

<img src="docs/img/clip_library.jpg" width="100%" alt="All 75 generated clips">

All footage is AI-generated. Prompts are in [`prompts/`](prompts) in the order they were used, and
[`scripts/gen_clips.py`](scripts/gen_clips.py) regenerates any of them.

| File | Model | Content |
|---|---|---|
| `01` | Gemini 3.1 Flash Image | 33 keyframes |
| `02` | gpt-image-2 | 5 keyframe replacements |
| `03`, `04` | Kling 2.5 Turbo Pro (image-to-video) | Initial animation pass |
| `05` | Kling 2.5 Turbo Pro (text-to-video) | Motion-led clips |
| `06` | Kling 2.5 Turbo Pro | Animated keyframes and additional footage |
| `07` | Veo 3.1, Kling | People in desolate locations |
| `08` | Veo 3.1, Kling | Jungle sequence |
| `09` | Veo 3.1 | Facial close-ups |

For realistic people, Veo 3.1 outperformed Kling on subjects close to camera. The prompt suffix used:
*"Documentary realism, shot on 16mm film by a handheld camera, real ordinary people, natural imperfect
framing, overcast flat light"*.

Total generation cost was approximately $44.

## Usage

```bash
pip install -r requirements.txt
scripts/setup_fonts.sh                       # OFL fonts from Google Fonts
scripts/make_music.sh path/to/track.mp4      # -> build/music.wav (bar-aligned 58.8 s edit)
python engine/perc.py                        # -> build/perc.json (kick, snare, hi-hat onsets)

export FAL_KEY=...
python scripts/gen_clips.py prompts/07_real_people_veo_kling.jsonl --dry-run   # payloads and cost estimate
python scripts/gen_clips.py prompts/07_real_people_veo_kling.jsonl             # -> assets/vid/<name>_0.mp4
# Image-to-video prompts expect keyframes at assets/img/<name>_0.png (prompts 01 and 02).

python engine/prep.py                        # clip frames and audio envelopes
python engine/render3.py stills 6.5 41.5     # preview frames -> build/stills3/
python engine/render3.py video out.mp4       # full 1080p60 render
python scripts/check_render.py out.mp4       # sync stats, off-beat cuts, dark stretches, frame strips
```

A full render takes about 5 minutes on a 16-core CPU with 8 workers and uses about 3 GB of RAM.

| File | Description |
|---|---|
| [`engine/render3.py`](engine/render3.py) | Current engine (v4 to v6): scene lists, onset-driven cuts, treatment switching |
| [`engine/render2.py`](engine/render2.py) | v3 engine; also renders the 34 to 41 s section of the final edit |
| [`engine/render.py`](engine/render.py) | v1 and v2 engine, kept for reference |
| [`engine/fxgen.py`](engine/fxgen.py) | Treatments: contours, dot matrix, ASCII, edges, slit-scan, strips, iris, tunnel, point cloud |
| [`engine/perc.py`](engine/perc.py) | Three-band onset detection |
| [`engine/analyze.py`](engine/analyze.py), [`engine/drops.py`](engine/drops.py) | Tempo, energy curve and drop timing |
| [`scripts/gen_clips.py`](scripts/gen_clips.py) | fal.ai batch generation (Kling 2.5 Turbo Pro, Veo 3.1) |
| [`scripts/check_render.py`](scripts/check_render.py) | Render QC |

## Findings

- Glitch effects (RGB split, slice displacement, echo trails) reduced perceived quality and were removed.
- Slow zooms on still images read as a slideshow. All stills were animated or dropped.
- On-screen text weakened the edit. The final version has none.
- Abstract geometry (wireframes, point clouds) was less effective than live-action footage of people.
- A hard cut to black one downbeat before the final hit was stronger than a fade-out.
- Beat trackers may report half-time: the track is 154 BPM and librosa reported 76.
- Chroma offset on 1-bit frames produces a green cast after 4:2:0 encoding, so it is applied only to non-binary frames.
- Unbounded per-worker frame caches exhausted 62 GB of RAM at 15 workers. Eight workers with bounded caches use about 3 GB.

## Music

**warhorse** by **fuyomo** ([YouTube](https://www.youtube.com/watch?v=zI9-1F5-A5M)), 154 BPM, G major.

Licensed by the producer as free for non-profit use only; monetized use requires a lease. The audio is
not included in this repository and the GIFs are silent.

## Credits

- Creative direction: [@RomanSlack](https://github.com/RomanSlack)
- Engine, rendering and review: [Claude Code](https://claude.com/claude-code)
- Music: fuyomo
- Fonts: Anton, VT323, Bebas Neue, Monoton, UnifrakturMaguntia (SIL Open Font License)

Code is MIT licensed. Generated footage is not included.
