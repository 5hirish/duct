"""ClaudeAuditRunner — SEO audit agent powered by Claude Agent SDK (v3 engine).

Architecture:
  Phase 1 (crawl): Pure Python via httpx + stdlib parsers.
    Fetches sitemap, robots.txt, llms.txt, and all selected pages concurrently.

  Phase 2 (synthesis): ClaudeSDKClient (streaming mode) with a single agent.
    - Allowed tool: AskUserQuestion (for mid-run clarifying questions, max 3)
    - can_use_tool callback bridges AskUserQuestion → SSE stream → asyncio.Future
    - The message generator stays alive for continued chat after the initial report

  Phase 3 (continued session): The message_generator keeps yielding from the
    asyncio.Queue as the user sends follow-up messages, keeping the SDK session alive.

Note: Uses streaming mode (ClaudeSDKClient) not query() because:
  1. AskUserQuestion requires streaming mode + PreToolUse hook in Python SDK
  2. Persistent continued-chat session requires streaming input mode
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Callable, Awaitable
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any

from agents.audit.events import AuditEvent, AuditStep, STEP_LABELS
from agents.audit.prompts import (
    build_audit_system_prompt,
    build_audit_user_prompt,
    build_chat_seed_message,
    build_chat_system_prompt,
)
from agents.audit.schema import (
    AuditBusinessContext,
    AuditReport,
    AuditSession,
    CrawlResult,
    VersionedReport,
)
from agents.engines import Engine, get_env_var_for_engine_provider
from agents.models import AgentPermissionMode, AgentTool, ModelName, Provider
from service.crawl.extractor import extract_signals
from service.crawl.fetcher import fetch_text, make_client
from service.crawl.sitemap import fetch_crawl_plan

logger = logging.getLogger(__name__)

_FALLBACK_MODEL = "claude-sonnet-4-6"
_ANTHROPIC_MODEL_MAP: dict[ModelName, str] = {
    ModelName.CLAUDE_SONNET: "claude-sonnet-4-6",
    ModelName.CLAUDE_HAIKU: "claude-haiku-4-5-20251001",
}

EmitFn = Callable[[dict[str, Any]], Awaitable[None]]

# Module-level session registry (in-process only; not shared across Railway instances)
_sessions: dict[str, AuditSession] = {}


def get_session(session_id: str) -> AuditSession | None:
    return _sessions.get(session_id)


def create_audit_session(session_id: str, agent_type: str = "audit_seo") -> AuditSession:
    """Create and register a new AuditSession with both queues.

    Call this before starting run_pipeline so the SSE stream endpoint
    can connect to event_queue independently of when the pipeline starts.
    """
    import time
    session = AuditSession(
        session_id=session_id,
        agent_type=agent_type,
        event_queue=asyncio.Queue(),   # agent → SSE consumer
        chat_queue=asyncio.Queue(),    # user messages → agent (Phase 3)
        answer_future=None,
        created_at=time.monotonic(),
    )
    _sessions[session_id] = session
    return session


def close_session(session_id: str) -> None:
    session = _sessions.pop(session_id, None)
    if session:
        # Signal Phase 3 message generator to stop
        try:
            session.chat_queue.put_nowait(None)  # type: ignore[attr-defined]
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Phase 1 — Crawl
# ---------------------------------------------------------------------------

async def _fetch_and_extract(
    client: Any,
    url: str,
    page_type: str,
) -> Any:
    from service.crawl.fetcher import fetch_text as _fetch_text
    html, status = await _fetch_text(client, url)
    signals = extract_signals(html, url, page_type)
    signals.http_status = status
    return signals


async def run_crawl(
    root_url: str,
    max_blog_posts: int = 5,
    emit: EmitFn | None = None,
) -> CrawlResult:
    async with make_client() as client:
        # Fetch sitemap + build plan
        plan = await fetch_crawl_plan(client, root_url, max_blog_posts=max_blog_posts)

        # Fetch robots.txt + llms.txt concurrently
        robots_coro = fetch_text(client, plan.robots_txt_url)
        llms_coro = fetch_text(client, plan.llms_txt_url)
        (robots_text, _), (llms_text, _) = await asyncio.gather(robots_coro, llms_coro)

        # Crawl all pages concurrently
        all_urls = [
            (url, "landing_page") for url in plan.landing_pages
        ] + [
            (url, "blog_post") for url in plan.blog_posts
        ]

        tasks = [_fetch_and_extract(client, url, ptype) for url, ptype in all_urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    pages = []
    errors = []
    for idx, result in enumerate(results):
        if isinstance(result, Exception):
            url = all_urls[idx][0]
            logger.warning("crawl: failed to fetch %s: %s", url, result)
            errors.append(f"{url}: {result}")
        else:
            pages.append(result)

    return CrawlResult(
        plan=plan,
        robots_txt=robots_text,
        llms_txt=llms_text,
        pages=pages,
        crawl_errors=errors,
    )


# ---------------------------------------------------------------------------
# Phase 2 — Synthesis via Claude Agent SDK streaming mode
# ---------------------------------------------------------------------------

def _resolve_model(provider: Provider, model: ModelName) -> str:
    if provider != Provider.ANTHROPIC:
        logger.warning(
            "audit v3: only Anthropic supported; ignoring provider=%s, falling back to %s",
            provider.value,
            _FALLBACK_MODEL,
        )
        return _FALLBACK_MODEL
    return _ANTHROPIC_MODEL_MAP.get(model, _FALLBACK_MODEL)


def _parse_report(text: str) -> AuditReport | None:
    """Extract and parse AuditReport JSON from the agent's result text."""
    stripped = text.strip()

    # Strip markdown fences if present
    fenced = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", stripped)
    if fenced:
        stripped = fenced.group(1).strip()

    # Find JSON object boundaries
    start = stripped.find("{")
    end = stripped.rfind("}") + 1
    if start == -1 or end == 0:
        logger.error("audit: no JSON object found in synthesis output")
        return None

    try:
        return AuditReport.model_validate_json(stripped[start:end])
    except Exception as exc:
        logger.error("audit: AuditReport validation failed: %s", exc)
        # Try relaxed parse
        try:
            raw = json.loads(stripped[start:end])
            return AuditReport.model_validate(raw)
        except Exception:
            return None


def _is_todo_write(block: Any) -> bool:
    """Return True if a content block is a TodoWrite tool call."""
    return (
        getattr(block, "type", None) == "tool_use"
        and getattr(block, "name", None) == AgentTool.TODO_WRITE
        and isinstance(getattr(block, "input", None), dict)
    )


def _extract_report_update(text: str) -> AuditReport | None:
    """Extract AuditReport from <audit_report_update> tags in chat response."""
    match = re.search(
        r"<audit_report_update>\s*([\s\S]+?)\s*</audit_report_update>",
        text,
    )
    if not match:
        return None
    return _parse_report(match.group(1))


async def run_synthesis(
    session_id: str,
    crawl_result: CrawlResult,
    business_context: AuditBusinessContext,
    model_str: str,
    api_key: str,
    provider: Provider,
    emit: EmitFn,
) -> AuditReport | None:
    """Run Phase 2+3 via two separate ClaudeSDKClient sessions.

    Phase 2 (initial audit):
      - Uses output_format with AuditReport JSON schema for validated structured output.
      - Uses AskUserQuestion for mid-run clarifications.
      - include_partial_messages=True but text chunks are NOT streamed to the user
        (the output is a JSON blob, not a conversational response).

    Phase 3 (continued chat):
      - Separate ClaudeSDKClient session seeded with the initial report and Q&A context.
      - include_partial_messages=True; text chunks ARE streamed as agent_message_chunk events.
      - output_format is NOT set — responses are conversational. If the agent modifies
        the report it wraps the JSON in <audit_report_update> tags.

    Splitting the sessions is necessary because output_format applies session-wide: using it
    in a single session would force all follow-up chat turns to return AuditReport JSON,
    breaking conversational responses.
    """
    from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient
    from claude_agent_sdk.types import HookMatcher, PermissionResultAllow, ResultMessage, StreamEvent

    env_var = get_env_var_for_engine_provider(Engine.V3, provider) or "ANTHROPIC_API_KEY"

    # Session must already exist — created by create_audit_session() before run_pipeline()
    session = _sessions.get(session_id)
    if session is None:
        logger.error("run_synthesis: session %s not found; creating fallback", session_id)
        session = create_audit_session(session_id)

    initial_prompt = build_audit_user_prompt(crawl_result, business_context)
    audit_system_prompt = build_audit_system_prompt()
    chat_system_prompt = build_chat_system_prompt()

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def _make_can_use_tool():
        async def can_use_tool(tool_name: str, input_data: dict, context: Any) -> Any:
            if tool_name != AgentTool.ASK_USER_QUESTION:
                return PermissionResultAllow(updated_input=input_data)
            loop = asyncio.get_event_loop()
            fut: asyncio.Future = loop.create_future()
            session.answer_future = fut  # type: ignore[assignment]
            await emit({
                "event": AuditEvent.QUESTIONS_REQUIRED,
                "session_id": session_id,
                "questions": input_data.get("questions", []),
            })
            try:
                answers = await asyncio.wait_for(asyncio.shield(fut), timeout=120.0)
            except asyncio.TimeoutError:
                logger.warning("audit: AskUserQuestion timed out for session %s", session_id)
                answers = {}
            finally:
                session.answer_future = None
            return PermissionResultAllow(updated_input={
                "questions": input_data.get("questions", []),
                "answers": answers,
            })
        return can_use_tool

    async def dummy_hook(input_data: dict, tool_use_id: str, context: Any) -> dict:
        return {"continue_": True}

    hooks = {"PreToolUse": [HookMatcher(matcher=None, hooks=[dummy_hook])]}

    # ------------------------------------------------------------------
    # Phase 2 — initial audit with structured output
    # ------------------------------------------------------------------

    initial_report: AuditReport | None = None
    # Track Q&A exchanges so Phase 3 can be seeded with context
    qa_context: list[dict] = []

    async def audit_message_gen():
        yield {"type": "user", "message": {"role": "user", "content": initial_prompt}}

    # Pass API key directly to the subprocess env rather than mutating os.environ.
    # Mutating os.environ is not safe when multiple sessions run concurrently because
    # one session's finally-block cleanup can remove the key before another session
    # has spawned its subprocess.
    _sdk_env: dict[str, str] = {
        "OTEL_SERVICE_NAME": "duct-audit-seo",
        "ENABLE_PROMPT_CACHING_1H": "1",
    }
    if api_key:
        _sdk_env[env_var] = api_key

    # Capture subprocess stderr so the actual claude CLI error appears in server logs
    # rather than only "Check stderr output for details".
    def _on_subprocess_stderr(line: str) -> None:
        logger.error("audit subprocess stderr [%s]: %s", session_id, line.rstrip())

    audit_options = ClaudeAgentOptions(
        model=model_str,
        permission_mode=AgentPermissionMode.DONT_ASK,  # deny any tool not in allowed_tools; AskUserQuestion still routes through canUseTool
        allowed_tools=[AgentTool.ASK_USER_QUESTION, AgentTool.TODO_WRITE],
        can_use_tool=_make_can_use_tool(),
        hooks=hooks,
        max_turns=10,
        system_prompt=audit_system_prompt,
        include_partial_messages=True,
        output_format={
            "type": "json_schema",
            "schema": AuditReport.model_json_schema(),
        },
        env=_sdk_env,
        stderr=_on_subprocess_stderr,
    )

    try:
        async with ClaudeSDKClient(audit_options) as client:
            await client.query(audit_message_gen())

            async for msg in client.receive_response():
                # StreamEvent — we don't forward the raw JSON tokens to the user
                # but we could log progress here if needed
                if isinstance(msg, StreamEvent):
                    ev = msg.event
                    if ev.get("type") == "content_block_delta":
                        delta = ev.get("delta", {})
                        if delta.get("type") == "text_delta":
                            chunk = delta.get("text", "")
                            if chunk:
                                await emit({"event": AuditEvent.SYNTHESIS_CHUNK, "text": chunk})
                    continue

                # ResultMessage — check for structured_output first, fall back to .result text
                if isinstance(msg, ResultMessage):
                    if msg.subtype == "error_max_structured_output_retries":
                        logger.error("audit: structured output retries exceeded for session %s", session_id)
                    elif msg.structured_output:
                        try:
                            initial_report = AuditReport.model_validate(msg.structured_output)
                        except Exception as exc:
                            logger.warning("audit: structured_output validation failed (%s), trying .result", exc)
                            if msg.result:
                                initial_report = _parse_report(msg.result)
                    elif msg.result:
                        initial_report = _parse_report(msg.result)
                    break  # initial audit is single-turn; stop after first ResultMessage

                # AssistantMessage — extract TodoWrite updates + accumulate Q&A context
                if hasattr(msg, "content") and msg.content:
                    for block in msg.content:
                        if _is_todo_write(block):
                            await emit({"event": AuditEvent.TODO_UPDATE, "todos": block.input.get("todos", [])})
                    text_parts = [
                        block.text for block in msg.content if hasattr(block, "text")
                    ]
                    if text_parts:
                        qa_context.append({"role": "assistant", "content": "\n".join(text_parts)})

    except Exception:
        logger.exception("audit v3: Phase 2 (synthesis) failed for session %s", session_id)

    if initial_report:
        if not initial_report.update_label:
            initial_report.update_label = "Initial audit"
        versioned = VersionedReport(
            version_id=1,
            label=initial_report.update_label,
            report=initial_report,
            created_at=initial_report.generated_at,
        )
        session.report_versions.append(versioned)
        await emit({
            "event": AuditEvent.REPORT_UPDATED,
            "version_id": 1,
            "label": initial_report.update_label,
            "payload": initial_report.model_dump(),
        })

    # ------------------------------------------------------------------
    # Phase 3 — continued chat session (no output_format; conversational)
    # ------------------------------------------------------------------

    # Seed message: include the report without html_report — that field is 10-20KB of HTML
    # the model doesn't need to reason about when answering conversational questions.
    if initial_report:
        report_without_html = initial_report.model_copy(update={"html_report": ""})
        report_json = report_without_html.model_dump_json(exclude={"html_report"})
    else:
        report_json = "null"
    seed_content = build_chat_seed_message(crawl_result.plan.root_url, report_json)

    async def chat_message_gen():
        # Seed message — gives the chat session full context of the initial audit
        yield {"type": "user", "message": {"role": "user", "content": seed_content}}

        # Wait for chat messages from the session's chat_queue
        while True:
            try:
                msg = await asyncio.wait_for(
                    session.chat_queue.get(), timeout=1800.0  # type: ignore[attr-defined]
                )
            except asyncio.TimeoutError:
                logger.info("audit: session %s idle timeout", session_id)
                break
            if msg is None:
                break
            yield {"type": "user", "message": msg}

    chat_options = ClaudeAgentOptions(
        model=model_str,
        permission_mode=AgentPermissionMode.DONT_ASK,
        allowed_tools=[AgentTool.ASK_USER_QUESTION, AgentTool.TODO_WRITE],
        can_use_tool=_make_can_use_tool(),
        hooks=hooks,
        max_turns=50,
        system_prompt=chat_system_prompt,
        include_partial_messages=True,
        env=_sdk_env,
        stderr=_on_subprocess_stderr,
        # No output_format — conversational responses
    )

    try:
        async with ClaudeSDKClient(chat_options) as client:
            await client.query(chat_message_gen())

            current_chat_text: list[str] = []

            async for msg in client.receive_response():
                # Stream text tokens in real-time for chat responses
                if isinstance(msg, StreamEvent):
                    event = msg.event
                    if event.get("type") == "content_block_delta":
                        delta = event.get("delta", {})
                        if delta.get("type") == "text_delta":
                            chunk = delta.get("text", "")
                            if chunk:
                                current_chat_text.append(chunk)
                                await emit({"event": AuditEvent.AGENT_MESSAGE_CHUNK, "text": chunk})
                    elif event.get("type") == "message_stop":
                        # Full message is done — check for report update in accumulated text
                        full_text = "".join(current_chat_text)
                        current_chat_text.clear()
                        updated = _extract_report_update(full_text)
                        if updated:
                            v_id = len(session.report_versions) + 1
                            if not updated.update_label:
                                updated.update_label = f"Update {v_id}"
                            versioned = VersionedReport(
                                version_id=v_id,
                                label=updated.update_label,
                                report=updated,
                                created_at=updated.generated_at,
                            )
                            session.report_versions.append(versioned)
                            await emit({
                                "event": AuditEvent.REPORT_UPDATED,
                                "version_id": v_id,
                                "label": updated.update_label,
                                "payload": updated.model_dump(),
                            })
                    continue

                # AssistantMessage — extract TodoWrite updates
                # (text is already streamed via StreamEvent above)
                if hasattr(msg, "content") and msg.content:
                    for block in msg.content:
                        if _is_todo_write(block):
                            await emit({"event": AuditEvent.TODO_UPDATE, "todos": block.input.get("todos", [])})


    except Exception:
        logger.exception("audit v3: Phase 3 (chat) failed for session %s", session_id)

    return initial_report


# ---------------------------------------------------------------------------
# Public runner class
# ---------------------------------------------------------------------------

class ClaudeAuditRunner:
    """Full SEO audit pipeline using Claude Agent SDK (v3 engine)."""

    def __init__(
        self,
        api_key: str,
        provider: Provider = Provider.ANTHROPIC,
        model: ModelName = ModelName.CLAUDE_SONNET,
    ) -> None:
        self.provider = provider
        self.model = model
        self.model_str = _resolve_model(provider, model)
        self._api_key = api_key

    async def run_pipeline(
        self,
        session_id: str,
        url: str,
        business_context: AuditBusinessContext,
        emit: EmitFn,
        max_blog_posts: int = 5,
    ) -> AuditReport | None:
        start = perf_counter()

        await emit({
            "event": AuditEvent.STEP_STARTED,
            "step_id": AuditStep.FETCH_SITEMAP,
            "label": STEP_LABELS[AuditStep.FETCH_SITEMAP],
            "status": "running",
        })
        crawl_result = await run_crawl(url, max_blog_posts=max_blog_posts, emit=emit)
        await emit({
            "event": AuditEvent.STEP_FINISHED,
            "step_id": AuditStep.FETCH_SITEMAP,
            "label": STEP_LABELS[AuditStep.FETCH_SITEMAP],
            "status": "success",
            "payload": {
                "landing_pages": len(crawl_result.plan.landing_pages),
                "blog_posts": len(crawl_result.plan.blog_posts),
            },
        })

        await emit({
            "event": AuditEvent.STEP_STARTED,
            "step_id": AuditStep.CRAWL_PAGES,
            "label": f"Crawled {len(crawl_result.pages)} pages",
            "status": "running",
        })
        await emit({
            "event": AuditEvent.STEP_FINISHED,
            "step_id": AuditStep.CRAWL_PAGES,
            "label": f"Crawled {len(crawl_result.pages)} pages",
            "status": "success",
        })

        await emit({
            "event": AuditEvent.STEP_STARTED,
            "step_id": AuditStep.SYNTHESIZE_AUDIT,
            "label": STEP_LABELS[AuditStep.SYNTHESIZE_AUDIT],
            "status": "running",
        })

        report = await run_synthesis(
            session_id=session_id,
            crawl_result=crawl_result,
            business_context=business_context,
            model_str=self.model_str,
            api_key=self._api_key,
            provider=self.provider,
            emit=emit,
        )

        await emit({
            "event": AuditEvent.STEP_FINISHED,
            "step_id": AuditStep.SYNTHESIZE_AUDIT,
            "label": STEP_LABELS[AuditStep.SYNTHESIZE_AUDIT],
            "status": "success" if report else "error",
        })

        elapsed = perf_counter() - start
        logger.info("audit v3: pipeline completed in %.1fs for session %s", elapsed, session_id)
        return report
