"""Open models on the instance's own Ollama server: a provider with no key.

What makes Ollama different from every other provider is pinned here, because
each difference is a place the generic path would quietly do the wrong thing:
a model id with no vendor shape (and one with a "/" that reads as OpenRouter),
a credential that is the server itself, a model list that lives on the server
rather than in the catalogue, and a context length Ollama sets far too low
unless Duct asks for one.

The server is ``FakeWire`` answering Ollama's own REST paths; no socket opens.
"""

from __future__ import annotations

import pytest

import agents.core.lc as lc
import config as config_module
from agents.engines import Engine, ProviderKeyRequired, resolve_engine_model, resolve_job_run, resolve_provider_key
from agents.models import OLLAMA_MODEL_PREFIX, Provider, cost_usd, provider_of
from agents.tiers import JOB_TIER, Job
from config import Configs
from service import ollama
from tests.fakes import FakeWire

SERVER = "http://ollama.test:11434"
HF_TAG = "hf.co/acme/open-model-GGUF:Q4_K_M"

_SHOW = {
    "qwen3:8b": {
        "details": {"parameter_size": "8.2B"},
        "capabilities": ["completion", "tools", "thinking"],
        "model_info": {"qwen3.context_length": 40960},
    },
    # Pulled, but it cannot call tools, so no Duct agent can run on it.
    "llama3.2:1b": {
        "details": {"parameter_size": "1.2B"},
        "capabilities": ["completion"],
        "model_info": {"llama.context_length": 131072},
    },
    HF_TAG: {
        "details": {"parameter_size": "7B"},
        "capabilities": ["completion", "tools"],
        "model_info": {"llama.context_length": 8192},
    },
}


@pytest.fixture(autouse=True)
def _fresh_cache():
    ollama.clear_cache()
    yield
    ollama.clear_cache()


def _configure(monkeypatch, **settings) -> Configs:
    cfg = Configs(generate_provider="google_genai", **settings)
    monkeypatch.setattr(config_module, "get_configs", lambda: cfg)
    monkeypatch.setattr(config_module, "allow_server_provider_keys", lambda: False)
    return cfg


@pytest.fixture
def server(monkeypatch):
    """An Ollama server holding three models, on the hosted shape: no server
    key may be spent, which Ollama does not need."""
    _configure(monkeypatch, ollama_base_url=SERVER)
    wire = FakeWire()
    wire.on("GET", "/api/tags", {"models": [{"name": tag} for tag in _SHOW]})
    wire.on("POST", "/api/show", lambda call: _SHOW[call.json["model"]])
    return wire.install(monkeypatch)


# ---------------------------------------------------------------------------
# A model id says which provider it is
# ---------------------------------------------------------------------------


def test_an_ollama_id_is_ollamas_even_with_a_slash_in_its_tag():
    """A Hugging Face tag has a "/", and the "/" test would send it to
    OpenRouter on the wrong credential; the namespace is checked first."""
    assert provider_of(f"{OLLAMA_MODEL_PREFIX}qwen3:8b") is Provider.OLLAMA
    assert provider_of(f"{OLLAMA_MODEL_PREFIX}{HF_TAG}") is Provider.OLLAMA
    assert provider_of("deepseek/deepseek-v4-flash:free") is Provider.OPENROUTER
    assert provider_of("qwen3:8b") is None


def test_a_local_model_costs_nothing_rather_than_an_unknown_amount():
    assert cost_usd(f"{OLLAMA_MODEL_PREFIX}qwen3:8b", input_tokens=10_000, output_tokens=2_000) == 0.0


# ---------------------------------------------------------------------------
# The server, not a key, decides whether a run can go there
# ---------------------------------------------------------------------------


def test_the_server_is_the_credential(monkeypatch):
    _configure(monkeypatch, ollama_base_url=SERVER)
    key = resolve_provider_key(Provider.OLLAMA)
    assert (key.key, key.source, key.billed_to_duct) == ("", "instance", False)

    _configure(monkeypatch)
    with pytest.raises(ProviderKeyRequired):
        resolve_provider_key(Provider.OLLAMA)


def test_only_models_that_call_tools_are_offered(server):
    assert [m.tag for m in ollama.tool_models()] == ["qwen3:8b", HF_TAG]


def test_a_server_that_does_not_answer_offers_nothing_and_raises_nothing(monkeypatch):
    _configure(monkeypatch, ollama_base_url=SERVER)
    FakeWire().on("GET", "/api/tags", {"error": "down"}, status=502).install(monkeypatch)
    assert ollama.tool_models() == []


def test_a_caller_with_no_key_runs_on_the_instances_ollama(server):
    """On the hosted shape a caller with no key used to get a 402; an instance
    that offers Ollama runs them there, on its first model that calls tools."""
    run = resolve_job_run(Job.AUDIT)
    assert run.provider is Provider.OLLAMA
    assert run.model == f"{OLLAMA_MODEL_PREFIX}qwen3:8b"
    assert (run.api_key, run.source) == ("", "instance")


def test_a_key_someone_brought_comes_before_the_instances_ollama(server):
    run = resolve_job_run(Job.AUDIT, user_keys={Provider.OPENAI: "sk-user"})
    assert run.provider is Provider.OPENAI


def test_a_picked_ollama_model_runs_as_picked(server):
    picked = f"{OLLAMA_MODEL_PREFIX}{HF_TAG}"
    run = resolve_job_run(Job.AUDIT, tier_map={JOB_TIER[Job.AUDIT].value: picked})
    assert (run.provider, run.model) == (Provider.OLLAMA, picked)
    # Not swapped for a catalogue default, the way an unknown id would be.
    assert resolve_engine_model(Engine.V1, Provider.OLLAMA, picked) == picked


# ---------------------------------------------------------------------------
# What reaches ChatOllama
# ---------------------------------------------------------------------------


def test_the_model_loads_with_a_context_that_fits_duct(server):
    """Ollama's own default is 4,096 tokens on most laptops, which silently
    cuts the system prompt and tools; Duct asks for its own length, held to
    what the model was trained on, and budgets the thread in the same window."""
    llm = lc.resolve_chat_model(Provider.OLLAMA, f"{OLLAMA_MODEL_PREFIX}qwen3:8b", "", temperature=0.0)
    assert (llm.model, llm.base_url) == ("qwen3:8b", SERVER)
    assert llm.num_ctx == 32_768
    assert llm.profile["max_input_tokens"] == 32_768

    small = lc.resolve_chat_model(Provider.OLLAMA, f"{OLLAMA_MODEL_PREFIX}{HF_TAG}", "", temperature=0.0)
    assert (small.model, small.num_ctx) == (HF_TAG, 8192)


def test_reasoning_is_asked_only_of_a_model_that_thinks(server):
    """A thinking model's reasoning is kept out of its answer; a model that
    cannot think is never asked, because Ollama refuses the request."""
    thinker = lc.resolve_chat_model(Provider.OLLAMA, f"{OLLAMA_MODEL_PREFIX}qwen3:8b", "", thinking="deep")
    quick = lc.resolve_chat_model(Provider.OLLAMA, f"{OLLAMA_MODEL_PREFIX}qwen3:8b", "", thinking="quick")
    plain = lc.resolve_chat_model(Provider.OLLAMA, f"{OLLAMA_MODEL_PREFIX}{HF_TAG}", "", thinking="deep")
    assert thinker.reasoning is True
    assert quick.reasoning is False
    assert plain.reasoning is None


def test_usage_is_priced_and_windowed_under_ollamas_namespace():
    """Ollama reports the bare tag; read as-is it would be a model Duct does
    not know, with no price and a window it never had."""
    configured = f"{OLLAMA_MODEL_PREFIX}qwen3:8b"
    assert lc._served_model_id("qwen3:8b", configured) == configured
    assert lc._served_model_id("gpt-6-luna", "gpt-6-luna") == "gpt-6-luna"
    assert lc._served_model_id(None, configured) == configured


# ---------------------------------------------------------------------------
# The settings page's routes
# ---------------------------------------------------------------------------


def test_the_catalogue_lists_what_the_server_holds(server):
    import routes.providers as providers

    local = [m for m in providers.models_catalogue()["models"] if m["provider"] == "ollama"]
    assert [m["id"] for m in local] == [f"{OLLAMA_MODEL_PREFIX}qwen3:8b", f"{OLLAMA_MODEL_PREFIX}{HF_TAG}"]
    assert local[0]["label"] == "qwen3:8b · 8.2B"


def _client(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import routes.providers as providers
    import service.auth as auth_service
    from models.auth import User

    app = FastAPI()
    app.include_router(providers.router)
    app.dependency_overrides[auth_service.get_current_user] = lambda: User(email="o@example.com")
    app.dependency_overrides[providers.db_session] = lambda: None
    return TestClient(app, raise_server_exceptions=False)


def test_no_key_is_ever_stored_for_ollama(server, monkeypatch):
    res = _client(monkeypatch).put("/providers/ollama/key", json={"api_key": "anything"})
    assert res.status_code == 422


@pytest.mark.parametrize(
    ("settings", "tags", "code"),
    [
        ({}, None, "missing_key"),
        ({"ollama_base_url": SERVER}, "down", "unreachable"),
        ({"ollama_base_url": SERVER}, ["llama3.2:1b"], "model_access"),
    ],
)
def test_verify_says_what_is_missing_on_the_server(monkeypatch, settings, tags, code):
    _configure(monkeypatch, **settings)
    wire = FakeWire()
    if tags == "down":
        wire.on("GET", "/api/tags", {"error": "down"}, status=502)
    elif tags:
        wire.on("GET", "/api/tags", {"models": [{"name": t} for t in tags]})
        wire.on("POST", "/api/show", lambda call: _SHOW[call.json["model"]])
    wire.install(monkeypatch)

    body = _client(monkeypatch).post("/providers/ollama/verify").json()
    assert body["ok"] is False and body["code"] == code
