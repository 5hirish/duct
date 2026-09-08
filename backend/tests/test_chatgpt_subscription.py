"""A ChatGPT plan as a credential — the desktop shell's "Continue with ChatGPT".

The shell runs the OAuth and keeps the refresh token; the backend receives an
hour-long access token in the ordinary ``X-Provider-OpenAI`` header and the
account id beside it. These pin the three things that make that safe and
usable: the credential is told from an API key by its own shape, it reaches
the Codex client rather than the public API, and it can never be stored.

No network and no ChatGPT login required.
"""

from __future__ import annotations

import base64
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import agents.core.lc as lc
import routes.providers as providers
import service.auth as auth_service
import service.provider_keys as provider_keys
from agents.core import codex
from agents.engines import resolve_provider_key
from agents.models import ModelName, Provider
from models.auth import User
from tests.fakes import AuthenticationError, RateLimitError

ACCOUNT_ID = "acct-0123456789ab"


def _jwt(claims: dict) -> str:
    def seg(obj: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()

    return f"{seg({'alg': 'RS256', 'typ': 'JWT'})}.{seg(claims)}.sig"


ACCESS_TOKEN = _jwt({
    "exp": 4102444800,  # 2100-01-01: a token that does not expire mid-test
    "https://api.openai.com/auth": {"chatgpt_account_id": ACCOUNT_ID, "chatgpt_plan_type": "plus"},
})


# ---------------------------------------------------------------------------
# The credential's shape
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (ACCESS_TOKEN, True),
        (codex.pack_subscription_credential(ACCESS_TOKEN, ACCOUNT_ID), True),
        ("sk-proj-abc", False),
        ("eyJ-not-a-jwt", False),
        ("", False),
    ],
)
def test_a_chatgpt_access_token_is_recognised_by_its_shape(value, expected):
    assert codex.is_subscription_credential(value) is expected


def test_the_packed_credential_round_trips_both_halves():
    packed = codex.pack_subscription_credential(ACCESS_TOKEN, ACCOUNT_ID)
    cred = codex.unpack_subscription_credential(packed)
    assert cred.access_token == ACCESS_TOKEN
    assert cred.account_id == ACCOUNT_ID
    assert cred.plan_type == "plus"
    assert cred.expires_at.year == 2100


def test_a_bare_token_takes_its_account_id_from_its_own_claims():
    """The header is the contract; the claim is the fallback for a shell that
    did not send it, so the Codex request still carries an account."""
    cred = codex.unpack_subscription_credential(ACCESS_TOKEN)
    assert cred.account_id == ACCOUNT_ID


def test_the_auth_dependency_packs_token_and_account_together():
    """``get_user_provider_keys`` is the only place that sees two headers; from
    there on the credential is one string, like every other provider's."""
    import asyncio

    keys = asyncio.run(
        auth_service.get_user_provider_keys(
            anthropic_key=None,
            openai_key=ACCESS_TOKEN,
            gemini_key=None,
            openrouter_key=None,
            xai_key=None,
            openai_account_id=ACCOUNT_ID,
        )
    )
    assert codex.unpack_subscription_credential(keys[Provider.OPENAI]).account_id == ACCOUNT_ID

    plain = asyncio.run(
        auth_service.get_user_provider_keys(
            anthropic_key=None,
            openai_key="sk-proj-x",
            gemini_key=None,
            openrouter_key=None,
            xai_key=None,
            openai_account_id=ACCOUNT_ID,
        )
    )
    assert plain[Provider.OPENAI] == "sk-proj-x"


# ---------------------------------------------------------------------------
# Where it goes
# ---------------------------------------------------------------------------


def test_a_subscription_credential_builds_the_codex_client_with_its_headers():
    packed = codex.pack_subscription_credential(ACCESS_TOKEN, ACCOUNT_ID)
    llm = lc.resolve_chat_model(Provider.OPENAI, ModelName.GPT_5_6_LUNA, packed)
    assert type(llm).__name__ == "_ChatOpenAICodex"
    token = llm.token_provider.get_token()
    assert token.access_token == ACCESS_TOKEN
    assert token.account_id == ACCOUNT_ID
    assert llm.originator == codex.ORIGINATOR


def test_an_api_key_still_builds_the_public_api_client():
    assert type(lc.resolve_chat_model(Provider.OPENAI, ModelName.GPT_5_6_LUNA, "sk-proj-x")).__name__ == "ChatOpenAI"


def test_the_credential_never_refreshes_on_the_backend():
    """The refresh token is the user's whole account. The backend does not
    have it and the provider must not pretend to: the same token every time."""
    cred = codex.unpack_subscription_credential(ACCESS_TOKEN)
    provider = codex._HeaderTokenProvider(cred)
    assert provider.get_token() is provider.get_token()
    assert provider.get_token().refresh_token == codex._REFRESH_HELD_BY_SHELL


def test_resolve_provider_key_names_the_source_as_the_users_plan():
    resolved = resolve_provider_key(Provider.OPENAI, {Provider.OPENAI: ACCESS_TOKEN})
    assert resolved.source == "subscription"
    assert resolved.billed_to_duct is False


# ---------------------------------------------------------------------------
# The routes
# ---------------------------------------------------------------------------


@pytest.fixture
def client(monkeypatch):
    app = FastAPI()
    app.include_router(providers.router)
    app.dependency_overrides[auth_service.get_current_user] = lambda: User(email="v@example.com")
    app.dependency_overrides[auth_service.get_current_user_optional] = lambda: None
    app.dependency_overrides[providers.db_session] = lambda: None
    monkeypatch.setattr(provider_keys, "stored_provider_keys", lambda _db, _uid: {})
    monkeypatch.setattr(provider_keys, "has_stored_provider_keys", lambda _db, _uid: set())
    monkeypatch.setattr(providers, "has_stored_provider_keys", lambda _db, _uid: set())
    return TestClient(app, raise_server_exceptions=False)


def test_a_chatgpt_sign_in_cannot_be_remembered_on_duct(client, monkeypatch):
    def must_not_store(*_a, **_k):
        raise AssertionError("stored a subscription credential")

    monkeypatch.setattr(providers, "save_provider_key", must_not_store)
    res = client.put("/providers/openai/key", json={"api_key": ACCESS_TOKEN})
    assert res.status_code == 422
    assert "keychain" in res.json()["detail"]


class _Raising:
    def __init__(self, exc):
        self.exc = exc

    async def ainvoke(self, _prompt):
        raise self.exc


class _PermissionDenied(Exception):
    status_code = 403


@pytest.mark.parametrize(
    ("exc", "code"),
    [
        (RateLimitError("429 usage limit reached for this plan"), providers.VERIFY_SUBSCRIPTION_QUOTA),
        (AuthenticationError("401 token expired"), providers.VERIFY_SUBSCRIPTION_REVOKED),
        (_PermissionDenied("403 originator not allowed"), providers.VERIFY_SUBSCRIPTION_BLOCKED),
    ],
)
def test_verify_names_subscription_failures_by_their_fix(client, monkeypatch, exc, code):
    monkeypatch.setattr(lc, "resolve_chat_model", lambda *_a, **_k: _Raising(exc))
    body = client.post(
        "/providers/openai/verify",
        headers={"X-Provider-OpenAI": ACCESS_TOKEN, "X-OpenAI-Account-Id": ACCOUNT_ID},
    ).json()
    assert body["ok"] is False
    assert body["code"] == code


def test_status_reports_the_plan_as_the_source_and_the_kill_switch(client):
    body = client.get(
        "/providers/status",
        headers={"X-Provider-OpenAI": ACCESS_TOKEN, "X-OpenAI-Account-Id": ACCOUNT_ID},
    ).json()
    openai = next(row for row in body["providers"] if row["id"] == "openai")
    assert openai["source"] == "subscription"
    assert openai["reachable"] is True
    assert body["chatgpt_auth_enabled"] is True
