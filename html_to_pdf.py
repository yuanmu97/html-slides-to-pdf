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
from collections.abc import Callable
from io import BytesIO
from pathlib import Path

ProgressCallback = Callable[[str, int, int], None]


class ConversionError(Exception):
    """Raised when the deck cannot be converted (missing file, no .slide, missing deps)."""

    def __init__(self, message: str, exit_code: int = 1) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def _url_for_path(html_path: Path) -> str:
    p = html_path.resolve()
    return p.as_uri()


def _cjk_font_stack_css() -> str:
    """
    Headless Linux often has no CJK fonts unless Noto/WQY are installed (see README).
    Decks usually set `font-family` on inner nodes (e.g. Syne / DM Sans only); those
    fonts lack Han glyphs, so we append CJK-capable faces after the deck's CSS variables.
    """
    return """
    .slide, .slide * {
      font-family: var(--font-display, var(--font-body, ui-sans-serif)),
        "Noto Sans CJK SC", "Noto Sans CJK TC", "Noto Serif CJK SC",
        "Source Han Sans SC", "WenQuanYi Zen Hei", "WenQuanYi Micro Hei",
        "PingFang SC", "Microsoft YaHei", "SimHei", sans-serif !important;
    }
    """


def _build_export_css(width: int, height: int) -> str:
    hide_ui_css = """
    .nav-dots, .progress-bar, .keyboard-hint, .edit-hotzone, .edit-toggle,
    [class*="nav-dot"], [class*="keyboard-hint"] {
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
    }}
    """
    return layout_fix_css + "\n" + hide_ui_css + "\n" + _cjk_font_stack_css()


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
    Read a local HTML file, render each `.slide` to one PDF page, return merged PDF bytes.

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
    export_css = _build_export_css(width, height)

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
        count = page.evaluate("() => document.querySelectorAll('.slide').length")
        if count == 0:
            browser.close()
            raise ConversionError(
                "no elements matching '.slide' found. Is this a slide-based HTML file?",
                exit_code=1,
            )

        tmpdir = tempfile.mkdtemp(prefix="html-slides-pdf-")
        part_paths: list[Path] = []

        try:
            _progress("rendering", 0, count)
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
