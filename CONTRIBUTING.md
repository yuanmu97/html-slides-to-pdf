# Contributing

Thanks for your interest in **html-slides-to-pdf**.

## Development setup

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
pip install -e .
```

## Checks before a PR

- Agent-facing changes belong in **`SKILL.md` at the repository root** (not under `docs/`). Keep **[README.md](README.md)** updated for human-oriented docs.
- Run the CLI against `examples/slides/mobile-ai-runtime.html` and confirm a 16-page PDF (or adjust the assertion in `.github/workflows/ci.yml` if the example slide count changes).
- If you change the showcase HTML, regenerate README previews: `python scripts/generate_readme_previews.py` (writes `docs/assets/example-slide-01.png` … `example-slide-03.png`).
- Changes to rendering should stay consistent with **[README.md](README.md) → How it works** (screen media, px-sized slides, do not set the active slide to `display: block`).
- Keep `html_to_pdf.py` suitable for single-file distribution (minimal dependencies beyond Playwright + pypdf).

## Publishing the package (maintainers)

After you create the GitHub repository, add `[project.urls]` in `pyproject.toml` with the real `Repository` URL.

## License

By contributing, you agree that your contributions are licensed under the MIT license (see [LICENSE](LICENSE)).
