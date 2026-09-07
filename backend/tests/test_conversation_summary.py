"""Conversation compaction must work for every provider, not just Anthropic.

The bug these pin: `summarize_conversation` only ever spoke to the Claude Agent
SDK, so callers zeroed the key for anyone else —

    summary_key = api_key if provider == "anthropic" else ""

— and the function returned the prior summary untouched. A customer on Gemini,
OpenAI or OpenRouter therefore got *no* compaction at all: every reopened chat
replayed its full history until the window blew, with nothing in the logs to
say why. It failed silently in exactly the configuration Duct's bring-your-own-
model story is for.

Anthropic deliberately stays on the SDK — see `_summarize_via_sdk` for why a
subscription token cannot use the Messages API — so these assert the *routing*,
not one transport for all.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from agents.content.persistence import summarize_conversation
from agents.models import Provider
from models.content import AgentConversation, AgentEvent as AgentEventRow


def _conversation(summary: str = "prior summary") -> AgentConversation:
    return AgentConversation(
        agent_type="tiktok_studio", project_id=uuid4(), summary=summary
    )


def _events() -> list[AgentEventRow]:
    conv_id = uuid4()
    return [
        AgentEventRow(conversation_id=conv_id, seq=1, kind="user",
                      data={"content": "make it punchier"}),
        AgentEventRow(conversation_id=conv_id, seq=2, kind="assistant",
                      data={"text": "tightened the hook"}),
    ]


class _Reply:
    def __init__(self, content):
        self.content = content


@pytest.mark.parametrize(
    "provider",
    [Provider.GOOGLE_GENAI, Provider.OPENAI, Provider.OPENROUTER],
)
async def test_a_byo_model_run_actually_gets_compacted(monkeypatch, provider):
    """The regression: these three used to return the prior summary unchanged."""
    seen: dict = {}

    def _fake_resolve(prov, model, key, *args, **kwargs):
        seen["provider"] = prov
        seen["key"] = key

        class _LLM:
            async def ainvoke(self, prompt):
                seen["prompt"] = prompt
                return _Reply("a fresh summary")

        return _LLM()

    monkeypatch.setattr("agents.core.lc.resolve_chat_model", _fake_resolve)

    result = await summarize_conversation(
        _conversation(), _events(), "byo-key", provider=provider, model=None
    )

    assert result == "a fresh summary"
    assert seen["provider"] is provider
    assert seen["key"] == "byo-key"
    # The transcript rides in, and is fenced as untrusted.
    assert "make it punchier" in seen["prompt"]
    assert "<untrusted_transcript>" in seen["prompt"]


async def test_a_list_content_reply_is_flattened(monkeypatch):
    """Anthropic-via-LangChain and Gemini return typed blocks, not a string."""
    class _LLM:
        async def ainvoke(self, prompt):
            return _Reply([
                {"type": "thinking", "thinking": "hmm"},
                {"type": "text", "text": "the summary"},
            ])

    monkeypatch.setattr("agents.core.lc.resolve_chat_model", lambda *a, **k: _LLM())

    result = await summarize_conversation(
        _conversation(), _events(), "k", provider=Provider.GOOGLE_GENAI
    )
    assert result == "the summary"


async def test_anthropic_summarises_on_langchain_like_everyone_else(monkeypatch):
    """The Agent SDK detour is gone; an Anthropic API key takes the same path
    every other provider takes."""
    seen: dict = {}

    class _Reply:
        content = "lc summary"

    class _LLM:
        async def ainvoke(self, _prompt):
            return _Reply()

    def _resolve(provider, model, api_key, *a, **k):
        seen["provider"] = provider
        return _LLM()

    monkeypatch.setattr("agents.core.lc.resolve_chat_model", _resolve)

    result = await summarize_conversation(
        _conversation(), _events(), "sk-ant-api03-real", provider=Provider.ANTHROPIC
    )

    assert result == "lc summary"
    assert seen["provider"] == Provider.ANTHROPIC


async def test_a_claude_subscription_token_keeps_the_prior_summary(monkeypatch):
    """A subscription credential authenticates through the CLI and the Messages
    API rejects it, so with the SDK gone there is nothing to summarise with.
    The chat keeps working; its summary simply stops advancing — and it must
    not burn a doomed call per turn to discover that."""
    def _explode(*_a, **_k):
        raise AssertionError("a subscription token must not reach the Messages API")

    monkeypatch.setattr("agents.core.lc.resolve_chat_model", _explode)

    result = await summarize_conversation(
        _conversation("kept"), _events(), "sk-ant-oat01-whatever", provider=Provider.ANTHROPIC
    )
    assert result == "kept"


async def test_an_omitted_provider_still_means_anthropic(monkeypatch):
    """Callers that never learned about providers keep their default."""
    seen: dict = {}

    class _Reply:
        content = "lc summary"

    class _LLM:
        async def ainvoke(self, _prompt):
            return _Reply()

    monkeypatch.setattr(
        "agents.core.lc.resolve_chat_model",
        lambda provider, *a, **k: (seen.setdefault("provider", provider), _LLM())[1],
    )

    result = await summarize_conversation(_conversation(), _events(), "key")

    assert result == "lc summary"
    assert seen["provider"] == Provider.ANTHROPIC


async def test_no_key_keeps_the_prior_summary():
    result = await summarize_conversation(_conversation("kept"), _events(), "")
    assert result == "kept"


async def test_an_empty_transcript_keeps_the_prior_summary():
    assert await summarize_conversation(_conversation("kept"), [], "key") == "kept"


async def test_a_provider_failure_never_raises_into_the_agent(monkeypatch):
    """Compaction is best-effort: a dead summariser must not end the session."""
    class _LLM:
        async def ainvoke(self, prompt):
            raise RuntimeError("provider is down")

    monkeypatch.setattr("agents.core.lc.resolve_chat_model", lambda *a, **k: _LLM())

    result = await summarize_conversation(
        _conversation("kept"), _events(), "k", provider=Provider.OPENAI
    )
    assert result == "kept"
