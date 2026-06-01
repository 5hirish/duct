"""Assemble all API routers for the FastAPI app."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from routes import (
    agents, audit, auth, chat, connectors, generate, health,
    lead_magnet, projects, reports, signin, user_connectors, user_contexts, user_projects,
)
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
router.include_router(
    reports.router,
    prefix="/api/insights",
    dependencies=[Depends(validate_api_key)],
)
router.include_router(
    chat.router,
    prefix="/api/insights",
    dependencies=[Depends(validate_api_key)],
)
router.include_router(
    projects.router,
    prefix="/api/projects",
    dependencies=[Depends(validate_api_key)],
)
router.include_router(
    audit.router,
    prefix="/api",
    dependencies=[Depends(validate_api_key)],
)
# Unified agent session API — all new agent types go here
router.include_router(
    agents.router,
    prefix="/api/agents",
    dependencies=[Depends(validate_api_key)],
)
# Lead magnet capture — public endpoints; rely on Cloudflare Turnstile, not API key
router.include_router(lead_magnet.router, prefix="/api/lead-magnet")
# User-scoped endpoints — authenticated via Bearer JWT
router.include_router(user_projects.router, prefix="/api/user/projects")
router.include_router(user_contexts.router, prefix="/api/user/projects")
router.include_router(user_connectors.router, prefix="/api/user/connectors")
