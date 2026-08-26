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
import os
import re
from collections import deque
from collections.abc import Awaitable, Callable
from contextlib import suppress
from time import perf_counter
from typing import Any

from agents.audit.events import AuditEvent, AuditStep, STEP_LABELS, StepStatus
from agents.audit.prompts import (
    build_audit_user_prompt,
    build_unified_system_prompt,
)
from agents.audit.tools import build_audit_mcp_server
from agents.audit.schema import (
    AuditBusinessContext,
    AuditReport,
    AuditSession,
    AuditTool,
    CrawlResult,
    CrawlSummary,
    StructuredAuditData,
    VersionedReport,
)
from agents.core import claude_sdk as _sdk
from agents.core import session as _core_session
from agents.core.session import bridge_ask_user_question, register_session
from agents.core.stream import DuctReportStreamParser, pump_stream_event
from agents.engines import Engine, get_env_var_for_engine_provider
from agents.engines import ENGINE_DEFAULT_EFFORT
from agents.models import AgentEffort, AgentPermissionMode, AgentTool, ModelName, Provider, ThinkingMode
from service.crawl.extractor import extract_signals
from service.crawl.fetcher import fetch, fetch_text, make_client
from service.crawl.sitemap import fetch_crawl_plan

logger = logging.getLogger(__name__)

# Set AUDIT_VERBOSE_LOGGING=1 to log per-message SDK events and costs to terminal
_VERBOSE = os.environ.get("AUDIT_VERBOSE_LOGGING", "").lower() in ("1", "true")

# Anthropic-only engine; model strings are owned by the ModelName enum in agents/models.py.
_ANTHROPIC_MODELS = (ModelName.CLAUDE_SONNET, ModelName.CLAUDE_HAIKU)

# Connector knowledge packs baked into the audit system prompt. STATIC per
# configuration — never vary these per request (cached-prefix invariant).
# google_ads/ga4/gtm join once execution tools mount (Phase 4).
_AUDIT_KNOWLEDGE_PACKS: tuple[str, ...] = ("gsc",)

EmitFn = Callable[[dict[str, Any]], Awaitable[None]]

# Session registry + close semantics are shared (agents/core/session.py). These
# wrappers keep the audit-specific import surface and AuditSession typing.
get_session = _core_session.get_session
close_session = _core_session.close_session


def create_audit_session(session_id: str, agent_type: str = "audit_seo") -> AuditSession:
    """Create and register a new AuditSession with both queues.

    Call this before starting run_pipeline so the SSE stream endpoint
    can connect to event_queue independently of when the pipeline starts.
    """
    session = AuditSession(
        session_id=session_id,
        agent_type=agent_type,
        event_queue=asyncio.Queue(),   # agent → SSE consumer
        chat_queue=asyncio.Queue(),    # user messages → agent (Phase 3)
        answer_future=None,
    )
    return register_session(session)


# ---------------------------------------------------------------------------
# Phase 1 — Crawl
# ---------------------------------------------------------------------------

async def _fetch_and_extract(
    client: Any,
    url: str,
    page_type: str,
) -> Any:
    result = await fetch(client, url)
    signals = extract_signals(result.text, url, page_type, response_headers=result.headers)
    signals.http_status = result.status
    signals.ttfb_ms = result.ttfb_ms
    signals.redirect_chain = result.redirect_chain
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
    if provider != Provider.ANTHROPIC or model not in _ANTHROPIC_MODELS:
        logger.warning(
            "audit v3: only Anthropic supported; ignoring provider=%s, falling back to %s",
            provider.value,
            ModelName.CLAUDE_SONNET.value,
        )
        return ModelName.CLAUDE_SONNET.value
    return model.value


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
    research_context=None,  # AuditResearchContext | None
    resume: bool = False,
    extra_context: str = "",
) -> tuple[AuditReport | None, bool]:  # (report, had_thinking)
    """Single-session artifact pattern: generation + chat in one ClaudeSDKClient.

    resume=True continues a persisted conversation: session.report_versions must
    be pre-seeded (rehydrated from the artifact store), crawl_result is a stub
    (root_url only — no crawl happens), the initial synthesis turn is skipped,
    and the session goes straight to the chat loop. History context arrives via
    the reprime block on the user's first message (routes.agents.send_message).

    The model produces a conversational analysis, then wraps the initial AuditReport
    JSON in <duct_report>…</duct_report> tags. A streaming tag parser buffers the JSON
    (keeping it out of the chat UI) and fires REPORT_UPDATED when the closing tag
    arrives. All non-tag text is forwarded to the frontend as AGENT_MESSAGE_CHUNK.
    Extended thinking tokens are forwarded as THINKING_CHUNK for the collapsible UI.

    Subsequent chat turns continue in the same session (full context) and may produce
    <audit_report_update> blocks for report versioning (existing pattern, unchanged).
    """
    from claude_agent_sdk import ClaudeAgentOptions
    from claude_agent_sdk.types import HookMatcher, PermissionResultAllow, PermissionResultDeny, ThinkingConfigAdaptive, ThinkingConfigEnabled

    env_var = get_env_var_for_engine_provider(Engine.V3, provider) or "ANTHROPIC_API_KEY"

    session = get_session(session_id)
    if session is None:
        logger.error("run_synthesis: session %s not found; creating fallback", session_id)
        session = create_audit_session(session_id)

    initial_prompt = build_audit_user_prompt(
        crawl_result, business_context, user_preferences,
        report_mode=report_mode, research_context=research_context,
        extra_context=extra_context,
    )
    system_prompt = build_unified_system_prompt(
        report_mode=report_mode, template_id=template_id,
        knowledge_packs=_AUDIT_KNOWLEDGE_PACKS,
    )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _can_use_tool(tool_name: str, input_data: dict, context: Any) -> Any:
        # FetchPages is only useful after the initial report — block it until then
        # to prevent the model from wasting all 60 turns on tool calls before
        # generating the <duct_report> JSON.
        # FetchPages: only after the initial report is generated
        if tool_name == AuditTool.FETCH_PAGES:
            if initial_report is None:
                first_step = (
                    "Finish the report first (StartAuditReport → AddAuditCategory ×9 → FinalizeAuditReport)"
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
        updated = await bridge_ask_user_question(
            session, session_id, input_data, emit, log_prefix="audit"
        )
        return PermissionResultAllow(updated_input=updated)

    async def _pre_tool_hook(input_data: dict, tool_use_id: str, context: Any) -> dict:
        # Forensics: log every tool the agent runs with its full input, paired by
        # tool_use_id to the tool_result in _record_tool_result_hook. Best-effort —
        # persistence must never block or fail a tool call. (Content pattern.)
        _rec = getattr(session, "recorder", None)
        if _rec is not None:
            try:
                await _rec.record_tool_use(
                    name=input_data.get("tool_name", ""),
                    tool_input=input_data.get("tool_input", input_data),
                    tool_use_id=tool_use_id,
                )
            except Exception:
                logger.debug("audit: tool_use persistence failed", exc_info=True)
        return {"continue_": True}

    async def _record_tool_result_hook(input_data: dict, tool_use_id: str, context: Any) -> dict:
        _rec = getattr(session, "recorder", None)
        if _rec is not None:
            try:
                result = (
                    input_data.get("tool_response")
                    or input_data.get("tool_result")
                    or input_data.get("response")
                )
                await _rec.record_tool_result(
                    name=input_data.get("tool_name", ""),
                    result=result,
                    tool_use_id=tool_use_id,
                    is_error=bool(input_data.get("is_error") or input_data.get("isError")),
                )
            except Exception:
                logger.debug("audit: tool_result persistence failed", exc_info=True)
        return {"continue_": True}

    hooks = {
        "PreToolUse": [HookMatcher(matcher=None, hooks=[_pre_tool_hook])],
        "PostToolUse": [HookMatcher(matcher=None, hooks=[_record_tool_result_hook])],
    }

    async def _emit_report_version(report: AuditReport, version_id: int) -> None:
        if not report.update_label:
            report.update_label = "Initial audit" if version_id == 1 else f"Update {version_id}"
        if report_mode == "template":
            # Template mode: report data lives on report.structured_data (NOT on the
            # AuditReport wrapper) — read it from there so the counts are accurate.
            _sd = report.structured_data
            logger.info(
                "synthesis: report v%d finalised — template mode, overall_score=%s, %d categories, %d findings",
                version_id,
                _sd.overall_score if _sd else "?",
                len(_sd.categories) if _sd else 0,
                sum(len(c.findings) for c in _sd.categories) if _sd else 0,
            )
        else:
            logger.info(
                "synthesis: report v%d finalised — %d chars HTML, %d chunks",
                version_id, len(report.html_report), parser.report_chunk_count,
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

    def _compute_crawl_summary() -> CrawlSummary:
        pages = crawl_result.pages
        if not pages:
            # Resume sessions run on a crawl stub — carry the last stored
            # version's crawl summary forward instead of zeroing it out.
            for v in reversed(session.report_versions):
                sd = v.report.structured_data
                if sd is not None and sd.crawl_summary is not None:
                    return sd.crawl_summary
            return CrawlSummary()
        ttfbs = [p.ttfb_ms for p in pages if p.ttfb_ms > 0]
        return CrawlSummary(
            avg_ttfb_ms=sum(ttfbs) / len(ttfbs) if ttfbs else 0.0,
            pages_with_redirects=sum(1 for p in pages if p.redirect_chain),
            spa_pages_count=sum(1 for p in pages if p.is_spa_suspected),
            pages_noindex=sum(1 for p in pages if p.is_noindex),
            pages_missing_title=sum(1 for p in pages if not p.title),
            pages_missing_h1=sum(1 for p in pages if not p.h1s),
        )

    async def _on_submit_report(args: dict) -> dict:
        nonlocal initial_report
        try:
            structured = StructuredAuditData.model_validate(args)
        except Exception as exc:
            return {
                "status": "validation_error",
                "message": f"Report validation failed — fix these issues and resubmit: {exc}",
            }
        # Always compute crawl_summary from raw page signals — deterministic, not LLM-generated.
        structured.crawl_summary = _compute_crawl_summary()
        from datetime import datetime, timezone
        version_id = len(session.report_versions) + 1
        report = AuditReport(
            url=crawl_result.plan.root_url,
            generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            update_label="Initial audit" if version_id == 1 else f"Update {version_id}",
            executive_summary=" · ".join(structured.key_signals) if structured.key_signals else "",
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

    # Subprocess env hygiene (clears IDE session/debugger vars and blank auth
    # keys, isolates a per-session CLAUDE_CONFIG_DIR, wires Sentry + local OTLP
    # tracing) is shared with content — see agents/core/claude_sdk.build_sdk_env.
    # Audit eager-loads tool schemas (enable_tool_search=False): a small fixed
    # tool set loads faster eagerly and guarantees the report tools' schemas are
    # present without a discovery round-trip that could trip auto-deferral.
    _sdk_env, _config_dir = _sdk.build_sdk_env(
        service_name="duct-audit-seo",
        api_key=api_key,
        oauth_token=_cfg.claude_code_oauth_token,
        config_env_var="DUCT_AUDIT_CLAUDE_CONFIG_DIR",
        config_suffix="duct-audit",
        log_prefix="audit",
        session_id=session_id,
        sentry_env=sentry_otel_env(_cfg),
        api_key_env_var=env_var,
        enable_tool_search=False,
    )

    # Ring buffer of recent stderr so connect_with_retry can attach the real
    # crash reason (the SDK drains stderr on a task cancelled during teardown).
    _stderr_buf: deque[str] = deque(maxlen=100)

    def _on_subprocess_stderr(line: str) -> None:
        stripped = line.rstrip()
        _stderr_buf.append(stripped)
        logger.error("audit subprocess stderr [%s]: %s", session_id, stripped)

    # Do NOT override cli_path — let the SDK use its own bundled binary which is
    # version-matched to the SDK. Passing shutil.which("claude") here would use the
    # system-installed CLI which may be a different (incompatible) version.
    _extra_tools = [
        AuditTool.START_AUDIT_REPORT,
        AuditTool.ADD_AUDIT_CATEGORY,
        AuditTool.FINALIZE_AUDIT_REPORT,
        AuditTool.SUBMIT_AUDIT_REPORT,  # chat-revision resubmit path
    ] if report_mode == "template" else []
    _submit_cb = _on_submit_report if report_mode == "template" else None

    async def _on_category_added(count: int, category: dict) -> None:
        # Live progress: surface each category as the model adds it, so the UI shows
        # "N/9 categories" instead of a static spinner during the build. Best-effort —
        # the tool layer never fails on a streaming-emit error.
        await emit({
            "event": AuditEvent.STEP_STARTED,
            "step_id": AuditStep.SYNTHESIZE_AUDIT,
            "label": STEP_LABELS[AuditStep.SYNTHESIZE_AUDIT],
            "status": StepStatus.RUNNING,
            "payload": {
                "categories_done": count,
                "categories_total": 9,
                "last_category": category.get("label") or category.get("id"),
            },
        })

    _category_cb = _on_category_added if report_mode == "template" else None
    # Artifact tools mount only for membership-checked project scope
    # (routes.agents stamps artifact_project_id after verifying membership).
    _artifact_project = getattr(session, "artifact_project_id", None)

    async def _on_artifact_card(card: dict) -> None:
        # In-chat artifact card: rendered by the UI as a compact chip that
        # opens the artifact viewer.
        await emit({"event": AuditEvent.ARTIFACT_UPDATED, "artifact": card})

    _mcp = build_audit_mcp_server(
        crawl_result,
        report_mode=report_mode,
        on_submit_report=_submit_cb,
        on_category_added=_category_cb,
        project_id=_artifact_project,
        artifact_user_id=getattr(session, "user_id", None),
        artifact_conversation_id=getattr(session, "conversation_id", None),
        on_artifact=_on_artifact_card,
    )
    _artifact_tools = (
        [
            AuditTool.LIST_ARTIFACTS,
            AuditTool.GET_ARTIFACT,
            AuditTool.CREATE_ARTIFACT,
            AuditTool.UPDATE_ARTIFACT,
            AuditTool.REWRITE_ARTIFACT,
        ]
        if _artifact_project
        else []
    )

    # Thinking config: template mode applies a rigid 9-category scoring framework, where
    # unbounded adaptive thinking burns minutes for little gain — cap it with a fixed
    # budget. Freehand narrative still benefits from unbounded adaptive thinking.
    if not adaptive_thinking:
        _thinking = None
    elif report_mode == "template":
        _thinking = ThinkingConfigEnabled(type=ThinkingMode.ENABLED, budget_tokens=8000)
    else:
        _thinking = ThinkingConfigAdaptive(type=ThinkingMode.ADAPTIVE)

    options = ClaudeAgentOptions(
        model=model_str,
        permission_mode=AgentPermissionMode.DONT_ASK,
        allowed_tools=[
            AgentTool.ASK_USER_QUESTION,
            AgentTool.TODO_WRITE,
            AgentTool.WEB_SEARCH,
            AgentTool.WEB_FETCH,
            AuditTool.FETCH_PAGES,  # mcp__duct_crawl__FetchPages — in-process MCP
            *_artifact_tools,       # ListArtifacts/GetArtifact — project scope only
            *_extra_tools,
        ],
        # Belt-and-suspenders with ENABLE_TOOL_SEARCH=false (the documented control,
        # set in _sdk_env): with tool search off, all audit tool schemas
        # (Start/Add/Finalize/SubmitAuditReport) load upfront, so the meta ToolSearch
        # tool is unnecessary — disallow it so the model can never waste a turn on it.
        disallowed_tools=["ToolSearch"],
        can_use_tool=_can_use_tool,
        hooks=hooks,
        max_turns=60,
        system_prompt=system_prompt,
        include_partial_messages=True,
        thinking=_thinking,
        effort=effort,
        env=_sdk_env,
        stderr=_on_subprocess_stderr,
        setting_sources=[],
        # sandbox intentionally omitted: the audit agent uses no Bash tools, so
        # macOS seatbelt sandboxing adds no security value but causes the subprocess
        # to exit with code 1 when launched from within a uvicorn server process.
        mcp_servers={"duct_crawl": _mcp},
    )

    # ------------------------------------------------------------------
    # Message generator — initial prompt
    # ------------------------------------------------------------------

    async def _initial_prompt_gen():
        yield {"type": "user", "message": {"role": "user", "content": initial_prompt}}

    # ------------------------------------------------------------------
    # Streaming tag parser state
    # ------------------------------------------------------------------

    # Report JSON tag — HTML is generated on demand, not during initial synthesis.
    had_thinking = False
    # On resume the rehydrated latest version IS the working report — FetchPages
    # unlocks immediately and chat edits version on top of it.
    initial_report: AuditReport | None = (
        session.report_versions[-1].report if resume and session.report_versions else None
    )
    _first_token_at: float | None = None   # perf_counter when first text delta arrived
    # Token accumulators — populated from streaming usage events
    _tok_in = 0
    _tok_out = 0
    _tok_cache_read = 0
    _tok_cache_write = 0

    # <duct_report> streaming is handled by the shared parser (core/stream).
    # Audit streams HTML and builds an AuditReport from the closed payload.
    async def _on_text(text: str) -> None:
        await emit({"event": AuditEvent.AGENT_MESSAGE_CHUNK, "text": text})

    async def _on_report_chunk(text: str) -> None:
        await emit({"event": AuditEvent.REPORT_CHUNK, "text": text})

    async def _on_report_open() -> None:
        elapsed = (perf_counter() - _first_token_at) if _first_token_at else 0.0
        logger.info(
            "synthesis: <duct_report> opened — HTML streaming started (%.1fs after first token)",
            elapsed,
        )

    async def _on_report_close(raw_html: str, turn_text: str) -> None:
        nonlocal initial_report
        from datetime import datetime, timezone
        initial_report = AuditReport(
            url=crawl_result.plan.root_url,
            generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            update_label="Initial audit",
            executive_summary=turn_text,
            html_report=raw_html.strip(),
        )
        await _emit_report_version(initial_report, 1)

    parser = DuctReportStreamParser(
        on_text=_on_text,
        on_report_chunk=_on_report_chunk,
        on_report_close=_on_report_close,
        on_open=_on_report_open,
        log_prefix="synthesis",
    )

    # ------------------------------------------------------------------
    # Shared event processing helper (used for synthesis + each chat turn)
    # ------------------------------------------------------------------

    async def _on_thinking(text: str) -> None:
        nonlocal had_thinking
        had_thinking = True
        await emit({"event": AuditEvent.THINKING_CHUNK, "text": text})

    async def _on_text_delta(text: str) -> None:
        nonlocal _first_token_at
        if _first_token_at is None:
            _first_token_at = perf_counter()
            logger.info("synthesis: first text token received")
        await parser.feed(text)

    def _on_usage(usage: dict, phase: str) -> None:
        nonlocal _tok_in, _tok_out, _tok_cache_read, _tok_cache_write
        if phase == "start":
            _tok_in += usage.get("input_tokens", 0)
            _tok_cache_read += usage.get("cache_read_input_tokens", 0)
            _tok_cache_write += usage.get("cache_creation_input_tokens", 0)
            if _VERBOSE:
                logger.info(
                    "synthesis [turn_start]: input=%d cache_read=%d cache_write=%d",
                    usage.get("input_tokens", 0),
                    usage.get("cache_read_input_tokens", 0),
                    usage.get("cache_creation_input_tokens", 0),
                )
        elif phase == "delta":
            _tok_out += usage.get("output_tokens", 0)

    async def _on_msg_stop() -> None:
        await parser.flush()
        full_text = "".join(parser.turn_text)
        parser.turn_text.clear()

        # Fallback: if report was parsed but REPORT_UPDATED not yet emitted
        if initial_report is not None and len(session.report_versions) == 0:
            await _emit_report_version(initial_report, 1)

        # Freehand: check for <audit_report_update> in accumulated text
        if report_mode == "freehand" and initial_report is not None and session.report_versions:
            updated = _extract_report_update(full_text, base=initial_report)
            if updated:
                v_id = len(session.report_versions) + 1
                await _emit_report_version(updated, v_id)

        await emit({"event": AuditEvent.MESSAGE_STOP})

    async def _on_todo(todos: list) -> None:
        await emit({"event": AuditEvent.TODO_UPDATE, "todos": todos})

    def _on_tool_use(name: str) -> None:
        logger.info("synthesis [tool_use]: %s", name)

    async def _receive_one_turn() -> None:
        # Shared StreamEvent decode lives in agents/core/stream.pump_stream_event;
        # the discrete-turn loop (one full receive_response() per turn) stays here.
        async for msg in client.receive_response():
            await pump_stream_event(
                msg,
                on_text=_on_text_delta,
                on_thinking=_on_thinking,
                on_message_stop=_on_msg_stop,
                on_usage=_on_usage,
                on_todo=_on_todo,
                on_tool_use=_on_tool_use if _VERBOSE else None,
            )

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    client = None
    try:
        # connect-with-retry (shared with content): a transient initialize crash
        # is side-effect-free, so a fresh connect is retried before giving up.
        client = await _sdk.connect_with_retry(
            options,
            stderr_buf=_stderr_buf,
            session_id=session_id,
            agent="audit",
            agent_label="audit engine",
            mode=report_mode,
        )
        if resume and session.report_versions:
            # Resumed session: no synthesis turn. Replay the latest stored
            # version so the UI renders it (replay=True keeps the artifact
            # persister and celebration logic from treating it as new), then
            # fall through to the chat loop below.
            latest = session.report_versions[-1]
            await emit({
                "event": AuditEvent.REPORT_UPDATED,
                "version_id": latest.version_id,
                "label": latest.label,
                "payload": latest.report.model_dump(),
                "replay": True,
            })
            logger.info(
                "audit: resumed session %s with %d stored report version(s)",
                session_id, len(session.report_versions),
            )
        else:
            logger.info("synthesis: subprocess started, sending prompt session=%s", session_id)
            await client.query(_initial_prompt_gen())
            logger.info("synthesis: prompt sent, waiting for first response session=%s", session_id)

            # Turn 1: initial synthesis
            await _receive_one_turn()

        # Recovery: with extended thinking on a large crawl, the model
        # sometimes spends the whole turn reasoning and ends WITHOUT emitting
        # <duct_report> (surfaces as out=0 / "no report generated"). It has
        # the analysis — it just didn't output the report. Nudge it once to
        # produce the report before giving up, which salvages most of these.
        if not session.report_versions:  # type: ignore[attr-defined]
            logger.warning(
                "synthesis: turn 1 produced no <duct_report> (out=%d) for session %s — "
                "sending one recovery nudge", _tok_out, session_id,
            )
            async def _recover_gen():
                yield {
                    "type": "user",
                    "message": (
                        "You analysed the data but did not emit the report. Output the "
                        "complete <duct_report>…</duct_report> now, in full — do not run "
                        "more tools or add further analysis, just produce the report."
                    ),
                }
            await client.query(_recover_gen())
            await _receive_one_turn()

        # Only enter chat mode when synthesis produced a report.
        # If no report, skip PIPELINE_FINISHED — the route handler will emit it after
        # run_pipeline() returns, which will surface the "no report" error to the frontend.
        if session.report_versions:  # type: ignore[attr-defined]
            # Signal the frontend that synthesis is done — phase transitions to READY
            await emit({"event": AuditEvent.PIPELINE_FINISHED, "status": StepStatus.SUCCESS})

            # Phase 3: sequential multi-turn chat loop.
            # ClaudeSDKClient keeps the subprocess alive across multiple
            # query() + receive_response() cycles within the same connected client.
            while True:
                try:
                    chat_msg = await asyncio.wait_for(
                        session.chat_queue.get(),  # type: ignore[attr-defined]
                        timeout=chat_idle_timeout,
                    )
                except asyncio.TimeoutError:
                    logger.info("audit: session %s chat idle timeout", session_id)
                    break
                if chat_msg is None:
                    break

                async def _chat_msg_gen(m=chat_msg):
                    yield {"type": "user", "message": m}

                await client.query(_chat_msg_gen())
                await _receive_one_turn()

    except Exception:
        logger.exception("audit v3: run_synthesis failed for session %s", session_id)
    finally:
        if client is not None:
            with suppress(Exception):
                await client.disconnect()
        # The subprocess is disconnected, so the throwaway per-session config dir
        # is safe to remove.
        _sdk.cleanup_session_config_dir(_config_dir, log_prefix="audit")

    logger.info(
        "synthesis: tokens in=%d out=%d cache_read=%d cache_write=%d session=%s",
        _tok_in, _tok_out, _tok_cache_read, _tok_cache_write, session_id,
    )
    if initial_report is None:
        logger.error(
            "synthesis: NO REPORT for session %s — model ended without <duct_report> "
            "(out=%d tokens, reasoned=%s) even after the recovery nudge; likely "
            "extended-thinking / max_turns exhaustion. Surfaces as a failed audit; "
            "a retry usually succeeds.",
            session_id, _tok_out, had_thinking,
        )
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
        lead_magnet: bool = False,
        extra_context: str = "",
    ) -> AuditReport | None:
        from agents.audit.schema import CrawlDepth
        session = get_session(session_id)
        if session:
            session.report_mode = report_mode
            session.template_id = template_id
        start = perf_counter()
        _t = perf_counter  # alias for inline timings

        await emit({
            "event": AuditEvent.STEP_STARTED,
            "step_id": AuditStep.FETCH_SITEMAP,
            "label": STEP_LABELS[AuditStep.FETCH_SITEMAP],
            "status": StepStatus.RUNNING,
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
            "status": StepStatus.SUCCESS,
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
            "status": StepStatus.RUNNING,
        })
        await emit({
            "event": AuditEvent.STEP_FINISHED,
            "step_id": AuditStep.CRAWL_PAGES,
            "label": f"Crawled {len(crawl_result.pages)} pages",
            "status": StepStatus.SUCCESS,
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

        # Enrichment — competitor research sub-agent (Haiku + WebSearch/WebFetch).
        # Lead-magnet (teaser) audits ALWAYS skip it — it's a ~60s+ sub-agent that
        # usually times out, and the lead flow is meant to be fast. The full audit
        # still runs it, but only when there's business context to research
        # (without competitors/industry/description the sub-agent has nothing to do
        # and would just burn time searching blindly).
        _has_biz_context = bool(
            business_context.competitors
            or business_context.industry
            or business_context.business_description
            or business_context.business_name
        )
        if _has_biz_context and not lead_magnet:
            await emit({
                "event": AuditEvent.STEP_STARTED,
                "step_id": AuditStep.ENRICHING,
                "label": STEP_LABELS[AuditStep.ENRICHING],
                "status": StepStatus.RUNNING,
            })
            t_enrich = _t()
            from agents.audit.enrichment import enrich_context
            research_context = await enrich_context(
                root_url=url,
                business_context=business_context,
                crawl_result=crawl_result,
                api_key=self._api_key,
            )
            logger.info("⏱ enrichment: %.1fs", _t() - t_enrich)
            await emit({
                "event": AuditEvent.STEP_FINISHED,
                "step_id": AuditStep.ENRICHING,
                "label": STEP_LABELS[AuditStep.ENRICHING],
                "status": StepStatus.SUCCESS,
                "payload": {
                    "competitors": [
                        {
                            "domain":          c.domain,
                            "positioning":     c.positioning,
                            "content_pillars": c.content_pillars,
                            "differentiators": c.differentiators,
                        }
                        for c in (research_context.competitors if research_context else [])
                    ],
                    "content_gaps":     research_context.content_gaps if research_context else [],
                    "enrichment_notes": research_context.enrichment_notes if research_context else [],
                },
            })
        else:
            from agents.audit.schema import AuditResearchContext
            from agents.audit.enrichment import _extract_brand_pillars, _extract_brand_schema_types
            logger.info("enrichment: skipping — no business context provided")
            research_context = AuditResearchContext(
                brand_content_pillars=_extract_brand_pillars(crawl_result),
                brand_schema_types=_extract_brand_schema_types(crawl_result),
            )

        await emit({
            "event": AuditEvent.STEP_STARTED,
            "step_id": AuditStep.SYNTHESIZE_AUDIT,
            "label": STEP_LABELS[AuditStep.SYNTHESIZE_AUDIT],
            "status": StepStatus.RUNNING,
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
            research_context=research_context,
            extra_context=extra_context,
        )

        await emit({
            "event": AuditEvent.STEP_FINISHED,
            "step_id": AuditStep.SYNTHESIZE_AUDIT,
            "label": STEP_LABELS[AuditStep.SYNTHESIZE_AUDIT],
            "status": StepStatus.SUCCESS if report else StepStatus.ERROR,
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

    async def run_resume(
        self,
        session_id: str,
        url: str,
        emit: EmitFn,
        chat_idle_timeout: float = 1800.0,
        user_preferences=None,  # UserPreferences | None
        report_mode: str = "freehand",
        template_id: str = "seo_v1",
    ) -> None:
        """Continue a persisted audit conversation — chat only, no re-crawl.

        The caller (routes.agents) rehydrates session.report_versions from the
        artifact store and sets the reprime primer before calling this. The
        crawl stub carries only root_url so FetchPages' same-origin check and
        the working-report context still resolve."""
        from agents.audit.schema import CrawlPlan
        session = get_session(session_id)
        if session:
            session.report_mode = report_mode
            session.template_id = template_id
        stub = CrawlResult(plan=CrawlPlan(root_url=url))
        await run_synthesis(
            session_id=session_id,
            crawl_result=stub,
            business_context=AuditBusinessContext(),
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
            resume=True,
        )
