#!/usr/bin/env python3
"""
Render each .slide in an HTML presentation to one PDF page and merge.
Designed for single-file HTML decks (e.g. frontend-slides: section.slide, .reveal, nav UI).
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path


def _url_for_path(html_path: Path) -> str:
    p = html_path.resolve()
    return p.as_uri()


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
    if not html_path.is_file():
        print(f"error: file not found: {html_path}", file=sys.stderr)
        return 1

    out_pdf = args.output or html_path.with_suffix(".pdf")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "error: playwright is not installed. Run:\n"
            "  pip install playwright pypdf\n"
            "  playwright install chromium",
            file=sys.stderr,
        )
        return 1

    url = _url_for_path(html_path)

    # PDF generation uses Chromium's print path; without this, @media print and print-specific
    # layout differ from what you see in a normal browser tab (screen). Match on-screen layout.
    hide_ui_css = """
    .nav-dots, .progress-bar, .keyboard-hint, .edit-hotzone, .edit-toggle,
    [class*="nav-dot"], [class*="keyboard-hint"] {
      display: none !important;
    }
    """
    # In PDF output, 100vh / 100dvh often resolve incorrectly, so .slide collapses to content
    # height and flex vertical centering (e.g. .slide-content { flex:1; justify-content:center })
    # fails — content sticks to the top. Pin slide and document size to the same px as the viewport.
    w, h = args.width, args.height
    layout_fix_css = f"""
    html, body {{
      margin: 0 !important;
      min-height: {h}px !important;
      width: {w}px !important;
      max-width: {w}px !important;
    }}
    .slide {{
      width: {w}px !important;
      min-width: {w}px !important;
      min-height: {h}px !important;
      height: {h}px !important;
      max-height: {h}px !important;
      box-sizing: border-box !important;
    }}
    """
    export_css = layout_fix_css + "\n" + hide_ui_css

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": args.width, "height": args.height},
            device_scale_factor=1,
        )
        page = context.new_page()
        page.goto(url, wait_until="networkidle", timeout=120_000)
        page.emulate_media(media="screen")
        count = page.evaluate("() => document.querySelectorAll('.slide').length")
        if count == 0:
            print(
                "error: no elements matching '.slide' found. "
                "Is this a slide-based HTML file?",
                file=sys.stderr,
            )
            browser.close()
            return 1

        tmpdir = tempfile.mkdtemp(prefix="html-slides-pdf-")
        part_paths: list[Path] = []

        try:
            for i in range(count):
                part = Path(tmpdir) / f"part_{i:04d}.pdf"
                page.evaluate(
                    """([idx, css]) => {
                        const style = document.getElementById('__pdf_export_style');
                        if (style) style.remove();
                        const s = document.createElement('style');
                        s.id = '__pdf_export_style';
                        s.textContent = css;
                        document.head.appendChild(s);
                        const slides = document.querySelectorAll('.slide');
                        slides.forEach((el, j) => {
                            /* Never use display:block — it overrides stylesheet display:flex on .slide */
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
                    }""",
                    [i, export_css],
                )
                page.wait_for_timeout(args.delay_ms)
                page.pdf(
                    path=str(part),
                    width=f"{args.width}px",
                    height=f"{args.height}px",
                    print_background=True,
                    margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
                )
                part_paths.append(part)

            browser.close()

            try:
                from pypdf import PdfWriter
            except ImportError:
                print(
                    "error: pypdf is not installed. Run: pip install pypdf",
                    file=sys.stderr,
                )
                return 1

            writer = PdfWriter()
            for pp in part_paths:
                writer.append(str(pp))
            out_pdf.parent.mkdir(parents=True, exist_ok=True)
            with open(out_pdf, "wb") as f:
                writer.write(f)

        finally:
            if not args.keep_temp:
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

    print(str(out_pdf.resolve()))
    return 0


def run() -> None:
    """Console entry point for setuptools."""
    raise SystemExit(main())


if __name__ == "__main__":
    raise SystemExit(main())
