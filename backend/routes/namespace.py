"""Assemble all API routers for the FastAPI app."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from routes import (
    activity, agents, artifacts, audit, auth, chat, connectors, content, engines, execution,
    generate, health, lead_magnet, memory, project_connectors, project_members, projects,
    reports, signin, user_connectors, user_contexts, user_projects,
)
from service.auth import get_current_user, validate_api_key

router = APIRouter()

# The two gates, and why most routers need both.
#
# `validate_api_key` checks X-API-Key, which ships to the browser as
# NEXT_PUBLIC_DUCT_API_KEY. It says "this request came from the Duct app" and
# nothing more — anyone who views source has it, so on its own it is not a
# boundary. `get_current_user` is the one that identifies a person.
#
# Every router below that spends model tokens, reaches a vendor API with the
# server's own credentials, or touches a user's data therefore lists both.
# The exceptions are deliberate and marked at their include: health, the OAuth
# entry points (a browser redirect carries no headers), the lead-magnet capture
# (Turnstile-gated by design), and invitation preview (the token is the secret).
APP_AND_USER = [Depends(validate_api_key), Depends(get_current_user)]

router.include_router(health.router)
router.include_router(auth.router)
router.include_router(signin.router)
# Lists a vendor's accounts for a refresh token the caller supplies. Reaching
# Google Ads on someone's behalf is not something an anonymous caller does.
router.include_router(
    connectors.router,
    prefix="/api/connectors",
    dependencies=APP_AND_USER,
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
    dependencies=APP_AND_USER,
)
# Streams from the server's own provider key with a caller-supplied prompt —
# an open LLM proxy without this gate.
router.include_router(
    chat.router,
    prefix="/api/insights",
    dependencies=APP_AND_USER,
)
router.include_router(
    projects.router,
    prefix="/api/projects",
    dependencies=[Depends(validate_api_key)],
)
# The pre-/api/agents audit entry points. No client calls them any more; they
# run a full agent pipeline, so they are signed-in-only until they are removed.
router.include_router(
    audit.router,
    prefix="/api",
    dependencies=APP_AND_USER,
)
router.include_router(
    content.router,
    prefix="/api",
    dependencies=APP_AND_USER,
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
router.include_router(memory.router, prefix="/api/user/projects")
router.include_router(memory.user_router, prefix="/api/user/memory")
router.include_router(project_members.router, prefix="/api/user/projects")
router.include_router(project_connectors.router, prefix="/api/user/projects")
router.include_router(user_connectors.router, prefix="/api/user/connectors")
# Invitation redemption. GET is unauthenticated (the recipient has not signed in
# yet and the token is the secret); POST /accept requires a Bearer JWT.
router.include_router(
    project_members.invitation_router,
    prefix="/api/invitations",
    dependencies=[Depends(validate_api_key)],
)
