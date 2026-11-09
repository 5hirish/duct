"""The Analytics tab's report: contract, templates, sources, run, storage, route.

What these pin, in the order a report comes to exist:

  * **The contract degrades, never raises.** A payload the schema refuses
    comes back as problems for a repair turn; a count over a limit is
    clamped. Losing a report over its thirteenth block is the one outcome
    worse than a long report.
  * **The plan is what the sources can fill.** A block none of the chosen
    sources can answer is left out of the plan, never left for a guess.
  * **The run writes the report as an artifact version**, on the same
    agent as the brief, and a refused payload gets one more turn.
  * **The route serves the stored copy, flags it stale after a day, and
    starts nothing by itself.** A stranger sees 404; a project with no
    source to read gets told what to connect.

Fake chat model throughout — no API key, no network.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import select

import routes.content_reports as reports_routes
import service.auth as auth_service
import service.artifact_store as store
from agents.core.events import AgentEvent
from agents.insights.report import (
    ARTIFACT_KIND,
    MAX_BLOCKS,
    MAX_ROWS,
    parse_report,
    report_artifact_version,
    report_source_text,
)
from agents.insights.report_templates import (
    SOURCES,
    STATUS_NEEDS_ACCOUNT,
    STATUS_NOT_CONNECTED,
    STATUS_READY,
    SourceState,
    choose_sources,
    source_states,
    template,
)
from agents.insights.prompts.autonomous import (
    DELIVERABLE_REPORT,
    build_insights_system_prompt,
    build_insights_user_prompt,
    report_plan_block,
)
from agents.insights.v1.runner import AutonomousInsightsRunner
from agents.registry import AgentType
from db.session import get_session as get_session_dep
from models.artifact import Artifact
from models.auth import User
from tests.fakes import fake_llm as _fake
from tests.test_artifact_store import (  # noqa: F401
    db,
    engine,
    local_storage,
    owner,
    project,
    store_db,
)
from utils.dates import utcnow

RUNNER = AutonomousInsightsRunner(api_key="unused-no-network")

REPORT_JSON = {
    "title": "Organic clicks up a third; signups flat",
    "date_from": "2026-10-01",
    "date_to": "2026-10-30",
    "verdict": "Organic clicks rose 34% to 4,210 while signups held at 61. Fix the pricing page's form before buying more traffic.",
    "summary": "Search grew on three guide posts; the extra visitors land on pricing and leave.",
    "takeaway": "Traffic is not the constraint this month; the form is.",
    "sources": [
        {"id": "gsc", "label": "Search Console", "status": "read", "window": "1–30 Oct"},
        {"id": "posthog", "label": "PostHog", "status": "failed", "note": "signed out"},
    ],
    "blocks": [
        {
            "block_id": "headline", "block_type": "kpi_strip", "title": "Headline numbers",
            "kpis": [
                {"label": "Organic clicks", "value": "4,210", "delta": "+34% vs the 30 days before", "tone": "good", "source": "Search Console"},
                {"label": "Signups", "value": "61", "delta": "+0%", "tone": "neutral", "source": "PostHog"},
            ],
            "insight_note": "Clicks moved, signups did not: the gap is on the site, not in search.",
        },
        {
            "block_id": "traffic", "block_type": "time_series", "title": "Organic clicks by day",
            "source": "Search Console", "window": "1–30 Oct 2026",
            "rows": [{"date": "2026-10-01", "clicks": 90}, {"date": "2026-10-02", "clicks": 120}, {"date": "2026-10-03", "clicks": 140}, {"date": "2026-10-04", "clicks": 155}],
            "x_field": "date", "y_field": "clicks", "y_unit": "clicks",
            "insight_note": "A step up on the 12th, when the agentic-workflow guide was indexed.",
        },
        {
            "block_id": "signals", "block_type": "signal_list", "title": "What moved",
            "signals": [{"id": "s1", "kind": "win", "title": "Guide posts rank", "impact": "3 posts, 1,900 clicks", "action": "Write the fourth", "source": "Search Console"}],
        },
        {
            "block_id": "actions", "block_type": "action_list", "title": "What to do next",
            "actions": [{"id": "a1", "title": "Fix the pricing form", "detail": "Drop the company field.", "size": "about 420 of 1,100 pricing visits bounce", "effort": "a form change", "check": "signups per pricing visit in two weeks"}],
        },
    ],
    "could_not_check": ["Signups by source: PostHog was signed out."],
    "method_note": "Window 1–30 Oct against 1–30 Sep. Brand queries excluded (14% of clicks).",
}


def _artifact(payload: dict, *, title: str = "", fenced: bool = False) -> str:
    body = json.dumps(payload)
    if fenced:
        body = f"```json\n{body}\n```"
    front = f"---\ntitle: {title}\nformat: report\n---\n" if title else ""
    return f"<duct_artifact>\n{front}{body}\n</duct_artifact>"


# ---------------------------------------------------------------------------
# The contract
# ---------------------------------------------------------------------------

def test_a_well_formed_payload_parses_with_its_blocks():
    parsed = parse_report(_artifact(REPORT_JSON))

    assert parsed.ok
    assert parsed.report.title.startswith("Organic clicks")
    assert [b.block_type for b in parsed.report.blocks] == ["kpi_strip", "time_series", "signal_list", "action_list"]
    assert parsed.report.blocks[1].rows[0]["clicks"] == 90


def test_a_code_fence_and_a_front_matter_title_are_tolerated():
    body = {**REPORT_JSON}
    body.pop("title")
    parsed = parse_report(_artifact(body, title="From the fence", fenced=True))

    assert parsed.ok
    assert parsed.report.title == "From the fence"


def test_broken_json_is_a_problem_not_an_exception():
    parsed = parse_report("<duct_artifact>\n{\"title\": \"x\", }\n</duct_artifact>")

    assert not parsed.ok
    assert parsed.problems and "JSON" in parsed.problems[0]


def test_a_wrong_block_type_names_where_it_went_wrong():
    body = {**REPORT_JSON, "blocks": [{"block_id": "x", "block_type": "sparkline", "title": "t"}]}
    parsed = parse_report(_artifact(body))

    assert not parsed.ok
    assert any("blocks.0.block_type" in p for p in parsed.problems)


def test_counts_over_the_limits_are_clamped_not_refused():
    many_rows = [{"date": f"2026-10-{d:02d}", "clicks": d} for d in range(1, 31)] * 3
    body = {
        **REPORT_JSON,
        "blocks": [
            {"block_id": f"b{i}", "block_type": "time_series", "title": "t", "rows": many_rows, "x_field": "date", "y_field": "clicks"}
            for i in range(MAX_BLOCKS + 3)
        ],
    }
    parsed = parse_report(_artifact(body))

    assert parsed.ok
    assert len(parsed.report.blocks) == MAX_BLOCKS
    assert len(parsed.report.blocks[0].rows) == MAX_ROWS


def test_source_text_carries_the_words_and_the_gaps_not_the_rows():
    text = report_source_text(parse_report(_artifact(REPORT_JSON)).report)

    assert "4,210" in text and "Fix the pricing form" in text
    assert "PostHog was signed out" in text
    assert "2026-10-02" not in text  # rows are for the chart, not the digest


# ---------------------------------------------------------------------------
# Templates and sources
# ---------------------------------------------------------------------------

def test_the_plan_keeps_only_blocks_the_chosen_sources_can_fill():
    tmpl = template("growth_overview")
    ids = [b.block_id for b in tmpl.plan_for({"gsc"})]

    assert "queries" in ids and "headline" in ids and "signals" in ids
    assert "posts" not in ids and "channels" not in ids


def test_the_plan_block_names_each_source_and_how_to_read_it():
    tmpl = template("growth_overview")
    chosen = [
        SourceState(SOURCES["gsc"], STATUS_READY, "example.com"),
        SourceState(SOURCES["publishers"], STATUS_READY, "Zernio"),
        SourceState(SOURCES["posthog"], STATUS_READY, "PostHog"),
    ]
    block = report_plan_block(tmpl, chosen, date_from="2026-10-01", date_to="2026-10-30")

    assert "<report_plan>" in block
    assert 'FetchData(entity_id="social_post_metrics")' in block
    assert 'CallConnectedTool on the "posthog" server' in block
    assert "- posts (bar_chart)" in block


def test_choose_sources_takes_ready_compatible_sources_only():
    tmpl = template("seo")
    states = [
        SourceState(SOURCES["gsc"], STATUS_READY),
        SourceState(SOURCES["ga4"], STATUS_NEEDS_ACCOUNT),
        SourceState(SOURCES["publishers"], STATUS_READY),  # not a search source
        SourceState(SOURCES["openseo"], STATUS_NOT_CONNECTED),
    ]
    assert [s.source.id for s in choose_sources(tmpl, states, None)] == ["gsc"]
    assert [s.source.id for s in choose_sources(tmpl, states, ["gsc", "ga4", "publishers"])] == ["gsc"]


def test_source_states_read_connectors_schedulers_and_servers(monkeypatch, db, project, owner):  # noqa: F811
    import service.connector_access as access
    import service.mcp.store as mcp_store
    import service.publishers.registry as registry

    class _Src:
        def __init__(self, cid, status, name=""):
            self.connector_id, self.status, self.account_id, self.account_name = cid, status, name, name

    monkeypatch.setattr(access, "list_data_sources", lambda *a, **k: [_Src("gsc", "bound", "example.com"), _Src("ga4", "available")])
    monkeypatch.setattr(mcp_store, "list_servers", lambda *a, **k: [
        {"preset": "posthog", "name": "PostHog", "problem": ""},
        {"preset": "openseo", "name": "OpenSEO", "problem": "signed_out"},
    ])

    class _Spec:
        id, label = "zernio", "Zernio"

    monkeypatch.setattr(registry, "connected_specs", lambda *a, **k: [_Spec()])

    by_id = {s.source.id: s for s in source_states(db, user_id=owner.id, project=project)}

    assert by_id["gsc"].status == STATUS_READY and by_id["gsc"].detail == "example.com"
    assert by_id["ga4"].status == STATUS_NEEDS_ACCOUNT
    assert by_id["publishers"].status == STATUS_READY and by_id["publishers"].detail == "Zernio"
    assert by_id["posthog"].status == STATUS_READY
    assert by_id["openseo"].status == "needs_attention"
    assert by_id["mixpanel"].status == STATUS_NOT_CONNECTED


# ---------------------------------------------------------------------------
# The prompt
# ---------------------------------------------------------------------------

def test_the_report_contract_replaces_the_briefs_and_is_cache_stable():
    brief = build_insights_system_prompt()
    report = build_insights_system_prompt(deliverable=DELIVERABLE_REPORT)

    assert "Writing the brief" in brief and "Writing the report" not in brief
    assert "Writing the report" in report and "Writing the brief" not in report
    assert report == build_insights_system_prompt(deliverable=DELIVERABLE_REPORT)
    # The picture rules reach both deliverables.
    assert "Choose the picture by the question" in brief
    assert "Choose the picture by the question" in report


def test_the_plan_rides_in_the_user_turn_never_the_system_prompt():
    plan = "<report_plan>\nTemplate: Search (seo).\n</report_plan>"
    turn = build_insights_user_prompt(prompt="write it", report_plan=plan)

    assert "Template: Search (seo)" in turn
    assert "Template: Search" not in build_insights_system_prompt(deliverable=DELIVERABLE_REPORT)


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------

async def test_the_run_emits_the_validated_report_as_an_artifact_version(emitted):
    result = await RUNNER.run_report(
        emitted, llm=_fake(f"Clicks up, signups flat.\n{_artifact(REPORT_JSON)}"),
        prompt="write it", report_plan="<report_plan>x</report_plan>", template="growth_overview",
    )

    versions = [e for e in emitted.events if e["event"] == AgentEvent.ARTIFACT_VERSION]
    assert len(versions) == 1
    assert versions[0]["version_id"] == 1
    assert versions[0]["payload"]["format"] == "report"
    assert versions[0]["payload"]["template"] == "growth_overview"
    assert versions[0]["payload"]["report"]["blocks"][0]["block_type"] == "kpi_strip"
    assert result.report is not None and not result.repaired
    assert emitted.events[-1]["event"] == AgentEvent.PIPELINE_FINISHED


async def test_a_refused_payload_gets_one_repair_turn(emitted):
    broken = "<duct_artifact>\n{\"title\": \"x\", \"verdict\": 1, }\n</duct_artifact>"
    result = await RUNNER.run_report(
        emitted, llm=_fake(broken, _artifact(REPORT_JSON)),
        prompt="write it", report_plan="<report_plan>x</report_plan>",
    )

    assert result.report is not None
    assert result.repaired
    versions = [e for e in emitted.events if e["event"] == AgentEvent.ARTIFACT_VERSION]
    assert len(versions) == 1


async def test_a_model_that_never_writes_json_ends_with_problems_not_a_crash(emitted):
    broken = "<duct_artifact>\nnot json at all\n</duct_artifact>"
    result = await RUNNER.run_report(
        emitted, llm=_fake(broken, broken, broken, broken),
        prompt="write it", report_plan="<report_plan>x</report_plan>", repair_turns=1,
    )

    assert result.report is None
    assert result.problems
    assert not [e for e in emitted.events if e["event"] == AgentEvent.ARTIFACT_VERSION]


async def test_a_refresh_numbers_the_next_version(emitted):
    await RUNNER.run_report(
        emitted, llm=_fake(_artifact(REPORT_JSON)),
        prompt="write it", report_plan="<report_plan>x</report_plan>", start_version=3,
    )
    versions = [e for e in emitted.events if e["event"] == AgentEvent.ARTIFACT_VERSION]
    assert versions[0]["version_id"] == 4


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

async def test_a_report_persists_as_a_structured_artifact(local_storage, store_db, project, owner, db):  # noqa: F811
    persister = store.ArtifactPersister(
        project_id=project.id, user_id=owner.id, agent_type=str(AgentType.INSIGHTS),
        kind=ARTIFACT_KIND, adapt=report_artifact_version,
    )
    wrapped = persister.wrap_emit(lambda body: asyncio.sleep(0))
    await wrapped({
        "event": AgentEvent.ARTIFACT_VERSION, "version_id": 1, "label": "Report",
        "payload": {"title": REPORT_JSON["title"], "format": "report", "template": "growth_overview", "report": REPORT_JSON},
    })
    await asyncio.sleep(0)

    row = db.exec(select(Artifact)).one()
    assert row.kind == ARTIFACT_KIND
    assert row.content_type == store.GROWTH_REPORT_JSON
    assert row.slug == "growth-report-growth-overview"
    assert row.structured_json["blocks"][1]["rows"][0] == {"date": "2026-10-01", "clicks": 90}
    assert row.meta["template"] == "growth_overview"
    assert row.storage_key == ""  # the app draws it from structured_json; no bytes to serve


# ---------------------------------------------------------------------------
# The route
# ---------------------------------------------------------------------------

def _client(session, user=None):
    app = FastAPI()
    app.include_router(reports_routes.router, prefix="/api")
    app.dependency_overrides[get_session_dep] = lambda: session
    app.dependency_overrides[auth_service.get_user_provider_keys] = lambda: {}
    if user is not None:
        app.dependency_overrides[auth_service.get_current_user] = lambda: user
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def no_sources(monkeypatch):
    import service.connector_access as access
    import service.mcp.store as mcp_store
    import service.publishers.registry as registry

    monkeypatch.setattr(access, "list_data_sources", lambda *a, **k: [])
    monkeypatch.setattr(mcp_store, "list_servers", lambda *a, **k: [])
    monkeypatch.setattr(registry, "connected_specs", lambda *a, **k: [])
    reports_routes._reset_runs_for_tests()


def _stored_report(session, proj, user, *, age_hours=0):
    row = Artifact(
        group_id=uuid.uuid4(), version=1, project_id=proj.id, user_id=user.id,
        agent_type=str(AgentType.INSIGHTS), kind=ARTIFACT_KIND, content_type=store.GROWTH_REPORT_JSON,
        title=REPORT_JSON["title"], structured_json=REPORT_JSON,
        meta={"template": "growth_overview"}, created_at=utcnow() - timedelta(hours=age_hours),
    )
    session.add(row)
    session.commit()
    return row


def test_get_lists_templates_and_sources_with_no_report_yet(db, project, owner, no_sources):  # noqa: F811
    body = _client(db, owner).get(f"/api/content/analytics/report?project_id={project.id}").json()

    assert body["template"]["id"] == "growth_overview"
    assert {t["id"] for t in body["templates"]} >= {"growth_overview", "seo", "social", "product"}
    assert body["report"] is None and body["generating"] is False
    assert all(s["status"] == STATUS_NOT_CONNECTED for s in body["sources"])
    assert body["ttl_hours"] == 24


def test_get_serves_the_stored_report_and_flags_a_day_old_one_stale(db, project, owner, no_sources):  # noqa: F811
    _stored_report(db, project, owner, age_hours=30)
    body = _client(db, owner).get(f"/api/content/analytics/report?project_id={project.id}").json()

    assert body["report"]["stale"] is True
    assert body["report"]["report"]["verdict"].startswith("Organic clicks")

    db.exec(select(Artifact)).one()
    fresh = _stored_report(db, project, owner, age_hours=1)
    body = _client(db, owner).get(f"/api/content/analytics/report?project_id={project.id}").json()
    assert body["report"]["stale"] is False
    assert body["report"]["artifact_id"] == str(fresh.id)


def test_an_unknown_template_is_a_422(db, project, owner, no_sources):  # noqa: F811
    res = _client(db, owner).get(f"/api/content/analytics/report?project_id={project.id}&template=weather")
    assert res.status_code == 422


def test_a_stranger_is_told_the_project_does_not_exist(db, project, no_sources):  # noqa: F811
    stranger = User(email="stranger@example.com")
    db.add(stranger)
    db.commit()
    db.refresh(stranger)

    res = _client(db, stranger).get(f"/api/content/analytics/report?project_id={project.id}")
    assert res.status_code == 404
    res = _client(db, stranger).post("/api/content/analytics/report", json={"project_id": str(project.id)})
    assert res.status_code == 404


def test_post_with_nothing_to_read_says_what_to_connect(db, project, owner, no_sources):  # noqa: F811
    res = _client(db, owner).post("/api/content/analytics/report", json={"project_id": str(project.id)})

    assert res.status_code == 400
    assert "Connect" in res.json()["detail"]


def test_post_starts_a_run_on_the_chosen_sources(monkeypatch, db, project, owner, no_sources):  # noqa: F811
    import service.publishers.registry as registry

    class _Spec:
        id, label = "zernio", "Zernio"

    monkeypatch.setattr(registry, "connected_specs", lambda *a, **k: [_Spec()])

    class _Run:
        project_id = project.id
        provider = model = api_key = summary_key = verify_provider = verify_model = verify_api_key = None

    import agents.insights.setup as setup

    monkeypatch.setattr(setup, "resolve_run", lambda **k: _Run())
    started: list[dict] = []

    async def _fake_generate(entry, **kwargs):
        started.append(kwargs)

    monkeypatch.setattr(reports_routes, "_generate", _fake_generate)

    res = _client(db, owner).post(
        "/api/content/analytics/report",
        json={"project_id": str(project.id), "template": "social", "sources": ["publishers", "ga4"]},
    )

    assert res.status_code == 202 and res.json()["generating"] is True
    assert res.json()["run_sources"] == ["publishers"]
    assert len(started) == 1
    assert [s.source.id for s in started[0]["chosen"]] == ["publishers"]
    assert started[0]["tmpl"].id == "social"


def test_post_joins_a_run_already_writing_the_same_report(monkeypatch, db, project, owner, no_sources):  # noqa: F811
    """One API worker, one run per project and template: a second click
    while the first is writing spends nothing more."""
    live = reports_routes._Run(started_at="2026-11-09T09:00:00+00:00", sources=["gsc"], task=object())
    reports_routes._runs[(project.id, "growth_overview")] = live
    called: list[dict] = []
    monkeypatch.setattr(reports_routes, "_generate", lambda *a, **k: called.append(k))

    body = _client(db, owner).post("/api/content/analytics/report", json={"project_id": str(project.id)}).json()

    assert body["generating"] is True
    assert body["started_at"] == live.started_at
    assert body["run_sources"] == ["gsc"]
    assert not called


def test_a_finished_run_reports_its_error_until_the_next_start(db, project, owner, no_sources):  # noqa: F811
    done = reports_routes._Run(started_at="2026-11-09T09:00:00+00:00", sources=["gsc"], task=object(), finished=True)
    done.error = {"code": "report_invalid", "error": "The agent could not write a report the tab can draw."}
    reports_routes._runs[(project.id, "growth_overview")] = done

    body = _client(db, owner).get(f"/api/content/analytics/report?project_id={project.id}").json()

    assert body["generating"] is False
    assert body["error"]["code"] == "report_invalid"


# ---------------------------------------------------------------------------
# The schedulers as a FetchData entity
# ---------------------------------------------------------------------------

def test_social_post_metrics_keeps_the_window_and_sums_by_platform(monkeypatch):
    from dataclasses import dataclass

    import agents.insights.fetchers as fetchers
    import service.publishers.metrics as metrics
    from agents.insights.fetchers import fetch_entity
    from service.publishers.base import ReportedPost

    @dataclass(frozen=True)
    class _Spec:
        id: str = "zernio"
        label: str = "Zernio"

    posts = [
        ReportedPost(ref="a", platform="linkedin", title="A", views=900, likes=40, comments=5, shares=5, posted_at="2026-10-05T10:00:00"),
        ReportedPost(ref="b", platform="linkedin", title="B", views=100, likes=10, posted_at="2026-10-20T10:00:00"),
        ReportedPost(ref="c", platform="x", title="C", views=300, likes=3, posted_at="2026-10-21T10:00:00"),
        ReportedPost(ref="old", platform="x", title="Old", views=5000, posted_at="2026-06-01T10:00:00"),
        ReportedPost(ref="undated", platform="x", title="Undated", views=50),
    ]

    async def _collect(session, proj, *, refresh=False):
        return metrics.ReportedPosts(rows=[(_Spec(), p) for p in posts], asked=[_Spec()])

    class _Proj:
        user_id = uuid.uuid4()

    class _Db:
        def get(self, *_a):
            return _Proj()

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

    monkeypatch.setattr(metrics, "collect_reported_posts", _collect)
    monkeypatch.setattr(metrics, "owner_has_scheduler", lambda *a, **k: True)
    monkeypatch.setattr("db.session.get_session", lambda: iter([_Db()]))

    result = fetch_entity(
        "social_post_metrics", user_id=uuid.uuid4(), project_id=uuid.uuid4(),
        date_from="2026-10-01", date_to="2026-10-30",
    )

    assert result["status"] == "ok"
    assert [r["title"] for r in result["data"]["rows"]] == ["A", "C", "B"]  # in the window, by views
    assert result["data"]["undated_rows"] == 1
    assert result["totals"]["views"] == 1300
    assert result["totals"]["engagement"] == 63
    assert result["rates"]["engagement_rate"]["ratio"] == "engagement / views"
    assert result["subtotals"]["platform"]["linkedin"]["views"] == 1000
    assert fetchers.PUBLISHERS_SOURCE == result["connector_id"]


def test_social_post_metrics_without_a_scheduler_says_where_to_connect_one(monkeypatch):
    import service.publishers.metrics as metrics
    from agents.insights.fetchers import fetch_entity

    class _Proj:
        user_id = uuid.uuid4()

    class _Db:
        def get(self, *_a):
            return _Proj()

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

    monkeypatch.setattr(metrics, "owner_has_scheduler", lambda *a, **k: False)
    monkeypatch.setattr("db.session.get_session", lambda: iter([_Db()]))

    result = fetch_entity("social_post_metrics", user_id=uuid.uuid4(), project_id=uuid.uuid4())

    assert result["status"] == "not_connected"
    assert "Content → Accounts" in result["message"]


def test_the_data_sources_block_names_the_schedulers():
    from agents.insights.setup import render_data_sources

    block = render_data_sources([
        {"connector_id": "gsc", "status": "bound", "account_id": "sc-domain:example.com"},
        {"connector_id": "publishers", "status": "not_connected", "hint": "no scheduler connected — the owner connects one in Content → Accounts"},
    ])

    assert "- publishers: not_connected (no scheduler connected" in block
    assert "RequestConnection" not in block.split("publishers")[1]


async def test_the_shared_fan_out_keeps_only_the_platforms_the_project_linked(monkeypatch):
    """One scheduler key can hold several brands' accounts; the project's links
    say which posts are its own. The tab applied that scope and the agent's
    entity did not, so the scope lives in the one fan-out both read."""
    from dataclasses import dataclass

    import service.publishers.metrics as metrics
    from service.publishers.base import ReportedPost

    @dataclass(frozen=True)
    class _Spec:
        id: str = "zernio"
        label: str = "Zernio"

    class _Pub:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_a):
            return False

        async def reported_posts(self, *, refresh=False):
            return [
                ReportedPost(ref="a", platform="linkedin", title="Ours"),
                ReportedPost(ref="b", platform="tiktok", title="Another brand on the same key"),
            ]

    class _Proj:
        id = uuid.uuid4()
        user_id = uuid.uuid4()

    monkeypatch.setattr(metrics, "connected_specs", lambda *a, **k: [_Spec()])
    monkeypatch.setattr(metrics, "publisher_for", lambda *a, **k: _Pub())
    monkeypatch.setattr(metrics, "_linked_platforms", lambda *a, **k: {"linkedin"})

    scoped = await metrics.collect_reported_posts(None, _Proj())
    assert [r.title for _, r in scoped.rows] == ["Ours"]

    monkeypatch.setattr(metrics, "_linked_platforms", lambda *a, **k: set())
    unscoped = await metrics.collect_reported_posts(None, _Proj())
    assert len(unscoped.rows) == 2  # nothing linked: show all, as the tab does
