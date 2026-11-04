#!/bin/bash
# Convert landing screenshots (2x PNG) to web-sized WebP, with crops for the tall inspector views.
cd "$(dirname "$0")/../../frontend/public/shots"
w() { ffmpeg -loglevel error -y -i "$1.png" -vf "$2" -c:v libwebp -quality 82 "$3.webp"; }
[ -f review.png ] && w review "scale=2000:-1" review
[ -f map.png ] && w map "scale=1800:-1" map
[ -f orders.png ] && w orders "scale=1800:-1" orders
w ask "crop=iw:ih*0.5:0:0,scale=1600:-1" ask
w defect "scale=760:-1" defect
w stage "scale=1600:-1" stage
[ -f site.png ] && w site "crop=iw*0.46:ih:iw*0.54:0,scale=1100:-1" site
[ -f capture.png ] && w capture "scale=1600:-1" capture
rm -f *.png
ls -la
