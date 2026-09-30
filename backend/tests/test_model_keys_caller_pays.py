"""A customer's model calls run on the customer's key, never on Duct's.

Two paths spent this instance's own model keys on a request that did not ask
Duct to pay. The insight chat streamed from the server key with a prompt the
caller writes, and a guest counts as signed in, so anyone who opened /start had
a free model on Duct's account. And every audit ran its web searches on the
server's Gemini key whatever key the caller brought. Both now follow
``allow_server_provider_keys()``, the rule every other run already follows.
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import agents.core.lc as lc
import routes.chat as chat_routes
import service.auth as auth_service
from agents.engines import web_search_key
from agents.models import Provider
from models.auth import User
from server import _provider_key_required
from agents.engines import ProviderKeyRequired
from service.model_settings import DEFAULTS

SERVER_KEY = "duct-owned-key"


def _cfg(monkeypatch, *, app_env: str) -> None:
    cfg = SimpleNamespace(
        generate_engine="v1", generate_provider="", generate_model="",
        anthropic_api_key="", openai_api_key=SERVER_KEY, gemini_api_key=SERVER_KEY,
        openrouter_api_key="", xai_api_key="",
        duct_local=False, app_env=app_env,
    )
    monkeypatch.setattr("config.get_configs", lambda: cfg)


@pytest.fixture
def hosted(monkeypatch):
    _cfg(monkeypatch, app_env="production")


@pytest.fixture
def local(monkeypatch):
    _cfg(monkeypatch, app_env="local")


# ---------------------------------------------------------------------------
# The insight chat
# ---------------------------------------------------------------------------

@pytest.fixture
def model(monkeypatch):
    """The model the chat is handed, and the key it was built with."""
    seen: dict = {}

    class _Llm:
        async def astream(self, _messages):
            yield SimpleNamespace(content="ok")

    def resolve_chat_model(provider, model_name, api_key, temperature=1.0, **_kw):
        seen.update(provider=provider, api_key=api_key)
        return _Llm()

    monkeypatch.setattr(lc, "resolve_chat_model", resolve_chat_model)
    monkeypatch.setattr(chat_routes, "get_model_settings", lambda _uid: DEFAULTS)
    monkeypatch.setattr(chat_routes, "stored_keys_for", lambda _uid: {})
    return seen


def _chat(headers=None):
    app = FastAPI()
    app.include_router(chat_routes.router, prefix="/api/insights")
    app.add_exception_handler(ProviderKeyRequired, _provider_key_required)
    guest = User(id=uuid4(), email="guest-install@guest.getduct.ai")
    app.dependency_overrides[auth_service.get_current_user] = lambda: guest
    body = {"chat_payload": {"summary_text": "x"}, "message": "Write me a poem about anything."}
    return TestClient(app, raise_server_exceptions=False).post("/api/insights/chat", json=body, headers=headers or {})


def test_a_guest_with_no_key_gets_the_402_not_ducts_model(hosted, model):
    res = _chat()
    assert res.status_code == 402
    assert model == {}  # no model was ever built


def test_a_caller_with_a_key_chats_on_their_own(hosted, model):
    res = _chat({"X-Provider-OpenAI": "sk-callers-own"})
    assert res.status_code == 200 and '"token": "ok"' in res.text
    assert model == {"provider": Provider.OPENAI, "api_key": "sk-callers-own"}


def test_local_dev_still_chats_on_the_env_key(local, model):
    assert _chat().status_code == 200
    assert model["api_key"] == SERVER_KEY


# ---------------------------------------------------------------------------
# The audit's web search
# ---------------------------------------------------------------------------

def test_search_runs_on_the_callers_gemini_key_header_before_saved(hosted):
    header = {Provider.GOOGLE_GENAI: "g-header"}
    saved = {Provider.GOOGLE_GENAI: "g-saved"}
    assert web_search_key(header, saved) == "g-header"
    assert web_search_key({}, saved) == "g-saved"


def test_a_customer_run_without_a_gemini_key_does_not_search_on_ducts(hosted):
    assert web_search_key({Provider.OPENAI: "sk-own"}, {}) == ""


def test_a_run_duct_pays_for_searches_on_ducts_key(hosted):
    assert web_search_key({}, {}, billed_to_duct=True) == SERVER_KEY


def test_local_dev_searches_on_the_env_key(local):
    assert web_search_key({}, {}) == SERVER_KEY
