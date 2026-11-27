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
            compatible_key=None,
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
            compatible_key=None,
            openai_account_id=ACCOUNT_ID,
        )
    )
    assert plain[Provider.OPENAI] == "sk-proj-x"


def test_the_kill_switch_drops_a_plan_token_on_the_server(monkeypatch):
    """Hiding the card was the whole switch, so a shell already signed in kept
    sending its token and every run kept spending the plan. Off now means the
    backend never sees one; an API key in the same slot still passes."""
    import asyncio
    from types import SimpleNamespace

    monkeypatch.setattr(auth_service, "get_configs", lambda: SimpleNamespace(chatgpt_auth_enabled=False))

    def keys(openai_key):
        return asyncio.run(
            auth_service.get_user_provider_keys(
                anthropic_key=None,
                openai_key=openai_key,
                gemini_key="AIza-x",
                openrouter_key=None,
                xai_key=None,
                compatible_key=None,
                openai_account_id=ACCOUNT_ID,
            )
        )

    assert keys(ACCESS_TOKEN) == {Provider.GOOGLE_GENAI: "AIza-x"}
    assert keys("sk-proj-x")[Provider.OPENAI] == "sk-proj-x"


# ---------------------------------------------------------------------------
# Where it goes
# ---------------------------------------------------------------------------


def test_a_subscription_credential_builds_the_codex_client_with_its_headers():
    packed = codex.pack_subscription_credential(ACCESS_TOKEN, ACCOUNT_ID)
    llm = lc.resolve_chat_model(Provider.OPENAI, ModelName.GPT_6_LUNA, packed)
    from langchain_openai.chat_models.codex import _ChatOpenAICodex

    assert isinstance(llm, _ChatOpenAICodex)
    token = llm.token_provider.get_token()
    assert token.access_token == ACCESS_TOKEN
    assert token.account_id == ACCOUNT_ID
    assert llm.originator == codex.ORIGINATOR


def test_an_api_key_still_builds_the_public_api_client():
    assert type(lc.resolve_chat_model(Provider.OPENAI, ModelName.GPT_6_LUNA, "sk-proj-x")).__name__ == "ChatOpenAI"


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
    assert (openai["plan_type"], openai["plan_only_model"]) == ("plus", None)


def _token_on(plan: str) -> str:
    return _jwt({
        "exp": 4102444800,
        "https://api.openai.com/auth": {"chatgpt_account_id": ACCOUNT_ID, "chatgpt_plan_type": plan},
    })


@pytest.mark.parametrize(("plan", "served"), [
    ("go", "gpt-6-luna"), ("free", "gpt-6-luna"), ("plus", "gpt-6.1-sol"), ("pro", "gpt-6.1-sol"), ("", "gpt-6.1-sol"),
])
def test_a_plan_that_reaches_one_model_is_served_on_it(plan, served):
    """Free and Go reach only Luna through Codex, and a Go plan refused Sol
    live. Asking for Sol there failed every call before the fallback caught
    it, so the model is chosen from the plan before the first request."""
    packed = codex.pack_subscription_credential(_token_on(plan), ACCOUNT_ID)
    llm = lc.resolve_chat_model(Provider.OPENAI, ModelName.GPT_6_1_SOL, packed)
    assert llm.model_name == served


def test_status_names_the_one_model_a_go_plan_serves(client):
    body = client.get("/providers/status", headers={"X-Provider-OpenAI": _token_on("go")}).json()
    openai = next(row for row in body["providers"] if row["id"] == "openai")
    assert (openai["source"], openai["plan_type"], openai["plan_only_model"]) == ("subscription", "go", "gpt-6-luna")


# ---------------------------------------------------------------------------
# A session outlives its token
# ---------------------------------------------------------------------------


def _plan_token(exp: int, account: str = ACCOUNT_ID) -> str:
    return _jwt({"exp": exp, "https://api.openai.com/auth": {"chatgpt_account_id": account}})


def test_a_fresher_token_reaches_a_model_already_built():
    """A question card answered after the hour: the model built at the start
    of the run must spend the token the answer brought, not the dead one."""
    held = codex.pack_subscription_credential(_plan_token(2000000000), ACCOUNT_ID)
    fresh = codex.pack_subscription_credential(_plan_token(2000003600), ACCOUNT_ID)
    llm = lc.resolve_chat_model(Provider.OPENAI, ModelName.GPT_6_LUNA, held)

    assert codex.renew_subscription_credential(held, fresh)

    new_token = codex.unpack_subscription_credential(fresh).access_token
    assert llm.token_provider.get_access_token() == new_token
    assert llm.token_provider.get_token().access_token == new_token
    # A model built later from the string the runner started with gets it too.
    later = lc.resolve_chat_model(Provider.OPENAI, ModelName.GPT_6_LUNA, held)
    assert later.token_provider.get_access_token() == new_token


@pytest.mark.parametrize(
    "fresh",
    [
        pytest.param(_plan_token(2100000000, account="acct-someone-else"), id="another-account"),
        pytest.param(_plan_token(1900000000), id="older"),
        pytest.param("sk-proj-a-pasted-key", id="an-api-key"),
    ],
)
def test_a_run_never_moves_to_another_plan_or_an_older_token(fresh):
    held = codex.pack_subscription_credential(_plan_token(2000000000), ACCOUNT_ID)
    llm = lc.resolve_chat_model(Provider.OPENAI, ModelName.GPT_6_LUNA, held)
    before = llm.token_provider.get_access_token()

    assert not codex.renew_subscription_credential(held, fresh)
    assert llm.token_provider.get_access_token() == before


def test_a_message_hands_its_fresh_token_to_the_session():
    from types import SimpleNamespace

    from routes.agents import _renew_plan_credential

    held = codex.pack_subscription_credential(_plan_token(2000000000), ACCOUNT_ID)
    fresh = codex.pack_subscription_credential(_plan_token(2000003600), ACCOUNT_ID)
    session = SimpleNamespace(lent_keys={Provider.OPENAI: held})

    _renew_plan_credential(session, {Provider.OPENAI: fresh})
    assert session.lent_keys[Provider.OPENAI] == fresh
    # A message with no plan header leaves the session as it was.
    _renew_plan_credential(session, {})
    assert session.lent_keys[Provider.OPENAI] == fresh


# ---------------------------------------------------------------------------
# Prompt caching on the ChatGPT backend
# ---------------------------------------------------------------------------


def test_the_system_prompt_leads_the_input_where_the_cache_sees_it():
    """GPT-6.2 does not cache ``instructions``. Built through the real client,
    offline: what would go over the wire, not what we hope it is."""
    from langchain_core.messages import HumanMessage, SystemMessage

    packed = codex.pack_subscription_credential(ACCESS_TOKEN, ACCOUNT_ID)
    llm = lc.resolve_chat_model(Provider.OPENAI, ModelName.GPT_6_LUNA, packed, cache_key="conv-42")
    payload = llm._get_request_payload([SystemMessage("You are Duct."), HumanMessage("hi")])

    lead = payload["input"][0]
    assert lead["role"] == "developer"
    assert lead["content"] == "You are Duct."
    assert payload["instructions"] == codex._INSTRUCTIONS_POINTER
    assert not any(item.get("role") == "system" for item in payload["input"])
    # One conversation, one cache: the key and the backend's affinity headers.
    assert payload["prompt_cache_key"] == "conv-42"
    headers = payload["extra_headers"]
    assert headers["session-id"] == "conv-42"
    assert headers["thread-id"] == "conv-42"
    # The Codex headers are still there.
    assert headers["ChatGPT-Account-Id"] == ACCOUNT_ID
    assert headers["originator"] == codex.ORIGINATOR


def test_the_payload_rewrite_is_stable_across_steps():
    """Every step of a tool loop must open with the same bytes, or the cache
    misses. Running the rewrite on an already-shaped payload changes nothing."""
    payload = {"instructions": "You are Duct.", "input": [{"role": "user", "content": "hi"}]}
    once = codex.cache_friendly_payload(payload, "conv-42")
    snapshot = json.dumps(once, sort_keys=True)
    twice = codex.cache_friendly_payload(once, "conv-42")
    assert json.dumps(twice, sort_keys=True) == snapshot


def test_no_affinity_means_no_session_headers():
    payload = codex.cache_friendly_payload({"instructions": "x", "input": []}, "")
    assert "extra_headers" not in payload
    assert "prompt_cache_key" not in payload


def test_a_run_says_when_its_plan_answers_with_another_model():
    """The run-start event names the model that answers and the pick it
    overrode, so the transcript can say why a Go plan drafted on Luna."""
    from agents.core.codex import pack_subscription_credential
    from agents.models import ModelName, Provider, run_model_fields

    go = pack_subscription_credential(_token_on("go"), ACCOUNT_ID)
    fields = run_model_fields(Provider.OPENAI, ModelName.GPT_6_1_SOL, go)
    assert (fields["model"], fields["requested_model"], fields["plan"]) == ("gpt-6-luna", "gpt-6.1-sol", "go")
    assert fields["model_label"] != fields["requested_label"]

    plus = pack_subscription_credential(_token_on("plus"), ACCOUNT_ID)
    assert "requested_model" not in run_model_fields(Provider.OPENAI, ModelName.GPT_6_1_SOL, plus)
    assert "requested_model" not in run_model_fields(Provider.OPENAI, ModelName.GPT_6_1_SOL, "sk-test")
