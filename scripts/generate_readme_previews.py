#!/usr/bin/env python3
"""Regenerate docs/assets/example-slide-0[123].png from examples/slides/mobile-ai-runtime.html."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "examples/slides/mobile-ai-runtime.html"
OUT_DIR = ROOT / "docs/assets"
W, H = 1920, 1080
INDICES = (0, 1, 2)
OUT_NAMES = ("example-slide-01.png", "example-slide-02.png", "example-slide-03.png")


def main() -> int:
    if not HTML.is_file():
        print(f"error: missing {HTML}", file=sys.stderr)
        return 1
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("error: pip install playwright && playwright install chromium", file=sys.stderr)
        return 1

    hide = """
    .nav-dots, .progress-bar, .keyboard-hint, .edit-hotzone, .edit-toggle,
    [class*="nav-dot"], [class*="keyboard-hint"] {
      display: none !important;
    }
    """
    layout = f"""
    html, body {{
      margin: 0 !important;
      min-height: {H}px !important;
      width: {W}px !important;
      max-width: {W}px !important;
    }}
    .slide {{
      width: {W}px !important;
      min-width: {W}px !important;
      min-height: {H}px !important;
      height: {H}px !important;
      max-height: {H}px !important;
      box-sizing: border-box !important;
    }}
    """
    export_css = layout + "\n" + hide
    url = HTML.resolve().as_uri()

    js = """([idx, css]) => {
      const old = document.getElementById('__pdf_export_style');
      if (old) old.remove();
      const s = document.createElement('style');
      s.id = '__pdf_export_style';
      s.textContent = css;
      document.head.appendChild(s);
      document.querySelectorAll('.slide').forEach((el, j) => {
        if (j === idx) {
          el.style.removeProperty('display');
          el.classList.add('visible');
          el.querySelectorAll('.reveal').forEach(r => r.classList.add('visible'));
        } else {
          el.style.display = 'none';
        }
      });
      document.body.style.overflow = 'hidden';
      document.documentElement.style.overflow = 'hidden';
    }"""

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_context(viewport={"width": W, "height": H}).new_page()
        page.goto(url, wait_until="networkidle", timeout=120_000)
        page.emulate_media(media="screen")
        for idx, name in zip(INDICES, OUT_NAMES):
            page.evaluate(js, [idx, export_css])
            page.wait_for_timeout(1200)
            page.screenshot(path=str(OUT_DIR / name), full_page=False)
            print(OUT_DIR / name)
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
