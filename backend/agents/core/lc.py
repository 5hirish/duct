"""LangChain adapter — model transport and stream translation for V1 runners.

Two harness-shaped pieces every V1 runner needs, in one place because there are
now two runners (audit, insights) that need them. Both started life inside
``agents/audit/v1/runner.py``; a third copy is how the twenty-three private
``_utcnow()`` definitions started, so they moved here on the second consumer
rather than the third.

What lives here and what does not:

* ``resolve_chat_model`` is the LangChain half of the **model transport** port
  (``agents/core/ports``). Named ``resolve_chat_model``, not ``resolve_model``,
  because ``agents/models.py`` already owns that name for a different job
  (string → ``ModelName``).
* ``stream_agent`` is the LangChain half of the **events out** port: it drives
  a compiled LangGraph agent and translates its stream into Duct's ``AgentEvent``
  vocabulary, so the frontend cannot tell which harness served a run.

Everything agent-specific stays in the runner — what the prompt says, which
tools are bound, what an artifact payload means. This module knows only how to
talk to LangChain.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from langchain.chat_models import init_chat_model
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from agents.core.events import AgentEvent
from agents.core.session import ASK_USER_TIMEOUT, BaseAgentSession, bridge_ask_user_question
from agents.core.stream import DuctArtifactStreamParser
from agents.core.telemetry import model_span
from agents.models import (
    OPENAI_COMPATIBLE_BASE_URL,
    ModelName,
    Provider,
    get_api_key_kwargs,
    langchain_provider,
)
from agents.thinking import thinking_kwargs

logger = logging.getLogger(__name__)

# Cap on clarifying questions in one AskUserQuestion call. Matches the V3
# runners, so a user sees the same maximum whichever engine served the run.
MAX_QUESTIONS = 3


# ---------------------------------------------------------------------------
# Human-in-the-loop — the LangChain half of the AskUser port
# ---------------------------------------------------------------------------

class AskUserArgs(BaseModel):
    """Arguments for the AskUserQuestion tool."""

    questions: list[dict] = Field(
        description=(
            "Clarifying questions for the user. Each item: "
            '{"question": str, "header": str, "options": [{"label": str, "description": str}], '
            '"multiSelect": bool}.'
        )
    )


def build_ask_user_tool(
    session: BaseAgentSession,
    session_id: str,
    emit: Callable,
    *,
    log_prefix: str = "agent-v1",
    timeout: float = ASK_USER_TIMEOUT,
    description: str = (
        "Ask the user up to 3 clarifying questions when their answer would "
        "materially change your conclusions. Use sparingly and early; never ask "
        "about information already provided."
    ),
) -> StructuredTool:
    """AskUserQuestion as a LangChain tool, bridged to the SSE consumer.

    The tool call blocks until the user answers (or the bridge times out and
    returns empty answers), which is what keeps the agent loop paused — the same
    behaviour V3 gets from its ``can_use_tool`` hook.
    """

    async def ask_user_question(questions: list[dict]) -> str:
        result = await bridge_ask_user_question(
            session,
            session_id,
            {"questions": questions[:MAX_QUESTIONS]},
            emit,
            timeout=timeout,
            log_prefix=log_prefix,
        )
        answers = result.get("answers") or {}
        if not answers:
            return (
                "The user did not answer in time. Continue using the information "
                "you already have; do not ask again."
            )
        return "\n".join(f"{k}: {v}" for k, v in answers.items())

    return StructuredTool.from_function(
        coroutine=ask_user_question,
        name="AskUserQuestion",
        description=description,
        args_schema=AskUserArgs,
    )


# ---------------------------------------------------------------------------
# Model transport
# ---------------------------------------------------------------------------

def default_base_url(provider: Provider) -> str:
    """Installation-level endpoint override for OpenAI-compatible providers.

    Read here rather than threaded through every route because it is an
    install-wide setting, not a per-request one — and because agents/models.py
    stays a config-free leaf module. Native providers never consult it.
    """
    if provider not in OPENAI_COMPATIBLE_BASE_URL:
        return ""
    from config import get_configs
    return getattr(get_configs(), "openrouter_base_url", "") or ""


def resolve_chat_model(
    provider: Provider,
    model: ModelName | str,
    api_key: str,
    temperature: float = 1.0,
    *,
    base_url: str = "",
    thinking: str = "",
):
    """Any LangChain-supported provider — this is the point of the migration.

    ``model`` may be a plain string: OpenRouter slugs are passed through
    un-enumerated (see ``agents/engines.resolve_engine_model``). ``base_url`` is
    only consulted by OpenAI-compatible providers.

    ``thinking`` is a *Duct* level ("quick" … "exhaustive"), not a provider
    value. It resolves through agents/thinking.py to whatever this model calls
    that rung, and contributes nothing when the model has no such dial — which
    is why it is safe to pass unconditionally from every call site.
    """
    return init_chat_model(
        model=getattr(model, "value", model),
        model_provider=langchain_provider(provider),
        temperature=temperature,
        **thinking_kwargs(model, thinking),
        **get_api_key_kwargs(provider, api_key, base_url=base_url or default_base_url(provider)),
    )


# ---------------------------------------------------------------------------
# Stream translation
# ---------------------------------------------------------------------------

def split_chunk(message: Any) -> tuple[str, str]:
    """Separate visible text from reasoning in a stream chunk.

    Providers differ: a plain string, or a list of typed blocks where reasoning
    arrives as ``thinking`` / ``reasoning``. Unknown block types are ignored
    rather than leaked into the artifact.
    """
    content = getattr(message, "content", None)
    if isinstance(content, str):
        return content, ""
    if not isinstance(content, list):
        return "", ""

    text_parts: list[str] = []
    thinking_parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        kind = block.get("type")
        if kind == "text":
            text_parts.append(block.get("text", ""))
        elif kind in ("thinking", "reasoning"):
            thinking_parts.append(block.get("thinking") or block.get("text", ""))
    return "".join(text_parts), "".join(thinking_parts)


async def _dispatch_updates(
    chunk: Any,
    *,
    on_todo: Callable[[list], Awaitable[None]] | None,
    on_tool_use: Callable[[str, Any, str], Awaitable[None]] | None,
    on_tool_result: Callable[[str, Any, str, bool], Awaitable[None]] | None,
) -> None:
    """Read one ``updates`` chunk for todos and tool traffic.

    Defensive throughout: the shape is ``{node_name: state_delta}``, but
    LangGraph also puts control keys (``__interrupt__``) alongside the nodes,
    and middleware may deliver a list of deltas. Anything unrecognised is
    skipped — a stream translator must never be the thing that ends a run.
    """
    if not isinstance(chunk, dict):
        return
    for node, delta in chunk.items():
        if str(node).startswith("__"):
            continue
        for state in delta if isinstance(delta, list) else [delta]:
            if not isinstance(state, dict):
                continue
            todos = state.get("todos")
            if todos and on_todo is not None:
                await on_todo(list(todos))
            for msg in state.get("messages") or []:
                for call in getattr(msg, "tool_calls", None) or []:
                    if on_tool_use is not None and isinstance(call, dict):
                        await on_tool_use(
                            call.get("name", ""), call.get("args"), call.get("id", "") or ""
                        )
                if getattr(msg, "type", "") == "tool" and on_tool_result is not None:
                    await on_tool_result(
                        getattr(msg, "name", "") or "",
                        getattr(msg, "content", ""),
                        getattr(msg, "tool_call_id", "") or "",
                        getattr(msg, "status", "") == "error",
                    )


async def stream_agent(
    agent: Any,
    prompt: str,
    emit: Callable,
    *,
    on_artifact_chunk_event: str = AgentEvent.ARTIFACT_CHUNK,
    on_artifact_close: Callable,
    log_prefix: str = "agent-v1",
    config: dict | None = None,
    provider: Provider | None = None,
    model: ModelName | str = "",
    conversation_id: str = "",
    on_todo: Callable[[list], Awaitable[None]] | None = None,
    on_tool_use: Callable[[str, Any, str], Awaitable[None]] | None = None,
    on_tool_result: Callable[[str, Any, str, bool], Awaitable[None]] | None = None,
) -> None:
    """Drive one agent turn and translate its stream into Duct's SSE vocabulary.

    Emits the same ``AgentEvent`` values as the V3 (Claude Agent SDK) runners so
    the frontend is unchanged: AGENT_MESSAGE_CHUNK for prose, ARTIFACT_CHUNK for
    tokens inside ``<duct_artifact>``, THINKING_CHUNK for reasoning deltas,
    MESSAGE_STOP at the end of the turn.

    The optional ``on_todo`` / ``on_tool_*`` hooks read the ``updates`` stream.
    They default to ``None``, so a caller that wants only prose gets exactly the
    behaviour this had before they existed.
    """
    parser = DuctArtifactStreamParser(
        on_text=lambda text: emit({"event": AgentEvent.AGENT_MESSAGE_CHUNK, "text": text}),
        on_artifact_chunk=lambda text: emit({"event": on_artifact_chunk_event, "text": text}),
        on_artifact_close=on_artifact_close,
        log_prefix=log_prefix,
    )

    # V3 gets OTel traces free from the Claude Agent SDK; V1 does not, so the
    # span is emitted here. Same convention either way — see core/telemetry.py.
    with model_span(
        provider=(provider or Provider.ANTHROPIC).value,
        model=getattr(model, "value", model) or "unknown",
        conversation_id=conversation_id,
        agent_name=log_prefix,
    ):
        async for mode, chunk in agent.astream(
            {"messages": [{"role": "user", "content": prompt}]},
            config or {},
            stream_mode=["messages", "updates"],
        ):
            if mode == "updates":
                await _dispatch_updates(
                    chunk,
                    on_todo=on_todo,
                    on_tool_use=on_tool_use,
                    on_tool_result=on_tool_result,
                )
                continue
            if mode != "messages":
                continue
            message, _meta = chunk
            text, thinking = split_chunk(message)
            if thinking:
                await emit({"event": AgentEvent.THINKING_CHUNK, "text": thinking})
            if text:
                await parser.feed(text)

    # The parser holds back the last few characters of every chunk in case they
    # are a split `<duct_artifact>` open tag, so a turn's tail only reaches the
    # stream on flush. Both V3 runners do this at their message_stop; V1 did
    # not, which silently truncated every turn by up to 14 characters — visible
    # as a short chat reply vanishing entirely.
    await parser.flush()
    await emit({"event": AgentEvent.MESSAGE_STOP})
