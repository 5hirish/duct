"""FastAPI server: Google Ads report generation for the Next.js app."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import service.google.ads  # noqa: F401 — registers connectors before routes import

from config import get_configs
from db.session import init_db
import models  # noqa: F401 - registers SQLModel metadata
from routes.namespace import router as api_router
from utils.openapi_docs_auth import OpenapiDocsBasicAuthMiddleware

_cfg = get_configs()
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
    init_db()


app.include_router(api_router)
