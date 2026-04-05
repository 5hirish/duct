"""FastAPI server: Google Ads report generation for the Next.js app."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import service.google.ads  # noqa: F401 — registers connectors before routes import

from config import get_configs
from routes.namespace import router as api_router

app = FastAPI(title="Duct API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[get_configs().frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
