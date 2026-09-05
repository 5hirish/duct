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

import pytest

from agents.engines import ProviderKeyRequired, resolve_provider_key
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
        # Desktop/local by default: there the env file IS the user's own key, so
        # the fallback is permitted and these tests can assert on it. The hosted
        # case gets its own block at the bottom.
        duct_local=True,
        app_env="local",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _patch_cfg(monkeypatch, **overrides):
    """Patch the one config reader.

    Both the provider choice (``agents.engines.resolve_run_model``) and the key
    (``agents.engines.resolve_provider_key``) read ``config.get_configs``
    directly, so no call site can quietly opt out of the policy — and one
    patch covers the whole resolver.
    """
    cfg = _fake_cfg(**overrides)
    monkeypatch.setattr("config.get_configs", lambda: cfg)
    # The operator's own Claude login must not decide a test's outcome.
    monkeypatch.setattr("config.claude_oauth_available", lambda: False)
    return cfg


def test_byo_key_overrides_backend_key(monkeypatch):
    _patch_cfg(monkeypatch, anthropic_api_key="sk-ant-backend")
    provider, _model, api_key, _summary = resolve_model(
        "v3", {Provider.ANTHROPIC: "sk-ant-user"}
    )
    assert provider == Provider.ANTHROPIC
    assert api_key == "sk-ant-user"  # BYO wins over the backend key


def test_falls_back_to_backend_key_when_no_user_key(monkeypatch):
    _patch_cfg(monkeypatch, anthropic_api_key="sk-ant-backend")
    provider, _model, api_key, _summary = resolve_model("v3", {})
    assert provider == Provider.ANTHROPIC
    # Desktop/local only. That env file is the user's own, so spending from it
    # is bring-your-own by another route — see the hosted case below.
    assert api_key == "sk-ant-backend"


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
    _patch_cfg(monkeypatch, generate_engine="v1", gemini_api_key="g-backend")
    provider, _model, api_key, _summary = resolve_model(
        "v1", {Provider.OPENAI: "sk-openai-user"}
    )
    assert provider == Provider.OPENAI
    assert api_key == "sk-openai-user"


def test_an_openrouter_key_reaches_openrouter(monkeypatch):
    """The case the Providers card exists to serve: one key, no server config."""
    _patch_cfg(monkeypatch, generate_engine="v1")
    provider, model, api_key, _summary = resolve_model(
        "v1", {Provider.OPENROUTER: "sk-or-v1-user"}
    )
    assert provider == Provider.OPENROUTER
    assert api_key == "sk-or-v1-user"
    assert "/" in str(getattr(model, "value", model))  # a routed vendor/slug


def test_two_keys_are_not_a_preference(monkeypatch):
    """Ambiguity keeps the engine default, and neither BYO key is spent there."""
    _patch_cfg(monkeypatch, generate_engine="v1", gemini_api_key="g-backend")
    provider, _model, api_key, _summary = resolve_model(
        "v1", {Provider.OPENAI: "sk-openai-user", Provider.ANTHROPIC: "sk-ant-user"}
    )
    assert provider == Provider.GOOGLE_GENAI
    assert api_key == "g-backend"


def test_an_operator_pinned_provider_outranks_a_byo_key(monkeypatch):
    """GENERATE_PROVIDER is an explicit choice; a key does not override it, and
    the non-matching key is not spent on it either."""
    _patch_cfg(monkeypatch, generate_engine="v1", generate_provider="google_genai", gemini_api_key="g-backend")
    provider, _model, api_key, _summary = resolve_model(
        "v1", {Provider.OPENAI: "sk-openai-user"}
    )
    assert provider == Provider.GOOGLE_GENAI
    assert api_key == "g-backend"


def test_v3_never_takes_an_openrouter_key(monkeypatch):
    """The Claude Agent SDK is provider-locked, so an OpenRouter key cannot move
    it — the engine's supported set is the gate, not the key."""
    _patch_cfg(monkeypatch, anthropic_api_key="sk-ant-backend")
    provider, _model, api_key, _summary = resolve_model(
        "v3", {Provider.OPENROUTER: "sk-or-v1-user"}
    )
    assert provider == Provider.ANTHROPIC
    assert api_key == "sk-ant-backend"


def test_a_stale_generate_model_is_dropped_when_the_key_moves_the_provider(monkeypatch):
    """GENERATE_MODEL belongs to the provider the operator picked. Forwarding
    `gemini-2.5-flash` to OpenRouter is a guaranteed upstream 404."""
    _patch_cfg(monkeypatch, generate_engine="v1", generate_model="gemini-2.5-flash")
    provider, model, _api_key, _summary = resolve_model(
        "v1", {Provider.OPENROUTER: "sk-or-v1-user"}
    )
    assert provider == Provider.OPENROUTER
    assert str(getattr(model, "value", model)) != "gemini-2.5-flash"


# --- the gate: whose key the hosted deployment is allowed to spend ----------
#
# The reason this module exists. On Railway the env key is Duct's Console
# account, so a run that arrives with no key of its own must fail rather than
# bill us — "there is no key configured" and "there is a key and you may not
# have it" are different states, and only the second survives someone adding
# the variable back.


def test_hosted_prod_refuses_to_spend_the_server_key(monkeypatch):
    _patch_cfg(monkeypatch, duct_local=False, app_env="production",
               anthropic_api_key="sk-ant-ducts-own")
    with pytest.raises(ProviderKeyRequired) as exc:
        resolve_model("v3", {})
    assert exc.value.provider == "anthropic"


def test_hosted_prod_still_runs_on_the_callers_own_key(monkeypatch):
    """Failing closed must not mean failing always: BYOK is the supported path,
    not a degraded one."""
    _patch_cfg(monkeypatch, duct_local=False, app_env="production",
               anthropic_api_key="sk-ant-ducts-own")
    _provider, _model, api_key, _summary = resolve_model(
        "v3", {Provider.ANTHROPIC: "sk-ant-user"}
    )
    assert api_key == "sk-ant-user"


def test_a_saved_key_serves_a_run_with_no_headers(monkeypatch):
    """Background work — consolidation, the unattended brief — has no request to
    carry an X-Provider-* header, so the stored key is its only BYOK."""
    _patch_cfg(monkeypatch, duct_local=False, app_env="production")
    _provider, _model, api_key, _summary = resolve_model(
        "v3", {}, {Provider.ANTHROPIC: "sk-ant-saved"}
    )
    assert api_key == "sk-ant-saved"


def test_a_header_key_beats_a_saved_one(monkeypatch):
    """The key pasted into this request is the more recent statement of intent."""
    _patch_cfg(monkeypatch, duct_local=False, app_env="production")
    _provider, _model, api_key, _summary = resolve_model(
        "v3", {Provider.ANTHROPIC: "sk-ant-header"}, {Provider.ANTHROPIC: "sk-ant-saved"}
    )
    assert api_key == "sk-ant-header"


def test_duct_pays_is_the_only_way_back_to_our_key_in_prod(monkeypatch):
    """The lead-magnet teaser audit, and nothing else. Declared at the call site
    rather than inferred, so it can be found by reading the code."""
    _patch_cfg(monkeypatch, duct_local=False, app_env="production",
               anthropic_api_key="sk-ant-ducts-own")
    resolved = resolve_provider_key(Provider.ANTHROPIC, {}, duct_pays=True)
    assert resolved.key == "sk-ant-ducts-own"
    assert resolved.source == "cloud"
    assert resolved.billed_to_duct is True


def test_the_operators_subscription_is_behind_the_same_gate(monkeypatch):
    """A Claude subscription is the operator's account too, so it is not a way
    around the gate — and Anthropic's own policy forbids serving users from it."""
    _patch_cfg(monkeypatch, duct_local=False, app_env="production")
    monkeypatch.setattr("config.claude_oauth_available", lambda: True)
    with pytest.raises(ProviderKeyRequired):
        resolve_provider_key(Provider.ANTHROPIC, {})
    # ...and available again once the run is one Duct has chosen to fund.
    assert resolve_provider_key(
        Provider.ANTHROPIC, {}, duct_pays=True
    ).source == "subscription"


def test_desktop_labels_its_own_env_key_as_the_users(monkeypatch):
    """`env` vs `cloud` is the whole question a customer cares about, and the
    same config field answers it differently depending on where this runs."""
    _patch_cfg(monkeypatch, duct_local=True, app_env="production",
               anthropic_api_key="sk-ant-on-my-laptop")
    resolved = resolve_provider_key(Provider.ANTHROPIC, {})
    assert resolved.source == "env"
    assert resolved.billed_to_duct is False
