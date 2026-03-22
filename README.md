# html-slides-to-pdf

**Agent-first:** start with **[SKILL.md](SKILL.md)** at the repo root (copy it into your agent’s skills folder as `SKILL.md`). This README documents installation, behavior, and troubleshooting for humans.

Export a **single-file HTML slide deck** to one **multi-page PDF** (one page per slide). Uses [Playwright](https://playwright.dev/python/) (Chromium) to render and [pypdf](https://pypdf.readthedocs.io/) to merge pages.

|                       |                                                                                                         |
| --------------------- | ------------------------------------------------------------------------------------------------------- |
| **Agent skill** | **[SKILL.md](SKILL.md)** — copy to `~/.cursor/skills/.../SKILL.md`, Claude Code skills path, etc. |
| **CLI**         | Run `html_to_pdf.py` or the `html-slides-to-pdf` command after `pip install -e .`                 |

Typical use: share decks via **WeChat**, email, or print—contexts where raw HTML is awkward.

## Example deck

Sample HTML: **[`examples/slides/mobile-ai-runtime.html`](examples/slides/mobile-ai-runtime.html)** — 16 slides, web fonts, dense layout, Chinese copy. Below are **three** representative pages (same rendering pipeline as PDF export).

| 封面                                               | 摘要                                               | 背景与动机                                               |
| -------------------------------------------------- | -------------------------------------------------- | -------------------------------------------------------- |
| ![Slide 1 — 封面](docs/assets/example-slide-01.png) | ![Slide 2 — 摘要](docs/assets/example-slide-02.png) | ![Slide 3 — 背景与动机](docs/assets/example-slide-03.png) |

|                 |                                                              |
| --------------- | ------------------------------------------------------------ |
| **Title** | *移动端开源模型推理基础软件 · 概念简报*                   |
| **Pages** | 16 (each `.slide` → one PDF page)                         |
| **Tip**   | Fonts load from CDNs; use `--delay-ms 1000` on slow links. |

```bash
python html_to_pdf.py examples/slides/mobile-ai-runtime.html -o mobile-ai-runtime.pdf --delay-ms 1000
```

To refresh the preview images after editing the sample HTML: `python scripts/generate_readme_previews.py` (requires Playwright Chromium).

## Requirements

- Python 3.10+
- Network access if the deck pulls fonts from CDNs

## Install

```bash
git clone https://github.com/yuanmu97/html-slides-to-pdf.git
cd html-slides-to-pdf
python -m pip install -r requirements.txt
python -m playwright install chromium
```

Editable install (adds the `html-slides-to-pdf` CLI):

```bash
python -m pip install -e .
```

Use the **same** Python for `pip` and for running the tool (e.g. Conda vs system `python3`).

## Usage

```bash
python html_to_pdf.py path/to/deck.html -o path/to/deck.pdf
```

Defaults: viewport **1920×1080**, **800 ms** per slide (fonts + reveal animations).

| Option                    | Meaning                                              |
| ------------------------- | ---------------------------------------------------- |
| `-h`, `--help`        | Show all options                                     |
| `-o`, `--output`      | Output PDF path (default: next to the HTML,`.pdf`) |
| `--width`, `--height` | Viewport CSS pixels (match the window you design in) |
| `--delay-ms`            | Wait after each slide before capture (default 800)   |
| `--keep-temp`           | Keep per-page PDFs in a temp dir (debug)             |

## How it works

1. Opens the HTML in headless Chromium at the chosen viewport.
2. **`emulate_media("screen")`** so layout matches a normal tab, not print styles.
3. Injects CSS to pin **`html` / `body` / `.slide`** to `--width`×`--height` **px**—`vh`/`dvh` are unreliable in PDF output and would break flex-based vertical alignment.
4. Shows **one** `.slide` at a time: hidden slides get `display: none`; the active slide has its **inline `display` cleared** so stylesheet rules like **`display: flex`** stay intact (setting `display: block` would break centered columns).
5. Hides common UI (nav dots, progress bar, keyboard hints, edit controls).
6. Adds `.visible` on the active slide and on `.reveal` nodes so animated copy appears in the PDF.
7. Prints one PDF page per slide and merges with **pypdf**.

## HTML contract

- Each slide is an element with class **`slide`** (e.g. `<section class="slide">`).
- See **How it works** if your slides use **flex** for vertical centering—the exporter preserves it by design.

## Repository layout

```text
html-slides-to-pdf/
├── SKILL.md                # Agent skill (canonical; copy into agent skills dir)
├── html_to_pdf.py          # CLI implementation
├── requirements.txt
├── pyproject.toml
├── docs/assets/            # README preview PNGs (scripts/generate_readme_previews.py)
├── scripts/
│   └── generate_readme_previews.py
├── examples/slides/        # Sample deck + exported PDF
└── .github/workflows/      # CI smoke test
```

## License

MIT — see [LICENSE](LICENSE).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).
