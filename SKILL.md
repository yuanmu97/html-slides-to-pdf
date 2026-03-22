---
name: html-slides-to-pdf
description: >-
  Converts single-file HTML slide decks into a multi-page PDF for WeChat, email, or print.
  Runs a headless browser, one PDF page per `.slide`, merges with pypdf. Use when the user
  wants PDF from HTML slides, export slides to PDF, share slides on WeChat, or print presentations.
---

# HTML Slides → PDF (Agent Skill)

This repository is **agent-first**: this file is the **machine-readable skill** at the repo root. Install the CLI once on disk, then copy **this file** into your coding agent’s skill directory as **`SKILL.md`** so the agent knows when and how to run `html_to_pdf.py`. Human-oriented docs are in **[README.md](README.md)**.

Supported setups (same skill file, different install paths):

| Agent | Typical skill location | Notes |
|--------|-------------------------|--------|
| **Cursor Agent** | `~/.cursor/skills/html-slides-to-pdf/SKILL.md` | Copy or symlink from **`SKILL.md`** in this repository (repo root). |
| **Claude Code** | Per Claude Code docs for **skills** (user- or project-level) | Skill folder must contain **`SKILL.md`** with this content; exact path follows upstream docs. |

The **canonical** skill file in git is **`SKILL.md` at the repository root** (not under `docs/`).

## Prerequisites (one-time, machine)

Use **one** Python for both `pip install` and running the script:

```bash
cd /path/to/html-slides-to-pdf
python -m pip install -r requirements.txt
python -m playwright install chromium
```

## What the agent should run

Replace `/path/to/html-slides-to-pdf` with the actual clone path:

```bash
python /path/to/html-slides-to-pdf/html_to_pdf.py "/path/to/deck.html" -o "/path/to/deck.pdf"
```

If the package was installed with `pip install -e .`, the **`html-slides-to-pdf`** command is equivalent to `python .../html_to_pdf.py`.

Defaults: viewport **1920×1080**, **800 ms** delay per slide. Override with `--width`, `--height`, `--delay-ms`. Debug: `--keep-temp`.

Rendering details (screen media, `vh` pinning, flex-safe slide toggling) are in **[README.md](README.md)** under **How it works**.

## Behavior summary

- One merged PDF page per `.slide` element.
- **Screen** media; pins document/slide size to `--width`×`--height` px; clears inline `display` on the active slide so stylesheet **`display: flex`** (and similar) is preserved.
- Hides `.nav-dots`, `.progress-bar`, `.keyboard-hint`, `.edit-hotzone`, `.edit-toggle` (and similar) during capture.
- Adds `.visible` on the active slide and on `.reveal` descendants for animated content.

## If something goes wrong

1. **`No module named 'playwright'`** — Same `python` for `pip install` and `html_to_pdf.py`.
2. **No slides** — Need elements matching `.slide`.
3. **Clipped / fonts / timing** — Adjust `--width`, `--height`, `--delay-ms`.
4. **Layout vs browser** — Match `--width` / `--height` to the viewport you design in (default 1920×1080).

## Repo layout (for the agent)

- `html_to_pdf.py` — main script  
- `requirements.txt` — dependencies  
- `examples/slides/mobile-ai-runtime.html` — example deck (16 slides)  
