"""FastAPI server: Google Ads report generation for the Next.js app."""

from __future__ import annotations

import logging
from urllib.parse import urlparse

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import sentry_sdk

import service.google.ads  # noqa: F401 — registers connectors before routes import
import service.google.ga4  # noqa: F401 — registers connectors before routes import
import service.google.gsc  # noqa: F401 — registers connectors before routes import

from config import get_configs
from db.session import init_db
import models  # noqa: F401 - registers SQLModel metadata
from routes.namespace import router as api_router
from utils.openapi_docs_auth import OpenapiDocsBasicAuthMiddleware

_cfg = get_configs()

def _is_localhost_url(url: str) -> bool:
    hostname = urlparse(url).hostname
    return hostname in {"localhost", "127.0.0.1", "::1"}


if _cfg.sentry_dsn and not _is_localhost_url(_cfg.api_public_url):
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

_openapi = "/openapi.json" if _cfg.expose_openapi_docs else None
app = FastAPI(
    title="Duct API",
    openapi_url=_openapi,
    docs_url="/docs" if _cfg.expose_openapi_docs else None,
    redoc_url="/redoc" if _cfg.expose_openapi_docs else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[get_configs().frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(OpenapiDocsBasicAuthMiddleware)


@app.on_event("startup")
def _startup_init_db() -> None:
    if _cfg.init_db_on_startup:
        init_db()


app.include_router(api_router)
