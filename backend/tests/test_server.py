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


def test_connector_callback_invalid_state_returns_400():
    server = _load_server_with_env()
    client = TestClient(server.app)
    res = client.get(
        "/auth/connectors/google_ads/oauth/callback",
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
    assert "Missing Google Ads credentials" in (detail if isinstance(detail, str) else str(detail))


def test_unknown_connector_accounts_returns_404():
    server = _load_server_with_env()
    client = TestClient(server.app)
    headers = {"X-API-Key": TEST_DUCT_API_KEY}
    res = client.get("/api/connectors/unknown_source/accounts", headers=headers)
    assert res.status_code == 404
    assert res.json().get("detail") == "Unknown connector"


def test_report_demo_payload_shape():
    server = _load_server_with_env()
    client = TestClient(server.app)
    headers = {"X-API-Key": TEST_DUCT_API_KEY}
    res = client.post(
        "/api/report/google_ads",
        json={"use_demo": True, "theme": "paid_ads"},
        headers=headers,
    )
    assert res.status_code == 200
    payload = res.json()
    assert "source_metadata" in payload
    assert "narrative" in payload
    assert "campaigns" in payload


def test_report_unknown_connector_returns_404():
    server = _load_server_with_env()
    client = TestClient(server.app)
    headers = {"X-API-Key": TEST_DUCT_API_KEY}
    res = client.post(
        "/api/report/unknown_source",
        json={"use_demo": True},
        headers=headers,
    )
    assert res.status_code == 404
    assert res.json().get("detail") == "Unknown connector"
