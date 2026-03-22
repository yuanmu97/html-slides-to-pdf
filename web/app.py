"""
Online HTML slide deck → PDF API and static web UI.

Privacy / storage: uploaded HTML is written to a temp file only for the duration of
`convert_html_file_to_pdf`, then deleted immediately (before the PDF bytes are stored
in the in-memory job, or before the HTTP response is returned for `/api/convert`).
PDFs for async jobs live in RAM until the client downloads them or the job expires.
"""
from __future__ import annotations

import os
import re
import tempfile
import threading
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from html_to_pdf import ConversionError, convert_html_file_to_pdf

STATIC_DIR = Path(__file__).resolve().parent / "static"

DEFAULT_MAX_UPLOAD = 25 * 1024 * 1024  # 25 MiB
MAX_UPLOAD_BYTES = int(os.environ.get("HTML_SLIDES_MAX_UPLOAD_BYTES", str(DEFAULT_MAX_UPLOAD)))

CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*").strip()

JOB_TTL_SEC = int(os.environ.get("HTML_SLIDES_JOB_TTL_SEC", "3600"))

JOBS_LOCK = threading.Lock()
JOBS: dict[str, dict] = {}


def _unlink_upload(path: Path) -> None:
    """Remove a temp upload file; ignore missing paths."""
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _safe_pdf_filename(name: str) -> str:
    base = Path(name or "deck.html").stem
    base = re.sub(r"[^\w\u4e00-\u9fff\-_.]", "_", base)[:120] or "slides"
    return f"{base}.pdf"


def _cleanup_stale_jobs() -> None:
    now = time.time()
    with JOBS_LOCK:
        stale = [k for k, v in JOBS.items() if now - v.get("created", 0) > JOB_TTL_SEC]
        for k in stale:
            JOBS.pop(k, None)


def _run_conversion_job(
    job_id: str,
    path: Path,
    *,
    width: int,
    height: int,
    delay_ms: int,
) -> None:
    def on_progress(phase: str, current: int, total: int) -> None:
        with JOBS_LOCK:
            if job_id not in JOBS:
                return
            JOBS[job_id]["phase"] = phase
            JOBS[job_id]["current"] = current
            JOBS[job_id]["total"] = total

    pdf: bytes | None = None
    with JOBS_LOCK:
        if job_id in JOBS:
            JOBS[job_id]["status"] = "running"

    try:
        pdf = convert_html_file_to_pdf(
            path,
            width=width,
            height=height,
            delay_ms=delay_ms,
            on_progress=on_progress,
        )
    except ConversionError as e:
        with JOBS_LOCK:
            if job_id in JOBS:
                JOBS[job_id]["status"] = "error"
                JOBS[job_id]["detail"] = str(e)
                JOBS[job_id]["phase"] = "error"
    except Exception as e:  # noqa: BLE001 — surface unexpected errors to client
        with JOBS_LOCK:
            if job_id in JOBS:
                JOBS[job_id]["status"] = "error"
                JOBS[job_id]["detail"] = str(e)
                JOBS[job_id]["phase"] = "error"
    finally:
        # Delete the uploaded HTML from disk as soon as conversion finishes (or fails).
        _unlink_upload(path)

    if pdf is not None:
        with JOBS_LOCK:
            if job_id in JOBS:
                JOBS[job_id]["pdf"] = pdf
                JOBS[job_id]["status"] = "done"
                JOBS[job_id]["phase"] = "done"
                JOBS[job_id]["current"] = JOBS[job_id].get("total", 0)


def create_app() -> FastAPI:
    app = FastAPI(
        title="html-slides-to-pdf",
        description="Convert single-file HTML slide decks (`.slide` sections) to one multi-page PDF.",
        version="0.2.0",
    )

    if CORS_ORIGINS == "*":
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    else:
        origins = [o.strip() for o in CORS_ORIGINS.split(",") if o.strip()]
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.get("/api/health")
    def api_health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/convert/jobs")
    async def api_convert_job(
        file: UploadFile = File(..., description="Single .html file with `.slide` sections"),
        width: int = Form(1920, ge=320, le=7680),
        height: int = Form(1080, ge=240, le=4320),
        delay_ms: int = Form(800, ge=0, le=60_000),
    ) -> dict[str, str]:
        if not file.filename or not file.filename.lower().endswith((".html", ".htm")):
            raise HTTPException(
                status_code=400,
                detail="Upload a .html or .htm file.",
            )
        raw = await file.read()
        if len(raw) > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"File too large (max {MAX_UPLOAD_BYTES // (1024 * 1024)} MiB).",
            )
        if len(raw) == 0:
            raise HTTPException(status_code=400, detail="Empty file.")

        _cleanup_stale_jobs()
        suffix = Path(file.filename).suffix or ".html"
        fd, tmp_path = tempfile.mkstemp(prefix="html-slides-in-", suffix=suffix)
        os.close(fd)
        path = Path(tmp_path)
        path.write_bytes(raw)
        del raw

        job_id = uuid.uuid4().hex
        out_name = _safe_pdf_filename(file.filename)
        with JOBS_LOCK:
            JOBS[job_id] = {
                "status": "queued",
                "phase": "loading",
                "current": 0,
                "total": 0,
                "detail": None,
                "pdf": None,
                "filename": out_name,
                "created": time.time(),
            }

        t = threading.Thread(
            target=_run_conversion_job,
            args=(job_id, path),
            kwargs={"width": width, "height": height, "delay_ms": delay_ms},
            daemon=True,
        )
        t.start()
        return {"job_id": job_id}

    @app.get("/api/convert/jobs/{job_id}")
    def api_convert_job_status(job_id: str) -> dict:
        _cleanup_stale_jobs()
        with JOBS_LOCK:
            job = JOBS.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Unknown or expired job_id.")
        return {
            "status": job["status"],
            "phase": job.get("phase", "loading"),
            "current": job.get("current", 0),
            "total": job.get("total", 0),
            "detail": job.get("detail"),
        }

    @app.get("/api/convert/jobs/{job_id}/pdf")
    def api_convert_job_pdf(job_id: str) -> Response:
        _cleanup_stale_jobs()
        with JOBS_LOCK:
            job = JOBS.pop(job_id, None)
        if not job:
            raise HTTPException(status_code=404, detail="Unknown or expired job_id.")
        if job["status"] != "done" or not job.get("pdf"):
            raise HTTPException(status_code=400, detail="Job is not finished or failed.")
        name = job.get("filename") or "slides.pdf"
        return Response(
            content=job["pdf"],
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{name}"',
                "Cache-Control": "no-store",
            },
        )

    @app.post("/api/convert")
    async def api_convert(
        file: UploadFile = File(..., description="Single .html file with `.slide` sections"),
        width: int = Form(1920, ge=320, le=7680),
        height: int = Form(1080, ge=240, le=4320),
        delay_ms: int = Form(800, ge=0, le=60_000),
    ) -> Response:
        if not file.filename or not file.filename.lower().endswith((".html", ".htm")):
            raise HTTPException(
                status_code=400,
                detail="Upload a .html or .htm file.",
            )
        raw = await file.read()
        if len(raw) > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"File too large (max {MAX_UPLOAD_BYTES // (1024 * 1024)} MiB).",
            )
        if len(raw) == 0:
            raise HTTPException(status_code=400, detail="Empty file.")

        suffix = Path(file.filename).suffix or ".html"
        fd, tmp_path = tempfile.mkstemp(prefix="html-slides-in-", suffix=suffix)
        os.close(fd)
        path = Path(tmp_path)
        try:
            path.write_bytes(raw)
            del raw

            def _run() -> bytes:
                return convert_html_file_to_pdf(
                    path,
                    width=width,
                    height=height,
                    delay_ms=delay_ms,
                )

            try:
                from starlette.concurrency import run_in_threadpool

                pdf_bytes = await run_in_threadpool(_run)
            except ConversionError as e:
                raise HTTPException(status_code=400, detail=str(e)) from e
        finally:
            # Uploaded HTML is only needed during conversion; remove immediately after.
            _unlink_upload(path)

        out_name = _safe_pdf_filename(file.filename)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{out_name}"',
                "Cache-Control": "no-store",
            },
        )

    app.mount(
        "/",
        StaticFiles(directory=str(STATIC_DIR), html=True),
        name="static",
    )
    return app


app = create_app()
