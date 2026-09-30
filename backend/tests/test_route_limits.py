"""The limits on routes that spend before a caller has proven much.

Anonymous routes and guest-reachable ones cost Duct a row, a crawl, an
outbound request or a model call on its own key. Each test here pins one limit
to its behaviour: under it the route answers as it always did, past it the
answer is a 429 with a Retry-After, and a different caller is untouched. The
limiters are swapped for small ones, so no threshold is asserted and a tuning
change breaks nothing here.

The address tests come first because every per-address limit is only as good
as the address it is keyed on: behind Railway's proxy ``request.client`` is the
proxy, and a key the caller can choose is no key at all.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

import agents.core.lc as lc
from agents.core.session import _sessions, close_session, get_session, live_session_count
from models.auth import User
import routes.agents as agent_routes
import routes.audit_prefetch as audit_prefetch
import routes.auth as connector_auth
import routes.chat as insight_chat
import routes.lead_magnet as lead_magnet
import routes.signin as signin
import service.auth as auth_service
from service.model_settings import DEFAULTS
from service.ratelimit import RateLimit, client_address

AUDIT = "audit_seo"
LIVE_TOKEN = "live-lead-token"
HOME = "81.2.69.142"
ELSEWHERE = "81.2.69.160"


def _small(limit: int = 2) -> RateLimit:
    return RateLimit(limit=limit, window_seconds=600.0)


def _roomy() -> RateLimit:
    return RateLimit(limit=1000, window_seconds=600.0)


def _user() -> User:
    return User(email=f"{uuid.uuid4().hex}@example.com")


def _at(address: str) -> dict[str, str]:
    """Headers as Railway's edge would set them. TestClient's peer is not an IP,
    so it reads as a proxy on our side and the header is believed."""
    return {"X-Real-IP": address}


def _assert_limited(res) -> None:
    assert res.status_code == 429, res.text
    assert int(res.headers["Retry-After"]) >= 1


# ---------------------------------------------------------------------------
# Whose address it is
# ---------------------------------------------------------------------------

def _request(peer: str, **headers: str) -> Request:
    return Request({
        "type": "http",
        "client": (peer, 443),
        "headers": [(k.replace("_", "-").encode(), v.encode()) for k, v in headers.items()],
    })


def test_behind_railway_the_caller_is_the_edges_x_real_ip():
    assert client_address(_request("100.64.0.7", x_real_ip=HOME)) == HOME


def test_behind_cloudflare_the_caller_is_cf_connecting_ip():
    req = _request("100.64.0.7", x_real_ip="172.70.1.1", cf_connecting_ip=HOME)
    assert client_address(req) == HOME


def test_a_caller_cannot_choose_its_own_address():
    # A public peer is the caller itself; its X-Real-IP is its own say-so.
    assert client_address(_request(ELSEWHERE, x_real_ip=HOME)) == ELSEWHERE
    # Arriving from outside Cloudflare, CF-Connecting-IP is whatever was typed.
    req = _request("100.64.0.7", x_real_ip=ELSEWHERE, cf_connecting_ip=HOME)
    assert client_address(req) == ELSEWHERE


# ---------------------------------------------------------------------------
# Public entry points, per address
# ---------------------------------------------------------------------------

def test_the_lead_magnet_router_shares_one_budget_per_address(monkeypatch):
    monkeypatch.setattr(lead_magnet, "_LEAD_MAGNET_LIMIT", _small())
    app = FastAPI()
    app.include_router(lead_magnet.router, prefix="/api/lead-magnet")
    client = TestClient(app, raise_server_exceptions=False)

    def check(address):
        # An internal address: refused by the SSRF guard, so nothing leaves.
        return client.get(
            "/api/lead-magnet/check-url", params={"url": "http://127.0.0.1/"}, headers=_at(address)
        )

    for _ in range(2):
        assert check(HOME).json() == {"ok": False, "reason": "That doesn't look like a valid public URL."}
    _assert_limited(check(HOME))
    # The router holds the limit, so the other endpoints are spent with it.
    _assert_limited(client.post("/api/lead-magnet/validate", json={"token": "t"}, headers=_at(HOME)))
    assert check(ELSEWHERE).status_code == 200


@pytest.mark.parametrize("module, limiter, path", [
    (signin, "_SIGNIN_START_LIMIT", "/auth/signin/google/authorize"),
    (connector_auth, "_CONNECT_START_LIMIT", "/auth/connectors/not-a-connector/oauth/authorize"),
])
def test_oauth_starts_are_limited_per_address(monkeypatch, module, limiter, path):
    """Each start writes an OAuth state row with nobody signed in behind it.
    Under the limit the route answers however it would (unconfigured here), so
    the assertion is only that it was reached."""
    monkeypatch.setattr(module, limiter, _small())
    app = FastAPI()
    app.include_router(module.router)
    client = TestClient(app, raise_server_exceptions=False)

    for _ in range(2):
        assert client.get(path, headers=_at(HOME), follow_redirects=False).status_code != 429
    _assert_limited(client.get(path, headers=_at(HOME), follow_redirects=False))
    assert client.get(path, headers=_at(ELSEWHERE), follow_redirects=False).status_code != 429


def test_the_crawl_prefetch_is_limited_per_address_as_well_as_per_user(monkeypatch):
    """A guest is a user anyone can mint, so one address holding many guests
    must not multiply the per-user crawl allowance."""
    monkeypatch.setattr(audit_prefetch, "_PREFETCH_ADDRESS_LIMIT", _small())
    monkeypatch.setattr(audit_prefetch, "_PREFETCH_LIMIT", _roomy())

    async def refuse(*_a, **_k):
        raise ValueError("not public")  # the SSRF guard's answer; no crawl starts

    monkeypatch.setattr(audit_prefetch, "start_prefetch", refuse)
    app = FastAPI()
    app.include_router(audit_prefetch.router, prefix="/api")
    client = TestClient(app, raise_server_exceptions=False)

    def prefetch(address):
        app.dependency_overrides[auth_service.get_current_user] = _user  # a fresh guest each call
        return client.post("/api/audit/prefetch", json={"url": "example.com"}, headers=_at(address))

    for _ in range(2):
        assert prefetch(HOME).status_code == 422
    _assert_limited(prefetch(HOME))
    assert prefetch(ELSEWHERE).status_code == 422


# ---------------------------------------------------------------------------
# Starting an agent run
# ---------------------------------------------------------------------------

@pytest.fixture
def runs(monkeypatch):
    """Session creation with the pipeline stubbed out and every limiter fresh.

    Yields a function that starts a run as ``user`` (None for the anonymous
    teaser) from ``address``. Whatever the tests register is closed after.
    """
    for name in (
        "_SESSION_STARTS_PER_USER", "_SESSION_STARTS_PER_ADDRESS", "_TEASER_RUNS_PER_TOKEN",
        "_TEASER_RUNS_PER_ADDRESS", "_TEASER_FOLLOWUPS_PER_SESSION",
    ):
        monkeypatch.setattr(agent_routes, name, _roomy())

    async def no_pipeline(*_a, **_k):
        return None

    monkeypatch.setattr(agent_routes, "_dispatch_start", no_pipeline)
    monkeypatch.setattr(agent_routes, "lead_token_is_live", lambda token: token == LIVE_TOKEN)

    app = FastAPI()
    app.include_router(agent_routes.router, prefix="/api/agents")
    client = TestClient(app, raise_server_exceptions=False)
    client.as_user = lambda user: app.dependency_overrides.__setitem__(
        auth_service.get_current_user_optional, lambda: user
    )

    def start(user, *, address=HOME, teaser_token=None):
        client.as_user(user)
        body = {"url": "https://example.com"}
        if teaser_token is not None:
            body.update(lead_magnet=True, lead_token=teaser_token)
        return client.post(f"/api/agents/{AUDIT}/sessions", json=body, headers=_at(address))

    start.client = client
    before = set(_sessions)
    yield start
    for sid in set(_sessions) - before:
        close_session(sid)


def test_a_signed_in_user_starts_a_run_as_before(runs):
    user = _user()
    res = runs(user)
    assert res.status_code == 200, res.text
    session = get_session(res.json()["session_id"])
    assert session.user_id == user.id
    assert session.duct_funded is False


def test_run_starts_are_limited_per_user(runs, monkeypatch):
    monkeypatch.setattr(agent_routes, "_SESSION_STARTS_PER_USER", _small())
    alice, bob = _user(), _user()
    for _ in range(2):
        assert runs(alice).status_code == 200
    _assert_limited(runs(alice))
    assert runs(bob).status_code == 200


def test_run_starts_are_limited_per_address(runs, monkeypatch):
    monkeypatch.setattr(agent_routes, "_SESSION_STARTS_PER_ADDRESS", _small())
    for _ in range(2):
        assert runs(_user()).status_code == 200
    _assert_limited(runs(_user()))
    assert runs(_user(), address=ELSEWHERE).status_code == 200


def test_a_user_holds_only_so_many_live_runs(runs, monkeypatch):
    monkeypatch.setattr(agent_routes, "_MAX_LIVE_SESSIONS_PER_USER", 2)
    user = _user()
    first = runs(user).json()["session_id"]
    assert runs(user).status_code == 200
    _assert_limited(runs(user))
    assert runs(_user()).status_code == 200  # someone else's runs are theirs

    runs.client.as_user(user)
    assert runs.client.delete(f"/api/agents/{AUDIT}/sessions/{first}").status_code == 200
    assert runs(user).status_code == 200


def test_a_failed_start_does_not_hold_a_slot(runs, monkeypatch):
    """A 402 or 422 at dispatch leaves nothing running; a session left behind
    would count against the cap until the pruner got to it."""

    async def refuse(*_a, **_k):
        raise HTTPException(422, "bad config")

    monkeypatch.setattr(agent_routes, "_dispatch_start", refuse)
    user = _user()
    assert runs(user).status_code == 422
    assert live_session_count(user.id) == 0


# ---------------------------------------------------------------------------
# The teaser: Duct's key, so held to the token and the address
# ---------------------------------------------------------------------------

def test_teaser_runs_are_limited_per_lead_token(runs, monkeypatch):
    monkeypatch.setattr(agent_routes, "_TEASER_RUNS_PER_TOKEN", _small())
    for address in (HOME, ELSEWHERE):
        assert runs(None, address=address, teaser_token=LIVE_TOKEN).status_code == 200
    _assert_limited(runs(None, address="81.2.69.161", teaser_token=LIVE_TOKEN))


def test_teaser_runs_are_limited_per_address(runs, monkeypatch):
    monkeypatch.setattr(agent_routes, "_TEASER_RUNS_PER_ADDRESS", _small())
    for _ in range(2):
        assert runs(None, teaser_token=LIVE_TOKEN).status_code == 200
    _assert_limited(runs(None, teaser_token=LIVE_TOKEN))
    assert runs(None, address=ELSEWHERE, teaser_token=LIVE_TOKEN).status_code == 200


def test_teaser_follow_ups_are_capped_but_a_users_own_run_is_not(runs, monkeypatch):
    monkeypatch.setattr(agent_routes, "_TEASER_FOLLOWUPS_PER_SESSION", _small())

    def ask(user, session_id):
        runs.client.as_user(user)
        return runs.client.post(
            f"/api/agents/{AUDIT}/sessions/{session_id}/messages",
            json={"type": "chat", "content": "and the title tags?"},
        )

    teaser = runs(None, teaser_token=LIVE_TOKEN).json()["session_id"]
    assert get_session(teaser).duct_funded is True
    for _ in range(2):
        assert ask(None, teaser).status_code == 200
    _assert_limited(ask(None, teaser))

    user = _user()
    own = runs(user).json()["session_id"]
    for _ in range(3):
        assert ask(user, own).status_code == 200


# ---------------------------------------------------------------------------
# Insight chat: reachable by any guest, and each call is a model call
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("limiter, same_user", [
    ("_CHAT_PER_USER", True),
    ("_CHAT_PER_ADDRESS", False),
])
def test_insight_chat_is_limited(monkeypatch, limiter, same_user):
    monkeypatch.setattr(insight_chat, "_CHAT_PER_USER", _roomy())
    monkeypatch.setattr(insight_chat, "_CHAT_PER_ADDRESS", _roomy())
    monkeypatch.setattr(insight_chat, limiter, _small(1))

    class _Llm:
        async def astream(self, _messages):
            yield SimpleNamespace(content="fine")

    # The chat runs on the caller's key (routes/chat.py); the header below
    # is that key, so what is under test is the limit, not key resolution.
    monkeypatch.setattr(lc, "resolve_chat_model", lambda *_a, **_kw: _Llm())
    monkeypatch.setattr(insight_chat, "get_model_settings", lambda _uid: DEFAULTS)
    monkeypatch.setattr(insight_chat, "stored_keys_for", lambda _uid: {})
    app = FastAPI()
    app.include_router(insight_chat.router, prefix="/api/insights")
    client = TestClient(app, raise_server_exceptions=False)
    alice = _user()

    def ask(user, address=HOME):
        app.dependency_overrides[auth_service.get_current_user] = lambda: user
        return client.post(
            "/api/insights/chat",
            json={"chat_payload": {}, "message": "why did CPA move?"},
            headers={**_at(address), "X-Provider-OpenAI": "sk-callers-own"},
        )

    assert ask(alice).status_code == 200
    _assert_limited(ask(alice if same_user else _user()))
    # The other key still has room: a new user for the per-user limit, a new
    # address for the per-address one.
    assert ask(_user(), address=ELSEWHERE).status_code == 200
