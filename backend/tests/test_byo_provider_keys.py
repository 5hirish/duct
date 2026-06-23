"""Unit tests for the per-request bring-your-own provider key plumbing (Phase 0).

No network / DB: exercises the X-Provider-* header dependency and the key
precedence resolver (bring-your-own first, backend fallback).
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from starlette.datastructures import Headers

from agents.models import ModelName, Provider
from routes.generate import _missing_key_message, _resolve_agent_config
from service.auth import get_user_provider_keys, provider_keys_from_headers


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


# --- provider_keys_from_headers: the agents-route (request.headers) path -----


def test_provider_keys_from_headers_parses_strips_and_is_case_insensitive():
    # Starlette Headers are case-insensitive — the agents route pulls BYO keys
    # straight off request.headers (no Depends), so this mirrors the real call.
    headers = Headers({
        "X-Provider-Anthropic": "  sk-ant-xyz  ",
        "x-provider-gemini": "g-key",
        "X-Provider-OpenAI": "   ",  # blank -> ignored
        "X-API-Key": "gate",         # unrelated header -> ignored
    })
    assert provider_keys_from_headers(headers) == {
        Provider.ANTHROPIC: "sk-ant-xyz",
        Provider.GOOGLE_GENAI: "g-key",
    }


def test_provider_keys_from_headers_empty_when_absent():
    assert provider_keys_from_headers(Headers({})) == {}


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


# --- missing-key error message (gap #2: no silent empty report) -------------


def test_missing_key_message_is_actionable():
    from agents.engines import Engine

    msg = _missing_key_message(Provider.ANTHROPIC, Engine.V3)
    assert "Anthropic" in msg
    assert "Providers" in msg  # points the user at the Providers tab


# --- v2 ADK per-model key (gap #4: no process-global env race) --------------


def test_v2_server_key_keeps_env_path_no_per_model_key():
    from agents.insights.v2.runner import _build_adk_model

    # Server key (prefer_per_model=False) → plain string model, ADK reads the env
    # var. per_model_key False means nothing is carried on the model.
    model, per_model = _build_adk_model(
        Provider.GOOGLE_GENAI, ModelName.GEMINI_2_5_FLASH, "g-key", prefer_per_model=False
    )
    assert per_model is False
    assert isinstance(model, str)


def test_v2_no_key_returns_string_model():
    from agents.insights.v2.runner import _build_adk_model

    model, per_model = _build_adk_model(
        Provider.ANTHROPIC, ModelName.CLAUDE_SONNET_4_6, "", prefer_per_model=True
    )
    assert per_model is False
    assert isinstance(model, str)


def _litellm_constructible() -> bool:
    """True only when google-adk[extensions] is fully installed: the lite_llm
    module imports even without the extra, but constructing LiteLlm raises
    ImportError when the `litellm` package is missing."""
    try:
        from google.adk.models.lite_llm import LiteLlm

        LiteLlm(model="openai/probe", api_key="probe")
        return True
    except Exception:
        return False


def test_v2_byo_key_per_model_or_safe_fallback():
    # The race fix: a BYO key is carried on a LiteLlm model (no os.environ
    # mutation) when the extra is installed; otherwise it falls back to a plain
    # string (serialized env injection — still race-safe). Critically it must
    # NEVER raise, even when `litellm` is absent (the construction-guard bug).
    from agents.insights.v2.runner import _build_adk_model

    model, per_model = _build_adk_model(
        Provider.OPENAI, ModelName.GPT_5_MINI, "sk-openai-user", prefer_per_model=True
    )
    if _litellm_constructible():
        assert per_model is True
        assert not isinstance(model, str)  # a LiteLlm instance carrying the key
    else:
        assert per_model is False
        assert isinstance(model, str)  # safe fallback, no crash


# --- Anthropic OAuth-vs-API credential routing -----------------------------
# A bring-your-own Anthropic credential can be either an API key (sk-ant-api…)
# or a Claude subscription OAuth token (sk-ant-oat…, from `claude setup-token`).
# The env builder must route each to the env var the CLI expects, by prefix.


def test_is_anthropic_oauth_token_detects_by_prefix():
    from agents.core.claude_sdk import is_anthropic_oauth_token

    assert is_anthropic_oauth_token("sk-ant-oat01-abc") is True
    assert is_anthropic_oauth_token("  sk-ant-oat01-abc  ") is True  # trimmed
    assert is_anthropic_oauth_token("sk-ant-api03-abc") is False
    assert is_anthropic_oauth_token("sk-ant-xyz") is False
    assert is_anthropic_oauth_token("") is False
    assert is_anthropic_oauth_token(None) is False


def test_build_sdk_env_routes_oauth_token_to_oauth_var(monkeypatch):
    # An OAuth token supplied as the api_key must land in CLAUDE_CODE_OAUTH_TOKEN,
    # never ANTHROPIC_API_KEY (the CLI exits 1 on an OAuth token there).
    from agents.core.claude_sdk import build_sdk_env

    # Disable the isolated config dir so the test does no filesystem work.
    monkeypatch.setenv("DUCT_TEST_CLAUDE_CFG", "off")
    env, _ = build_sdk_env(
        service_name="test",
        api_key="sk-ant-oat01-token",
        config_env_var="DUCT_TEST_CLAUDE_CFG",
        config_suffix="test",
    )
    assert env.get("CLAUDE_CODE_OAUTH_TOKEN") == "sk-ant-oat01-token"
    assert "ANTHROPIC_API_KEY" not in env


def test_build_sdk_env_routes_api_key_to_api_var(monkeypatch):
    from agents.core.claude_sdk import build_sdk_env

    monkeypatch.setenv("DUCT_TEST_CLAUDE_CFG", "off")
    env, _ = build_sdk_env(
        service_name="test",
        api_key="sk-ant-api03-key",
        config_env_var="DUCT_TEST_CLAUDE_CFG",
        config_suffix="test",
    )
    assert env.get("ANTHROPIC_API_KEY") == "sk-ant-api03-key"
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in env


def test_build_sdk_env_byo_oauth_token_overrides_server_oauth(monkeypatch):
    # A supplied OAuth token wins over a server-configured one.
    from agents.core.claude_sdk import build_sdk_env

    monkeypatch.setenv("DUCT_TEST_CLAUDE_CFG", "off")
    env, _ = build_sdk_env(
        service_name="test",
        api_key="sk-ant-oat01-user",
        oauth_token="sk-ant-oat01-server",
        config_env_var="DUCT_TEST_CLAUDE_CFG",
        config_suffix="test",
    )
    assert env.get("CLAUDE_CODE_OAUTH_TOKEN") == "sk-ant-oat01-user"
