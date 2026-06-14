"""FastAPI server: Google Ads insight generation for the Next.js app."""

from __future__ import annotations

import asyncio
import logging
import sys
import time
from contextlib import asynccontextmanager
from urllib.parse import urlparse

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import sentry_sdk
from uvicorn.logging import DefaultFormatter

import service.google.ads  # noqa: F401 — registers connectors before routes import
import service.google.ga4  # noqa: F401 — registers connectors before routes import
import service.google.gsc  # noqa: F401 — registers connectors before routes import

from config import get_configs
from db.session import init_db
import models  # noqa: F401 - registers SQLModel metadata
from routes.namespace import router as api_router
from utils.openapi_docs_auth import OpenapiDocsBasicAuthMiddleware

_cfg = get_configs()

# Logging: timestamp every line + per-request HTTP timing, keeping colour.
# Uvicorn's dictConfig leaves the root logger handlerless (app messages would be
# dropped) and its access lines carry neither a timestamp nor a duration. So we
# (1) attach a timestamped handler to the app namespaces, (2) timestamp uvicorn's
# own startup/error lines, and (3) silence uvicorn's access log in favour of
# AccessLogMiddleware below, which records wall-clock duration per request.
# We use uvicorn's DefaultFormatter (not a plain logging.Formatter) so the level
# stays colourised in a TTY (%(levelprefix)s) — what terminal level-highlighting
# keys on — while degrading to plain text when piped (prod / log files).
# The `,%(msecs)` in the default asctime gives millisecond precision for free.
_LOG_FORMAT = "%(asctime)s %(levelprefix)s %(name)s: %(message)s"
_log_formatter = DefaultFormatter(fmt=_LOG_FORMAT, use_colors=sys.stderr.isatty())

_app_handler = logging.StreamHandler()
_app_handler.setFormatter(_log_formatter)
for _ns in ("agents", "routes", "service", "duct.access"):
    _log = logging.getLogger(_ns)
    _log.setLevel(logging.INFO)
    if not _log.handlers:
        _log.addHandler(_app_handler)
    _log.propagate = False

# Timestamp uvicorn's own startup/error lines; drop its access log (superseded).
for _uv in ("uvicorn", "uvicorn.error"):
    for _h in logging.getLogger(_uv).handlers:
        _h.setFormatter(_log_formatter)
_uv_access = logging.getLogger("uvicorn.access")
_uv_access.handlers = []
_uv_access.propagate = False

_access_logger = logging.getLogger("duct.access")


class AccessLogMiddleware:
    """Pure-ASGI access log with per-request wall-clock duration.

    Replaces uvicorn's access log. Implemented at the ASGI layer (not
    BaseHTTPMiddleware) so it never buffers the response body — safe for the SSE
    streaming endpoints, where the line is emitted when the stream closes and the
    duration then reflects the full session lifetime.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        start = time.perf_counter()
        status = {"code": 0}

        async def _send(message):
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, _send)
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            client = scope.get("client")
            client_str = f"{client[0]}:{client[1]}" if client else "-"
            path = scope.get("path", "-")
            qs = scope.get("query_string", b"")
            if qs:
                path = f"{path}?{qs.decode('latin-1')}"
            _access_logger.info(
                "%s %s %s -> %d (%.1fms)",
                client_str,
                scope.get("method", "-"),
                path,
                status["code"],
                elapsed_ms,
            )


def _is_localhost_url(url: str) -> bool:
    hostname = urlparse(url).hostname
    return hostname in {"localhost", "127.0.0.1", "::1"}


if _cfg.sentry_dsn and (
    _cfg.sentry_enable_localhost or not _is_localhost_url(_cfg.api_public_url)
):
    sentry_sdk.init(
        dsn=_cfg.sentry_dsn,
        environment=_cfg.app_env,
        send_default_pii=_cfg.sentry_send_default_pii,
        enable_logs=_cfg.sentry_enable_logs,
        traces_sample_rate=_cfg.sentry_traces_sample_rate,
        profile_session_sample_rate=_cfg.sentry_profile_session_sample_rate,
        profile_lifecycle=_cfg.sentry_profile_lifecycle,
    )
    logging.getLogger(__name__).info("Sentry SDK initialized for backend.")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Single startup/shutdown owner for the app.

    Replaces the deprecated `@app.on_event("startup")` and the per-router
    `@router.on_event("startup")` pruner hooks. Per the FastAPI docs, providing
    a `lifespan` disables ALL `on_event` handlers — including the ones merged in
    from included routers — so every startup action must live here.
    """
    # Optional dev convenience: create tables from SQLModel metadata.
    if _cfg.init_db_on_startup:
        init_db()

    # Background session-pruner loops: the shared agent registry plus the two
    # legacy per-route session maps. Each runs forever; cancel on shutdown.
    # Imported here (not at module top) to keep startup wiring beside the tasks.
    from routes.agents import _prune_stale_sessions as _prune_agent_sessions
    from routes.audit import _prune_stale_sessions as _prune_audit_sessions
    from routes.content import _prune_stale_sessions as _prune_content_sessions

    pruners = [
        asyncio.create_task(_prune_agent_sessions(), name="prune-agent-sessions"),
        asyncio.create_task(_prune_audit_sessions(), name="prune-audit-sessions"),
        asyncio.create_task(_prune_content_sessions(), name="prune-content-sessions"),
    ]
    try:
        yield
    finally:
        for task in pruners:
            task.cancel()
        await asyncio.gather(*pruners, return_exceptions=True)


_openapi = "/openapi.json" if _cfg.expose_openapi_docs else None
app = FastAPI(
    title="Duct API",
    openapi_url=_openapi,
    docs_url="/docs" if _cfg.expose_openapi_docs else None,
    redoc_url="/redoc" if _cfg.expose_openapi_docs else None,
    lifespan=lifespan,
)

_cfg_cors = get_configs()
_cors_origins = [o for o in [_cfg_cors.frontend_origin, _cfg_cors.site_origin] if o]

# In local dev allow any localhost port (static site, app, storybook, etc.)
_cors_kwargs: dict = dict(
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
if _cfg_cors.app_env == "local":
    _cors_kwargs["allow_origin_regex"] = r"http://(localhost|127\.0\.0\.1)(:\d+)?"
else:
    _cors_kwargs["allow_origins"] = _cors_origins

app.add_middleware(CORSMiddleware, **_cors_kwargs)
app.add_middleware(OpenapiDocsBasicAuthMiddleware)
# Added last → outermost, so the timing spans CORS + auth + handler.
app.add_middleware(AccessLogMiddleware)


# Mount the uploads directory as a static-file route when enabled. In
# production this points at a Railway Volume; in dev it's a local path.
if _cfg.uploads_enabled:
    import os

    from fastapi.staticfiles import StaticFiles

    uploads_dir = _cfg.uploads_dir or "/app/uploads"
    os.makedirs(uploads_dir, exist_ok=True)
    app.mount("/uploads", StaticFiles(directory=uploads_dir), name="uploads")


# Mount the global content reference library if it exists. These are
# repo-bundled curated images (`backend/data/content/references/`) the
# Gemini agent picks from when generating slides — see
# `service/content_references.py` and the README at the disk root.
# Always-on when the directory exists: no config gate (cheap, read-only).
try:
    from fastapi.staticfiles import StaticFiles
    from service.content_references import (
        PUBLIC_URL_PREFIX as _REFS_URL_PREFIX,
        global_references_dir as _refs_dir,
    )

    _refs_path = _refs_dir()
    if _refs_path.is_dir():
        app.mount(
            _REFS_URL_PREFIX,
            StaticFiles(directory=str(_refs_path)),
            name="content-references",
        )
except Exception as exc:  # noqa: BLE001 — never let static-mount fail boot
    logging.getLogger(__name__).warning(
        "content references not mounted: %s", exc,
    )


app.include_router(api_router)
