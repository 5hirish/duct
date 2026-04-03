import importlib
import os
import sys
from pathlib import Path

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_server_with_env():
    os.environ["GOOGLE_OAUTH_CLIENT_ID"] = "test-client-id"
    os.environ["GOOGLE_OAUTH_CLIENT_SECRET"] = "test-client-secret"
    os.environ["GOOGLE_OAUTH_REDIRECT_URI"] = "http://localhost:8000/auth/google/callback"
    os.environ["FRONTEND_ORIGIN"] = "http://localhost:3000"
    os.environ["GOOGLE_ADS_DEVELOPER_TOKEN"] = "test-dev-token"
    os.environ.pop("GEMINI_API_KEY", None)
    import server

    return importlib.reload(server)


def test_health_ok():
    server = _load_server_with_env()
    client = TestClient(server.app)
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_authorize_redirects_to_google():
    server = _load_server_with_env()
    client = TestClient(server.app)
    res = client.get("/auth/google/authorize", follow_redirects=False)
    assert res.status_code == 307
    location = res.headers.get("location", "")
    assert "accounts.google.com" in location


def test_callback_invalid_state_returns_400():
    server = _load_server_with_env()
    client = TestClient(server.app)
    res = client.get("/auth/google/callback", params={"code": "abc", "state": "bad"})
    assert res.status_code == 400
    assert "Invalid or expired OAuth state" in res.text


def test_accounts_missing_refresh_token_returns_422():
    server = _load_server_with_env()
    client = TestClient(server.app)
    res = client.get("/api/google-ads/accounts")
    assert res.status_code == 422
    assert "Missing Google Ads credentials" in res.text


def test_report_demo_payload_shape():
    server = _load_server_with_env()
    client = TestClient(server.app)
    res = client.post("/api/report/google-ads", json={"use_demo": True, "theme": "paid_ads"})
    assert res.status_code == 200
    payload = res.json()
    assert "source_metadata" in payload
    assert "narrative" in payload
    assert "campaigns" in payload
