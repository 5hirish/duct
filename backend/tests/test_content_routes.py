"""Integration tests for /api/content/* routes.

Scope: route registration + auth gating + session lifecycle (no DB writes).
DB-touching paths (brand, plans, posts, formats, avatars) use Postgres
JSONB columns that can't be compiled to SQLite, so end-to-end coverage of
those endpoints lives in Phase 6 e2e tests against a real Postgres.
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


TEST_DUCT_API_KEY = "test-duct-api-key"


def _load_server_with_env():
    os.environ["GOOGLE_OAUTH_CLIENT_ID"]     = "test-client-id"
    os.environ["GOOGLE_OAUTH_CLIENT_SECRET"] = "test-client-secret"
    os.environ["GOOGLE_OAUTH_REDIRECT_URI"]  = "http://localhost:8002/auth/connectors/google_ads/oauth/callback"
    os.environ["FRONTEND_ORIGIN"]            = "http://localhost:3003"
    os.environ["GOOGLE_ADS_DEVELOPER_TOKEN"] = "test-dev-token"
    os.environ["DUCT_API_KEY"]               = TEST_DUCT_API_KEY
    os.environ.pop("DATABASE_URL", None)  # No DB — DB-touching paths are out of scope.
    os.environ.pop("GEMINI_API_KEY", None)

    import config
    config.get_configs.cache_clear()
    import server
    return importlib.reload(server)


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------


def test_content_routes_registered():
    server = _load_server_with_env()
    paths = {r.path for r in server.app.routes if r.path.startswith("/api/content")}
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
        "/api/content/plans/{plan_id}/days/{day}",
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
    }
    missing = expected - paths
    assert not missing, f"Missing routes: {missing}"


# ---------------------------------------------------------------------------
# Auth gating
# ---------------------------------------------------------------------------


def test_content_brand_requires_api_key():
    server = _load_server_with_env()
    client = TestClient(server.app)
    res = client.get(f"/api/content/brand?project_id={uuid4()}")
    assert res.status_code == 403


def test_content_plans_requires_api_key():
    server = _load_server_with_env()
    client = TestClient(server.app)
    res = client.get(f"/api/content/plans?project_id={uuid4()}")
    assert res.status_code == 403


def test_content_posts_requires_api_key():
    server = _load_server_with_env()
    client = TestClient(server.app)
    res = client.get(f"/api/content/posts?project_id={uuid4()}")
    assert res.status_code == 403


def test_content_session_close_requires_api_key():
    server = _load_server_with_env()
    client = TestClient(server.app)
    res = client.delete(f"/api/content/session/{uuid4()}")
    assert res.status_code == 403


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


def test_plan_stream_requires_project_id():
    server = _load_server_with_env()
    client = TestClient(server.app)
    res = client.post(
        "/api/content/plan/stream",
        headers={"X-API-Key": TEST_DUCT_API_KEY},
        json={},  # missing project_id
    )
    assert res.status_code == 422


def test_post_stream_requires_project_id():
    server = _load_server_with_env()
    client = TestClient(server.app)
    res = client.post(
        "/api/content/post/stream",
        headers={"X-API-Key": TEST_DUCT_API_KEY},
        json={},
    )
    assert res.status_code == 422


def test_chat_message_validation():
    """content is required (str | list)."""
    server = _load_server_with_env()
    client = TestClient(server.app)
    res = client.post(
        f"/api/content/chat/{uuid4()}",
        headers={"X-API-Key": TEST_DUCT_API_KEY},
        json={},
    )
    assert res.status_code == 422


# ---------------------------------------------------------------------------
# Session lifecycle (no DB needed)
# ---------------------------------------------------------------------------


def test_close_unknown_session_is_ok():
    """DELETE is idempotent — closing a non-existent session is not an error."""
    server = _load_server_with_env()
    client = TestClient(server.app)
    res = client.delete(
        f"/api/content/session/{uuid4()}",
        headers={"X-API-Key": TEST_DUCT_API_KEY},
    )
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_answer_unknown_session_404():
    server = _load_server_with_env()
    client = TestClient(server.app)
    res = client.post(
        f"/api/content/answer/{uuid4()}",
        headers={"X-API-Key": TEST_DUCT_API_KEY},
        json={"answers": {"q1": "a1"}},
    )
    assert res.status_code == 404


def test_chat_unknown_session_404():
    server = _load_server_with_env()
    client = TestClient(server.app)
    res = client.post(
        f"/api/content/chat/{uuid4()}",
        headers={"X-API-Key": TEST_DUCT_API_KEY},
        json={"content": "hello"},
    )
    assert res.status_code == 404
