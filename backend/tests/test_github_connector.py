"""GitHub connector: registration, the repository picker, and the token rules.

The pull itself runs over ``FakeWire`` in ``test_rest_connector_requests.py``.
This file holds what sits around it: what the Connections page lists, what a
bad token says, how FetchData reaches the fetcher, and that Duct, not the
model, adds up the line counts.
"""

from __future__ import annotations

import pytest

from service.connectors import CAP_ACCOUNTS, ConnectorAuthContext, load_connectors, registry
from service.github import GITHUB_CONNECTOR_ID
from service.github import client as gh
from tests.fakes import FakeWire


@pytest.fixture
def wire(monkeypatch):
    import service.rest as rest

    monkeypatch.setattr(rest.time, "sleep", lambda *_: None)  # the 5xx retry backoff
    return FakeWire().install(monkeypatch)


def _accounts(extras: dict) -> list[dict]:
    load_connectors()
    _meta, adapter = registry()[GITHUB_CONNECTOR_ID]
    return adapter.list_accounts(ConnectorAuthContext(GITHUB_CONNECTOR_ID, extras=extras))


# ---------------------------------------------------------------------------
# Registration and dispatch
# ---------------------------------------------------------------------------

def test_github_registers_as_a_read_only_manual_connector_over_repositories():
    from routes.user_connectors import ALLOWED_CONNECTOR_TYPES

    load_connectors()
    meta, adapter = registry()[GITHUB_CONNECTOR_ID]
    assert meta.oauth_scope is None  # a pasted token; nothing registered with GitHub
    assert CAP_ACCOUNTS in meta.capabilities
    assert meta.access == frozenset({"read"})
    assert (meta.entity_noun, meta.entity_noun_plural) == ("repository", "repositories")
    assert hasattr(adapter, "list_accounts")
    # The same set gates saving a credential and binding it to a project.
    assert GITHUB_CONNECTOR_ID in ALLOWED_CONNECTOR_TYPES


def test_fetchdata_reaches_github_and_its_notes():
    from agents.insights.data_tools import KNOWLEDGE_INDEX
    from agents.insights.fetchers import fetch_specs
    from agents.knowledge import load_knowledge_pack

    spec = fetch_specs()["github_work_events"]
    assert (spec.connector_id, spec.fetch_fn) == (GITHUB_CONNECTOR_ID, "fetch_github")
    assert GITHUB_CONNECTOR_ID in KNOWLEDGE_INDEX
    assert load_knowledge_pack(GITHUB_CONNECTOR_ID).strip()


def test_the_fetcher_adapter_keeps_the_exact_dates_and_the_picked_repository():
    from agents.insights.fetchers import _manual_dated

    seen = []
    call = _manual_dated(lambda *args: seen.append(args) or {}, "repo")

    call("acme/app", "2026-09-28", "2026-09-28", {"token": "t"})
    # Not a day count: "today" stays today instead of becoming yesterday.
    assert seen == [({"token": "t", "repo": "acme/app"}, "2026-09-28", "2026-09-28")]


# ---------------------------------------------------------------------------
# The repository picker
# ---------------------------------------------------------------------------

def test_list_accounts_offers_each_repository_the_token_can_read(wire):
    wire.on("GET", "/user/repos", [
        {"full_name": "acme/app", "description": "The app", "private": True, "visibility": "private",
         "pushed_at": "2026-09-27T10:00:00Z", "default_branch": "main"},
        {"full_name": "acme/site", "description": None, "private": False, "pushed_at": "2026-09-01T00:00:00Z"},
    ])

    rows = _accounts({"token": "github_pat_x"})

    (listing,) = wire.sent("GET", "/user/repos")
    assert listing.query == {"sort": "pushed", "per_page": "100", "page": "1"}
    assert listing.headers["Authorization"] == "Bearer github_pat_x"
    assert listing.headers["X-GitHub-Api-Version"] == gh.API_VERSION
    assert [(r["account_id"], r["account_name"]) for r in rows] == [
        ("acme/app", "acme/app"), ("acme/site", "acme/site")]
    assert rows[0]["entity_detail"] == "The app"
    assert rows[0]["entity_meta"] == [
        {"label": "Visibility", "value": "private"}, {"label": "Last push", "value": "2026-09-27"}]
    assert rows[1]["entity_detail"] == ""
    assert rows[1]["entity_meta"][0] == {"label": "Visibility", "value": "public"}
    assert all("warning" not in r for r in rows)


def test_a_classic_token_is_accepted_with_a_warning_on_every_row(wire):
    wire.on("GET", "/user/repos", [{"full_name": "acme/app"}, {"full_name": "acme/site"}])

    rows = _accounts({"token": "ghp_classic"})

    # On every row, because the Connections page shows the one that gets picked.
    assert all("classic token" in r["warning"] for r in rows)
    assert gh.token_warning("github_pat_x") == ""


@pytest.mark.parametrize(("status", "error"), [(401, ValueError), (403, ValueError), (502, RuntimeError)])
def test_list_accounts_maps_a_refusal_to_a_fixable_error_and_an_outage_to_upstream(wire, status, error):
    # ValueError is the 422 the paste form shows; RuntimeError the 502.
    wire.on("GET", "/user/repos", {"message": "nope"}, status=status)

    with pytest.raises(error):
        _accounts({"token": "github_pat_x"})


def test_list_accounts_needs_a_token_and_a_repository_to_offer(wire):
    with pytest.raises(ValueError, match="token missing"):
        _accounts({})
    assert wire.calls == []  # refused before anything is sent

    wire.on("GET", "/user/repos", [])
    with pytest.raises(ValueError, match="no repositories"):
        _accounts({"token": "github_pat_x"})


# ---------------------------------------------------------------------------
# Token, repository and error rules
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(("status", "message", "says"), [
    (401, "Bad credentials", "expired or been revoked"),
    (301, "Moved Permanently", "renamed or transferred"),
    (403, "API rate limit exceeded for user ID 1.", "rate limit"),
    (429, "You have exceeded a secondary rate limit.", "rate limit"),
    (403, "Resource not accessible by personal access token", "Pull requests"),
    (403, "Although you appear to have the correct authorization credentials...", "approve"),
    (404, "Not Found", "not among those granted to Duct"),
])
def test_each_refusal_names_its_fix(status, message, says):
    error = gh.ApiError(status, f'{{"message": "{message}"}}')
    assert error.summary == message
    assert says in error.hint()


def test_a_rate_limit_is_not_retried_but_an_outage_is():
    """A limit wants a minute to an hour; a FetchData call should not hold a turn that long."""
    policy = gh._ENDPOINT.retry
    assert policy.delay(gh.ApiError(429, ""), 0) is None
    assert policy.delay(gh.ApiError(403, ""), 0) is None
    assert policy.delay(gh.ApiError(503, ""), 0) is not None


@pytest.mark.parametrize("repo", ["", "acme", "acme/app/extra", "../app", "acme/..", "acme/.", "acme/a b"])
def test_the_repository_must_be_owner_slash_name(repo):
    # It is spliced into a URL path, so anything else is refused before a request is built.
    with pytest.raises(ValueError, match="owner/name"):
        gh.require_repo({"repo": repo})


def test_a_real_repository_name_passes():
    assert gh.require_repo({"repo": "acme-co/app.js_v2"}) == ("acme-co", "app.js_v2")


# ---------------------------------------------------------------------------
# Totals
# ---------------------------------------------------------------------------

def test_duct_sums_the_line_stats_and_calls_a_capped_sum_a_floor():
    from agents.insights.totals import summarise
    from service.github.fetch import add_file_stats, commit_event, pull_request_event

    first, second = commit_event({"sha": "a" * 40}), commit_event({"sha": "b" * 40})
    add_file_stats(first, {"stats": {"additions": 10, "deletions": 2}, "files": [{}, {}, {}]})
    add_file_stats(second, {"stats": {"additions": 5, "deletions": 0}, "files": [{}]})
    beyond_the_cap = commit_event({"sha": "c" * 40})
    rows = [pull_request_event({"number": 1}), first, second, beyond_the_cap]

    out = summarise("github_work_events", {"rows": rows, "truncated": True})

    assert out["totals"] == {"files_changed": 4, "additions": 15, "deletions": 2}
    assert "floor" in out["totals_cover"]
