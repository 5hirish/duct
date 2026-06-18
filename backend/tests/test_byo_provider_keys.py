"""Unit tests for the per-request bring-your-own provider key plumbing (Phase 0).

No network / DB: exercises the X-Provider-* header dependency and the key
precedence resolver (bring-your-own first, backend fallback).
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from agents.models import Provider
from routes.generate import _resolve_agent_config
from service.auth import get_user_provider_keys


# --- get_user_provider_keys: header parsing --------------------------------


def test_provider_keys_only_includes_supplied_and_strips():
    keys = asyncio.run(
        get_user_provider_keys(
            anthropic_key="  sk-ant-xyz  ",
            openai_key=None,
            gemini_key="   ",  # blank -> ignored
        )
    )
    assert keys == {Provider.ANTHROPIC: "sk-ant-xyz"}


def test_provider_keys_empty_when_none_supplied():
    keys = asyncio.run(
        get_user_provider_keys(anthropic_key=None, openai_key=None, gemini_key=None)
    )
    assert keys == {}


# --- _resolve_agent_config: precedence -------------------------------------


def _fake_cfg(**overrides):
    base = dict(
        generate_engine="v3",
        generate_provider="",
        generate_model="",
        anthropic_api_key="",
        openai_api_key="",
        gemini_api_key="",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_byo_key_overrides_backend_key(monkeypatch):
    monkeypatch.setattr(
        "routes.generate.get_configs",
        lambda: _fake_cfg(anthropic_api_key="sk-ant-backend"),
    )
    api_key, provider, _model, _engine = _resolve_agent_config(
        "v3", user_keys={Provider.ANTHROPIC: "sk-ant-user"}
    )
    assert provider == Provider.ANTHROPIC
    assert api_key == "sk-ant-user"  # BYO wins over the backend key


def test_falls_back_to_backend_key_when_no_user_key(monkeypatch):
    monkeypatch.setattr(
        "routes.generate.get_configs",
        lambda: _fake_cfg(anthropic_api_key="sk-ant-backend"),
    )
    api_key, provider, _model, _engine = _resolve_agent_config("v3", user_keys={})
    assert provider == Provider.ANTHROPIC
    assert api_key == "sk-ant-backend"  # open fallback to the server key


def test_user_key_for_other_provider_does_not_leak(monkeypatch):
    # v1 resolves to GOOGLE_GENAI by default; an OpenAI BYO key must not be used
    # for a different provider.
    monkeypatch.setattr(
        "routes.generate.get_configs",
        lambda: _fake_cfg(generate_engine="v1", gemini_api_key="g-backend"),
    )
    api_key, provider, _model, _engine = _resolve_agent_config(
        "v1", user_keys={Provider.OPENAI: "sk-openai-user"}
    )
    assert provider == Provider.GOOGLE_GENAI
    assert api_key == "g-backend"  # falls back to gemini key, not the OpenAI BYO key
