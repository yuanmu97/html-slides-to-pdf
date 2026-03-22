# Playwright base image includes Chromium and OS deps for headless PDF.
# Pin tag to a known-good release; bump alongside playwright in requirements.txt when upgrading.
FROM mcr.microsoft.com/playwright/python:v1.50.0-jammy

USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt requirements-web.txt pyproject.toml html_to_pdf.py ./
COPY web ./web

RUN pip install --no-cache-dir -U pip && \
    pip install --no-cache-dir -r requirements-web.txt

ENV PYTHONUNBUFFERED=1
ENV HOST=0.0.0.0
ENV PORT=8000

EXPOSE 8000

CMD uvicorn web.app:app --host ${HOST} --port ${PORT}
