"""
Shared API dependencies.

Two things every protected route needs: a handle to the wired ``Container`` and
a verified caller. Both are expressed as FastAPI dependencies so handlers can
simply declare them as parameters.

Auth is a simple shared-key scheme (``X-API-Key``) suitable for service-to-
service use and easy to put behind a gateway. It is enforced only when
``require_auth`` is set, so local development and the bundled demo run without
ceremony while production stays locked down.
"""
from __future__ import annotations

from fastapi import Depends, Request

from app.config import Settings
from app.container import Container
from app.errors import AuthError


def get_container(request: Request) -> Container:
    container = getattr(request.app.state, "container", None)
    if container is None:  # pragma: no cover - only if misconfigured
        raise RuntimeError("Application container is not initialised.")
    return container


def get_settings_dep(container: Container = Depends(get_container)) -> Settings:
    return container.settings


def require_api_key(
    request: Request,
    container: Container = Depends(get_container),
) -> str:
    """Validate the API key header. Returns the key (or 'anonymous')."""
    settings = container.settings
    if not settings.require_auth:
        return "anonymous"

    header_name = settings.api_key_header
    provided = request.headers.get(header_name)
    if not provided:
        raise AuthError(f"Missing API key header '{header_name}'.")
    if provided not in settings.api_keys:
        raise AuthError("Invalid API key.")
    return provided
