"""Vercel serverless entrypoint.

Vercel's Python runtime looks for a module-level ASGI app named `app` and drives
it directly; there is no uvicorn process here. See vercel.json for the routing
and docs/DEPLOY.md for why this platform needs care.

The application package lives in backend/, which is not importable from the
repository root, so it is put on the path before importing.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.main import app  # noqa: E402  (path must be set before this import)

__all__ = ["app"]
