"""The session-scoped FetchData cache and the dead-token status.

The verifier runs in its own context and cannot see what the analyst just
fetched, so it fetched it again — a 45-second GA4 report, twice, in the run
this was measured on. Same tool objects, one cache.
"""

from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

import pytest

from agents.insights import data_tools


def _fetch_tool(monkeypatch, calls: list, result: dict):
    monkeypatch.setattr(data_tools, "fetch_entity", lambda entity_id, **kw: calls.append(entity_id) or dict(result))
    tools = data_tools.build_data_tools_lc(uuid4(), user_id=uuid4(), compress=False)
    return next(t for t in tools if t.name == "FetchData")


@pytest.mark.asyncio
async def test_a_repeated_pull_is_served_from_the_session_cache(monkeypatch):
    calls: list[str] = []
    fetch = _fetch_tool(monkeypatch, calls, {"status": "ok", "data": {"rows": [1]}})
    first = await fetch.ainvoke({"entity_id": "ga4_landing_pages", "date_from": "", "date_to": ""})
    second = await fetch.ainvoke({"entity_id": "ga4_landing_pages"})
    assert first == second
    assert calls == ["ga4_landing_pages"]
    # A different window is a different question.
    await fetch.ainvoke({"entity_id": "ga4_landing_pages", "date_from": "2026-09-01", "date_to": "2026-09-07"})
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_failures_are_not_cached(monkeypatch):
    calls: list[str] = []
    fetch = _fetch_tool(monkeypatch, calls, {"status": "fetch_failed", "message": "nope"})
    await fetch.ainvoke({"entity_id": "ga4_landing_pages"})
    await fetch.ainvoke({"entity_id": "ga4_landing_pages"})
    assert len(calls) == 2


def test_an_expired_grant_is_a_reauth_status_not_a_fetch_failure(monkeypatch):
    from google.auth.exceptions import RefreshError

    from agents.insights import fetchers

    spec = next(iter(fetchers.fetch_specs().values()))

    def boom(*_a, **_k):
        raise RefreshError("invalid_grant: Token has been expired or revoked.")

    monkeypatch.setattr(fetchers, "fetch_specs", lambda: {spec.entity_id: replace(spec, call=boom)})

    class _Source:
        status = "bound"
        account_id = "123"

    monkeypatch.setattr("service.connector_access.get_data_source", lambda *a, **k: _Source())
    monkeypatch.setattr("service.connector_access.resolve_read_credentials", lambda *a, **k: {"refresh_token": "r", "blob": 1})
    monkeypatch.setattr("service.connector_access._GOOGLE_SHAPED", set())
    result = fetchers.fetch_entity(spec.entity_id, user_id=uuid4(), project_id=None)
    assert result["status"] == "reauth_required"
    assert "reconnect" in result["message"]
