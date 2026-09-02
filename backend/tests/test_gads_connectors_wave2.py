"""Unit tests for the Gads wave-2 connectors: Mixpanel, Clarity, GrowthBook.

Each test pins one of the encoded gotchas: Mixpanel's missing internal-traffic
filter + per-day funnel summing + service-account project scoping; Clarity's
non-retried daily budget + metric-list normalisation; GrowthBook's "running is a
setting" staleness flag. Executors run against a fake App API. No network —
transport calls are monkeypatched.
"""

from __future__ import annotations

from datetime import date

import pytest

import service.clarity.client as cl
import service.clarity.fetch as cl_fetch
import service.growthbook.client as gb
import service.growthbook.fetch as gb_fetch
import service.mixpanel.client as mp
import service.mixpanel.fetch as mp_fetch
from service.connectors import CAP_ACCOUNTS, ConnectorAuthContext, load_connectors, registry
from service.execution import mixpanel_exec  # noqa: F401  (registers executors)
from service.execution.registry import EXECUTOR_REGISTRY


# ---------------------------------------------------------------------------
# Registry + framework wiring
# ---------------------------------------------------------------------------

def test_wave2_connectors_registered_as_manual():
    load_connectors()
    for cid in ("mixpanel", "clarity", "growthbook"):
        meta_row, adapter = registry()[cid]
        assert meta_row.oauth_scope is None
        assert CAP_ACCOUNTS in meta_row.capabilities
        assert hasattr(adapter, "list_accounts")


def test_wave2_knowledge_packs_and_catalogs():
    from agents.insights.catalog import get_catalog_for_connector
    from agents.insights.data_tools import KNOWLEDGE_INDEX
    from agents.knowledge import load_knowledge_pack

    for name in ("mixpanel", "clarity", "growthbook"):
        assert load_knowledge_pack(name).strip()
        assert name in KNOWLEDGE_INDEX
        assert get_catalog_for_connector(name)["connector_id"] == name


def test_wave2_fetchers_dispatch():
    from agents.insights.fetchers import fetch_specs

    specs = fetch_specs()
    assert {"mixpanel_event_counts", "clarity_friction", "growthbook_experiments"} <= set(specs)
    assert specs["mixpanel_event_counts"].connector_id == "mixpanel"


# ---------------------------------------------------------------------------
# Mixpanel
# ---------------------------------------------------------------------------

MP_CREDS = {
    "service_account_username": "duct.sa",
    "service_account_secret": "s3cr3t",
    "project_id": "3853123",
    "internal_patterns": "ahsankhan, ds-ios-test",
}


def test_mixpanel_requires_service_account_and_numeric_project():
    with pytest.raises(ValueError, match="service_account_username"):
        mp.require_credentials({"service_account_username": "x"})
    with pytest.raises(ValueError, match="project_id"):
        mp.require_project_id({"project_id": "designsense"})
    assert mp.require_project_id(MP_CREDS) == "3853123"


def test_mixpanel_region_and_internal_traffic_where():
    assert mp.region({"region": "EU"}) == "eu"
    assert mp.region({"region": "mars"}) == "us"
    where = mp.internal_traffic_where(mp.internal_patterns(MP_CREDS))
    assert 'not ("ahsankhan" in string(properties["distinct_id"]))' in where
    assert " and " in where
    assert mp.internal_traffic_where([]) == ""


def test_mixpanel_funnel_summing_recomputes_ratios():
    raw = {
        "data": {
            "2026-07-01": {"steps": [{"event": "signup", "count": 10}, {"event": "upgrade", "count": 2}]},
            "2026-07-02": {"steps": [{"event": "signup", "count": 30}, {"event": "upgrade", "count": 6}]},
        }
    }
    out = mp_fetch.summarise_funnel(raw)
    assert out["entered"] == 40 and out["completed"] == 8
    assert out["completion_rate"] == 0.2
    assert out["steps"][1]["step_conversion"] == 0.2


def test_mixpanel_fetch_applies_exclusion_and_pins_key_events(monkeypatch):
    calls: dict[str, dict] = {}

    def fake_api(path, creds, params=None, *, method="GET", json_body=None):
        calls[path] = dict(params or {})
        if path == "api/query/events/names":
            return ["signup", "page_view", "plan_upgrade_completed"]
        if path == "api/query/events":
            return {"data": {"series": ["2026-07-01"], "values": {"signup": {"2026-07-01": 5}}}}
        if path == "api/query/funnels/list":
            return []
        raise AssertionError(path)

    monkeypatch.setattr(mp, "api", fake_api)
    out = mp_fetch.fetch_mixpanel(MP_CREDS, days=7)
    assert out["summary"]["key_events"] == ["signup", "plan_upgrade_completed"]
    assert out["summary"]["event_totals"] == {"signup": 5}
    assert out["summary"]["internal_traffic_excluded"] == ["ahsankhan", "ds-ios-test"]
    assert "ahsankhan" in calls["api/query/events"]["where"]
    assert out["errors"] == {}


def test_mixpanel_list_accounts_scopes_to_granted_projects(monkeypatch):
    monkeypatch.setattr(
        mp, "me",
        lambda creds: {"results": {"projects": {"3853123": {"id": 3853123, "name": "DesignSenseAI"},
                                               "3583500": {"id": 3583500, "name": "DeftGPT"}}}},
    )
    adapter = registry()["mixpanel"][1]
    rows = adapter.list_accounts(ConnectorAuthContext("mixpanel", extras=MP_CREDS))
    # Sorted by project name: DeftGPT before DesignSenseAI.
    assert [r["account_id"] for r in rows] == ["3583500", "3853123"]
    with pytest.raises(ValueError, match="cannot access project 999"):
        adapter.list_accounts(ConnectorAuthContext("mixpanel", extras={**MP_CREDS, "project_id": "999"}))


# ---------------------------------------------------------------------------
# Mixpanel executors — fake App API
# ---------------------------------------------------------------------------

class _FakeApp:
    def __init__(self):
        self.annotations: dict[int, dict] = {}
        self.schemas: dict[str, dict] = {}
        self.next_id = 100

    def list_annotations(self, creds, from_date="", to_date=""):
        return [a for a in self.annotations.values() if a["date"][:10] == from_date[:10]]

    def create_annotation(self, creds, when, description):
        self.next_id += 1
        row = {"id": self.next_id, "date": when, "description": description}
        self.annotations[self.next_id] = row
        return row

    def delete_annotation(self, creds, annotation_id):
        del self.annotations[int(annotation_id)]
        return {}

    def get_schema(self, creds, entity_type, name):
        entry = self.schemas.get(name)
        return {"schemaJson": entry} if entry is not None else None

    def upsert_schema(self, creds, entity_type, name, schema_json):
        self.schemas[name] = dict(schema_json)
        return {"status": "ok"}


@pytest.fixture
def fake_app(monkeypatch):
    app = _FakeApp()
    for fn in ("list_annotations", "create_annotation", "delete_annotation", "get_schema", "upsert_schema"):
        monkeypatch.setattr(mp, fn, getattr(app, fn))
    return app


def test_mixpanel_executors_registered_reversible_and_annotation_allowlisted():
    from service.execution.policy import AUTO_APPLY_ALLOWLIST

    for op in ("mixpanel.create_annotation", "mixpanel.hide_event"):
        spec = EXECUTOR_REGISTRY[op]
        assert spec.connector_type == "mixpanel"
        assert spec.rollback is not None and spec.destructive is False
    assert "mixpanel.create_annotation" in AUTO_APPLY_ALLOWLIST
    assert "mixpanel.hide_event" not in AUTO_APPLY_ALLOWLIST


def test_annotation_preview_apply_rollback(fake_app):
    spec = EXECUTOR_REGISTRY["mixpanel.create_annotation"]
    change = {
        "op_type": spec.op_type,
        "target": {"project_id": "3853123"},
        "payload": {"date": "2026-08-14", "description": "Duct: paused PMax campaign 555"},
    }
    preview = spec.preview(change, MP_CREDS)
    assert "2026-08-14 00:00:00" in preview["diff"] and preview["warnings"] == []

    change["result"] = spec.apply(change, MP_CREDS)
    assert change["result"]["rollback"]["annotation_id"] == 101
    assert fake_app.annotations[101]["description"].startswith("Duct:")

    # A second identical proposal warns instead of silently duplicating.
    assert spec.preview(change, MP_CREDS)["warnings"]

    spec.rollback(change, MP_CREDS)
    assert fake_app.annotations == {}


def test_annotation_rejects_bad_date_before_network(fake_app):
    spec = EXECUTOR_REGISTRY["mixpanel.create_annotation"]
    with pytest.raises(ValueError, match="payload.date"):
        spec.preview({"op_type": spec.op_type, "target": {"project_id": "1"},
                      "payload": {"date": "14/08/2026", "description": "x"}}, MP_CREDS)


def test_hide_event_snapshots_and_restores_schema(fake_app):
    fake_app.schemas["plan_upgrade_initated"] = {"description": "legacy typo", "hidden": False}
    spec = EXECUTOR_REGISTRY["mixpanel.hide_event"]
    change = {
        "op_type": spec.op_type,
        "target": {"project_id": "3853123", "event_name": "plan_upgrade_initated"},
        "payload": {},
    }
    preview = spec.preview(change, MP_CREDS)
    change["current"] = preview.pop("current")
    assert change["current"]["schema_json"]["hidden"] is False

    change["result"] = spec.apply(change, MP_CREDS)
    assert fake_app.schemas["plan_upgrade_initated"] == {"description": "legacy typo", "hidden": True}

    spec.rollback(change, MP_CREDS)
    assert fake_app.schemas["plan_upgrade_initated"]["hidden"] is False
    assert fake_app.schemas["plan_upgrade_initated"]["description"] == "legacy typo"


def test_mixpanel_executor_translates_auth_errors(monkeypatch):
    def boom(*a, **k):
        raise mp.ApiError(403, '{"error": "forbidden"}', "u")

    monkeypatch.setattr(mp, "list_annotations", boom)
    spec = EXECUTOR_REGISTRY["mixpanel.create_annotation"]
    with pytest.raises(ValueError, match="service account"):
        spec.preview({"op_type": spec.op_type, "target": {"project_id": "1"},
                      "payload": {"date": "2026-08-14", "description": "x"}}, MP_CREDS)


def test_execution_creds_hand_back_manual_blob(monkeypatch):
    """Non-Google connectors get their stored shape, override on top, no env keys."""
    from types import SimpleNamespace
    from uuid import uuid4

    import service.execution.creds as creds_module

    monkeypatch.setattr(
        creds_module, "_stored_credentials",
        lambda *a, **k: {"service_account_username": "sa", "service_account_secret": "s", "project_id": "1"},
    )
    monkeypatch.setattr(creds_module, "get_configs", lambda: SimpleNamespace(
        google_ads_developer_token="env-dt", google_ads_login_customer_id="", google_oauth_client_id="cid",
        google_oauth_client_secret="cs", google_ads_client_id="", google_ads_client_secret=""))
    out = creds_module.resolve_execution_creds(None, uuid4(), "mixpanel", override={"project_id": "2"})
    assert out == {"service_account_username": "sa", "service_account_secret": "s", "project_id": "2"}
    assert "client_id" not in out


# ---------------------------------------------------------------------------
# Clarity
# ---------------------------------------------------------------------------

CLARITY_METRICS = [
    {"metricName": "Traffic", "information": [{"totalSessionCount": "1200", "totalBotSessionCount": "40",
                                               "distinctUserCount": "900", "PagesPerSessionPercentage": "2.3"}]},
    {"metricName": "ScrollDepth", "information": [{"averageScrollDepth": "54.2"}]},
    {"metricName": "EngagementTime", "information": [{"totalTime": "9000", "activeTime": "4000"}]},
    {"metricName": "RageClickCount", "information": [{"sessionsCount": "96", "sessionsWithMetricPercentage": "8.0",
                                                      "pagesViews": "120", "subTotal": "140"}]},
    {"metricName": "DeadClickCount", "information": [{"sessionsCount": "30", "sessionsWithMetricPercentage": "2.5",
                                                      "pagesViews": "35", "subTotal": "40"}]},
    {"metricName": "PopularPages", "information": [{"Url": "https://x.com/for/realtors", "VisitsCount": "600"}]},
]


def test_clarity_normalises_metric_list():
    out = cl_fetch.normalise(CLARITY_METRICS)
    assert out["traffic"] == {"sessions": 1200, "bot_sessions": 40, "distinct_users": 900, "pages_per_session": 2.3}
    assert out["friction"]["rage_clicks"] == {"sessions": 96, "sessions_pct": 8.0, "page_views": 120, "total": 140}
    assert out["friction"]["quick_backs"]["sessions"] == 0  # absent metric → zeros, not KeyError
    assert out["pages"] == [{"url": "https://x.com/for/realtors", "visits": 600}]


def test_clarity_friction_by_url_sorts_by_worst():
    metrics = [
        {"metricName": "RageClickCount", "information": [
            {"url": "/a", "sessionsCount": "1", "sessionsWithMetricPercentage": "1"},
            {"url": "/b", "sessionsCount": "9", "sessionsWithMetricPercentage": "9"},
        ]},
    ]
    rows = cl_fetch.friction_by_url(metrics)
    assert [r["url"] for r in rows] == ["/b", "/a"]


def test_clarity_days_are_clamped_and_budget_reported(monkeypatch):
    seen: list[dict] = []

    def fake_live(creds, num_days=1, dimensions=None):
        seen.append({"days": num_days, "dims": dimensions})
        return CLARITY_METRICS

    monkeypatch.setattr(cl, "live_insights", fake_live)
    out = cl_fetch.fetch_clarity({"api_token": "t"}, days=30)
    assert seen[0]["days"] == 3 and seen[1]["dims"] == ["URL"]
    assert out["summary"]["api_calls_spent"] == 2 and out["summary"]["daily_budget"] == 10
    assert out["summary"]["rage_click_sessions_pct"] == 8.0


def test_clarity_429_is_never_retried():
    """The daily budget is not a throttle — a retry would only burn tomorrow's call."""
    policy = cl._ENDPOINT.retry
    assert policy.delay(cl.ApiError(429, "", "u"), 0) is None
    assert policy.delay(cl.ApiError(503, "", "u"), 0) is not None
    with pytest.raises(ValueError, match="api_token"):
        cl.require_credentials({})
    with pytest.raises(ValueError, match="Unknown Clarity dimension"):
        cl.live_insights({"api_token": "t"}, 1, ["Planet"])


# ---------------------------------------------------------------------------
# GrowthBook
# ---------------------------------------------------------------------------

def test_growthbook_base_url_and_key():
    assert gb.base_url({}) == gb.DEFAULT_API_BASE
    assert gb.base_url({"base_url": "https://gb.example.com/"}) == "https://gb.example.com/api/v1"
    assert gb.base_url({"base_url": "https://gb.example.com/api/v1"}) == "https://gb.example.com/api/v1"
    with pytest.raises(ValueError, match="api_key"):
        gb.require_credentials({})


def test_growthbook_stale_running_flag():
    exp = {"status": "running", "phases": [{"started": "2026-05-08"}]}
    today = date(2026, 8, 4)
    # Old phase, results stop in May → stale.
    assert gb_fetch.stale_running(exp, {"end": "2026-05-22"}, today)
    # Old phase, results reach this week → fine.
    assert not gb_fetch.stale_running(exp, {"end": "2026-08-03"}, today)
    # Young phase → never stale.
    assert not gb_fetch.stale_running({"status": "running", "phases": [{"started": "2026-07-20"}]}, None, today)
    assert not gb_fetch.stale_running({"status": "stopped", "phases": [{"started": "2026-01-01"}]}, None, today)


def test_growthbook_fetch_summarises_results(monkeypatch):
    pages = {
        "experiments": {"experiments": [
            {"id": "exp_1", "name": "onboarding-flow-test", "status": "running",
             "phases": [{"name": "Main", "dateStarted": "2026-05-08T00:00:00Z", "coverage": 1}],
             "variations": [{"name": "Control"}, {"name": "Variant"}], "dateUpdated": "2026-05-20T12:27:00Z"},
        ], "hasMore": False},
        "features": {"features": [{"id": "f1"}, {"id": "f2"}], "hasMore": False},
    }

    def fake_api(path, creds, params=None):
        if path in pages:
            return pages[path]
        if path == "experiments/exp_1/results":
            return {"result": {"status": "running", "startDate": "2026-05-08", "endDate": "2026-05-22",
                               "metrics": [{"metricId": "m_upgrade", "variations": [
                                   {"variationId": 0, "users": 150, "analyses": [{"numerator": 13, "denominator": 150}]},
                                   {"variationId": 1, "users": 164, "analyses": [{"numerator": 35, "denominator": 164, "chanceToWin": 0.97}]},
                               ]}]}}
        raise AssertionError(path)

    monkeypatch.setattr(gb, "api", fake_api)
    out = gb_fetch.fetch_growthbook({"api_key": "secret_x"})
    assert out["summary"]["experiments"] == 1 and out["summary"]["feature_count"] == 2
    exp = out["data"]["experiments"][0]
    assert exp["variations"] == ["Control", "Variant"] and exp["phases"][0]["started"] == "2026-05-08"
    res = out["data"]["results"]["exp_1"]
    assert res["metrics"][0]["variations"][1]["conversion_rate"] == round(35 / 164, 4)
    assert res["metrics"][0]["variations"][1]["chance_to_win"] == 0.97
    # Phase started long ago, results end in May → the F9 trap is flagged.
    assert out["summary"]["stale_running"] == ["onboarding-flow-test"]


def test_growthbook_list_accounts_offers_all_projects_first(monkeypatch):
    monkeypatch.setattr(gb, "get_all", lambda *a, **k: [{"id": "prj_1", "name": "DesignSense"}])
    adapter = registry()["growthbook"][1]
    rows = adapter.list_accounts(ConnectorAuthContext("growthbook", extras={"api_key": "secret_x"}))
    assert rows[0] == {"account_id": "", "account_name": "All projects"}
    assert rows[1]["account_id"] == "prj_1"
