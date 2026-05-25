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
from time import perf_counter
from typing import Any

from agents.audit.events import AuditEvent, AuditStep, STEP_LABELS
from agents.audit.prompts import (
    build_audit_user_prompt,
    build_unified_system_prompt,
)
from agents.audit.tools import build_audit_mcp_server
from agents.audit.schema import (
    AuditBusinessContext,
    AuditReport,
    AuditSession,
    CrawlResult,
    StructuredAuditData,
    VersionedReport,
)
from agents.engines import Engine, get_env_var_for_engine_provider
from agents.engines import ENGINE_DEFAULT_EFFORT
from agents.models import AgentEffort, AgentPermissionMode, AgentTool, ModelName, Provider, ThinkingMode
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
    light: bool = False,
    emit: EmitFn | None = None,
) -> CrawlResult:
    async with make_client() as client:
        # Fetch sitemap + build plan
        plan = await fetch_crawl_plan(client, root_url, max_blog_posts=max_blog_posts, light=light)

        # Fetch robots.txt + llms.txt concurrently.
        # llms.txt may not exist; SPAs often return a 200 HTML page for unknown
        # paths, so treat HTML responses as "not found" (empty string).
        from service.crawl.sitemap import _is_html_body
        robots_coro = fetch_text(client, plan.robots_txt_url)
        llms_coro = fetch_text(client, plan.llms_txt_url)
        (robots_text, _), (llms_raw, _) = await asyncio.gather(robots_coro, llms_coro)
        llms_text = "" if _is_html_body(llms_raw) else llms_raw

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
    """Extract and parse AuditReport JSON from agent output.

    Tries several fallback strategies so partial/mis-escaped JSON still produces
    a usable report:
      1. Strip markdown fences and parse directly.
      2. If parsing fails because html_report contains unescaped HTML (a known
         model quirk), strip html_report from the JSON string, parse the rest,
         then re-attach any HTML that was found separately.
    """
    stripped = text.strip()

    # Strip markdown fences
    fenced = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", stripped, re.DOTALL)
    if fenced:
        stripped = fenced.group(1).strip()

    start = stripped.find("{")
    end = stripped.rfind("}") + 1
    if start == -1 or end == 0:
        logger.error("audit: no JSON object found in synthesis output (len=%d)", len(stripped))
        return None

    candidate = stripped[start:end]

    # Attempt 1: standard parse
    try:
        return AuditReport.model_validate_json(candidate)
    except Exception:
        pass

    try:
        return AuditReport.model_validate(json.loads(candidate))
    except Exception as exc:
        logger.warning("audit: standard JSON parse failed (%s) — trying html_report strip", exc)

    # Attempt 2: remove html_report field (it may contain unescaped HTML quotes)
    # and parse the rest, then inject an empty html_report so the report is usable.
    html_stripped = re.sub(
        r',?\s*"html_report"\s*:\s*"(?:[^"\\]|\\.)*"',
        '',
        candidate,
        flags=re.DOTALL,
    )
    try:
        raw = json.loads(html_stripped)
        raw.setdefault("html_report", "")
        report = AuditReport.model_validate(raw)
        logger.info("audit: parsed report after stripping html_report field")
        return report
    except Exception as exc2:
        logger.error("audit: all parse attempts failed: %s", exc2)
        return None


def _is_todo_write(block: Any) -> bool:
    """Return True if a content block is a TodoWrite tool call."""
    return (
        getattr(block, "type", None) == "tool_use"
        and getattr(block, "name", None) == AgentTool.TODO_WRITE
        and isinstance(getattr(block, "input", None), dict)
    )


def _extract_report_update(text: str, base: AuditReport | None = None) -> AuditReport | None:
    """Extract updated HTML from <audit_report_update> tags in a chat turn."""
    match = re.search(
        r"<audit_report_update>\s*([\s\S]+?)\s*</audit_report_update>",
        text,
    )
    if not match:
        return None
    from datetime import datetime, timezone
    html = match.group(1).strip()
    return AuditReport(
        url=base.url if base else "",
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        update_label="",
        executive_summary="",
        html_report=html,
    )


async def run_synthesis(
    session_id: str,
    crawl_result: CrawlResult,
    business_context: AuditBusinessContext,
    model_str: str,
    api_key: str,
    provider: Provider,
    emit: EmitFn,
    effort: AgentEffort = ENGINE_DEFAULT_EFFORT[Engine.V3],
    adaptive_thinking: bool = False,
    user_preferences=None,  # UserPreferences | None
    chat_idle_timeout: float = 1800.0,
    report_mode: str = "freehand",
    template_id: str = "",
) -> tuple[AuditReport | None, bool]:  # (report, had_thinking)
    """Single-session artifact pattern: generation + chat in one ClaudeSDKClient.

    The model produces a conversational analysis, then wraps the initial AuditReport
    JSON in <duct_report>…</duct_report> tags. A streaming tag parser buffers the JSON
    (keeping it out of the chat UI) and fires REPORT_UPDATED when the closing tag
    arrives. All non-tag text is forwarded to the frontend as AGENT_MESSAGE_CHUNK.
    Extended thinking tokens are forwarded as THINKING_CHUNK for the collapsible UI.

    Subsequent chat turns continue in the same session (full context) and may produce
    <audit_report_update> blocks for report versioning (existing pattern, unchanged).
    """
    import shutil
    from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient
    from claude_agent_sdk.types import HookMatcher, PermissionResultAllow, PermissionResultDeny, StreamEvent, ThinkingConfigAdaptive

    env_var = get_env_var_for_engine_provider(Engine.V3, provider) or "ANTHROPIC_API_KEY"

    session = _sessions.get(session_id)
    if session is None:
        logger.error("run_synthesis: session %s not found; creating fallback", session_id)
        session = create_audit_session(session_id)

    initial_prompt = build_audit_user_prompt(crawl_result, business_context, user_preferences, report_mode=report_mode)
    system_prompt = build_unified_system_prompt(report_mode=report_mode, template_id=template_id)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _can_use_tool(tool_name: str, input_data: dict, context: Any) -> Any:
        # FetchPages is only useful after the initial report — block it until then
        # to prevent the model from wasting all 60 turns on tool calls before
        # generating the <duct_report> JSON.
        # FetchPages: only after the initial report is generated
        if tool_name == AgentTool.FETCH_PAGES:
            if initial_report is None:
                first_step = (
                    "Call SubmitAuditReport first"
                    if report_mode == "template"
                    else "Produce the <duct_report> HTML first"
                )
                return PermissionResultDeny(
                    message=(
                        f"FetchPages is only available after the initial report has been "
                        f"generated. {first_step}, then use FetchPages to answer follow-up questions."
                    )
                )
            return PermissionResultAllow(updated_input=input_data)

        # WebFetch: redirect own-site URLs to FetchPages for richer structured signals
        if tool_name == AgentTool.WEB_FETCH:
            url = input_data.get("url", "")
            from urllib.parse import urlparse as _parse
            site_host = _parse(crawl_result.plan.root_url).netloc.lower().removeprefix("www.")
            req_host  = _parse(url).netloc.lower().removeprefix("www.")
            if req_host == site_host:
                return PermissionResultDeny(
                    message=(
                        f"Use FetchPages(['{url}']) instead of WebFetch for pages on the "
                        "audited site — it returns structured SEO signals and full body text."
                    )
                )
            return PermissionResultAllow(updated_input=input_data)

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

    async def _dummy_hook(input_data: dict, tool_use_id: str, context: Any) -> dict:
        return {"continue_": True}

    hooks = {"PreToolUse": [HookMatcher(matcher=None, hooks=[_dummy_hook])]}

    async def _emit_report_version(report: AuditReport, version_id: int) -> None:
        if not report.update_label:
            report.update_label = "Initial audit" if version_id == 1 else f"Update {version_id}"
        elapsed_html = (perf_counter() - _open_tag_at) if _open_tag_at else 0.0
        logger.info(
            "synthesis: report v%d finalised — %d chars HTML, %d chunks, %.1fs streaming",
            version_id, len(report.html_report), _report_chunk_count, elapsed_html,
        )
        versioned = VersionedReport(
            version_id=version_id,
            label=report.update_label,
            report=report,
            created_at=report.generated_at,
        )
        session.report_versions.append(versioned)
        await emit({
            "event": AuditEvent.REPORT_UPDATED,
            "version_id": version_id,
            "label": report.update_label,
            "payload": report.model_dump(),
        })

    async def _on_submit_report(args: dict) -> dict:
        nonlocal initial_report
        try:
            structured = StructuredAuditData.model_validate(args)
        except Exception as exc:
            return {
                "status": "validation_error",
                "message": f"Report validation failed — fix these issues and resubmit: {exc}",
            }
        from datetime import datetime, timezone
        version_id = len(session.report_versions) + 1
        report = AuditReport(
            url=crawl_result.plan.root_url,
            generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            update_label="Initial audit" if version_id == 1 else f"Update {version_id}",
            executive_summary=structured.executive_summary,
            report_mode="template",
            template_id=template_id,
            structured_data=structured,
        )
        initial_report = report
        await _emit_report_version(report, version_id)
        return {"status": "received", "version_id": version_id}

    # ------------------------------------------------------------------
    # SDK options
    # ------------------------------------------------------------------

    from config import get_configs, sentry_otel_env
    _cfg = get_configs()

    _sdk_env: dict[str, str] = {
        "OTEL_SERVICE_NAME": "duct-audit-seo",
        "ENABLE_PROMPT_CACHING_1H": "1",
        # Sentry OTLP tracing — spans for every turn, tool call, LLM request.
        # Activated only when sdk_otel_enabled=true + sentry_dsn is set.
        **sentry_otel_env(_cfg),
    }
    if api_key:
        _sdk_env[env_var] = api_key

    def _on_subprocess_stderr(line: str) -> None:
        logger.error("audit subprocess stderr [%s]: %s", session_id, line.rstrip())

    _cli_path = shutil.which("claude") or None
    _extra_tools = [AgentTool.SUBMIT_AUDIT_REPORT] if report_mode == "template" else []
    _submit_cb = _on_submit_report if report_mode == "template" else None
    _mcp = build_audit_mcp_server(crawl_result, report_mode=report_mode, on_submit_report=_submit_cb)

    options = ClaudeAgentOptions(
        model=model_str,
        permission_mode=AgentPermissionMode.DONT_ASK,
        allowed_tools=[
            AgentTool.ASK_USER_QUESTION,
            AgentTool.TODO_WRITE,
            AgentTool.WEB_SEARCH,
            AgentTool.WEB_FETCH,
            AgentTool.FETCH_PAGES,  # mcp__duct_crawl__FetchPages — in-process MCP
            *_extra_tools,
        ],
        can_use_tool=_can_use_tool,
        hooks=hooks,
        max_turns=60,
        system_prompt=system_prompt,
        include_partial_messages=True,
        thinking=ThinkingConfigAdaptive(type=ThinkingMode.ADAPTIVE) if adaptive_thinking else None,
        effort=effort,
        env=_sdk_env,
        stderr=_on_subprocess_stderr,
        setting_sources=[],
        # sandbox intentionally omitted: the audit agent uses no Bash tools, so
        # macOS seatbelt sandboxing adds no security value but causes the subprocess
        # to exit with code 1 when launched from within a uvicorn server process.
        cli_path=_cli_path,
        mcp_servers={"duct_crawl": _mcp},
    )

    # ------------------------------------------------------------------
    # Message generator — initial prompt then chat queue
    # ------------------------------------------------------------------

    async def message_gen():
        yield {"type": "user", "message": {"role": "user", "content": initial_prompt}}
        while True:
            try:
                msg = await asyncio.wait_for(
                    session.chat_queue.get(), timeout=chat_idle_timeout  # type: ignore[attr-defined]
                )
            except asyncio.TimeoutError:
                # The chat queue was empty — no user follow-up arrived.
                # Synthesis is still running in the background; this only
                # means no further messages will be sent to the model.
                logger.info(
                    "audit: session %s chat queue idle (synthesis still running)",
                    session_id,
                )
                break
            if msg is None:
                break
            yield {"type": "user", "message": msg}

    # ------------------------------------------------------------------
    # Streaming tag parser state
    # ------------------------------------------------------------------

    # Report JSON tag — HTML is generated on demand, not during initial synthesis.
    _OPEN_TAG = "<duct_report>"
    _CLOSE_TAG = "</duct_report>"

    _in_report_tag = False
    _report_buf = ""
    _holdback = ""
    _turn_text: list[str] = []
    had_thinking = False
    initial_report: AuditReport | None = None
    _first_token_at: float | None = None   # perf_counter when first text delta arrived
    _open_tag_at: float | None = None      # perf_counter when <duct_report> opened
    _report_chunk_count = 0                # total REPORT_CHUNK events emitted

    async def _flush_holdback() -> None:
        nonlocal _holdback
        if _holdback:
            await emit({"event": AuditEvent.AGENT_MESSAGE_CHUNK, "text": _holdback})
            _turn_text.append(_holdback)
            _holdback = ""

    async def _process_text(chunk: str) -> None:
        """Stream <duct_report> HTML tokens live; stream everything else as AGENT_MESSAGE_CHUNK."""
        nonlocal _in_report_tag, _report_buf, _holdback, initial_report
        nonlocal _open_tag_at, _report_chunk_count

        if _in_report_tag:
            if _CLOSE_TAG in chunk:
                # Close tag fully contained in this chunk
                safe, _, remainder = chunk.partition(_CLOSE_TAG)
                if safe:
                    _report_chunk_count += 1
                    _report_buf += safe
                    await emit({"event": AuditEvent.REPORT_CHUNK, "text": safe})
                _in_report_tag = False
                html_part = _report_buf
                _report_buf = ""
                from datetime import datetime, timezone
                summary = "".join(_turn_text).strip()
                initial_report = AuditReport(
                    url=crawl_result.plan.root_url,
                    generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    update_label="Initial audit",
                    executive_summary=summary,
                    html_report=html_part.strip(),
                )
                await _emit_report_version(initial_report, 1)
                if remainder:
                    await _process_text(remainder)
            else:
                # Accumulate and check for close tag split across chunks
                _report_buf += chunk
                if _CLOSE_TAG in _report_buf:
                    html_part, _, remainder = _report_buf.partition(_CLOSE_TAG)
                    _in_report_tag = False
                    _report_buf = ""
                    from datetime import datetime, timezone
                    summary = "".join(_turn_text).strip()
                    initial_report = AuditReport(
                        url=crawl_result.plan.root_url,
                        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        update_label="Initial audit",
                        executive_summary=summary,
                        html_report=html_part.strip(),
                    )
                    await _emit_report_version(initial_report, 1)
                    if remainder:
                        await _process_text(remainder)
                elif chunk:
                    _report_chunk_count += 1
                    if _report_chunk_count % 50 == 0:
                        logger.info(
                            "synthesis: HTML streaming — %d chunks, ~%d chars buffered",
                            _report_chunk_count, len(_report_buf),
                        )
                    await emit({"event": AuditEvent.REPORT_CHUNK, "text": chunk})
            return

        working = _holdback + chunk
        _holdback = ""

        if _OPEN_TAG in working:
            before, _, after = working.partition(_OPEN_TAG)
            if before:
                await emit({"event": AuditEvent.AGENT_MESSAGE_CHUNK, "text": before})
                _turn_text.append(before)
            _in_report_tag = True
            _report_buf = ""
            _open_tag_at = perf_counter()
            elapsed_to_tag = (_open_tag_at - _first_token_at) if _first_token_at else 0.0
            logger.info(
                "synthesis: <duct_report> opened — HTML streaming started (%.1fs after first token)",
                elapsed_to_tag,
            )
            # Recurse to process `after` through the streaming path
            if after:
                await _process_text(after)
        else:
            holdback_len = len(_OPEN_TAG) - 1
            if len(working) > holdback_len:
                safe = working[:-holdback_len]
                _holdback = working[-holdback_len:]
                await emit({"event": AuditEvent.AGENT_MESSAGE_CHUNK, "text": safe})
                _turn_text.append(safe)
            else:
                _holdback = working

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    try:
        async with ClaudeSDKClient(options) as client:
            await client.query(message_gen())

            async for msg in client.receive_response():
                if isinstance(msg, StreamEvent):
                    ev = msg.event
                    ev_type = ev.get("type")

                    if ev_type == "content_block_delta":
                        delta = ev.get("delta", {})
                        delta_type = delta.get("type")

                        if delta_type == "thinking_delta":
                            thinking_text = delta.get("thinking", "")
                            if thinking_text:
                                had_thinking = True
                                await emit({"event": AuditEvent.THINKING_CHUNK, "text": thinking_text})

                        elif delta_type == "text_delta":
                            chunk = delta.get("text", "")
                            if chunk:
                                if _first_token_at is None:
                                    _first_token_at = perf_counter()
                                    logger.info("synthesis: first text token received")
                                await _process_text(chunk)

                    elif ev_type == "message_stop":
                        await _flush_holdback()
                        full_text = "".join(_turn_text)
                        _turn_text.clear()

                        # Fallback: if JSON was parsed but REPORT_UPDATED not yet emitted
                        if initial_report is not None and len(session.report_versions) == 0:
                            await _emit_report_version(initial_report, 1)

                        # Freehand only: check for <audit_report_update> in accumulated text
                        if report_mode == "freehand" and initial_report is not None and session.report_versions:
                            updated = _extract_report_update(full_text, base=initial_report)
                            if updated:
                                v_id = len(session.report_versions) + 1
                                await _emit_report_version(updated, v_id)

                        await emit({"event": AuditEvent.MESSAGE_STOP})

                    continue  # StreamEvent fully handled

                if hasattr(msg, "content") and msg.content:
                    for block in msg.content:
                        if _is_todo_write(block):
                            await emit({"event": AuditEvent.TODO_UPDATE, "todos": block.input.get("todos", [])})

    except Exception:
        logger.exception("audit v3: run_synthesis failed for session %s", session_id)

    return initial_report, had_thinking


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
        effort: AgentEffort = ENGINE_DEFAULT_EFFORT[Engine.V3],
        adaptive_thinking: bool = False,
    ) -> None:
        self.provider = provider
        self.model = model
        self.model_str = _resolve_model(provider, model)
        self._api_key = api_key
        self.effort = effort
        self.adaptive_thinking = adaptive_thinking

    async def run_pipeline(
        self,
        session_id: str,
        url: str,
        business_context: AuditBusinessContext,
        emit: EmitFn,
        max_blog_posts: int = 5,
        crawl_depth: str = "deep",
        chat_idle_timeout: float = 1800.0,
        user_preferences=None,  # UserPreferences | None
        report_mode: str = "freehand",
        template_id: str = "seo_v1",
    ) -> AuditReport | None:
        from agents.audit.schema import CrawlDepth
        session = _sessions.get(session_id)
        if session:
            session.report_mode = report_mode
            session.template_id = template_id
        start = perf_counter()
        _t = perf_counter  # alias for inline timings

        await emit({
            "event": AuditEvent.STEP_STARTED,
            "step_id": AuditStep.FETCH_SITEMAP,
            "label": STEP_LABELS[AuditStep.FETCH_SITEMAP],
            "status": "running",
        })
        light = (crawl_depth == CrawlDepth.LIGHT)
        t0 = _t()
        crawl_result = await run_crawl(url, max_blog_posts=max_blog_posts, light=light, emit=emit)
        logger.info("⏱ crawl: %.1fs  pages=%d", _t() - t0, len(crawl_result.pages))

        _robots = crawl_result.robots_txt or ""
        _llms   = crawl_result.llms_txt   or ""
        await emit({
            "event": AuditEvent.STEP_FINISHED,
            "step_id": AuditStep.FETCH_SITEMAP,
            "label": STEP_LABELS[AuditStep.FETCH_SITEMAP],
            "status": "success",
            "payload": {
                "landing_pages":      len(crawl_result.plan.landing_pages),
                "blog_posts":         len(crawl_result.plan.blog_posts),
                "sitemap_url":        crawl_result.plan.sitemap_url,
                "landing_page_urls":  crawl_result.plan.landing_pages,
                "blog_post_urls":     crawl_result.plan.blog_posts,
                "robots_txt_found":   bool(_robots),
                "robots_txt_bytes":   len(_robots.encode()),
                "robots_txt_lines":   _robots.count("\n") + 1 if _robots else 0,
                "robots_txt_preview": _robots[:300],
                "llms_txt_found":     bool(_llms),
                "llms_txt_bytes":     len(_llms.encode()) if _llms else 0,
                "llms_txt_lines":     _llms.count("\n") + 1 if _llms else 0,
                "llms_txt_preview":   _llms[:300],
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
            "payload": {
                "pages": [
                    {
                        "url":                    p.url,
                        "page_type":              p.page_type,
                        "http_status":            p.http_status,
                        "word_count":             p.word_count_approx,
                        "body_preview":           p.body_text_snippet,
                        "title":                  p.title,
                        "title_chars":            len(p.title),
                        "meta_description":       p.meta_description,
                        "meta_description_chars": len(p.meta_description),
                        "images":                 p.image_count,
                        "images_missing_alt":     p.images_missing_alt,
                        "has_schema_org":         p.has_schema_org,
                        "schema_types":           p.schema_types,
                        "has_canonical":          bool(p.canonical),
                        "canonical":              p.canonical,
                        "is_noindex":             p.is_noindex,
                        "hreflang_count":         len(p.hreflang_langs),
                        "internal_links":         len(p.internal_links),
                        "external_links":         len(p.external_links),
                    }
                    for p in crawl_result.pages
                ],
                "errors": crawl_result.crawl_errors,
            },
        })

        await emit({
            "event": AuditEvent.STEP_STARTED,
            "step_id": AuditStep.SYNTHESIZE_AUDIT,
            "label": STEP_LABELS[AuditStep.SYNTHESIZE_AUDIT],
            "status": "running",
        })

        t1 = _t()
        report, had_thinking = await run_synthesis(
            session_id=session_id,
            crawl_result=crawl_result,
            business_context=business_context,
            model_str=self.model_str,
            api_key=self._api_key,
            provider=self.provider,
            emit=emit,
            effort=self.effort,
            adaptive_thinking=self.adaptive_thinking,
            chat_idle_timeout=chat_idle_timeout,
            user_preferences=user_preferences,
            report_mode=report_mode,
            template_id=template_id,
        )

        await emit({
            "event": AuditEvent.STEP_FINISHED,
            "step_id": AuditStep.SYNTHESIZE_AUDIT,
            "label": STEP_LABELS[AuditStep.SYNTHESIZE_AUDIT],
            "status": "success" if report else "error",
            "payload": {"reasoned": had_thinking},
        })

        elapsed = perf_counter() - start
        logger.info(
            "⏱ pipeline done  total=%.1fs  crawl=%.1fs  synthesis=%.1fs  "
            "pages=%d  thinking=%s  session=%s",
            elapsed,
            t1 - t0,
            elapsed - (t1 - t0),
            len(crawl_result.pages),
            had_thinking,
            session_id,
        )
        return report
