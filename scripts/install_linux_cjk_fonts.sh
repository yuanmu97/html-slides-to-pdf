#!/usr/bin/env sh
# Install CJK fonts for headless Chromium PDF on Debian/Ubuntu servers.
# Without these, Chinese/Japanese/Korean text can render as empty boxes in exported PDFs.
set -e
if command -v apt-get >/dev/null 2>&1; then
  sudo apt-get update
  sudo apt-get install -y --no-install-recommends fonts-noto-cjk
  echo "Installed fonts-noto-cjk. Restart the html-slides-to-pdf service if it is running."
else
  echo "This script supports apt-based systems (Debian/Ubuntu). Install a CJK font package for your distro (e.g. noto-cjk) and restart Chromium/your service."
  exit 1
fi
