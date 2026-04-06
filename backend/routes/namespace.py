"""Assemble all API routers for the FastAPI app."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from routes import auth, connectors, generate, health, signin
from service.auth import validate_api_key

router = APIRouter()

router.include_router(health.router)
router.include_router(auth.router)
router.include_router(signin.router)
router.include_router(
    connectors.router,
    prefix="/api/connectors",
    dependencies=[Depends(validate_api_key)],
)
router.include_router(
    generate.router,
    prefix="/api",
    dependencies=[Depends(validate_api_key)],
)
