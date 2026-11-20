"""Deployment entry point (e.g. Vercel): exposes the FastAPI app.

The real code lives in src/backend. Its modules import each other as `backend.…`, so src/ must
be on the import path even when the host doesn't install this project as a package.
Locally, keep using:  uv run uvicorn backend.main:app --port 8000
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from backend.main import app

__all__ = ["app"]
