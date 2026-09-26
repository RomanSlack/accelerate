#!/usr/bin/env bash
# Download the OFL display fonts the engine uses (Google Fonts).
set -euo pipefail
mkdir -p fonts && cd fonts
base=https://github.com/google/fonts/raw/main/ofl
for f in anton/Anton-Regular.ttf bebasneue/BebasNeue-Regular.ttf monoton/Monoton-Regular.ttf \
         vt323/VT323-Regular.ttf unifrakturmaguntia/UnifrakturMaguntia-Book.ttf; do
  curl -sfLO "$base/$f"
done
ls
