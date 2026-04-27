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


def test_projects_config_requires_api_key():
    server = _load_server_with_env()
    client = TestClient(server.app)
    res = client.get("/api/projects/config")
    assert res.status_code == 403
    assert "API key is required" in res.json().get("detail", "")


def test_projects_config_returns_all_base_options():
    server = _load_server_with_env()
    client = TestClient(server.app)
    headers = {"X-API-Key": TEST_DUCT_API_KEY}
    res = client.get("/api/projects/config", headers=headers)
    assert res.status_code == 200
    payload = res.json()
    assert len(payload["industry_options"]) == 10
    assert len(payload["business_model_options"]) == 6
    assert len(payload["north_star_metric_options"]) == 8
    assert len(payload["growth_stage_milestone_options"]) == 5


def test_projects_config_filters_for_b2b_in_saas():
    server = _load_server_with_env()
    client = TestClient(server.app)
    headers = {"X-API-Key": TEST_DUCT_API_KEY}
    res = client.get(
        "/api/projects/config",
        headers=headers,
        params={"industry": "SaaS & Software", "business_model": "B2B"},
    )
    assert res.status_code == 200
    payload = res.json()
    north_star_values = [item["value"] for item in payload["north_star_metric_options"]]
    assert "Qualified leads" in north_star_values
    assert "Pipeline created" in north_star_values
    assert "Weekly active users" in north_star_values
    assert "Bookings" not in north_star_values


def test_projects_config_filters_growth_stage_for_agency():
    server = _load_server_with_env()
    client = TestClient(server.app)
    headers = {"X-API-Key": TEST_DUCT_API_KEY}
    res = client.get(
        "/api/projects/config",
        headers=headers,
        params={"industry": "Other", "business_model": "Agency"},
    )
    assert res.status_code == 200
    payload = res.json()
    stage_values = [item["value"] for item in payload["growth_stage_milestone_options"]]
    assert "0_pre_customer" not in stage_values
    assert "1_first_users" in stage_values
    assert "4_scaling" in stage_values
