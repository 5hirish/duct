"""Which chat model does v1 build for each OpenAI credential shape?

A ChatGPT subscription credential targets ``chatgpt.com/backend-api/codex``, not
the public OpenAI API, so it needs ``_ChatOpenAICodex`` rather than
``ChatOpenAI``. The invariant worth protecting: **an explicit API key always
wins** — it is the supported path, the only one that may serve end users, and
the one with predictable latency.

There is deliberately no Anthropic equivalent. Anthropic disabled `sk-ant-oat…`
on the Messages API in Feb 2026, and the only thing that authenticates one is
the `claude` CLI subprocess — measured at ~125s per synthesis with no token
streaming, versus ~$0.04 to run the same call on an API key. Claude on v1 uses
ANTHROPIC_API_KEY; v3 remains the subscription path.

No network and no ChatGPT login required.
"""

from __future__ import annotations

import pytest

from agents.core import codex
from agents.models import ModelName, Provider


# ---------------------------------------------------------------------------
# Credential classification
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("sk-proj-abc", True),
        ("sk-abc", True),
        # A ChatGPT OAuth access token is not an API key.
        ("eyJhbGciOiJSUzI1NiJ9.abc", False),
        ("", False),
    ],
)
def test_an_openai_api_key_is_recognised_by_its_prefix(value, expected):
    assert codex.is_openai_api_key(value) is expected


# ---------------------------------------------------------------------------
# Route selection
# ---------------------------------------------------------------------------


def test_an_openai_api_key_never_routes_to_the_subscription(monkeypatch):
    """Even with a ChatGPT login present, a real key wins."""
    monkeypatch.setattr(codex, "codex_available", lambda: True)
    assert codex.should_use_codex("sk-proj-abc") is False


def test_the_subscription_is_used_only_when_a_login_exists(monkeypatch):
    monkeypatch.setattr(codex, "codex_available", lambda: True)
    assert codex.should_use_codex("") is True

    monkeypatch.setattr(codex, "codex_available", lambda: False)
    assert codex.should_use_codex("") is False


def test_building_a_codex_model_without_a_login_says_how_to_log_in(monkeypatch):
    monkeypatch.setattr(codex, "codex_available", lambda: False)
    with pytest.raises(RuntimeError, match="login_chatgpt"):
        codex.build_codex_chat(model="gpt-5-mini")


# ---------------------------------------------------------------------------
# End to end through the v1 constructor
# ---------------------------------------------------------------------------


def _llm_for(api_key: str, provider: Provider, model: ModelName) -> str:
    from agents.insights.v1.agent import GenerateInsightsAgent

    return type(
        GenerateInsightsAgent(api_key=api_key, provider=provider, model=model).llm
    ).__name__


def test_v1_routes_each_credential_to_the_right_chat_model(monkeypatch):
    monkeypatch.setattr(codex, "codex_available", lambda: True)

    # A subscription takes its own path...
    assert _llm_for("", Provider.OPENAI, ModelName.GPT_5_MINI) == "_ChatOpenAICodex"

    # ...and an explicit API key always beats it.
    assert _llm_for("sk-proj-x", Provider.OPENAI, ModelName.GPT_5_MINI) == "ChatOpenAI"


def test_anthropic_always_uses_the_messages_api(monkeypatch):
    """No subscription path exists for Claude on v1 — see the module docstring."""
    monkeypatch.setattr(codex, "codex_available", lambda: True)
    assert _llm_for("", Provider.ANTHROPIC, ModelName.CLAUDE_SONNET) == "ChatAnthropic"


def test_other_providers_are_untouched_by_the_subscription_path(monkeypatch):
    """Gemini and OpenRouter must not acquire a ChatGPT dependency."""
    monkeypatch.setattr(codex, "codex_available", lambda: True)
    assert _llm_for("k", Provider.GOOGLE_GENAI, ModelName.GEMINI_2_5_FLASH) == "ChatGoogleGenerativeAI"
