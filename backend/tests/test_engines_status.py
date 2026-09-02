"""Tests for GET /api/engines/status — the engine-picker availability endpoint.

Verifies the three-state model (active / needs_auth / inactive) and that v3
(Claude Agent SDK) flips to active via either an ANTHROPIC_API_KEY or a
CLAUDE_CODE_OAUTH_TOKEN, while v1 (Gemini) depends on the Gemini key.
"""

from __future__ import annotations

import importlib
import os

from fastapi.testclient import TestClient

TEST_DUCT_API_KEY = "test-duct-api-key"


def _client_with_env(**overrides: str) -> TestClient:
    """Reload config + server with a controlled credential environment.

    Clears every LLM credential by default; pass overrides to set specific ones.
    Credentials are set to "" (not unset) so they override any value coming from
    backend/.env / .env.local, which pydantic-settings loads unconditionally.
    app_env is forced non-local so the local ~/.claude OAuth fallback is off and
    only the explicit credentials under test influence the result.
    """
    creds = {
        "GEMINI_API_KEY": "",
        "OPENAI_API_KEY": "",
        "ANTHROPIC_API_KEY": "",
        "CLAUDE_CODE_OAUTH_TOKEN": "",
    }
    creds.update(overrides)
    os.environ.update(creds)

    for var in ("GENERATE_PROVIDER", "GENERATE_MODEL"):
        os.environ.pop(var, None)

    os.environ["DUCT_API_KEY"] = TEST_DUCT_API_KEY
    os.environ["APP_ENV"] = "production"
    os.environ.pop("DATABASE_URL", None)

    import config

    config.get_configs.cache_clear()
    import server

    server = importlib.reload(server)
    return TestClient(server.app)


def _status_map(client: TestClient) -> dict[str, dict]:
    res = client.get("/api/engines/status", headers={"X-API-Key": TEST_DUCT_API_KEY})
    assert res.status_code == 200, res.text
    return {e["key"]: e for e in res.json()["engines"]}


def test_requires_api_key():
    client = _client_with_env()
    res = client.get("/api/engines/status")
    assert res.status_code in (401, 403)


def test_no_credentials():
    engines = _status_map(_client_with_env())
    # v1 has no OAuth fallback → inactive without a Gemini key
    assert engines["v1"]["status"] == "inactive"
    # v3 supports OAuth → recoverable, with guidance
    assert engines["v3"]["status"] == "needs_auth"
    assert engines["v3"]["supports_oauth"] is True
    assert engines["v3"]["detail"]


def test_gemini_key_activates_v1():
    engines = _status_map(_client_with_env(GEMINI_API_KEY="g-key"))
    assert engines["v1"]["status"] == "active"
    assert engines["v1"]["auth_method"] == "api_key"
    assert engines["v3"]["status"] == "needs_auth"


def test_the_removed_adk_engine_is_not_advertised():
    """The status endpoint is what the UI builds its engine picker from.

    v2 was removed because nothing dispatched its runner while the UI still
    offered it — a user could pick "Google ADK" and be served v1. Re-adding an
    engine here without a runner behind it would recreate exactly that.
    """
    assert "v2" not in _status_map(_client_with_env(GEMINI_API_KEY="g-key"))


def test_anthropic_key_activates_v3_via_api_key():
    engines = _status_map(_client_with_env(ANTHROPIC_API_KEY="a-key"))
    assert engines["v3"]["status"] == "active"
    assert engines["v3"]["auth_method"] == "api_key"


def test_oauth_token_activates_v3():
    engines = _status_map(_client_with_env(CLAUDE_CODE_OAUTH_TOKEN="oauth-token"))
    assert engines["v3"]["status"] == "active"
    assert engines["v3"]["auth_method"] == "oauth"
