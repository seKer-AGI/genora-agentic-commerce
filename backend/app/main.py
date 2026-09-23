"""FastAPI application factory."""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging, log_event, request_id_ctx, user_id_ctx
from app.db.session import get_engine, session_scope
from app.services.bootstrap import ensure_reference_data

logger = logging.getLogger("app.http")


@asynccontextmanager
async def lifespan(_: FastAPI):
    s = get_settings()
    if s.run_migrations:
        from alembic import command
        from alembic.config import Config

        command.upgrade(Config("alembic.ini"), "head")
    with session_scope() as db:
        ensure_reference_data(db)
    if s.seed_on_start:
        from app.seed.seed import seed

        seed(reset=False)
    log_event(logger, "startup_complete", env=s.app_env)
    yield


def create_app() -> FastAPI:
    s = get_settings()
    configure_logging(s.log_level, s.log_json)
    app = FastAPI(
        title=s.app_name,
        version="1.0.0",
        description="REST API for the GenOra AI-powered multi-vendor marketplace. "
        "Errors follow `{success: false, error: {code, message, details?}}`.",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url=f"{s.api_prefix}/openapi.json",
    )
    register_exception_handlers(app, expose_internal=not s.is_production)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID", "X-Session-Key"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex
        request_id_ctx.set(rid[:64])
        user_id_ctx.set(None)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("request_failed")
            raise
        latency = round((time.perf_counter() - started) * 1000, 1)
        response.headers["X-Request-ID"] = rid[:64]
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if not request.url.path.startswith("/health"):
            log_event(
                logger, "http_request", method=request.method, path=request.url.path,
                status=response.status_code, latency_ms=latency,
            )
        return response

    @app.get("/health/live", tags=["health"])
    def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready", tags=["health"])
    def ready() -> JSONResponse:
        try:
            with get_engine().connect() as conn:
                conn.execute(text("SELECT 1"))
            return JSONResponse({"status": "ok", "database": "ok"})
        except Exception:  # noqa: BLE001 - health endpoint must never raise
            return JSONResponse({"status": "degraded", "database": "unreachable"}, status_code=503)

    app.include_router(api_router, prefix=s.api_prefix)
    return app


app = create_app()
