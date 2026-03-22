# html-slides-to-pdf

[License: MIT](LICENSE)

> **[Live converter](http://210.45.70.236:8000/)** — Open the hosted UI to upload a single-file HTML deck and download a multi-page PDF

**Privacy & storage (web service):** Your uploaded HTML is written to a **temporary file** only while Chromium renders it, then **deleted from disk as soon as that step finishes**. The resulting PDF is kept **in RAM** until you download it or the job expires (default one hour)—we **do not** keep your deck on the server disk after conversion.

---

Export a **single-file HTML slide deck** to one **multi-page PDF** (one page per slide). Uses [Playwright](https://playwright.dev/python/) (Chromium) to render and [pypdf](https://pypdf.readthedocs.io/) to merge pages.


| **Agent skill** | **[SKILL.md](SKILL.md)** for Cursor / Claude Code agents          |
| --------------- | ----------------------------------------------------------------- |
| **CLI**         | `html_to_pdf.py` or `html-slides-to-pdf` after `pip install -e .` |


## Install the agent skill

**Cursor**

```bash
git clone https://github.com/yuanmu97/html-slides-to-pdf.git ~/.cursor/skills/html-slides-to-pdf
```

**Claude Code**

```bash
git clone https://github.com/yuanmu97/html-slides-to-pdf.git ~/.claude/skills/html-slides-to-pdf
```

Typical use: share decks via **WeChat**, email, or print—contexts where raw HTML is awkward.

## Example deck

Sample HTML: `**[examples/slides/mobile-ai-runtime.html](examples/slides/mobile-ai-runtime.html)`** — 16 slides, web fonts, dense layout, Chinese copy. Three representative pages below.

```bash
python html_to_pdf.py examples/slides/mobile-ai-runtime.html -o mobile-ai-runtime.pdf --delay-ms 1000
```

### 1 · cover

Slide 1 — cover

### 2 · abstract

Slide 2 — abstract

### 3 · background

Slide 3 — background

## Requirements

- Python 3.10+

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

## Usage (for human)

```bash
python html_to_pdf.py path/to/deck.html -o path/to/deck.pdf
```

Defaults: viewport **1920×1080**, **800 ms** per slide (fonts + reveal animations).


| Option                | Meaning                                              |
| --------------------- | ---------------------------------------------------- |
| `-h`, `--help`        | Show all options                                     |
| `-o`, `--output`      | Output PDF path (default: next to the HTML,`.pdf`)   |
| `--width`, `--height` | Viewport CSS pixels (match the window you design in) |
| `--delay-ms`          | Wait after each slide before capture (default 800)   |
| `--keep-temp`         | Keep per-page PDFs in a temp dir (debug)             |


## How it works

1. Opens the HTML in headless Chromium at the chosen viewport.
2. `**emulate_media("screen")`** so layout matches a normal tab, not print styles.
3. Injects CSS to pin `**html` / `body` / `.slide**` to `--width`×`--height` **px**—`vh`/`dvh` are unreliable in PDF output and would break flex-based vertical alignment.
4. Shows **one** `.slide` at a time: hidden slides get `display: none`; the active slide has its **inline `display` cleared** so stylesheet rules like `**display: flex`** stay intact (setting `display: block` would break centered columns).
5. Hides common UI (nav dots, progress bar, keyboard hints, edit controls).
6. Adds `.visible` on the active slide and on `.reveal` nodes so animated copy appears in the PDF.
7. Prints one PDF page per slide and merges with **pypdf**.

## Maintainer notes: hosting the web service

For **maintainers** deploying the public “Try it online” app on their own machine. End users can ignore this section.

```bash
python -m pip install -r requirements-web.txt
python -m playwright install chromium
python -m web
# listens on 0.0.0.0:8000 by default; or: uvicorn web.app:app --host 0.0.0.0 --port 8000
```

- `GET /` serves the upload UI (Chinese / English toggle; progress uses the job API below).
- `POST /api/convert/jobs` → `{ "job_id" }`; `GET /api/convert/jobs/{id}` → `{ status, phase, current, total, detail }`; `GET /api/convert/jobs/{id}/pdf` downloads the PDF when `status` is `done`. `POST /api/convert` (same form fields) still returns the PDF in one response for scripts.
- **Privacy / storage:** Uploaded HTML is written to a **temporary file** only for the conversion step, then **deleted immediately** afterward (before the async job stores the PDF in memory, or before the synchronous response is built). The generated PDF for job-based flows is kept **in RAM** until the client downloads it or the job expires (`HTML_SLIDES_JOB_TTL_SEC`, default 1 hour).
- `GET /api/health` is a health check.
- Environment variables: `HOST` / `PORT`, `CORS_ORIGINS` (default `*`), `HTML_SLIDES_MAX_UPLOAD_BYTES` (default ~25 MiB).
- **CJK / Han glyphs in PDF:** On Linux, install system fonts such as **Noto CJK** or Chinese PDF output can show empty boxes. Debian/Ubuntu: `sudo apt install fonts-noto-cjk` or run `[scripts/install_linux_cjk_fonts.sh](scripts/install_linux_cjk_fonts.sh)`, then restart the service. The Docker image installs `fonts-noto-cjk` by default.

**systemd (user service):** see `[deploy/html-slides-to-pdf.user.service](deploy/html-slides-to-pdf.user.service)`, then `systemctl --user enable --now html-slides-to-pdf`. With `loginctl enable-linger` for your user, the user service can start at boot without an interactive session.

**Docker:** `Dockerfile` and `docker-compose.yml` at the repo root use the [official Playwright Python image](https://playwright.dev/python/docs/docker). On a cloud VM: `docker compose up -d --build`, then terminate TLS with Nginx (or similar) if needed.

**Optional GitHub Pages:** publish the `docs/` folder as a static mirror; if the static site and API are on different origins, use the “mirror / API base URL” field in the UI to point at your public API. After editing `web/static/index.html`, run `./scripts/sync_docs_ui.sh` to refresh `docs/`.

## Repository layout

```text
html-slides-to-pdf/
├── SKILL.md                # Agent skill (canonical; copy into agent skills dir)
├── html_to_pdf.py          # CLI + convert_html_file_to_pdf()
├── requirements.txt
├── requirements-web.txt    # Optional FastAPI / uvicorn / multipart
├── pyproject.toml
├── web/                    # HTTP service + static UI
│   ├── app.py
│   ├── static/index.html
│   └── __main__.py         # python -m web
├── deploy/
│   └── html-slides-to-pdf.user.service  # example systemd --user unit
├── Dockerfile
├── docker-compose.yml
├── docs/                   # Optional GitHub Pages mirror; index.html sync from web/static/
├── scripts/
│   ├── install_linux_cjk_fonts.sh
│   ├── sync_docs_ui.sh
│   └── generate_readme_previews.py
├── examples/slides/        # Sample deck + exported PDF
└── .github/workflows/      # CI smoke test
```

## License

MIT — see [LICENSE](LICENSE).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).