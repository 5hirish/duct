"""Integration tests for /api/content/* routes.

Scope: registration + auth gating + idempotent session lifecycle.
DB-touching CRUD paths are exercised end-to-end against a real Postgres
in tests/test_content_e2e.py — those catch real bugs (JSONB shape,
foreign key cascades, etc.) that SQLite stand-ins cannot.

Anti-scope (intentionally NOT tested here):
  - Pydantic body validation — Pydantic tests itself.
  - Per-endpoint auth gating one-test-per-endpoint — parameterised below.
"""

from __future__ import annotations

import importlib
import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from tests.conftest import api_routes

TEST_DUCT_API_KEY = "test-duct-api-key"


def _load_server_with_env():
    os.environ["GOOGLE_OAUTH_CLIENT_ID"]     = "test-client-id"
    os.environ["GOOGLE_OAUTH_CLIENT_SECRET"] = "test-client-secret"
    os.environ["GOOGLE_OAUTH_REDIRECT_URI"]  = "http://localhost:8002/auth/connectors/google_ads/oauth/callback"
    os.environ["FRONTEND_ORIGIN"]            = "http://localhost:3003"
    os.environ["GOOGLE_ADS_DEVELOPER_TOKEN"] = "test-dev-token"
    os.environ["DUCT_API_KEY"]               = TEST_DUCT_API_KEY
    os.environ.pop("DATABASE_URL", None)
    os.environ.pop("GEMINI_API_KEY", None)

    import config
    config.get_configs.cache_clear()
    import server
    return importlib.reload(server)


# ---------------------------------------------------------------------------
# Route registration — single test covering every endpoint we expose
# ---------------------------------------------------------------------------


def test_content_routes_registered():
    """If any of these vanish, a frontend page breaks. One regression test
    covers all 24 endpoints."""
    server = _load_server_with_env()
    paths = {r.path for r in api_routes(server.app) if r.path.startswith("/api/content")}
    expected = {
        # SSE
        "/api/content/plan/stream",
        "/api/content/post/stream",
        "/api/content/answer/{session_id}",
        "/api/content/chat/{session_id}",
        "/api/content/session/{session_id}",
        # Brand
        "/api/content/brand",
        # Plans
        "/api/content/plans",
        "/api/content/plans/{plan_id}",
        "/api/content/plans/{plan_id}/days/{index}",
        # Posts
        "/api/content/posts",
        "/api/content/posts/{post_id}",
        "/api/content/posts/{post_id}/mark-posted",
        "/api/content/posts/{post_id}/log-metrics",
        # Libraries
        "/api/content/formats",
        "/api/content/formats/{format_id}",
        "/api/content/avatars",
        "/api/content/avatars/{avatar_id}",
        # Uploads + assets
        "/api/content/uploads",
        "/api/content/assets",
        "/api/content/assets/{asset_id}",
        # PostBridge
        "/api/content/social-accounts",
        "/api/content/posts/{post_id}/publish",
        "/api/content/posts/{post_id}/sync-metrics",
        "/api/content/posts/{post_id}/sync-daily",
    }
    missing = expected - paths
    assert not missing, f"Missing routes: {missing}"


# ---------------------------------------------------------------------------
# Auth gating — one parameterised test, not 12
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        # SSE + session lifecycle
        ("GET",    "/api/content/brand?project_id={uuid}",                   None),
        ("GET",    "/api/content/plans?project_id={uuid}",                   None),
        ("GET",    "/api/content/posts?project_id={uuid}",                   None),
        ("GET",    "/api/content/assets?project_id={uuid}",                  None),
        ("GET",    "/api/content/social-accounts?project_id={uuid}",         None),
        ("DELETE", "/api/content/session/{uuid}",                            None),
        ("DELETE", "/api/content/assets/{uuid}",                             None),
        # Mutating endpoints
        ("POST",   "/api/content/posts/{uuid}/publish",                      {"social_account_ids": [101]}),
        ("POST",   "/api/content/posts/{uuid}/sync-metrics",                 None),
        ("POST",   "/api/content/posts/{uuid}/sync-daily",                   None),
    ],
)
def test_endpoints_require_api_key(method, path, body):
    """Every content endpoint must reject calls without X-API-Key. If a
    new endpoint is added and forgets the dependency, add it here."""
    server = _load_server_with_env()
    client = TestClient(server.app)
    url = path.format(uuid=uuid4())
    res = client.request(method, url, json=body) if body is not None else client.request(method, url)
    assert res.status_code == 403, f"{method} {url} returned {res.status_code} without auth"


# ---------------------------------------------------------------------------
# Idempotent session lifecycle — protects against zombie sessions
# ---------------------------------------------------------------------------


def test_session_lifecycle_is_idempotent_and_404s_for_unknown_ids():
    """DELETE must be idempotent (calling close on a session twice or on
    a session that never existed should NOT error). Answer / chat
    against an unknown session must 404 — silent acceptance would leak
    "is this session alive?" timing info.

    The signed-in caller is stubbed rather than signed in: these endpoints now
    require one, but whose it is only matters for a session that exists, and
    who may touch one is tested in tests/test_content_access.py. The DB is
    stubbed for the same reason — nothing here reaches it.
    """
    from db.session import get_session as get_session_dep
    from models.auth import User
    import service.auth as auth_service

    server = _load_server_with_env()
    server.app.dependency_overrides[auth_service.get_current_user] = (
        lambda: User(email="lifecycle@example.com")
    )
    server.app.dependency_overrides[get_session_dep] = lambda: None
    client = TestClient(server.app)
    h = {"X-API-Key": TEST_DUCT_API_KEY}
    unknown = uuid4()

    res = client.delete(f"/api/content/session/{unknown}", headers=h)
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}

    res = client.post(f"/api/content/answer/{unknown}", headers=h, json={"answers": {}})
    assert res.status_code == 404

    res = client.post(f"/api/content/chat/{unknown}", headers=h, json={"content": "x"})
    assert res.status_code == 404

    server.app.dependency_overrides.clear()
