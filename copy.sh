#!/bin/bash
# Copies a paste-ready embed fragment to the macOS clipboard.
#   ./copy.sh            -> sectioned layout (embed_sections.html)  [default]
#   ./copy.sh flat       -> flat single-column, ranked layout (embed.html)
set -euo pipefail
DIR="/Users/filitti/Downloads/mamdani-dsa-tracker"

case "${1:-sections}" in
  flat|ranked|single) FILE="embed.html" ;;
  *)                  FILE="embed_sections.html" ;;
esac

pbcopy < "$DIR/public/$FILE"
echo "Copied public/$FILE to the clipboard."
echo "Now paste it into your site's code block and Save."
