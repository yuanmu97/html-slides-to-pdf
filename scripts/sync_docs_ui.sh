#!/usr/bin/env sh
# Copy the web UI into docs/ for GitHub Pages after editing web/static/index.html.
set -e
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cp -f "$ROOT/web/static/index.html" "$ROOT/docs/index.html"
touch "$ROOT/docs/.nojekyll"
echo "Synced $ROOT/docs/index.html"
