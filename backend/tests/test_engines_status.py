from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

TEST_DUCT_API_KEY = "test-duct-api-key"


@pytest.fixture
def client_with_env(monkeypatch):
    """A client whose credential environment is exactly what the test sets.

    Credentials are set to "" rather than deleted so they override anything
    pydantic-settings would read from backend/.env / .env.local. `app_env` is
    forced non-local so the ~/.claude OAuth fallback is off and only the
    explicit credentials under test count.

    `monkeypatch` is the point: the previous version wrote `os.environ` by hand
    and never restored it, so every test after this module ran with blank
    provider keys and no DATABASE_URL — an order dependency nothing declared.
    It also reloaded `server` per test, the slowest fixture in the suite; the
    route reads `get_configs()` per request, so clearing that cache is enough.
    """
    import config
    import server

    def make(**overrides: str) -> TestClient:
        creds = {
            "GEMINI_API_KEY": "",
            "OPENAI_API_KEY": "",
            "ANTHROPIC_API_KEY": "",
            "CLAUDE_CODE_OAUTH_TOKEN": "",
            **overrides,
        }
        for var, value in creds.items():
            monkeypatch.setenv(var, value)
        for var in ("GENERATE_PROVIDER", "GENERATE_MODEL", "DATABASE_URL"):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setenv("DUCT_API_KEY", TEST_DUCT_API_KEY)
        monkeypatch.setenv("APP_ENV", "production")
        config.get_configs.cache_clear()
        return TestClient(server.app)

    yield make
    # A config built from the environment above must not outlive the test.
    config.get_configs.cache_clear()


def _status_map(client: TestClient) -> dict[str, dict]:
    res = client.get("/api/engines/status", headers={"X-API-Key": TEST_DUCT_API_KEY})
    assert res.status_code == 200, res.text
    return {e["key"]: e for e in res.json()["engines"]}


def test_requires_api_key(client_with_env):
    client = client_with_env()
    res = client.get("/api/engines/status")
    assert res.status_code in (401, 403)


def test_no_credentials(client_with_env):
    engines = _status_map(client_with_env())
    # No key, no engine: there is no credential path that does not start with one.
    assert engines["v1"]["status"] == "inactive"
    assert engines["v1"]["detail"]


def test_gemini_key_activates_v1(client_with_env):
    engines = _status_map(client_with_env(GEMINI_API_KEY="g-key"))
    assert engines["v1"]["status"] == "active"
    assert engines["v1"]["auth_method"] == "api_key"


def test_the_removed_adk_engine_is_not_advertised(client_with_env):
    """The status endpoint is what the UI builds its engine picker from.

    v2 was removed because nothing dispatched its runner while the UI still
    offered it — a user could pick "Google ADK" and be served v1. v3 went the
    same way once V1 could do everything it did. Re-adding an engine here
    without a runner behind it would recreate exactly that.
    """
    engines = _status_map(client_with_env(GEMINI_API_KEY="g-key"))
    assert "v2" not in engines
    assert "v3" not in engines
    assert set(engines) == {"v1"}


