import importlib
import os

from fastapi.testclient import TestClient

TEST_DUCT_API_KEY = "test-duct-api-key"


def _load_server_with_env():
    os.environ["GOOGLE_OAUTH_CLIENT_ID"] = "test-client-id"
    os.environ["GOOGLE_OAUTH_CLIENT_SECRET"] = "test-client-secret"
    os.environ["GOOGLE_OAUTH_REDIRECT_URI"] = (
        "http://localhost:8002/auth/connectors/google_ads/oauth/callback"
    )
    os.environ["FRONTEND_ORIGIN"] = "http://localhost:3003"
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
    assert len(payload["industry_options"]) == 11
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


def test_web_and_desktop_oauth_clients_are_selected_by_mode(clean_env, tmp_path):
    """The desktop pair is only correct for the sidecar's loopback redirect.

    Google accepts a loopback redirect on an OS-picked port for an
    installed-app client only, so the wrong pair fails at sign-in rather than
    at startup - worth pinning here instead of discovering it in a bundle.
    """
    from config import Configs

    for var in (
        "GOOGLE_WEB_OAUTH_CLIENT_ID", "GOOGLE_WEB_OAUTH_CLIENT_SECRET",
        "GOOGLE_DESKTOP_OAUTH_CLIENT_ID", "GOOGLE_DESKTOP_OAUTH_CLIENT_SECRET",
        "GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET",
    ):
        clean_env.delenv(var, raising=False)
    clean_env.setenv("GOOGLE_WEB_OAUTH_CLIENT_ID", "web-id")
    clean_env.setenv("GOOGLE_WEB_OAUTH_CLIENT_SECRET", "web-secret")
    clean_env.setenv("GOOGLE_DESKTOP_OAUTH_CLIENT_ID", "desktop-id")
    clean_env.setenv("GOOGLE_DESKTOP_OAUTH_CLIENT_SECRET", "desktop-secret")

    hosted = Configs()
    assert hosted.google_oauth_client_id == "web-id"
    assert hosted.google_oauth_client_secret == "web-secret"

    clean_env.setenv("DUCT_LOCAL", "1")
    clean_env.setenv("DUCT_DATA_DIR", str(tmp_path))
    desktop = Configs()
    assert desktop.google_oauth_client_id == "desktop-id"
    assert desktop.google_oauth_client_secret == "desktop-secret"


def test_legacy_unprefixed_oauth_names_still_resolve(clean_env):
    """Railway and any older .env keep working until they are renamed."""
    from config import Configs

    clean_env.delenv("GOOGLE_WEB_OAUTH_CLIENT_ID", raising=False)
    clean_env.delenv("GOOGLE_WEB_OAUTH_CLIENT_SECRET", raising=False)
    clean_env.setenv("GOOGLE_OAUTH_CLIENT_ID", "legacy-id")
    clean_env.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "legacy-secret")

    cfg = Configs()
    assert cfg.google_oauth_client_id == "legacy-id"
    assert cfg.google_oauth_client_secret == "legacy-secret"
