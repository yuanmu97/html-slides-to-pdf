"""Run with: python -m web (HOST/PORT from environment)."""
from __future__ import annotations

import os

import uvicorn

if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("web.app:app", host=host, port=port)
