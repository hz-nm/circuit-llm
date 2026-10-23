"""Serve the built single-page frontend (copied into ``static/`` at build time)."""

from __future__ import annotations

from pathlib import Path
from typing import Final

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

STATIC_DIR: Final = Path(__file__).parent / "static"


def mount_frontend(app: FastAPI, static_dir: Path = STATIC_DIR) -> bool:
    """Serve the SPA if it has been built; return False when there is nothing to serve."""
    index = static_dir / "index.html"
    if not index.is_file():
        return False

    assets = static_dir / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    root = static_dir.resolve()

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:  # pyright: ignore[reportUnusedFunction]
        if path.startswith("api/"):
            raise HTTPException(status.HTTP_404_NOT_FOUND)
        candidate = (root / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(root):
            return FileResponse(candidate)
        return FileResponse(index)  # client-side routing

    return True
