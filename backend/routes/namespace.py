"""Assemble all API routers for the FastAPI app."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from routes import (
    activity, agents, artifacts, audit, auth, chat, connectors, content, engines, execution,
    generate, health, lead_magnet, project_members, projects, reports, signin, user_connectors,
    user_contexts, user_projects,
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
    engines.router,
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
router.include_router(
    content.router,
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
router.include_router(execution.router, prefix="/api/execute")
router.include_router(artifacts.router, prefix="/api/user/artifacts")
router.include_router(activity.router, prefix="/api/user/activity")
router.include_router(user_projects.router, prefix="/api/user/projects")
router.include_router(user_contexts.router, prefix="/api/user/projects")
router.include_router(project_members.router, prefix="/api/user/projects")
router.include_router(user_connectors.router, prefix="/api/user/connectors")
# Invitation redemption. GET is unauthenticated (the recipient has not signed in
# yet and the token is the secret); POST /accept requires a Bearer JWT.
router.include_router(
    project_members.invitation_router,
    prefix="/api/invitations",
    dependencies=[Depends(validate_api_key)],
)
