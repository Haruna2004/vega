#!/bin/bash
# Convert landing screenshots (2x PNG) to web-sized WebP, with crops for the tall inspector views.
set -e
cd "$(dirname "$0")/../../frontend/public/shots"
w() { ffmpeg -loglevel error -y -i "$1.png" -vf "$2" -c:v libwebp -quality 82 "$3.webp"; }
w review "scale=2000:-1" review
w map "scale=1800:-1" map
w orders "scale=1800:-1" orders
w ask "crop=iw:ih*0.42:0:0,scale=1800:-1" ask
w defect "crop=iw*0.46:ih:iw*0.54:0,scale=1100:-1" defect
w site "crop=iw*0.46:ih:iw*0.54:0,scale=1100:-1" site
w capture "scale=1600:-1" capture
rm -f *.png
ls -la
