import importlib
import os
import uuid

import pytest
from fastapi.testclient import TestClient

TEST_DUCT_API_KEY = "test-duct-api-key"


def _load_server_with_env(*, expose_docs=False, docs_password="", docs_user="docs"):
    os.environ["GOOGLE_OAUTH_CLIENT_ID"] = "test-client-id"
    os.environ["GOOGLE_OAUTH_CLIENT_SECRET"] = "test-client-secret"
    os.environ["GOOGLE_OAUTH_REDIRECT_URI"] = (
        "http://localhost:8002/auth/connectors/google_ads/oauth/callback"
    )
    os.environ["FRONTEND_ORIGIN"] = "http://localhost:3003"
    os.environ["GOOGLE_ADS_DEVELOPER_TOKEN"] = "test-dev-token"
    os.environ["DUCT_API_KEY"] = TEST_DUCT_API_KEY
    os.environ.pop("GEMINI_API_KEY", None)
    # Pin the docs config hermetically. A developer's .env.local may set the
    # docs vars (EXPOSE_OPENAPI_DOCS / DUCT_OPENAPI_DOCS_BASIC_*); setting the
    # canonical aliases in os.environ (env source out-ranks the dotenv file) and
    # dropping the DUCT_ ones keeps these tests deterministic regardless of it.
    os.environ["EXPOSE_OPENAPI_DOCS"] = "true" if expose_docs else "false"
    os.environ["OPENAPI_DOCS_BASIC_USER"] = docs_user
    os.environ["OPENAPI_DOCS_BASIC_PASSWORD"] = docs_password
    os.environ.pop("DUCT_OPENAPI_DOCS_BASIC_USER", None)
    os.environ.pop("DUCT_OPENAPI_DOCS_BASIC_PASSWORD", None)
    import config

    config.get_configs.cache_clear()
    import server

    return importlib.reload(server)


@pytest.fixture(scope="module")
def server_client():
    """One default-env server for the tests that do not vary the environment.

    `_load_server_with_env` calls `importlib.reload(server)`, which is the most
    expensive thing this module does. The tests that *do* vary the env (docs
    exposure, basic auth) still call it directly.
    """
    server = _load_server_with_env()
    return TestClient(server.app)


@pytest.fixture(scope="module")
def signed_in_client():
    """The same server, with a resolved user.

    `/api/connectors/*` takes both gates: the API key says "this is the Duct
    app", the Bearer token says who is asking. Reaching a vendor with somebody's
    refresh token is not something an anonymous caller does, so the tests that
    exercise what happens *after* those gates need to pass them both.
    """
    import service.auth as auth_service

    server = _load_server_with_env()

    class _User:
        id = uuid.uuid4()
        email = "server-test@example.com"

    server.app.dependency_overrides[auth_service.get_current_user] = lambda: _User()
    client = TestClient(server.app)
    yield client
    server.app.dependency_overrides.clear()


def test_health_ok():
    server = _load_server_with_env()
    client = TestClient(server.app)
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_root_ok():
    server = _load_server_with_env()
    client = TestClient(server.app)
    res = client.get("/")
    assert res.status_code == 200
    body = res.json()
    assert body["service"] == "Duct API"
    assert body["version"] == "0.1.0"
    assert body["links"] == {"health": "/health"}
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_root_and_openapi_when_expose_docs_enabled():
    server = _load_server_with_env(expose_docs=True)
    client = TestClient(server.app)
    res = client.get("/")
    assert res.status_code == 200
    assert res.json()["links"] == {
        "health": "/health",
        "openapi": "/openapi.json",
        "docs": "/docs",
    }
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200


def test_duct_prefixed_openapi_basic_auth_env_names():
    import config

    # This asserts the DUCT_-prefixed aliases resolve, so the canonical aliases
    # must be absent (a prior _load_server_with_env may have pinned them).
    os.environ.pop("OPENAPI_DOCS_BASIC_USER", None)
    os.environ.pop("OPENAPI_DOCS_BASIC_PASSWORD", None)
    os.environ["DUCT_OPENAPI_DOCS_BASIC_USER"] = "shirish"
    os.environ["DUCT_OPENAPI_DOCS_BASIC_PASSWORD"] = "duct-secret"
    try:
        config.get_configs.cache_clear()
        cfg = config.Configs()
        assert cfg.openapi_docs_basic_user == "shirish"
        assert cfg.openapi_docs_basic_password == "duct-secret"
    finally:
        os.environ.pop("DUCT_OPENAPI_DOCS_BASIC_USER", None)
        os.environ.pop("DUCT_OPENAPI_DOCS_BASIC_PASSWORD", None)
        config.get_configs.cache_clear()


def test_openapi_docs_require_basic_auth_when_password_set():
    server = _load_server_with_env(expose_docs=True, docs_password="secret-docs-pass")
    client = TestClient(server.app)
    assert client.get("/docs").status_code == 401
    assert client.get("/openapi.json").status_code == 401
    ok = client.get("/docs", auth=("docs", "secret-docs-pass"))
    assert ok.status_code == 200
    assert (
        client.get("/openapi.json", auth=("docs", "secret-docs-pass")).status_code
        == 200
    )


# Every Google connector shares one OAuth implementation, so these are the same
# assertion per registered connector id — a table, not three copies. A connector
# that is missing from the registry fails here with a 404, which is what the old
# `test_ga4_and_gsc_connectors_registered` proved indirectly.
GOOGLE_CONNECTORS = ("google_ads", "ga4", "gsc")


@pytest.mark.parametrize("connector", GOOGLE_CONNECTORS)
def test_connector_oauth_authorize_redirects_to_google(server_client, connector):
    res = server_client.get(
        f"/auth/connectors/{connector}/oauth/authorize",
        follow_redirects=False,
    )
    assert res.status_code == 307
    assert "accounts.google.com" in res.headers.get("location", "")


@pytest.mark.parametrize(
    "path",
    [f"/auth/connectors/{c}/oauth/callback" for c in GOOGLE_CONNECTORS]
    # The short path is a separate route that must reject the same way.
    + ["/auth/google/callback"],
)
def test_callback_rejects_invalid_state(server_client, path):
    res = server_client.get(path, params={"code": "abc", "state": "bad"})
    assert res.status_code == 400
    assert "Invalid or expired OAuth state" in res.text


def test_unknown_connector_oauth_authorize_returns_404(server_client):
    res = server_client.get(
        "/auth/connectors/unknown/oauth/authorize", follow_redirects=False
    )
    assert res.status_code == 404
    assert res.json().get("detail") == "Unknown connector"


def test_accounts_missing_api_key_returns_403(server_client):
    res = server_client.get("/api/connectors/google_ads/accounts")
    assert res.status_code == 403
    assert "API key is required" in res.json().get("detail", "")


def test_accounts_with_only_the_api_key_returns_401(server_client):
    """The key ships in the browser bundle, so it cannot be the whole gate.

    This route lists a vendor's accounts for a refresh token in the request —
    the caller has to be somebody, not just "the Duct app".
    """
    res = server_client.get(
        "/api/connectors/google_ads/accounts", headers={"X-API-Key": TEST_DUCT_API_KEY}
    )
    assert res.status_code == 401


def test_accounts_missing_refresh_token_returns_422(signed_in_client):
    headers = {"X-API-Key": TEST_DUCT_API_KEY}
    res = signed_in_client.get("/api/connectors/google_ads/accounts", headers=headers)
    assert res.status_code == 422
    detail = res.json().get("detail", "")
    assert "refresh_token" in (detail if isinstance(detail, str) else str(detail)).lower()


def test_unknown_connector_accounts_returns_404(signed_in_client):
    headers = {"X-API-Key": TEST_DUCT_API_KEY}
    res = signed_in_client.get("/api/connectors/unknown_source/accounts", headers=headers)
    assert res.status_code == 404
    assert res.json().get("detail") == "Unknown connector"
