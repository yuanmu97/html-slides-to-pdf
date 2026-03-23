#!/usr/bin/env python3
"""
Render each slide in an HTML deck to one PDF page and merge.

Supports: (1) reveal.js — `.reveal .slides` with `Reveal.getSlides()` when available,
or static `> section` children; (2) stacked `.slide` panels (excluding the reveal root
that also has class `slide`). Dot-slide decks toggle `.active` per page so CSS like
`.slide { display:none }` + `.slide.active { display:flex }` export correctly.
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
from collections.abc import Callable
from io import BytesIO
from pathlib import Path

ProgressCallback = Callable[[str, int, int], None]

# Slightly under-fill the PDF page so Chromium does not clip anti-aliased edges (subpixel).
_REVEAL_SCALE_EPSILON = 0.998

class ConversionError(Exception):
    """Raised when the deck cannot be converted (missing file, no slides, missing deps)."""

    def __init__(self, message: str, exit_code: int = 1) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def _url_for_path(html_path: Path) -> str:
    p = html_path.resolve()
    return p.as_uri()


def _cjk_font_stack_css(*, reveal: bool = False) -> str:
    """
    Headless Linux often has no CJK fonts unless Noto/WQY are installed (see README).
    Decks usually set `font-family` on inner nodes (e.g. Syne / DM Sans only); those
    fonts lack Han glyphs, so we append CJK-capable faces after the deck's CSS variables.
    """
    selectors = ".slide, .slide *"
    if reveal:
        selectors = ".slide, .slide *, .reveal .slides section, .reveal .slides section *"
    return f"""
    {selectors} {{
      font-family: var(--font-display, var(--font-body, ui-sans-serif)),
        "Noto Sans CJK SC", "Noto Sans CJK TC", "Noto Serif CJK SC",
        "Source Han Sans SC", "WenQuanYi Zen Hei", "WenQuanYi Micro Hei",
        "PingFang SC", "Microsoft YaHei", "SimHei", sans-serif !important;
    }}
    """


def _print_color_css() -> str:
    """Help Chromium keep slide / theme backgrounds in PDF (dark themes, gradients)."""
    return """
    html, body, .reveal, .reveal-viewport {
      -webkit-print-color-adjust: exact !important;
      print-color-adjust: exact !important;
    }
    """


def _build_export_css(
    width: int,
    height: int,
    *,
    reveal: bool = False,
    reveal_design: tuple[int, int, float] | None = None,
) -> str:
    hide_ui_css = """
    .nav-dots, .progress-bar, .keyboard-hint, .edit-hotzone, .edit-toggle,
    [class*="nav-dot"], [class*="keyboard-hint"],
    body > .controls, body > .page-indicator,
    .reveal .controls, .reveal aside.controls, .reveal .progress,
    .reveal .slide-number, .reveal .speaker-notes, .reveal .pause-overlay,
    .reveal .aria-status, .export-btn {
      display: none !important;
    }
    """
    layout_fix_css = f"""
    html, body {{
      margin: 0 !important;
      min-height: {height}px !important;
      width: {width}px !important;
      max-width: {width}px !important;
    }}
    .slide {{
      width: {width}px !important;
      min-width: {width}px !important;
      min-height: {height}px !important;
      height: {height}px !important;
      max-height: {height}px !important;
      box-sizing: border-box !important;
      transition: none !important;
      animation: none !important;
    }}
    """
    reveal_layout_css = ""
    if reveal and reveal_design is not None:
        dw, dh, scale = reveal_design
        # Keep reveal's authored layout (e.g. 960×700); scale to fit PDF viewport without cropping.
        # Use top-left + scale(origin 0,0) instead of translate(-50%,-50%) scale(...) to avoid
        # transform-order bugs that shift the deck and clip content in Chromium PDF.
        scale_s = f"{scale:.8f}".rstrip("0").rstrip(".")
        ox = (width - dw * scale) / 2
        oy = (height - dh * scale) / 2
        ox_s = f"{ox:.4f}".rstrip("0").rstrip(".")
        oy_s = f"{oy:.4f}".rstrip("0").rstrip(".")
        # Do not add `inset: ...` after explicit top/left here — it resets those longhands.
        reveal_layout_css = f"""
    .reveal, .reveal-viewport {{
      width: {width}px !important;
      height: {height}px !important;
      max-width: {width}px !important;
      max-height: {height}px !important;
      overflow: hidden !important;
      margin: 0 !important;
      position: relative !important;
      perspective: none !important;
    }}
    .reveal .slides {{
      perspective: none !important;
      position: absolute !important;
      left: {ox_s}px !important;
      top: {oy_s}px !important;
      right: auto !important;
      bottom: auto !important;
      width: {dw}px !important;
      height: {dh}px !important;
      margin: 0 !important;
      padding: 0 !important;
      zoom: 1 !important;
      transform: scale({scale_s}) !important;
      transform-origin: 0 0 !important;
    }}
    .reveal .slides section {{
      box-sizing: border-box !important;
      transition: none !important;
      animation: none !important;
    }}
    .reveal .slides section.present .fragment {{
      opacity: 1 !important;
      visibility: visible !important;
    }}
    /* Reveal lays out all horizontal sections in one row (huge scrollWidth). Clipping to
       design width without hiding siblings only shows the left slice of that strip. */
    .reveal .slides > section:not(.present):not(:has(section.present)) {{
      display: none !important;
    }}
    .reveal .backgrounds {{
      position: absolute !important;
      left: {ox_s}px !important;
      top: {oy_s}px !important;
      width: {dw}px !important;
      height: {dh}px !important;
      margin: 0 !important;
      padding: 0 !important;
      zoom: 1 !important;
      transform: scale({scale_s}) !important;
      transform-origin: 0 0 !important;
    }}
    .reveal .slide-background {{
      width: 100% !important;
      height: 100% !important;
    }}
    """
    elif reveal:
        # Fallback if design size could not be read (should be rare).
        reveal_layout_css = f"""
    .reveal, .reveal-viewport {{
      width: {width}px !important;
      height: {height}px !important;
      overflow: hidden !important;
      margin: 0 !important;
      position: relative !important;
    }}
    """
    return (
        layout_fix_css
        + reveal_layout_css
        + "\n"
        + _print_color_css()
        + "\n"
        + hide_ui_css
        + "\n"
        + _cjk_font_stack_css(reveal=reveal)
    )


_DECK_MODE_JS = r"""
() => {
  const slidesHost = document.querySelector(".reveal .slides");
  if (slidesHost) {
    if (typeof Reveal !== "undefined" && typeof Reveal.getSlides === "function") {
      try {
        const slides = Reveal.getSlides();
        if (slides && slides.length) return { mode: "reveal", count: slides.length };
      } catch (e) {}
    }
    const topSections = slidesHost.querySelectorAll(":scope > section");
    if (topSections.length) return { mode: "reveal-static", count: topSections.length };
  }
  const dotSlides = Array.from(document.querySelectorAll(".slide")).filter((el) => {
    if (el.classList.contains("reveal") && el.querySelector(".slides")) return false;
    return true;
  });
  if (dotSlides.length) return { mode: "dot-slide", count: dotSlides.length };
  return { mode: "none", count: 0 };
}
"""

_WAIT_REVEAL_READY_JS = r"""
async () => {
  if (typeof Reveal === "undefined" || typeof Reveal.isReady !== "function") {
    return;
  }
  if (Reveal.isReady()) {
    return;
  }
  await new Promise((resolve) => {
    const done = () => resolve(undefined);
    if (typeof Reveal.on === "function") {
      Reveal.on("ready", done);
    }
    setTimeout(done, 4000);
  });
}
"""

_REVEAL_DESIGN_JS = r"""
([vw, vh]) => {
  let dw = 960;
  let dh = 700;
  const num = (v, fb) => {
    if (typeof v === "number" && v > 0) return v;
    if (typeof v === "string" && /^\d+(\.\d+)?px\s*$/i.test(v.trim())) return parseFloat(v);
    return fb;
  };
  if (typeof Reveal !== "undefined" && Reveal.getConfig) {
    const c = Reveal.getConfig();
    if (c) {
      const w = c.width;
      const h = c.height;
      if (typeof w === "string" && w.trim().endsWith("%")) dw = vw;
      else dw = num(w, dw);
      if (typeof h === "string" && h.trim().endsWith("%")) dh = vh;
      else dh = num(h, dh);
    }
  }
  const cs = getComputedStyle(document.body);
  const vx = parseInt(cs.getPropertyValue("--slide-width"), 10);
  const vy = parseInt(cs.getPropertyValue("--slide-height"), 10);
  if (vx > 0) dw = vx;
  if (vy > 0) dh = vy;
  const slidesEl = document.querySelector(".reveal .slides");
  if (slidesEl) {
    const st = slidesEl.getAttribute("style") || "";
    const wm = st.match(/width:\s*(\d+(?:\.\d+)?)px/i);
    const hm = st.match(/height:\s*(\d+(?:\.\d+)?)px/i);
    if (wm) dw = Math.max(1, Math.round(parseFloat(wm[1])));
    if (hm) dh = Math.max(1, Math.round(parseFloat(hm[1])));
  }
  dw = Math.max(1, dw);
  dh = Math.max(1, dh);
  return { dw, dh };
}
"""

_APPLY_SLIDE_JS = r"""
([idx, css, mode]) => {
  const style = document.getElementById("__pdf_export_style");
  if (style) style.remove();
  const s = document.createElement("style");
  s.id = "__pdf_export_style";
  s.textContent = css;
  document.head.appendChild(s);

  const copyBackgroundToRoot = () => {
    const candidates = [
      document.querySelector(".reveal-viewport"),
      document.querySelector(".reveal"),
      document.body,
    ].filter(Boolean);
    let src = document.body;
    for (const el of candidates) {
      const cs = getComputedStyle(el);
      const bgc = cs.backgroundColor;
      if (bgc && bgc !== "rgba(0, 0, 0, 0)" && bgc !== "transparent") {
        src = el;
        break;
      }
    }
    const cs = getComputedStyle(src);
    const props = [
      "background-color",
      "background-image",
      "background-size",
      "background-position",
      "background-repeat",
      "background-attachment",
      "background-clip",
      "background-origin",
    ];
    const html = document.documentElement;
    const body = document.body;
    for (const p of props) {
      const v = cs.getPropertyValue(p);
      if (v) {
        html.style.setProperty(p, v);
        body.style.setProperty(p, v);
      }
    }
  };

  if (mode === "reveal") {
    copyBackgroundToRoot();
    const slides = Reveal.getSlides();
    const el = slides[idx];
    if (el) {
      try {
        const { h, v } = Reveal.getIndices(el);
        Reveal.slide(h, v);
      } catch (e) {
        Reveal.slide(idx, 0);
      }
    }
    /* Reveal sets non-standard `zoom` on .slides for viewport fit; it stacks with our scale() and clips content. */
    document.querySelectorAll(".reveal .slides, .reveal .backgrounds").forEach((node) => {
      node.style.setProperty("zoom", "1", "important");
    });
    const rootReveal = document.querySelector(".reveal");
    if (rootReveal) {
      const rz = parseFloat(getComputedStyle(rootReveal).zoom || "1");
      if (rz && rz !== 1 && !Number.isNaN(rz)) {
        rootReveal.style.setProperty("zoom", "1", "important");
      }
    }
    if (typeof Reveal !== "undefined" && typeof Reveal.layout === "function") {
      try {
        Reveal.layout();
      } catch (e) {}
    }
    copyBackgroundToRoot();
    document.body.style.overflow = "hidden";
    document.documentElement.style.overflow = "hidden";
    return;
  }

  if (mode === "reveal-static") {
    const deck = document.querySelector(".reveal .slides");
    const sections = Array.from(deck.querySelectorAll(":scope > section"));
    copyBackgroundToRoot();
    sections.forEach((sec, j) => {
      if (j === idx) {
        sec.removeAttribute("hidden");
        sec.style.removeProperty("display");
        sec.classList.remove("past", "future");
        sec.classList.add("present");
      } else {
        sec.style.setProperty("display", "none", "important");
        sec.setAttribute("hidden", "");
        sec.setAttribute("aria-hidden", "true");
      }
    });
    const bgRoot = document.querySelector(".reveal .backgrounds");
    if (bgRoot) {
      const bgSlides = bgRoot.querySelectorAll(":scope > .slide-background");
      bgSlides.forEach((bg, j) => {
        if (j === idx) bg.style.removeProperty("display");
        else bg.style.setProperty("display", "none", "important");
      });
    }
    document.querySelectorAll(".reveal .slides, .reveal .backgrounds").forEach((node) => {
      node.style.setProperty("zoom", "1", "important");
    });
    const rootReveal2 = document.querySelector(".reveal");
    if (rootReveal2) {
      const rz = parseFloat(getComputedStyle(rootReveal2).zoom || "1");
      if (rz && rz !== 1 && !Number.isNaN(rz)) {
        rootReveal2.style.setProperty("zoom", "1", "important");
      }
    }
    copyBackgroundToRoot();
    document.body.style.overflow = "hidden";
    document.documentElement.style.overflow = "hidden";
    return;
  }

  const slides = Array.from(document.querySelectorAll(".slide")).filter((el) => {
    if (el.classList.contains("reveal") && el.querySelector(".slides")) return false;
    return true;
  });
  copyBackgroundToRoot();
  slides.forEach((el, j) => {
    if (j === idx) {
      el.classList.add("active");
      el.style.removeProperty("display");
      el.querySelectorAll(".reveal").forEach((r) => r.classList.add("visible"));
    } else {
      el.classList.remove("active");
      el.style.setProperty("display", "none", "important");
    }
  });
  copyBackgroundToRoot();
  document.body.style.overflow = "hidden";
  document.documentElement.style.overflow = "hidden";
}
"""


def convert_html_file_to_pdf(
    html_path: Path,
    *,
    width: int = 1920,
    height: int = 1080,
    delay_ms: int = 800,
    keep_temp: bool = False,
    goto_timeout_ms: int = 120_000,
    on_progress: ProgressCallback | None = None,
) -> bytes:
    """
    Read a local HTML file, render each slide to one PDF page, return merged PDF bytes.

    Raises ConversionError on user-facing failures (missing file, no slides, deps).
    """
    html_path = Path(html_path)
    if not html_path.is_file():
        raise ConversionError(f"file not found: {html_path}", exit_code=1)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise ConversionError(
            "playwright is not installed. Run:\n"
            "  pip install playwright pypdf\n"
            "  playwright install chromium",
            exit_code=1,
        ) from e

    try:
        from pypdf import PdfWriter
    except ImportError as e:
        raise ConversionError("pypdf is not installed. Run: pip install pypdf", exit_code=1) from e

    url = _url_for_path(html_path)

    def _progress(phase: str, current: int, total: int) -> None:
        if on_progress is not None:
            on_progress(phase, current, total)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--lang=zh-CN"],
        )
        context = browser.new_context(
            viewport={"width": width, "height": height},
            device_scale_factor=1,
            locale="zh-CN",
        )
        page = context.new_page()
        _progress("loading", 0, 0)
        page.goto(url, wait_until="networkidle", timeout=goto_timeout_ms)
        page.emulate_media(media="screen")
        # Ensure @font-face / webfonts are loaded before counting slides & printing.
        page.evaluate("async () => { await document.fonts.ready; }")
        page.evaluate(_WAIT_REVEAL_READY_JS)
        deck = page.evaluate(_DECK_MODE_JS)
        count = int(deck.get("count") or 0)
        mode = str(deck.get("mode") or "none")
        if count == 0 or mode == "none":
            browser.close()
            raise ConversionError(
                "no slides found. Expected reveal.js (.reveal .slides > section), "
                "or elements with class .slide (excluding the reveal root).",
                exit_code=1,
            )

        reveal_css = mode in ("reveal", "reveal-static")
        reveal_design: tuple[int, int, float] | None = None
        if reveal_css:
            dim = page.evaluate(_REVEAL_DESIGN_JS, [width, height])
            dw = max(1, int(dim.get("dw") or 960))
            dh = max(1, int(dim.get("dh") or 700))
            sc = min(width / dw, height / dh) * _REVEAL_SCALE_EPSILON
            reveal_design = (dw, dh, sc)
        export_css = _build_export_css(
            width, height, reveal=reveal_css, reveal_design=reveal_design
        )

        tmpdir = tempfile.mkdtemp(prefix="html-slides-pdf-")
        part_paths: list[Path] = []

        try:
            _progress("rendering", 0, count)
            for i in range(count):
                part = Path(tmpdir) / f"part_{i:04d}.pdf"
                page.evaluate(_APPLY_SLIDE_JS, [i, export_css, mode])
                page.wait_for_timeout(delay_ms)
                page.pdf(
                    path=str(part),
                    width=f"{width}px",
                    height=f"{height}px",
                    print_background=True,
                    margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
                )
                part_paths.append(part)
                _progress("rendering", i + 1, count)

            browser.close()

            _progress("merging", count, count)
            writer = PdfWriter()
            for pp in part_paths:
                writer.append(str(pp))
            out = BytesIO()
            writer.write(out)
            return out.getvalue()

        finally:
            if not keep_temp:
                for pp in part_paths:
                    try:
                        pp.unlink(missing_ok=True)
                    except OSError:
                        pass
                try:
                    os.rmdir(tmpdir)
                except OSError:
                    pass
            else:
                print(f"temp PDF parts: {tmpdir}", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser(description="HTML slides -> single PDF (one page per slide)")
    ap.add_argument("input_html", type=Path, help="Path to the presentation .html file")
    ap.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output PDF path (default: same basename as input with .pdf)",
    )
    ap.add_argument(
        "--width",
        type=int,
        default=1920,
        help="Viewport width in CSS pixels (default 1920, 16:9 with --height 1080)",
    )
    ap.add_argument(
        "--height",
        type=int,
        default=1080,
        help="Viewport height in CSS pixels (default 1080)",
    )
    ap.add_argument(
        "--delay-ms",
        type=int,
        default=800,
        help="Wait after showing each slide (fonts, web fonts, CSS animations)",
    )
    ap.add_argument(
        "--keep-temp",
        action="store_true",
        help="Keep per-page PDFs in a temp directory (for debugging)",
    )
    args = ap.parse_args()

    html_path = args.input_html
    out_pdf = args.output or html_path.with_suffix(".pdf")

    try:
        data = convert_html_file_to_pdf(
            html_path,
            width=args.width,
            height=args.height,
            delay_ms=args.delay_ms,
            keep_temp=args.keep_temp,
        )
    except ConversionError as e:
        print(f"error: {e}", file=sys.stderr)
        if args.keep_temp:
            pass
        return e.exit_code

    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    with open(out_pdf, "wb") as f:
        f.write(data)

    print(str(out_pdf.resolve()))
    return 0


def run() -> None:
    """Console entry point for setuptools."""
    raise SystemExit(main())


if __name__ == "__main__":
    raise SystemExit(main())
