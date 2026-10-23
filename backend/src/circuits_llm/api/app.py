"""FastAPI application factory."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Final

import httpx
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from pydantic import TypeAdapter

from circuits_llm import __version__
from circuits_llm.settings import Settings
from circuits_llm.simulation import NgspiceSimulator, Simulator, locate_ngspice
from circuits_llm.storage import NotFoundError, Store
from circuits_llm.web import mount_frontend

from . import routes_models, routes_projects, routes_system
from .schemas import StreamEvent
from .services import Services

logger = logging.getLogger(__name__)

_HTTP_TIMEOUT: Final = httpx.Timeout(connect=15.0, read=600.0, write=30.0, pool=30.0)
_HTTP_LIMITS: Final = httpx.Limits(max_connections=20, max_keepalive_connections=10)


def _build_simulator(settings: Settings) -> tuple[Simulator | None, Path | None]:

    path = locate_ngspice(settings.ngspice_path)
    if path is None:
        logger.warning("ngspice not found; simulation is disabled")
        return None, None
    logger.info("using ngspice at %s", path)
    return NgspiceSimulator(path, timeout_s=settings.simulation_timeout_s), path


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        simulator, ngspice_path = _build_simulator(settings)
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT, limits=_HTTP_LIMITS) as http:
            app.state.services = Services(
                settings=settings,
                store=Store(settings.database_path),
                http=http,
                simulator=simulator,
                ngspice_path=ngspice_path,
            )
            yield

    app = FastAPI(title="circuits-llm", version=__version__, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(NotFoundError)
    async def not_found(_: Request, exc: NotFoundError) -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": str(exc)})

    app.include_router(routes_system.router)
    app.include_router(routes_models.router)
    app.include_router(routes_projects.router)
    mount_frontend(app)
    app.openapi = lambda: _openapi_with_stream_events(app)
    return app


def _openapi_with_stream_events(app: FastAPI) -> dict[str, Any]:
    """Add the SSE ``StreamEvent`` union to the schema so clients can generate its types."""
    if app.openapi_schema is not None:
        return app.openapi_schema
    schema = get_openapi(title=app.title, version=app.version, routes=app.routes)
    event_schema = TypeAdapter(StreamEvent).json_schema(ref_template="#/components/schemas/{model}")
    components: dict[str, Any] = schema.setdefault("components", {}).setdefault("schemas", {})
    for name, definition in event_schema.pop("$defs", {}).items():
        components.setdefault(name, definition)
    components["StreamEvent"] = event_schema
    app.openapi_schema = schema
    return schema
