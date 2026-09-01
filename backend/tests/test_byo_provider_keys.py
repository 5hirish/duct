"""Unit tests for the per-request bring-your-own provider key plumbing.

No network / DB: exercises the X-Provider-* header dependency and the key
precedence resolver (bring-your-own first, backend fallback).

The resolver moved from ``routes/generate._resolve_agent_config`` to
``agents/insights/setup.resolve_model`` when the wizard's request-shaped
pipeline was deleted and both insights entry points — the live session and the
unattended brief — started sharing one setup path. Both now honour a caller's
own key; the session route never did before.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from agents.models import Provider
from agents.insights.setup import resolve_model
from service.auth import get_user_provider_keys


# --- get_user_provider_keys: header parsing --------------------------------


def test_provider_keys_only_includes_supplied_and_strips():
    keys = asyncio.run(
        get_user_provider_keys(
            anthropic_key="  sk-ant-xyz  ",
            openai_key=None,
            gemini_key="   ",  # blank -> ignored
            openrouter_key=None,
        )
    )
    assert keys == {Provider.ANTHROPIC: "sk-ant-xyz"}


def test_provider_keys_empty_when_none_supplied():
    keys = asyncio.run(
        get_user_provider_keys(
            anthropic_key=None, openai_key=None, gemini_key=None, openrouter_key=None
        )
    )
    assert keys == {}


def test_openrouter_key_is_its_own_provider_not_an_openai_one():
    """`sk-or-v1-…` is an OpenRouter credential even though the transport is the
    OpenAI wire format. Collapsing the two would spend a caller's OpenRouter key
    on a direct OpenAI call — a different vendor, a different bill."""
    keys = asyncio.run(
        get_user_provider_keys(
            anthropic_key=None,
            openai_key=None,
            gemini_key=None,
            openrouter_key="sk-or-v1-abc",
        )
    )
    assert keys == {Provider.OPENROUTER: "sk-or-v1-abc"}


# --- resolve_model: precedence ---------------------------------------------


def _fake_cfg(**overrides):
    base = dict(
        generate_engine="v3",
        generate_provider="",
        generate_model="",
        anthropic_api_key="",
        openai_api_key="",
        gemini_api_key="",
        openrouter_api_key="",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_byo_key_overrides_backend_key(monkeypatch):
    monkeypatch.setattr(
        "agents.insights.setup.get_configs",
        lambda: _fake_cfg(anthropic_api_key="sk-ant-backend"),
    )
    provider, _model, api_key, _summary = resolve_model(
        "v3", {Provider.ANTHROPIC: "sk-ant-user"}
    )
    assert provider == Provider.ANTHROPIC
    assert api_key == "sk-ant-user"  # BYO wins over the backend key


def test_falls_back_to_backend_key_when_no_user_key(monkeypatch):
    monkeypatch.setattr(
        "agents.insights.setup.get_configs",
        lambda: _fake_cfg(anthropic_api_key="sk-ant-backend"),
    )
    provider, _model, api_key, _summary = resolve_model("v3", {})
    assert provider == Provider.ANTHROPIC
    assert api_key == "sk-ant-backend"  # open fallback to the server key


# --- resolve_model: a lone BYO key chooses its own provider ----------------
#
# The invariant under test in this block is *not* "the provider never moves" —
# it is "a key is never spent on a provider it does not belong to". A lone key
# moves the provider to itself, which satisfies that; ambiguity does not move it
# at all.


def test_a_lone_byo_key_selects_its_own_provider(monkeypatch):
    """v1 defaults to GOOGLE_GENAI, but a caller who supplied only an OpenAI key
    asked for OpenAI. Before this, that request resolved to Gemini and died at
    the door with "no API key configured" while holding a perfectly good key."""
    monkeypatch.setattr(
        "agents.insights.setup.get_configs",
        lambda: _fake_cfg(generate_engine="v1", gemini_api_key="g-backend"),
    )
    provider, _model, api_key, _summary = resolve_model(
        "v1", {Provider.OPENAI: "sk-openai-user"}
    )
    assert provider == Provider.OPENAI
    assert api_key == "sk-openai-user"


def test_an_openrouter_key_reaches_openrouter(monkeypatch):
    """The case the Providers card exists to serve: one key, no server config."""
    monkeypatch.setattr(
        "agents.insights.setup.get_configs", lambda: _fake_cfg(generate_engine="v1")
    )
    provider, model, api_key, _summary = resolve_model(
        "v1", {Provider.OPENROUTER: "sk-or-v1-user"}
    )
    assert provider == Provider.OPENROUTER
    assert api_key == "sk-or-v1-user"
    assert "/" in str(getattr(model, "value", model))  # a routed vendor/slug


def test_two_keys_are_not_a_preference(monkeypatch):
    """Ambiguity keeps the engine default, and neither BYO key is spent there."""
    monkeypatch.setattr(
        "agents.insights.setup.get_configs",
        lambda: _fake_cfg(generate_engine="v1", gemini_api_key="g-backend"),
    )
    provider, _model, api_key, _summary = resolve_model(
        "v1", {Provider.OPENAI: "sk-openai-user", Provider.ANTHROPIC: "sk-ant-user"}
    )
    assert provider == Provider.GOOGLE_GENAI
    assert api_key == "g-backend"


def test_an_operator_pinned_provider_outranks_a_byo_key(monkeypatch):
    """GENERATE_PROVIDER is an explicit choice; a key does not override it, and
    the non-matching key is not spent on it either."""
    monkeypatch.setattr(
        "agents.insights.setup.get_configs",
        lambda: _fake_cfg(
            generate_engine="v1", generate_provider="google_genai", gemini_api_key="g-backend"
        ),
    )
    provider, _model, api_key, _summary = resolve_model(
        "v1", {Provider.OPENAI: "sk-openai-user"}
    )
    assert provider == Provider.GOOGLE_GENAI
    assert api_key == "g-backend"


def test_v3_never_takes_an_openrouter_key(monkeypatch):
    """The Claude Agent SDK is provider-locked, so an OpenRouter key cannot move
    it — the engine's supported set is the gate, not the key."""
    monkeypatch.setattr(
        "agents.insights.setup.get_configs",
        lambda: _fake_cfg(anthropic_api_key="sk-ant-backend"),
    )
    provider, _model, api_key, _summary = resolve_model(
        "v3", {Provider.OPENROUTER: "sk-or-v1-user"}
    )
    assert provider == Provider.ANTHROPIC
    assert api_key == "sk-ant-backend"


def test_a_stale_generate_model_is_dropped_when_the_key_moves_the_provider(monkeypatch):
    """GENERATE_MODEL belongs to the provider the operator picked. Forwarding
    `gemini-2.5-flash` to OpenRouter is a guaranteed upstream 404."""
    monkeypatch.setattr(
        "agents.insights.setup.get_configs",
        lambda: _fake_cfg(generate_engine="v1", generate_model="gemini-2.5-flash"),
    )
    provider, model, _api_key, _summary = resolve_model(
        "v1", {Provider.OPENROUTER: "sk-or-v1-user"}
    )
    assert provider == Provider.OPENROUTER
    assert str(getattr(model, "value", model)) != "gemini-2.5-flash"
