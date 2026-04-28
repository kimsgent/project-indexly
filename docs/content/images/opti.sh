#!/bin/bash
# Dependencies
# - img-optimize - https://virtubox.github.io/img-optimize/
# - imagemagick
# - jpegoptim
# - optipng

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DOCS_ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"
FOLDER="${DOCS_ROOT}/static/images"

# max width
WIDTH=800

# max height
HEIGHT=600

# Resize images to either height or width, keeping proportions using ImageMagick.
find "$FOLDER" \( -iname '*.png' -o -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.webp' \) \
	-exec convert {} -verbose -resize "${WIDTH}x${HEIGHT}>" {} \;
img-optimize --std --path "$FOLDER"
