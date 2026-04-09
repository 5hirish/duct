import importlib
import os
import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


TEST_DUCT_API_KEY = "test-duct-api-key"


def _load_server_with_env():
    os.environ["GOOGLE_OAUTH_CLIENT_ID"] = "test-client-id"
    os.environ["GOOGLE_OAUTH_CLIENT_SECRET"] = "test-client-secret"
    os.environ["GOOGLE_OAUTH_REDIRECT_URI"] = (
        "http://localhost:8000/auth/connectors/google_ads/oauth/callback"
    )
    os.environ["FRONTEND_ORIGIN"] = "http://localhost:3000"
    os.environ["GOOGLE_ADS_DEVELOPER_TOKEN"] = "test-dev-token"
    os.environ["DUCT_API_KEY"] = TEST_DUCT_API_KEY
    os.environ.pop("GEMINI_API_KEY", None)
    import config

    config.get_configs.cache_clear()
    import server

    return importlib.reload(server)


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
    os.environ["EXPOSE_OPENAPI_DOCS"] = "true"
    try:
        server = _load_server_with_env()
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
    finally:
        os.environ.pop("EXPOSE_OPENAPI_DOCS", None)


def test_duct_prefixed_openapi_basic_auth_env_names():
    import config

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
    os.environ["EXPOSE_OPENAPI_DOCS"] = "true"
    os.environ["OPENAPI_DOCS_BASIC_PASSWORD"] = "secret-docs-pass"
    try:
        server = _load_server_with_env()
        client = TestClient(server.app)
        assert client.get("/docs").status_code == 401
        assert client.get("/openapi.json").status_code == 401
        ok = client.get("/docs", auth=("docs", "secret-docs-pass"))
        assert ok.status_code == 200
        assert (
            client.get("/openapi.json", auth=("docs", "secret-docs-pass")).status_code
            == 200
        )
    finally:
        os.environ.pop("EXPOSE_OPENAPI_DOCS", None)
        os.environ.pop("OPENAPI_DOCS_BASIC_PASSWORD", None)


def test_connector_oauth_authorize_redirects_to_google():
    server = _load_server_with_env()
    client = TestClient(server.app)
    res = client.get(
        "/auth/connectors/google_ads/oauth/authorize",
        follow_redirects=False,
    )
    assert res.status_code == 307
    location = res.headers.get("location", "")
    assert "accounts.google.com" in location


def test_ga4_connector_oauth_authorize_redirects_to_google():
    server = _load_server_with_env()
    client = TestClient(server.app)
    res = client.get(
        "/auth/connectors/ga4/oauth/authorize",
        follow_redirects=False,
    )
    assert res.status_code == 307
    location = res.headers.get("location", "")
    assert "accounts.google.com" in location


def test_gsc_connector_oauth_authorize_redirects_to_google():
    server = _load_server_with_env()
    client = TestClient(server.app)
    res = client.get(
        "/auth/connectors/gsc/oauth/authorize",
        follow_redirects=False,
    )
    assert res.status_code == 307
    location = res.headers.get("location", "")
    assert "accounts.google.com" in location


def test_connector_callback_invalid_state_returns_400():
    server = _load_server_with_env()
    client = TestClient(server.app)
    res = client.get(
        "/auth/connectors/google_ads/oauth/callback",
        params={"code": "abc", "state": "bad"},
    )
    assert res.status_code == 400
    assert "Invalid or expired OAuth state" in res.text


def test_ga4_connector_callback_invalid_state_returns_400():
    server = _load_server_with_env()
    client = TestClient(server.app)
    res = client.get(
        "/auth/connectors/ga4/oauth/callback",
        params={"code": "abc", "state": "bad"},
    )
    assert res.status_code == 400
    assert "Invalid or expired OAuth state" in res.text


def test_gsc_connector_callback_invalid_state_returns_400():
    server = _load_server_with_env()
    client = TestClient(server.app)
    res = client.get(
        "/auth/connectors/gsc/oauth/callback",
        params={"code": "abc", "state": "bad"},
    )
    assert res.status_code == 400
    assert "Invalid or expired OAuth state" in res.text


def test_google_short_callback_path_invalid_state_returns_400():
    server = _load_server_with_env()
    client = TestClient(server.app)
    res = client.get(
        "/auth/google/callback",
        params={"code": "abc", "state": "bad"},
    )
    assert res.status_code == 400
    assert "Invalid or expired OAuth state" in res.text


def test_unknown_connector_oauth_authorize_returns_404():
    server = _load_server_with_env()
    client = TestClient(server.app)
    res = client.get("/auth/connectors/unknown/oauth/authorize", follow_redirects=False)
    assert res.status_code == 404
    assert res.json().get("detail") == "Unknown connector"


def test_ga4_and_gsc_connectors_registered():
    from service.connectors import get_connector

    _load_server_with_env()
    ga4_meta, _ = get_connector("ga4")
    gsc_meta, _ = get_connector("gsc")
    assert ga4_meta.id == "ga4"
    assert gsc_meta.id == "gsc"


def test_accounts_missing_api_key_returns_403():
    server = _load_server_with_env()
    client = TestClient(server.app)
    res = client.get("/api/connectors/google_ads/accounts")
    assert res.status_code == 403
    assert "API key is required" in res.json().get("detail", "")


def test_accounts_missing_refresh_token_returns_422():
    server = _load_server_with_env()
    client = TestClient(server.app)
    headers = {"X-API-Key": TEST_DUCT_API_KEY}
    res = client.get("/api/connectors/google_ads/accounts", headers=headers)
    assert res.status_code == 422
    detail = res.json().get("detail", "")
    assert "refresh_token" in (detail if isinstance(detail, str) else str(detail)).lower()


def test_unknown_connector_accounts_returns_404():
    server = _load_server_with_env()
    client = TestClient(server.app)
    headers = {"X-API-Key": TEST_DUCT_API_KEY}
    res = client.get("/api/connectors/unknown_source/accounts", headers=headers)
    assert res.status_code == 404
    assert res.json().get("detail") == "Unknown connector"
