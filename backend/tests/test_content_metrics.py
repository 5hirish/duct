"""One metrics contract for a content post, and a sync that never overwrites a
number somebody typed.

A post's ``perf`` carried three key conventions (PostBridge's ``view_count``,
migrated ``views`` / ``avgWatchTime``, and hand-entered keys), read by a
different alias list in the board card, the planner and each sync. A typed
saves count could be read under the wrong name on one screen, and the
``/log-metrics`` route merged any JSON last-write-wins, so the next write could
replace it. This pins the contract on both sides and the rule on every writer.
"""

from __future__ import annotations

import re
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session

import routes.content as content_routes
import service.auth as auth_service
import service.post_bridge as post_bridge
from db.session import get_session as get_session_dep
from models.auth import User
from models.content import ContentPost
from models.membership import ProjectMember
from models.project import Project
from routes.content import ManualMetrics
from service.content_metrics import (
    MANUAL_KEYS,
    METRIC_ALIASES,
    merge_manual_metrics,
    merge_synced_metrics,
    metric_value,
    save_rate,
)
from service.membership import ROLE_OWNER
from service.post_bridge import PostBridgeClient
from service.post_bridge.schema import PostBridgeAnalytics
from tests.conftest import make_sqlite_engine

APP_METRICS = Path(__file__).resolve().parents[2] / "app" / "src" / "lib" / "contentMetrics.js"
_ROW = re.compile(r"^\s*([a-z_]+)\s*:\s*\[([^\]]*)\]", re.M)
_STRING = re.compile(r'"([^"]+)"')


def _js_frozen(name: str) -> str:
    source = APP_METRICS.read_text()
    match = re.search(rf"export const {name} = Object\.freeze\((.*?)\);\n", source, re.S)
    assert match, f"{name} not found as a frozen literal in {APP_METRICS.name}"
    return match.group(1)


# ---------------------------------------------------------------------------
# The contract, on both sides
# ---------------------------------------------------------------------------

def test_the_app_reads_every_metric_through_the_same_aliases_in_the_same_order():
    """Order is part of the contract: it decides which key wins when a post
    holds two, so a table that matches as a set can still show two numbers."""
    app = {name: tuple(_STRING.findall(keys)) for name, keys in _ROW.findall(_js_frozen("METRIC_ALIASES"))}
    assert app == METRIC_ALIASES


def test_the_apps_synced_list_is_what_postbridge_actually_returns():
    """The form shows these instead of asking for them, so a metric listed
    here that PostBridge never sends is a number nobody can enter."""
    metric_of = {key: name for name, keys in METRIC_ALIASES.items() for key in keys}
    from_schema = {metric_of[f] for f in PostBridgeAnalytics.model_fields if f in metric_of}
    assert set(_STRING.findall(_js_frozen("SYNCED_METRICS"))) == from_schema


def test_the_manual_entry_body_names_exactly_the_contracts_metrics():
    assert set(ManualMetrics.model_fields) == set(METRIC_ALIASES)


def test_each_metric_reads_its_own_canonical_key_and_no_key_is_shared():
    """A typed value is stored under the canonical name, so that name must be
    in its own chain; a key in two chains would be read as both metrics."""
    for name, keys in METRIC_ALIASES.items():
        assert name in keys, name
    every_key = [key for keys in METRIC_ALIASES.values() for key in keys]
    assert len(every_key) == len(set(every_key))


# ---------------------------------------------------------------------------
# The merges
# ---------------------------------------------------------------------------

AT = "2026-09-25T10:00:00+00:00"


def test_a_typed_value_replaces_the_metric_and_is_marked_manual():
    perf = {"view_count": 900, "avgWatchTime": 3.1, "share_url": "https://example.com/v/1"}
    out = merge_manual_metrics(perf, {"views": 500, "saves": 12}, at=AT)

    # view_count leads the chain, so leaving it would hide the typed 500.
    assert "view_count" not in out and metric_value(out, "views") == 500
    assert out["saves"] == 12
    assert out["avgWatchTime"] == 3.1 and out["share_url"] == "https://example.com/v/1"
    assert out[MANUAL_KEYS] == ["saves", "views"]
    assert out["manual_updated_at"] == AT
    assert "saves" not in perf  # a copy, not an edit in place


def test_null_withdraws_a_typed_value_so_the_sync_owns_it_again():
    first = merge_manual_metrics({}, {"saves": 12, "reach": 800}, at=AT)
    second = merge_manual_metrics(first, {"reach": None}, at=AT)
    assert metric_value(second, "reach") is None
    assert second[MANUAL_KEYS] == ["saves"]


def test_an_unknown_metric_is_refused_rather_than_stored_under_a_fourth_name():
    with pytest.raises(ValueError):
        merge_manual_metrics({}, {"savez": 1}, at=AT)


def test_a_sync_refreshes_what_it_owns_and_skips_every_alias_of_a_typed_metric():
    perf = merge_manual_metrics({"view_count": 100}, {"views": 500, "saves": 12}, at=AT)
    synced = {
        "id": "ana_1",
        "view_count": 900,     # aliases the typed views → skipped
        "save_count": 40,      # aliases the typed saves → skipped
        "like_count": 33,      # PostBridge's own → written
        "share_url": "https://example.com/v/1",
        MANUAL_KEYS: [],       # never taken from a payload
        "comment_count": None,
    }
    out = merge_synced_metrics(perf, synced, synced_at=AT)

    assert metric_value(out, "views") == 500
    assert metric_value(out, "saves") == 12
    assert metric_value(out, "likes") == 33
    assert out["share_url"] == "https://example.com/v/1"
    assert "id" not in out and "comment_count" not in out
    assert out[MANUAL_KEYS] == ["saves", "views"]
    assert out["last_synced_at"] == AT


def test_the_save_rate_is_derived_from_synced_views_and_typed_saves():
    """Nothing stores a rate, so reading one left the planner's median save
    rate empty for every post that had both numbers."""
    perf = merge_manual_metrics({"view_count": 2000}, {"saves": 50}, at=AT)
    assert save_rate(perf) == pytest.approx(0.025)
    assert save_rate({"save_rate": 0.04}) == 0.04  # a migrated row keeps its own
    assert save_rate({"view_count": 2000}) is None


# ---------------------------------------------------------------------------
# The route
# ---------------------------------------------------------------------------

@pytest.fixture
def db():
    with Session(make_sqlite_engine()) as session:
        yield session


def _user(db, email):
    row = User(email=email)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@pytest.fixture
def owner(db):
    return _user(db, "metrics-owner@example.com")


@pytest.fixture
def post(db, owner):
    project = Project(user_id=owner.id, name="Owner's brand")
    db.add(project)
    db.commit()
    db.refresh(project)
    db.add(ProjectMember(project_id=project.id, user_id=owner.id, role=ROLE_OWNER))
    row = ContentPost(
        project_id=project.id,
        post_dir_slug="launch-day",
        status="posted",
        post_bridge_post_id="pb_post_1",
        perf={"view_count": 100},
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def client(db, user):
    app = FastAPI()
    app.include_router(content_routes.router, prefix="/api")
    app.dependency_overrides[get_session_dep] = lambda: db
    app.dependency_overrides[auth_service.get_current_user] = lambda: user
    return TestClient(app, raise_server_exceptions=False)


def test_a_member_enters_saves_and_reads_them_back_under_the_same_name(db, post, owner):
    res = client(db, owner).post(f"/api/content/posts/{post.id}/metrics", json={"saves": 12})
    assert res.status_code == 200
    body = res.json()
    assert body["perf"]["saves"] == 12 and body["perf"][MANUAL_KEYS] == ["saves"]
    assert body["post_bridge_post_id"] == "pb_post_1"
    db.refresh(post)
    assert metric_value(post.perf, "saves") == 12


def test_a_stranger_gets_404_and_the_post_keeps_its_numbers(db, post):
    stranger = _user(db, "metrics-stranger@example.com")
    res = client(db, stranger).post(f"/api/content/posts/{post.id}/metrics", json={"saves": 9999})
    assert res.status_code == 404
    db.refresh(post)
    assert post.perf == {"view_count": 100}


@pytest.mark.parametrize(
    ("body", "status"),
    [
        ({}, 422),                          # nothing to save
        ({"savez": 1}, 422),                # not a metric
        ({"saves": -1}, 422),               # counts are not negative
        ({"completion_rate": 140}, 422),    # a percent
    ],
)
def test_the_route_refuses_what_is_not_a_metric(db, post, owner, body, status):
    assert client(db, owner).post(f"/api/content/posts/{post.id}/metrics", json=body).status_code == status


def test_a_post_that_is_not_out_yet_has_no_numbers_to_enter(db, post, owner):
    post.status = "draft"
    db.add(post)
    db.commit()
    res = client(db, owner).post(f"/api/content/posts/{post.id}/metrics", json={"saves": 3})
    assert res.status_code == 409


def test_typed_saves_survive_the_next_postbridge_sync(db, post, owner, monkeypatch):
    """The done-means of #223, end to end: a real PostBridgeClient against a
    faked transport, so the analytics payload goes through its own schema.
    Typed views ride along because PostBridge does send those: saves alone
    would survive even a sync that ignored the rule."""

    def respond(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/v1/analytics/sync":
            return httpx.Response(200, json={})
        if req.url.path == "/v1/post-results":
            return httpx.Response(200, json={"data": [{
                "id": "res_1", "post_id": "pb_post_1", "success": True,
                "social_account_id": 101, "error": None, "platform_data": None,
            }], "meta": {"total": 1, "offset": 0, "limit": 10, "next": None}})
        if req.url.path == "/v1/analytics":
            return httpx.Response(200, json={"data": [{
                "id": "ana_1", "post_result_id": "res_1", "platform": "tiktok",
                "view_count": 1800, "like_count": 70,
                "last_synced_at": "2026-09-25T09:00:00+00:00",
            }], "meta": {"total": 1, "offset": 0, "limit": 1, "next": None}})
        raise AssertionError(req.url.path)

    monkeypatch.setattr(
        post_bridge,
        "client_for_user",
        lambda _user_id, _db: PostBridgeClient(
            "sk-fake", client=httpx.AsyncClient(transport=httpx.MockTransport(respond)),
        ),
    )
    c = client(db, owner)
    typed = {"saves": 12, "views": 500}
    assert c.post(f"/api/content/posts/{post.id}/metrics", json=typed).status_code == 200

    res = c.post(f"/api/content/posts/{post.id}/sync-metrics")
    assert res.status_code == 200, res.text
    perf = res.json()["perf"]
    assert metric_value(perf, "saves") == 12
    assert metric_value(perf, "views") == 500   # PostBridge said 1800; the person wins
    assert metric_value(perf, "likes") == 70    # and the sync still refreshes the rest
    assert perf["last_synced_at"] == "2026-09-25T09:00:00+00:00"

