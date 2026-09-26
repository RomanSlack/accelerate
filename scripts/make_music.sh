#!/usr/bin/env bash
# Build the 58.8s edit of the track: bar 1 to the breakdown, skip 5 bars, straight into the riser.
# The two cut points are bar lines for "warhorse" (154 BPM, G major; the beat tracker runs it at half-time, 77). For another track, find your own bar
# lines with engine/analyze.py and engine/drops.py, then change the two atrim ranges below.
# usage: scripts/make_music.sh path/to/your_track.(mp4|wav|mp3)
set -euo pipefail
mkdir -p ref build
ffmpeg -v error -y -i "$1" -vn -ac 2 -ar 44100 ref/warhorse.wav
ffmpeg -v error -y -i ref/warhorse.wav -filter_complex "\
[0:a]atrim=0:34.475,asetpts=PTS-STARTPTS[a];\
[0:a]atrim=50.03:74.5,asetpts=PTS-STARTPTS[b];\
[a][b]acrossfade=d=0.03:c1=tri:c2=tri[ab];[ab]atrim=0:58.8[out]" -map "[out]" build/music.wav
echo "wrote build/music.wav"
