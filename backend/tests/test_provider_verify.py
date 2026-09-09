"""A key is verified by spending it, and a failure names what to fix.

``/providers/status`` resolves and never calls the vendor. Onboarding needs
the difference between a pasted key and a working one, and — the common
case on a fresh account — between a wrong key and an unfunded one. These pin
the classification (billing before status, so a 429 that says
``insufficient_quota`` is not "try again later") and the route's shape. The
model client is replaced at its seam.

No network.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import agents.core.lc as lc
import routes.providers as providers
import service.auth as auth_service
import service.provider_keys as provider_keys
from models.auth import User
from tests.fakes import AuthenticationError, RateLimitError


class _Answering:
    async def ainvoke(self, _prompt):
        return "ok"


class _Raising:
    def __init__(self, exc):
        self.exc = exc

    async def ainvoke(self, _prompt):
        raise self.exc


@pytest.mark.parametrize(
    ("exc", "code"),
    [
        (RateLimitError("429 insufficient_quota: You exceeded your current quota"), providers.VERIFY_NO_BILLING),
        (RuntimeError("Your credit balance is too low to access the Anthropic API"), providers.VERIFY_NO_BILLING),
        (AuthenticationError("401 Incorrect API key provided"), providers.VERIFY_INVALID_KEY),
        (RateLimitError("429 Too many requests"), providers.VERIFY_RATE_LIMITED),
        (ValueError("something else entirely"), providers.VERIFY_UNKNOWN),
    ],
)
def test_failures_classify_into_something_actionable(exc, code):
    assert providers._verify_code(exc) == code


@pytest.fixture
def client(monkeypatch):
    app = FastAPI()
    app.include_router(providers.router)
    app.dependency_overrides[auth_service.get_current_user] = lambda: User(email="v@example.com")
    app.dependency_overrides[providers.db_session] = lambda: None
    # The route imports this at call time from its home module, so patch it there.
    monkeypatch.setattr(provider_keys, "stored_provider_keys", lambda _db, _uid: {})
    return TestClient(app, raise_server_exceptions=False)


def test_a_working_key_answers_ok_with_the_model_it_used(client, monkeypatch):
    monkeypatch.setattr(lc, "resolve_chat_model", lambda *_a, **_k: _Answering())
    res = client.post("/providers/openai/verify", headers={"X-Provider-OpenAI": "sk-test"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ok"] is True
    assert body["model"].startswith("gpt-")
    assert "latency_ms" in body


def test_a_missing_key_says_so_without_calling_anyone(client, monkeypatch):
    def must_not_run(*_a, **_k):
        raise AssertionError("no key, no call")

    monkeypatch.setattr(lc, "resolve_chat_model", must_not_run)
    body = client.post("/providers/openai/verify").json()
    assert body == {"ok": False, "code": providers.VERIFY_MISSING_KEY, "detail": "No key supplied for this provider."}


def test_a_vendor_failure_comes_back_as_a_code_and_a_bounded_detail(client, monkeypatch):
    monkeypatch.setattr(
        lc, "resolve_chat_model", lambda *_a, **_k: _Raising(AuthenticationError("401 " + "x" * 500))
    )
    body = client.post("/providers/openai/verify", headers={"X-Provider-OpenAI": "sk-bad"}).json()
    assert body["ok"] is False
    assert body["code"] == providers.VERIFY_INVALID_KEY
    assert len(body["detail"]) <= 240
    assert "sk-bad" not in body["detail"]


def test_a_vendor_echoing_the_key_back_does_not_leak_it(client, monkeypatch):
    """The real risk the bounded-detail design carries.

    A provider that quotes an invalid key back in its own error text ("Invalid
    API key: sk-real-secret") would otherwise put a live credential straight
    into the JSON response and onto the onboarding screen — the same shape of
    bug ``error_payload``'s docstring says has happened once already, just in
    a route where `str(exc)` is deliberately shown rather than always hidden.
    """
    monkeypatch.setattr(
        lc,
        "resolve_chat_model",
        lambda *_a, **_k: _Raising(AuthenticationError("Invalid API key: sk-real-secret")),
    )
    body = client.post(
        "/providers/openai/verify", headers={"X-Provider-OpenAI": "sk-real-secret"}
    ).json()
    assert "sk-real-secret" not in body["detail"]
    assert "[key]" in body["detail"]


def test_an_unknown_provider_is_a_404(client):
    assert client.post("/providers/nope/verify").status_code == 404
