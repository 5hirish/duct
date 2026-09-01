"""FastAPI server: Google Ads insight generation for the Next.js app."""

from __future__ import annotations

import asyncio
import logging
import sys
import time
from contextlib import AsyncExitStack, asynccontextmanager
from urllib.parse import urlparse

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import sentry_sdk
from uvicorn.logging import DefaultFormatter

import service.apple.ads.fetch  # noqa: F401 — registers connectors before routes import
import service.google.ads  # noqa: F401 — registers connectors before routes import
import service.google.ga4  # noqa: F401 — registers connectors before routes import
import service.google.gsc  # noqa: F401 — registers connectors before routes import
import service.google.gtm  # noqa: F401 — registers connectors before routes import
import service.meta.ads.fetch  # noqa: F401 — registers connectors before routes import
import service.openai.ads.fetch  # noqa: F401 — registers connectors before routes import
import service.revenuecat.fetch  # noqa: F401 — registers connectors before routes import
import service.stripe.fetch  # noqa: F401 — registers connectors before routes import
import service.mixpanel.fetch  # noqa: F401 — registers connectors before routes import
import service.clarity.fetch  # noqa: F401 — registers connectors before routes import
import service.growthbook.fetch  # noqa: F401 — registers connectors before routes import

from config import cors_kwargs, get_configs
from db.migrate import ensure_schema
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
_LOG_FORMAT = "%(asctime)s %(levelprefix)s %(logname)s: %(message)s"

# Uvicorn logs *every* server lifecycle line — startup, shutdown, reload — on a
# logger literally named `uvicorn.error`, so a healthy boot reads like a stack of
# failures. Display those under `uvicorn`; the level field already says whether a
# line is an error. `%(logname)s` above (not `%(name)s`) is what gets rewritten,
# so the record's real logger name stays intact for anything else reading it.
_LOGGER_DISPLAY_NAMES = {"uvicorn.error": "uvicorn"}


class DisplayNameFormatter(DefaultFormatter):
    """DefaultFormatter that renders `_LOGGER_DISPLAY_NAMES` aliases as `logname`."""

    def formatMessage(self, record: logging.LogRecord) -> str:
        record.logname = _LOGGER_DISPLAY_NAMES.get(record.name, record.name)
        return super().formatMessage(record)


_log_formatter = DisplayNameFormatter(fmt=_LOG_FORMAT, use_colors=sys.stderr.isatty())

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


# Secret request headers that must never reach Sentry, even with
# send_default_pii enabled: the per-request bring-your-own provider keys and the
# app gate key. Matched case-insensitively in the before_send hook below.
_SENSITIVE_HEADERS = frozenset({
    "x-api-key",
    "x-provider-anthropic",
    "x-provider-openai",
    "x-provider-gemini",
    "x-provider-openrouter",
    "authorization",
})


def _scrub_sensitive_headers(event: dict, _hint: dict) -> dict:
    """Sentry before_send: redact secret request headers so BYO provider keys and
    the app API key are never captured. Best-effort — never drops the event."""
    try:
        headers = event.get("request", {}).get("headers")
        if isinstance(headers, dict):
            for name in list(headers):
                if name.lower() in _SENSITIVE_HEADERS:
                    headers[name] = "[redacted]"
    except Exception:  # noqa: BLE001 — scrubbing must never break error reporting
        pass
    return event


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
        before_send=_scrub_sensitive_headers,
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
    # Desktop/local mode runs the same Alembic migrations as the deployment,
    # so an upgraded install picks up new columns instead of silently missing
    # them (db/migrate.py explains the three cases). `init_db_on_startup` stays
    # what it always was: the dev bootstrap escape hatch for everywhere else.
    if _cfg.duct_local:
        ensure_schema()
    elif _cfg.init_db_on_startup:
        init_db()

    # Durable conversation state, opened once for the process. Deliberately
    # after the schema work above: LangGraph's `setup()` creates its own tables
    # in this same database, and `db/migrate.py` classifies a fresh install by
    # looking for `users` rather than "any table at all" so the two cannot be
    # confused. The saver holds a connection pool, which is why it is owned by
    # the lifespan and not built per session — see agents/core/checkpoint.py.
    from agents.core.checkpoint import open_checkpointer, set_checkpointer

    checkpoints = AsyncExitStack()
    set_checkpointer(
        await checkpoints.enter_async_context(open_checkpointer(_cfg.database_url))
    )

    # Once per server start, not once per import — see the docstring.
    from service.pipeline import log_stale_catalog_warnings

    log_stale_catalog_warnings()

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
        # Close active agent sessions FIRST: this sentinels each session's SSE
        # event queue so the long-lived stream generators exit, letting uvicorn's
        # graceful shutdown drain connections instead of blocking on them (a
        # --reload or a deploy would otherwise hang until the chat idle-timeout).
        from agents.core.session import close_all_sessions

        close_all_sessions()
        for task in pruners:
            task.cancel()
        await asyncio.gather(*pruners, return_exceptions=True)
        # Last: a still-draining session may write a final checkpoint, so the
        # pool outlives everything that could use it.
        set_checkpointer(None)
        await checkpoints.aclose()


_openapi = "/openapi.json" if _cfg.expose_openapi_docs else None
app = FastAPI(
    title="Duct API",
    openapi_url=_openapi,
    docs_url="/docs" if _cfg.expose_openapi_docs else None,
    redoc_url="/redoc" if _cfg.expose_openapi_docs else None,
    lifespan=lifespan,
)

app.add_middleware(CORSMiddleware, **cors_kwargs(get_configs()))
app.add_middleware(OpenapiDocsBasicAuthMiddleware)
# Added last → outermost, so the timing spans CORS + auth + handler.
app.add_middleware(AccessLogMiddleware)


# Serve /uploads only for the local storage backend (dev). In prod the 'r2'
# backend serves images straight from R2's CDN, so this mount is skipped.
from service import storage as _storage  # noqa: E402

if _storage.storage_backend() == "local":
    import os

    from fastapi.staticfiles import StaticFiles

    os.makedirs(_cfg.uploads_dir, exist_ok=True)
    app.mount("/uploads", StaticFiles(directory=_cfg.uploads_dir), name="uploads")


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
