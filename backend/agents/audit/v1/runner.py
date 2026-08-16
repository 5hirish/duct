"""Audit synthesis on the LangChain 1.x agent stack (V1 engine).

Runs alongside `agents/audit/v3/runner.py`, which stays the production path
until V1 earns confidence (`backend/CLAUDE.md`). Nothing here modifies V3.

What is reused rather than reimplemented — the reason this file is short:

* ``agents/core/stream.py::DuctReportStreamParser`` — the ``<duct_report>`` tag
  state machine is ours and framework-neutral.
* ``agents/core/session.py::bridge_ask_user_question`` — already engine-agnostic:
  it emits QUESTIONS_REQUIRED and awaits an asyncio.Future resolved by the
  messages route. A LangChain tool can await that directly, so mid-run questions
  need **no** new plumbing and the SSE contract is unchanged.
* ``agents/core/events.py::AgentEvent`` — the frontend contract. V1 emits exactly
  the values V3 emits, so the UI cannot tell which engine served a run.
* ``agents/audit/v1/tools.py`` — the crawl and report tools.

Why the ask-user bridge instead of LangGraph ``interrupt()``: the bridge keeps a
live coroutine and needs no checkpointer, which matches V3's behaviour exactly
and keeps the messages route untouched. ``interrupt()`` is the upgrade path when
a run must survive a process restart or move between instances — the primitives
are already proven in ``tests/test_deepagents_harness.py``.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from agents.audit.schema import CrawlResult
from agents.audit.v1.tools import build_audit_tools
from agents.core.events import AgentEvent
from agents.core.session import (
    ASK_USER_TIMEOUT,
    BaseAgentSession,
    bridge_ask_user_question,
)
from agents.core.stream import DuctReportStreamParser
from agents.models import ModelName, Provider, get_api_key_kwargs

logger = logging.getLogger(__name__)

# Mirrors the V3 runner's cap on clarifying questions.
MAX_QUESTIONS = 3


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
    log_prefix: str = "audit-v1",
    timeout: float = ASK_USER_TIMEOUT,
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
                "The user did not answer in time. Continue the audit using the "
                "information you already have; do not ask again."
            )
        return "\n".join(f"{k}: {v}" for k, v in answers.items())

    return StructuredTool.from_function(
        coroutine=ask_user_question,
        name="AskUserQuestion",
        description=(
            "Ask the user up to 3 clarifying questions when business context would "
            "materially change the audit's conclusions. Use sparingly and early; "
            "never ask about information already provided."
        ),
        args_schema=AskUserArgs,
    )


def resolve_model(provider: Provider, model: ModelName, api_key: str, temperature: float = 1.0):
    """Any LangChain-supported provider — this is the point of the migration."""
    return init_chat_model(
        model=model.value,
        model_provider=provider.value,
        temperature=temperature,
        **get_api_key_kwargs(provider, api_key),
    )


def build_audit_agent(
    *,
    crawl_result: CrawlResult,
    llm: Any,
    system_prompt: str,
    session: BaseAgentSession | None = None,
    session_id: str = "",
    emit: Callable | None = None,
    report_mode: str = "template",
    on_submit_report: Callable | None = None,
    on_category_added: Callable | None = None,
):
    """Assemble the audit agent: crawl/report tools plus optional mid-run questions."""
    tools = build_audit_tools(
        crawl_result,
        report_mode=report_mode,
        on_submit_report=on_submit_report,
        on_category_added=on_category_added,
    )
    if session is not None and emit is not None:
        tools.append(build_ask_user_tool(session, session_id, emit))

    return create_agent(model=llm, tools=tools, system_prompt=system_prompt)


async def stream_audit(
    agent: Any,
    prompt: str,
    emit: Callable,
    *,
    on_report_close: Callable,
    log_prefix: str = "audit-v1",
    config: dict | None = None,
) -> None:
    """Drive the agent and translate its stream into Duct's SSE vocabulary.

    Emits the same ``AgentEvent`` values as V3 so the frontend is unchanged:
    AGENT_MESSAGE_CHUNK for prose, REPORT_CHUNK for tokens inside
    ``<duct_report>``, THINKING_CHUNK for reasoning deltas, MESSAGE_STOP at the
    end of the turn.
    """
    parser = DuctReportStreamParser(
        on_text=lambda text: emit({"event": AgentEvent.AGENT_MESSAGE_CHUNK, "text": text}),
        on_report_chunk=lambda text: emit({"event": AgentEvent.REPORT_CHUNK, "text": text}),
        on_report_close=on_report_close,
        log_prefix=log_prefix,
    )

    async for mode, chunk in agent.astream(
        {"messages": [{"role": "user", "content": prompt}]},
        config or {},
        stream_mode=["messages", "updates"],
    ):
        if mode != "messages":
            continue
        message, _meta = chunk
        text, thinking = _split_chunk(message)
        if thinking:
            await emit({"event": AgentEvent.THINKING_CHUNK, "text": thinking})
        if text:
            await parser.feed(text)

    await emit({"event": AgentEvent.MESSAGE_STOP})


def _split_chunk(message: Any) -> tuple[str, str]:
    """Separate visible text from reasoning in a stream chunk.

    Providers differ: a plain string, or a list of typed blocks where reasoning
    arrives as ``thinking`` / ``reasoning``. Unknown block types are ignored
    rather than leaked into the report.
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
