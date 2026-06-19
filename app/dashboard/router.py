"""
Dashboard mounting.

Serves the single-page operations console and its static assets directly from
the FastAPI app — no separate web server, no build step. The page is plain
HTML/CSS/JS and talks to the same ``/v1`` API as any other client.
"""
from __future__ import annotations

import os

from fastapi import APIRouter, FastAPI
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
_INDEX = os.path.join(_STATIC_DIR, "index.html")

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard", include_in_schema=False)
@router.get("/dashboard/", include_in_schema=False)
async def dashboard_index() -> FileResponse:
    return FileResponse(_INDEX)


def mount_dashboard(app: FastAPI) -> None:
    """Attach the static asset mount and the dashboard route to the app."""
    app.mount(
        "/dashboard/static",
        StaticFiles(directory=_STATIC_DIR),
        name="dashboard-static",
    )
    app.include_router(router)
