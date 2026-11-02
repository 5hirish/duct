"""A user's own OpenAI-compatible endpoint: vLLM, llama.cpp, LM Studio, or a
host of open-weight models.

What is pinned here is what the generic key path would get wrong for it: a
credential that is three things packed into one (address, key, chosen
models), model ids that look like OpenRouter slugs, an address the user typed
that Duct then calls, and a model that may answer without ever calling a tool.

The server is an httpx2 transport answering ``/models``; the model is a fake that
does or does not call the tool it is handed. No socket opens.
"""

from __future__ import annotations

import socket

import httpx2
import pytest
from langchain_core.messages import AIMessage

import agents.core.lc as lc
import config as config_module
from agents.core import codex
from agents.engines import resolve_job_run
from agents.models import COMPATIBLE_MODEL_PREFIX, Provider, provider_of
from agents.tiers import Job
from config import Configs
from service import compatible

# Imported here, never first inside a test: both bind `get_configs` when they
# load, and a test that patches it first leaves the patch wired into the
# API-key check for every test after (test_engines_status got 403s).
import routes.providers  # noqa: E402,F401
import service.auth  # noqa: E402,F401
from service.crawl.fetcher import SSRFError

PUBLIC = "https://api.models.example/v1"
LOCAL = "http://localhost:1234/v1"
QWEN = "Qwen/Qwen3-32B"

_LISTING = {
    "object": "list",
    "data": [
        {"id": QWEN, "object": "model", "max_model_len": 40960},
        {"id": "meta-llama/Llama-4-Scout", "object": "model", "context_window": 131072},
        {"id": "BAAI/bge-large-en-v1.5", "object": "model"},
        {"id": "whisper-large-v3", "object": "model"},
        {"id": "open-diffusion", "object": "model", "type": "image"},
        {"id": "small-chat", "object": "model", "type": "chat"},
    ],
}


def _configure(monkeypatch, *, private: bool = False) -> Configs:
    """The hosted shape unless ``private``: no server keys, no private addresses."""
    cfg = Configs(generate_provider="google_genai", app_env="production", private_model_endpoints=private)
    monkeypatch.setattr(config_module, "get_configs", lambda: cfg)
    monkeypatch.setattr(config_module, "allow_server_provider_keys", lambda: False)
    return cfg


def _resolves_to(monkeypatch, address: str) -> None:
    """Every hostname resolves to ``address``, for the resolved-address check."""
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda host, *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))]
    )


def _credential(base_url: str = PUBLIC, key: str = "sk-endpoint", models=((QWEN, 40960),)) -> str:
    return compatible.pack(
        compatible.Endpoint(base_url, key, tuple(compatible.EndpointModel(m, n) for m, n in models))
    )


# ---------------------------------------------------------------------------
# The credential and the model ids
# ---------------------------------------------------------------------------


def test_a_server_model_id_is_the_endpoints_even_with_a_slash():
    """vLLM names a model by its Hugging Face repo; without the namespace it
    is an OpenRouter slug and would spend the OpenRouter key."""
    assert provider_of(f"{COMPATIBLE_MODEL_PREFIX}{QWEN}") is Provider.OPENAI_COMPATIBLE
    assert provider_of(QWEN) is Provider.OPENROUTER


def test_the_credential_round_trips_and_nothing_else_reads_as_one():
    endpoint = compatible.unpack(_credential())
    assert endpoint.base_url == PUBLIC and endpoint.api_key == "sk-endpoint"
    assert [(m.id, m.context_length) for m in endpoint.models] == [(QWEN, 40960)]
    for junk in ("sk-endpoint", "oaic1.not-base64!", "oaic1." + "e30", ""):
        assert compatible.unpack(junk) is None


# The same fixture as app/src/lib/__tests__/endpointCredential.test.js: the
# browser packs what this unpacks, so the two must agree byte for byte.
BROWSER_PACKED = "oaic1.eyJ1IjoiaHR0cHM6Ly9hcGkudG9nZXRoZXIueHl6L3YxIiwiayI6InNrLXRnIiwibSI6W1siUXdlbi9Rd2VuMy0zMkIiLDQwOTYwXSxbInNtYWxsLWNoYXQiLDBdXX0"


def test_the_browser_and_the_server_pack_alike():
    endpoint = compatible.Endpoint(
        "https://api.together.xyz/v1",
        "sk-tg",
        (compatible.EndpointModel(QWEN, 40960), compatible.EndpointModel("small-chat", 0)),
    )
    assert compatible.pack(endpoint) == BROWSER_PACKED
    assert compatible.unpack(BROWSER_PACKED) == endpoint


def test_a_packed_endpoint_is_usable_only_in_its_own_slot():
    packed = _credential()
    assert codex.is_usable_credential(Provider.OPENAI_COMPATIBLE, packed)
    assert not codex.is_usable_credential(Provider.OPENAI_COMPATIBLE, "sk-a-bare-key")
    assert not codex.is_usable_credential(Provider.OPENAI, packed)


# ---------------------------------------------------------------------------
# The address
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("pasted", "stored"),
    [
        ("https://api.models.example/v1/", PUBLIC),
        ("https://api.models.example/v1/chat/completions", PUBLIC),
        ("api.models.example/v1", PUBLIC),
        ("https://API.models.example/v1/models", PUBLIC),
    ],
)
def test_what_people_paste_becomes_the_base_the_sdk_wants(pasted, stored):
    assert compatible.canonical_base_url(pasted, private_ok=False) == stored


@pytest.mark.parametrize(
    "address",
    [
        "http://api.models.example/v1",  # a key in the clear
        "http://localhost:1234/v1",
        "https://10.0.0.5/v1",
        "https://169.254.169.254/latest",
        "https://user:pass@api.models.example/v1",
        "ftp://api.models.example",
    ],
)
def test_a_hosted_instance_refuses_what_it_should_not_call(address):
    with pytest.raises(compatible.UnsafeEndpoint):
        compatible.canonical_base_url(address, private_ok=False)


def test_a_private_address_is_fine_where_the_network_is_the_users_own():
    assert compatible.canonical_base_url("http://localhost:1234/v1", private_ok=True) == LOCAL


def test_private_addresses_follow_the_instance(monkeypatch):
    assert not compatible.private_allowed(Configs(app_env="production"))
    assert compatible.private_allowed(Configs(app_env="production", private_model_endpoints=True))
    assert compatible.private_allowed(Configs(app_env="local"))


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


class Wire:
    """The endpoint's server, as an httpx2 transport under discovery: what it
    answers, and every request that reached it."""

    def __init__(self, body=None, status: int = 200, content: bytes | None = None) -> None:
        self.body, self.status, self.content = body, status, content
        self.calls: list[httpx2.Request] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.calls.append(request)
        if self.content is not None:
            return httpx2.Response(self.status, content=self.content)
        return httpx2.Response(self.status, json=self.body)

    def install(self, monkeypatch) -> "Wire":
        monkeypatch.setattr(compatible, "_list_transport", lambda private_ok: httpx2.MockTransport(self))
        return self


@pytest.fixture
def server(monkeypatch):
    _configure(monkeypatch)
    return Wire(_LISTING).install(monkeypatch)


def test_discovery_lists_chat_models_with_their_context(server):
    models = compatible.discover(PUBLIC, "sk-endpoint", private_ok=False)
    assert [(m.id, m.context_length) for m in models] == [
        ("meta-llama/Llama-4-Scout", 131072),
        (QWEN, 40960),
        ("small-chat", 0),
    ]
    assert str(server.calls[0].url) == f"{PUBLIC}/models"
    assert server.calls[0].headers["Authorization"] == "Bearer sk-endpoint"


@pytest.mark.parametrize(
    ("status", "body", "code"),
    [
        (401, {"error": "nope"}, compatible.CODE_INVALID_KEY),
        (404, {"error": "no"}, compatible.CODE_NOT_COMPATIBLE),
        (200, {"data": [{"id": "whisper-1"}]}, compatible.CODE_NO_MODELS),
        (200, {"models": "?"}, compatible.CODE_NOT_COMPATIBLE),
        (502, {"error": "down"}, compatible.CODE_UNREACHABLE),
    ],
)
def test_discovery_says_what_went_wrong(monkeypatch, status, body, code):
    Wire(body, status=status).install(monkeypatch)
    with pytest.raises(compatible.EndpointError) as caught:
        compatible.discover(PUBLIC, private_ok=False)
    assert caught.value.code == code


def test_a_listing_that_never_ends_costs_a_bounded_read(monkeypatch):
    """The server is one the caller named; a reply past the cap is abandoned
    rather than held in memory whole."""
    Wire(content=b" " * (compatible._LIST_MAX_BYTES + 1)).install(monkeypatch)
    with pytest.raises(compatible.EndpointError) as caught:
        compatible.discover(PUBLIC, private_ok=False)
    assert caught.value.code == compatible.CODE_NOT_COMPATIBLE


@pytest.fixture
def sent(monkeypatch):
    """What the pinned transport hands to the network, which never opens."""
    seen: list[httpx2.Request] = []

    def record(self, request):
        seen.append(request)
        return httpx2.Response(200, json=_LISTING, request=request)

    monkeypatch.setattr(httpx2.HTTPTransport, "handle_request", record)
    return seen


def test_a_request_connects_to_the_address_that_was_checked(monkeypatch, sent):
    """Resolved once and pinned: a second lookup a hostile DNS server could
    answer differently never happens, and TLS still checks the real name."""
    _resolves_to(monkeypatch, "93.184.216.34")
    compatible.discover(PUBLIC, private_ok=False)
    (request,) = sent
    assert request.url.host == "93.184.216.34"
    assert request.headers["Host"] == "api.models.example"
    assert request.extensions["sni_hostname"] == "api.models.example"


def test_a_public_name_that_resolves_inside_is_refused_before_any_request(monkeypatch, sent):
    _resolves_to(monkeypatch, "10.0.0.5")
    with pytest.raises(compatible.EndpointError) as caught:
        compatible.discover(PUBLIC, private_ok=False)
    assert caught.value.code == compatible.CODE_REFUSED
    assert sent == []


def test_every_model_request_is_pinned_too(monkeypatch, sent):
    """The model client takes the same transport, so a chat call is held to
    the same rule as the listing, redirects included."""
    client = compatible.guarded_http_clients(private_ok=False)["http_client"]
    _resolves_to(monkeypatch, "10.0.0.5")
    with pytest.raises(SSRFError):
        client.post(f"{PUBLIC}/chat/completions", json={})
    _resolves_to(monkeypatch, "93.184.216.34")
    client.post(f"{PUBLIC}/chat/completions", json={})
    with pytest.raises(SSRFError):
        client.post("http://api.models.example/v1/chat/completions", json={})
    assert [r.url.host for r in sent] == ["93.184.216.34"]
    assert compatible.guarded_http_clients(private_ok=True) == {}


# ---------------------------------------------------------------------------
# The transport
# ---------------------------------------------------------------------------


def test_the_model_runs_at_the_users_address_in_its_reported_window(monkeypatch):
    _configure(monkeypatch)
    llm = lc.resolve_chat_model(Provider.OPENAI_COMPATIBLE, f"{COMPATIBLE_MODEL_PREFIX}{QWEN}", _credential())
    assert llm.openai_api_base == PUBLIC
    assert llm.model_name == QWEN
    assert llm.openai_api_key.get_secret_value() == "sk-endpoint"
    assert llm.profile["max_input_tokens"] == 40960
    assert lc.duct_window(f"{COMPATIBLE_MODEL_PREFIX}{QWEN}") == 40960


def test_a_model_that_is_not_theirs_takes_the_first_they_chose(monkeypatch):
    """A run that lands here with no tier naming this provider."""
    _configure(monkeypatch, private=True)
    credential = _credential(LOCAL, key="", models=(("small-chat", 0), (QWEN, 40960)))
    llm = lc.resolve_chat_model(Provider.OPENAI_COMPATIBLE, "gemini-3.8-flash", credential)
    assert llm.model_name == "small-chat"
    assert llm.profile["max_input_tokens"] == compatible.DEFAULT_CONTEXT_LENGTH
    # A key-less server is sent a placeholder rather than refusing to build.
    assert llm.openai_api_key.get_secret_value()


def test_a_typed_answer_is_held_to_its_schema_with_a_tool_call_behind_it(monkeypatch):
    """Constrained decoding first, because a small model answers in words to
    a forced tool call; a server that refuses the format falls back to the
    tool call connecting it proved."""
    from langchain_core.runnables import RunnableLambda
    from pydantic import BaseModel

    class Answer(BaseModel):
        text: str

    _configure(monkeypatch)
    llm = lc.resolve_chat_model(Provider.OPENAI_COMPATIBLE, f"{COMPATIBLE_MODEL_PREFIX}{QWEN}", _credential())
    methods = []

    def structured(self, schema, *, method, **kw):
        methods.append(method)
        if method == "json_schema":
            def refuse(_):
                raise ValueError("400: response_format json_schema is not supported")

            return RunnableLambda(refuse)
        return RunnableLambda(lambda _: Answer(text="from the tool call"))

    monkeypatch.setattr(type(llm), "with_structured_output", structured)
    answer = lc.structured_output(llm, Answer).invoke("hi")
    assert methods == ["json_schema", "function_calling"]
    assert answer == Answer(text="from the tool call")


def test_usage_keeps_the_endpoint_namespace():
    """The server reports its bare id, which reads as an OpenRouter slug."""
    configured = f"{COMPATIBLE_MODEL_PREFIX}{QWEN}"
    assert lc._served_model_id(QWEN, configured) == configured


# ---------------------------------------------------------------------------
# A run
# ---------------------------------------------------------------------------


def test_a_lone_endpoint_runs_on_the_first_model_they_chose(monkeypatch):
    _configure(monkeypatch)
    run = resolve_job_run(Job.CHAT, user_keys={Provider.OPENAI_COMPATIBLE: _credential()})
    assert run.provider is Provider.OPENAI_COMPATIBLE
    assert run.model == f"{COMPATIBLE_MODEL_PREFIX}{QWEN}"
    assert run.source == "user"


def test_a_remembered_endpoint_serves_a_background_run(monkeypatch):
    _configure(monkeypatch)
    run = resolve_job_run(Job.MEMORY, stored_keys={Provider.OPENAI_COMPATIBLE: _credential()})
    assert run.provider is Provider.OPENAI_COMPATIBLE and run.source == "stored"


def test_a_tier_pick_names_one_of_their_models(monkeypatch):
    _configure(monkeypatch)
    picked = f"{COMPATIBLE_MODEL_PREFIX}meta-llama/Llama-4-Scout"
    credential = _credential(models=((QWEN, 40960), ("meta-llama/Llama-4-Scout", 131072)))
    run = resolve_job_run(
        Job.CHAT,
        user_keys={Provider.OPENAI_COMPATIBLE: credential},
        tier_map={"heavy": picked, "standard": picked, "light": picked},
    )
    assert run.model == picked


def test_a_tier_naming_a_model_they_dropped_takes_their_first(monkeypatch):
    _configure(monkeypatch)
    dropped = f"{COMPATIBLE_MODEL_PREFIX}meta-llama/Llama-4-Scout"
    run = resolve_job_run(
        Job.CHAT,
        user_keys={Provider.OPENAI_COMPATIBLE: _credential()},
        tier_map={"heavy": dropped, "standard": dropped, "light": dropped},
    )
    assert run.model == f"{COMPATIBLE_MODEL_PREFIX}{QWEN}"


# ---------------------------------------------------------------------------
# The settings page's routes
# ---------------------------------------------------------------------------


class _Model:
    """A chat model that calls the tool it is handed, or answers in words."""

    def __init__(self, calls_tool: bool) -> None:
        self.calls_tool = calls_tool

    def bind_tools(self, tools):
        self.tools = tools
        return self

    async def ainvoke(self, prompt):
        if self.calls_tool:
            return AIMessage(content="", tool_calls=[{"name": "confirm_connection", "args": {"ok": True}, "id": "1"}])
        return AIMessage(content="ok")


def _client(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import routes.providers as providers
    import service.auth as auth_service
    from models.auth import User

    app = FastAPI()
    app.include_router(providers.router)
    user = User(email="o@example.com")
    app.dependency_overrides[auth_service.get_current_user] = lambda: user
    app.dependency_overrides[auth_service.get_current_user_optional] = lambda: user
    app.dependency_overrides[providers.db_session] = lambda: None
    monkeypatch.setattr(providers, "stored_provider_keys", lambda db, user_id: {})
    return TestClient(app, raise_server_exceptions=False)


def test_connecting_lists_the_models_and_checks_one_calls_tools(server, monkeypatch):
    monkeypatch.setattr(lc, "resolve_chat_model", lambda *a, **k: _Model(calls_tool=True))
    body = _client(monkeypatch).post(
        "/providers/openai_compatible/probe",
        json={"base_url": f"{PUBLIC}/chat/completions", "api_key": "sk-endpoint", "model": QWEN},
    ).json()
    assert body["ok"] is True and body["base_url"] == PUBLIC
    assert [m["id"] for m in body["models"]] == ["meta-llama/Llama-4-Scout", QWEN, "small-chat"]
    assert body["check"]["ok"] is True and body["check"]["model"] == QWEN


def test_a_model_that_answers_in_words_is_not_one_an_agent_can_run_on(server, monkeypatch):
    monkeypatch.setattr(lc, "resolve_chat_model", lambda *a, **k: _Model(calls_tool=False))
    body = _client(monkeypatch).post(
        "/providers/openai_compatible/probe", json={"base_url": PUBLIC, "model": QWEN}
    ).json()
    assert body["check"] == {
        "ok": False,
        "code": "no_tools",
        "model": QWEN,
        "detail": "It answered in words instead of calling the tool it was given.",
    }


def test_connecting_a_private_address_on_a_hosted_instance_says_why(monkeypatch):
    _configure(monkeypatch)
    wire = Wire(_LISTING).install(monkeypatch)
    body = _client(monkeypatch).post("/providers/openai_compatible/probe", json={"base_url": LOCAL}).json()
    assert body["ok"] is False and body["code"] == "refused"
    assert wire.calls == []


def test_only_a_connected_endpoint_is_remembered(monkeypatch):
    import routes.providers as providers

    _configure(monkeypatch)
    saved = []
    monkeypatch.setattr(providers, "save_provider_key", lambda db, uid, provider, key: saved.append(key))
    client = _client(monkeypatch)
    assert client.put("/providers/openai_compatible/key", json={"api_key": "sk-bare"}).status_code == 422
    private = _credential(LOCAL)
    assert client.put("/providers/openai_compatible/key", json={"api_key": private}).status_code == 422
    good = _credential()
    assert client.put("/providers/openai_compatible/key", json={"api_key": good}).status_code == 200
    assert saved == [good]


def test_the_pickers_offer_only_the_models_they_chose(monkeypatch):
    _configure(monkeypatch)
    credential = _credential(models=((QWEN, 40960), ("small-chat", 0)))
    catalogue = _client(monkeypatch).get(
        "/models/catalogue", headers={"X-Provider-Compatible": credential}
    ).json()
    theirs = [m for m in catalogue["models"] if m["provider"] == "openai_compatible"]
    assert [(m["id"], m["label"]) for m in theirs] == [
        (f"{COMPATIBLE_MODEL_PREFIX}{QWEN}", QWEN),
        (f"{COMPATIBLE_MODEL_PREFIX}small-chat", "small-chat"),
    ]


def test_status_describes_the_endpoint_and_never_its_key(monkeypatch):
    _configure(monkeypatch)
    rows = _client(monkeypatch).get(
        "/providers/status", headers={"X-Provider-Compatible": _credential()}
    ).json()["providers"]
    row = next(r for r in rows if r["id"] == "openai_compatible")
    assert row["source"] == "user" and row["private_ok"] is False
    assert row["endpoint"] == {
        "base_url": PUBLIC,
        "host": "api.models.example",
        "has_key": True,
        "models": [{"id": QWEN, "context_length": 40960}],
    }
    assert "sk-endpoint" not in str(rows)


def test_check_again_tests_the_connected_endpoint(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setattr(lc, "resolve_chat_model", lambda *a, **k: _Model(calls_tool=True))
    client = _client(monkeypatch)
    assert client.post("/providers/openai_compatible/verify").json()["code"] == "missing_key"
    body = client.post(
        "/providers/openai_compatible/verify", headers={"X-Provider-Compatible": _credential()}
    ).json()
    assert body["ok"] is True and body["model"] == QWEN
