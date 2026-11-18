import asyncio
import re
import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

import app.db.models  # noqa: F401  (registers all models on Base.metadata)
from app.api import (
    routes_analytics,
    routes_health,
    routes_process,
    routes_reports,
    routes_tickets,
)
from app.core.logging import get_logger, request_id_ctx, setup_logging
from app.core.settings import settings
from app.db.base import Base
from app.db.seed import ensure_tables_exist, run_seed
from app.db.session import engine
from app.services.gemini_service import get_gemini_service
from app.services.jev_service import get_jev_service
from app.services.rag_service import get_rag_service

logger = get_logger(__name__)

APP_VERSION = "0.1.0"
REQUEST_ID_HEADER = "X-Request-ID"
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._\-]{8,64}$")

ALLOWED_REQUEST_HEADERS = ["Content-Type", "X-User-Email", REQUEST_ID_HEADER]
EXPOSED_RESPONSE_HEADERS = ["Content-Disposition", REQUEST_ID_HEADER]


def _prepare_database() -> None:
    """Verifies the schema exists, then seeds routing rules and default users.

    Alembic is the supported way to create the schema. For a local SQLite file only, missing tables are
    created directly so the prototype starts with zero setup; PostgreSQL always requires migrations.
    """
    try:
        ensure_tables_exist()
    except RuntimeError:
        if not settings.DATABASE_URL.startswith("sqlite"):
            raise
        logger.warning(
            "Tables are missing; creating them directly because the database is SQLite. "
            "Run 'alembic upgrade head' on a fresh database instead for versioned migrations."
        )
        Base.metadata.create_all(engine)
    result = run_seed()
    logger.info("Database ready", extra=result)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Prepares the database and knowledge base on startup and releases pooled clients on shutdown."""
    setup_logging()
    await asyncio.to_thread(_prepare_database)
    rag_ready = await get_rag_service().initialize()
    await get_jev_service().warmup()
    logger.info(
        "Application started",
        extra={
            "environment": settings.ENVIRONMENT,
            "jev_engine_mode": "live" if get_jev_service().is_live else "simulated",
            "gemini_engine_mode": "live" if get_gemini_service().is_live else "simulated",
            "rag_enabled": rag_ready,
        },
    )
    try:
        yield
    finally:
        await get_jev_service().aclose()
        logger.info("Application stopped")


class RequestIDMiddleware:
    """Pure-ASGI middleware that assigns a request ID, exposes it to logging and echoes it in the response."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    @staticmethod
    def _resolve_request_id(scope: Scope) -> str:
        for name, value in scope.get("headers", []):
            if name == b"x-request-id":
                candidate = value.decode("latin-1")
                if _SAFE_REQUEST_ID.match(candidate):
                    return candidate
                break
        return uuid.uuid4().hex

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = self._resolve_request_id(scope)
        scope.setdefault("state", {})["request_id"] = request_id
        token = request_id_ctx.set(request_id)

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            request_id_ctx.reset(token)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Returns a generic 500 without leaking internals, and keeps the response readable by the dashboard."""
    request_id = request.scope.get("state", {}).get("request_id") or uuid.uuid4().hex
    token = request_id_ctx.set(request_id)
    try:
        logger.error(
            "Unhandled exception",
            exc_info=(type(exc), exc, exc.__traceback__),
            extra={"path": request.url.path, "method": request.method},
        )
    finally:
        request_id_ctx.reset(token)

    headers = {REQUEST_ID_HEADER: request_id}
    origin = request.headers.get("origin")
    if origin and origin in settings.CORS_ORIGINS:
        # Responses produced by the server-error layer bypass CORSMiddleware, so add the headers here.
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Expose-Headers"] = ", ".join(EXPOSED_RESPONSE_HEADERS)
        headers["Vary"] = "Origin"
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "request_id": request_id},
        headers=headers,
    )


def create_app() -> FastAPI:
    """Application factory: builds the FastAPI app with middleware, handlers and routers."""
    application = FastAPI(
        title="IT Support Ticket AI Routing & Resolution Engine",
        version=APP_VERSION,
        description=(
            "JEV classifies and routes support tickets in under 500 ms; tickets that need human action "
            "bypass Gemini, all others receive a Gemini-drafted step-by-step resolution."
        ),
        lifespan=lifespan,
        docs_url="/docs" if settings.DEBUG else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.DEBUG else None,
    )

    application.add_middleware(RequestIDMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=ALLOWED_REQUEST_HEADERS,
        expose_headers=EXPOSED_RESPONSE_HEADERS,
        max_age=600,
    )
    application.add_exception_handler(Exception, unhandled_exception_handler)

    application.include_router(routes_process.router)
    application.include_router(routes_tickets.router)
    application.include_router(routes_analytics.router)
    application.include_router(routes_reports.router)
    application.include_router(routes_health.router)
    return application


app = create_app()


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.BACKEND_HOST,
        port=settings.BACKEND_PORT,
        reload=settings.DEBUG,
    )
