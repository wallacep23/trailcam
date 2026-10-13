"""FastAPI app factory. The API never runs models; it reads/writes the DB and enqueues jobs."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute

from trailcam.api.routers import health, jobs, properties
from trailcam.config import Settings, get_settings
from trailcam.log import bind_context, configure_logging

log = logging.getLogger("trailcam.api")

OPENAPI_TITLE = "Trail Camera Analyzer API"


def _operation_id(route: APIRoute) -> str:
    """Stable, readable operationIds (``jobs_list_jobs``) for the generated client."""
    tag = route.tags[0] if route.tags else "default"
    return f"{tag}_{route.name}"


def create_app(settings: Settings | None = None, *, configure_logs: bool = True) -> FastAPI:
    settings = settings or get_settings()
    if configure_logs:
        configure_logging(settings.log_level, settings.log_format)

    app = FastAPI(
        title=OPENAPI_TITLE,
        version="0.1.0",
        openapi_url=f"{settings.api_prefix}/openapi.json",
        docs_url=f"{settings.api_prefix}/docs",
        redoc_url=None,
        generate_unique_id_function=_operation_id,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        started = time.perf_counter()
        with bind_context(request_id=request_id):
            response = await call_next(request)
            response.headers["x-request-id"] = request_id
            log.info(
                "request",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                },
            )
        return response

    for router in (health.router, jobs.router, properties.router):
        app.include_router(router, prefix=settings.api_prefix)
    return app


def app_factory() -> FastAPI:
    """Entry point for ``uvicorn --factory trailcam.api.main:app_factory``."""
    return create_app()
