"""ClaudeContentRunner — Content Studio agent (Claude Agent SDK, v3 engine).

Architecture mirrors agents/audit/v3/runner.py but with two structural deltas:

  1. Sub-agents instead of monolith.
     ClaudeAgentOptions(agents={"research_pillar": ..., "draft_post": ...}) is
     populated from agents/content/subagents/. The orchestrator dispatches via
     the built-in `Agent` tool. Sub-agent execution is observed through the
     can_use_tool callback (STEP_STARTED) and a PostToolUse hook (STEP_FINISHED).

  2. Discriminated <duct_report> payload.
     The streaming tag parser parses JSON inside the tag and branches on the
     "type" field — emits PLAN_GENERATED or POST_DRAFT_UPDATED accordingly.
     If parsing fails (slides_html with unescaped HTML, same problem as audit),
     the fallback path strips slides_html via regex and retries.

The runner does NOT crawl, scrape, or render — it only runs the Claude Agent
SDK session. Brand context comes from the DB via the Project model. Image
generation and PostBridge integration are stubbed in tools.py until Phase 4/4b.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
from collections import deque
from collections.abc import Awaitable, Callable
from contextlib import suppress
from time import perf_counter
from typing import Any
from uuid import UUID

from agents.content.events import ContentEvent, ContentStep, STEP_LABELS, StepStatus
from agents.content.prompts import (
    build_orchestrator_system_prompt,
    build_plan_user_prompt,
    build_post_user_prompt,
)
from agents.content.schema import (
    AppFeature,
    ContentBrandContext,
    ContentPillar,
    ContentSession,
    ContentTool,
    ContentVisualAssets,
    Day,
    PlanDraft,
    PostDraft,
    make_session,
)
from agents.content.subagents import (
    DRAFT_POST_AGENT,
    RESEARCH_PILLAR_AGENT,
)
from agents.content.tools import build_content_mcp_server
from agents.core import claude_sdk as _sdk
from agents.core import session as _core_session
from agents.core.session import bridge_ask_user_question, register_session
from agents.core.stream import DuctReportStreamParser, pump_stream_event
from agents.models import (
    AgentEffort,
    AgentPermissionMode,
    AgentTool,
    ModelName,
    ThinkingMode,
)

logger = logging.getLogger(__name__)

EmitFn = Callable[[dict[str, Any]], Awaitable[None]]

# CLI startup (env hygiene, connect-with-retry), per-message StreamEvent decode,
# and config-dir isolation now live in agents/core (claude_sdk.py, stream.py),
# shared with audit. Only the stderr helper below stays content-local.

# Max wall-clock to wait for the FIRST message from the subprocess. This guards
# the startup window only: a subprocess that connects but never produces anything
# (e.g. an MCP-server init that never readies) would otherwise leave the UI on an
# infinite "Starting…" spinner. It is deliberately NOT applied per-message — once
# output is flowing, mid-turn silences are legitimate (an AskUserQuestion waiting
# on the user, a long research sub-agent, image generation) and bounding them
# would tear down the SDK mid-tool-call → bogus PIPELINE_FAILED + a "hook callback
# hook_0: AbortError" from the subprocess.
_STALL_TIMEOUT_SECS = 120.0

# How long an AskUserQuestion may wait for the user before the bridge gives up and
# lets the model proceed with empty answers. The shared default (120s) is far too
# short for a human reading a multi-part question in an interactive chat: it makes
# the agent abandon the human-in-the-loop and guess, and the abandoned CLI-side
# interaction surfaces as a "hook_0: AbortError". An abandoned *session* is still
# torn down promptly via close_session (which cancels the pipeline task), so a
# generous budget here only ever benefits a user who is actively, slowly answering.
_ASK_USER_TIMEOUT_SECS = 600.0

# One-shot recovery nudge — mirrors the "no <duct_report>" recovery in
# agents/audit/v3/runner.py. With adaptive thinking + sub-agent dispatch the
# model occasionally ends a turn-group having analysed everything but WITHOUT
# persisting the deliverable (it never calls submit_plan / submit_post_draft).
# Left alone the run sits idle until the chat timeout and then reports a hollow
# "finished" with a null id. Nudging once to persist salvages most of these,
# exactly as it does for audit. The nudge rides the same chat_queue the user
# types into, so the main loop's chat turn picks it up as the next turn.
_RECOVERY_NUDGE_PLAN = (
    "You analysed everything but did not persist the plan. Emit the complete "
    '<duct_report>{"type":"plan", …}</duct_report> now and then call submit_plan '
    "with the same payload — do not run more research, just produce and save the plan."
)
_RECOVERY_NUDGE_POST = (
    "You analysed everything but did not persist the post draft. Emit the complete "
    '<duct_report>{"type":"post", …}</duct_report> now and then call '
    "submit_post_draft with the same payload — do not run more research, just "
    "produce and save the draft."
)


def _captured_stderr(buf: deque[str], exc: Exception | None) -> str:
    return _sdk.captured_stderr(buf, exc)


# ---------------------------------------------------------------------------
# Session registry — shared with all agents (agents/core/session.py). These
# wrappers keep the content-specific import surface and ContentSession typing.
# ---------------------------------------------------------------------------

get_session = _core_session.get_session
close_session = _core_session.close_session


def create_plan_session(session_id: str, project_id: UUID) -> ContentSession:
    return register_session(make_session(session_id, project_id, "plan_month"))


def create_draft_session(
    session_id: str,
    project_id: UUID,
    *,
    plan_id: UUID | None = None,
) -> ContentSession:
    session = make_session(session_id, project_id, "draft_post")
    if plan_id is not None:
        session.plan_id = plan_id
    return register_session(session)


# ---------------------------------------------------------------------------
# Brand context loader
# ---------------------------------------------------------------------------


def _load_brand_context(project_id: UUID) -> ContentBrandContext:
    """Build a ContentBrandContext snapshot from the Project row.

    Read at session start so the system prompt embeds the latest brand state.
    The fetch_brand_context tool re-reads on demand for long sessions.
    """
    from sqlmodel import Session

    from db.session import get_engine
    from models.project import Project

    engine = get_engine()
    if engine is None:
        raise RuntimeError("DATABASE_URL is not configured.")
    with Session(engine) as db:
        proj = db.get(Project, project_id)
        if proj is None:
            raise ValueError(f"Project {project_id} not found.")

        brand_blob = proj.content_brand or {}
        pillars_blob = proj.content_pillars or {}
        visual_blob = proj.content_visual_assets or {}

        pillars_list = pillars_blob.get("items") if isinstance(pillars_blob, dict) else pillars_blob
        pillars = [
            ContentPillar.model_validate(p)
            for p in (pillars_list or [])
            if isinstance(p, dict)
        ]
        features = [
            AppFeature.model_validate(f)
            for f in (brand_blob.get("features") or [])
            if isinstance(f, dict)
        ]
        visual = ContentVisualAssets.model_validate(visual_blob) if isinstance(visual_blob, dict) and visual_blob else ContentVisualAssets()

        # Shared business fields come from the project context (single source of
        # truth); content-specific fields stay in content_brand. Fall back to the
        # legacy content_brand values for projects edited before this split.
        channels_blob = proj.brand_channels or {}
        brand_voice = str(channels_blob.get("brand_voice") or brand_blob.get("brand_voice") or "")
        audience = _compose_audience(proj.audience) or str(brand_blob.get("audience") or "")

        return ContentBrandContext(
            project_id=proj.id,
            project_name=proj.name,
            slug=proj.slug or "",
            tagline=proj.tagline or "",
            description=proj.description or "",
            url=proj.url or "",
            audience=audience,
            brand_voice=brand_voice,
            tone=str(brand_blob.get("tone") or ""),
            value_prop=str(brand_blob.get("value_prop") or ""),
            content_goal=str(brand_blob.get("content_goal") or ""),
            do_say=str(brand_blob.get("do_say") or ""),
            do_not_say=str(brand_blob.get("do_not_say") or ""),
            features=features,
            pillars=pillars,
            visual=visual,
        )


def _compose_audience(audience: dict | None) -> str:
    """Render the project's structured audience into a prompt-friendly line.

    Shape: { primary_segment, personas: [{ name, description, priority }] }.
    Returns "" when nothing usable is set so callers can fall back.
    """
    if not isinstance(audience, dict):
        return ""
    parts: list[str] = []
    segment = str(audience.get("primary_segment") or "").strip()
    if segment:
        parts.append(segment)
    personas = audience.get("personas")
    if isinstance(personas, list):
        for p in personas:
            if not isinstance(p, dict):
                continue
            name = str(p.get("name") or "").strip()
            desc = str(p.get("description") or "").strip()
            if name and desc:
                parts.append(f"{name} — {desc}")
            elif name or desc:
                parts.append(name or desc)
    return "; ".join(parts)


# ---------------------------------------------------------------------------
# Helpers (mirrors audit/v3/runner.py)
# ---------------------------------------------------------------------------


def _resolve_anthropic_model(model: ModelName) -> str:
    if model not in (ModelName.CLAUDE_SONNET, ModelName.CLAUDE_HAIKU):
        return ModelName.CLAUDE_SONNET.value
    return model.value


_HTML_FIELD_RE = re.compile(
    r',?\s*"slides_html"\s*:\s*"(?:[^"\\]|\\.)*"',
    re.DOTALL,
)


def _parse_report_json(raw: str) -> dict | None:
    """Parse the JSON inside <duct_report>. Falls back to stripping slides_html
    if the model emitted unescaped HTML quotes (same problem audit has)."""
    candidate = raw.strip()
    fenced = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", candidate)
    if fenced:
        candidate = fenced.group(1).strip()
    try:
        return json.loads(candidate)
    except Exception:
        pass
    stripped = _HTML_FIELD_RE.sub("", candidate)
    try:
        payload = json.loads(stripped)
        payload.setdefault("slides_html", "")
        return payload
    except Exception as exc:
        logger.warning("content: <duct_report> JSON parse failed: %s", exc)
        return None


def _extract_subagent_name(input_data: dict[str, Any]) -> str:
    """Pull the sub-agent name out of an Agent tool invocation.

    The SDK's exact key is not pinned in docs; we look at the likely fields
    in priority order and fall back to 'unknown'.
    """
    for key in ("subagent_type", "agent", "agent_type", "name"):
        v = input_data.get(key)
        if isinstance(v, str) and v:
            return v
    return "unknown"


# ---------------------------------------------------------------------------
# Writer-tool upfront validators
#
# Each returns a PermissionResultDeny (with corrective text the model can act
# on) when the input is wrong, or None to fall through to allow. We mirror
# the audit agent's SubmitAuditReport pattern: rejecting in can_use_tool is
# faster than letting the @tool body produce is_error after the call.
# ---------------------------------------------------------------------------


def _deny(message: str):
    """Build a PermissionResultDeny — lazy import keeps SDK off the top-level."""
    from claude_agent_sdk.types import PermissionResultDeny
    return PermissionResultDeny(message=message)


def _unwrap(input_data: dict[str, Any], *keys: str) -> dict[str, Any]:
    """The model may pass `{"post": {...}}` or `{...}` directly. Accept both."""
    for k in keys:
        v = input_data.get(k)
        if isinstance(v, dict):
            return v
    return input_data


def _validate_submit_plan(input_data: dict[str, Any], session_project_id):
    """Validate the payload the model is about to hand to submit_plan."""
    from pydantic import ValidationError
    from agents.content.schema import PlanDraft

    payload = _unwrap(input_data, "plan")
    try:
        draft = PlanDraft.model_validate(payload)
    except ValidationError as exc:
        return _deny(
            "PlanDraft validation failed — fix these issues in the JSON and "
            f"call submit_plan again:\n{exc}"
        )
    if str(draft.project_id) != str(session_project_id):
        return _deny(
            f"project_id mismatch: this session is scoped to {session_project_id}, "
            f"but the payload had {draft.project_id}. Use the session's project_id "
            "and call submit_plan again."
        )
    return None


def _validate_submit_post_draft(input_data: dict[str, Any], session_project_id):
    """Validate the payload the model is about to hand to submit_post_draft."""
    from pydantic import ValidationError
    from agents.content.schema import PostDraft

    payload = _unwrap(input_data, "post")
    try:
        draft = PostDraft.model_validate(payload)
    except ValidationError as exc:
        return _deny(
            "PostDraft validation failed — fix these issues in the JSON and "
            f"call submit_post_draft again:\n{exc}"
        )
    if str(draft.project_id) != str(session_project_id):
        return _deny(
            f"project_id mismatch: this session is scoped to {session_project_id}, "
            f"but the payload had {draft.project_id}. Use the session's project_id "
            "and call submit_post_draft again."
        )
    return None


def _validate_generate_image(input_data: dict[str, Any]):
    """Validate generate_image arguments before paying for a Gemini call.

    Normalises the @tool's `input_asset_id` (legacy single) + the
    `input_asset_ids` (new multi) input keys into the Pydantic shape's
    single `input_asset_ids` list before validating. Keeps both legacy
    and multi-ref calls passing without paying Gemini for malformed
    inputs.
    """
    from pydantic import ValidationError
    from service.gemini.schema import GenerateImageRequest

    payload = {k: v for k, v in input_data.items() if v not in (None, "")}
    payload.setdefault("number_of_images", min(int(payload.get("number_of_images", 1) or 1), 4))
    # slide_id / item_index route the result onto a slide (or cell); they're
    # not Gemini request fields.
    payload.pop("slide_id", None)
    payload.pop("item_index", None)

    # Coalesce legacy + new reference keys.
    merged_ids: list = []
    if payload.get("input_asset_id"):
        merged_ids.append(payload["input_asset_id"])
    for x in (payload.get("input_asset_ids") or []):
        if x and x not in merged_ids:
            merged_ids.append(x)
    if merged_ids:
        if len(merged_ids) > 3:
            return _deny(
                "Too many reference images for generate_image — max 3. "
                "Pass [character_ref, camera_ref] for slides 2-5; drop "
                "extras and call again."
            )
        payload["input_asset_ids"] = merged_ids
    payload.pop("input_asset_id", None)

    try:
        GenerateImageRequest.model_validate(payload)
    except ValidationError as exc:
        return _deny(
            "generate_image input is invalid — fix and call again:\n"
            f"{exc}"
        )
    return None


def _validate_edit_image(input_data: dict[str, Any]):
    """Validate edit_image arguments before paying for a Gemini call."""
    from pydantic import ValidationError
    from service.gemini.schema import EditImageRequest

    payload = {k: v for k, v in input_data.items() if v not in (None, "")}
    payload.setdefault("number_of_images", min(int(payload.get("number_of_images", 1) or 1), 4))
    try:
        EditImageRequest.model_validate(payload)
    except ValidationError as exc:
        return _deny(
            "edit_image input is invalid — fix and call again:\n"
            f"{exc}"
        )
    return None


# ---------------------------------------------------------------------------
# Core run loop
# ---------------------------------------------------------------------------


async def _run(
    session: ContentSession,
    system_prompt: str,
    initial_prompt: str,
    emit: EmitFn,
    api_key: str,
    *,
    effort: AgentEffort,
    adaptive_thinking: bool = True,
    chat_idle_timeout: float = 1800.0,
    max_turns: int = 120,
    resume: bool = False,
) -> None:
    """Drive a single Claude Agent SDK session for plan_month or draft_post.

    Mirrors agents/audit/v3/runner.py:run_synthesis. The differences are:
      - options.agents populated with research_pillar + draft_post
      - allowed_tools includes Agent + the duct_content MCP tools
      - can_use_tool has a leading Agent branch that emits STEP_STARTED
      - PostToolUse hook matched on 'Agent' emits STEP_FINISHED
      - <duct_report> parser branches on the "type" discriminator
    """
    from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient
    from claude_agent_sdk.types import (
        HookMatcher,
        PermissionResultAllow,
        ThinkingConfigAdaptive,
    )

    session_id = session.session_id
    project_id = session.project_id

    # Recovery-nudge state. The canonical "deliverable persisted" signal is the
    # writer tool having stashed the id on the session (submit_plan → plan_id,
    # submit_post_draft → post_id). The <duct_report> tag only drives the live
    # preview, so a draft streamed but never written still counts as "not
    # produced". Nudge at most once per session (see ResultMessage handling).
    _is_plan = session.mode == "plan_month"

    def _artifact_produced() -> bool:
        return (session.plan_id is not None) if _is_plan else (session.post_id is not None)

    _nudged = False

    # Web research observability: can_use_tool emits STEP_STARTED when the model
    # opens a WebSearch/WebFetch; a PostToolUse hook pops the oldest pending step
    # and marks it finished. FIFO pairing is approximate under parallel searches
    # but accurate enough for the progress display.
    _research_pending: deque[tuple[str, str]] = deque()
    _research_seq = [0]

    # ------------------------------------------------------------------
    # can_use_tool — Agent dispatch observability + AskUserQuestion bridge
    # ------------------------------------------------------------------

    async def _can_use_tool(tool_name: str, input_data: dict, context: Any):
        # Sub-agent dispatch: observe + permit. The Agent tool input shape
        # is provided by the SDK; we accept whatever shape we get.
        if tool_name == AgentTool.AGENT:
            sub_name = _extract_subagent_name(input_data)
            brief = (
                input_data.get("prompt")
                or input_data.get("description")
                or input_data.get("input")
                or ""
            )
            if not isinstance(brief, str):
                brief = json.dumps(brief, default=str)
            await emit({
                "event":    ContentEvent.STEP_STARTED,
                "session_id": session_id,
                "step_id":  f"{ContentStep.DISPATCH_SUBAGENT.value}:{sub_name}",
                "label":    f"Sub-agent · {sub_name}",
                "summary":  brief[:160],
                "status": StepStatus.RUNNING,
            })
            return PermissionResultAllow(updated_input=input_data)

        # ---- Writer-tool upfront validation ------------------------------
        # Validating here (rather than letting the @tool body return
        # is_error=true) gives the model a tight feedback loop: the
        # corrective message arrives BEFORE any DB or API work runs, and
        # the SDK surfaces it as a permission denial which the model
        # treats as authoritative. Pattern borrowed from audit's
        # SubmitAuditReport handler.

        if tool_name == ContentTool.SUBMIT_PLAN:
            deny = _validate_submit_plan(input_data, project_id)
            if deny is not None:
                return deny
            return PermissionResultAllow(updated_input=input_data)

        if tool_name == ContentTool.SUBMIT_POST_DRAFT:
            deny = _validate_submit_post_draft(input_data, project_id)
            if deny is not None:
                return deny
            return PermissionResultAllow(updated_input=input_data)

        if tool_name == ContentTool.GENERATE_IMAGE:
            deny = _validate_generate_image(input_data)
            if deny is not None:
                return deny
            return PermissionResultAllow(updated_input=input_data)

        if tool_name == ContentTool.EDIT_IMAGE:
            deny = _validate_edit_image(input_data)
            if deny is not None:
                return deny
            return PermissionResultAllow(updated_input=input_data)

        # Web research: surface each search/fetch as a visible workflow step.
        if tool_name in (AgentTool.WEB_SEARCH, AgentTool.WEB_FETCH):
            _research_seq[0] += 1
            sid = f"research:{_research_seq[0]}"
            query = (
                input_data.get("query")
                or input_data.get("url")
                or input_data.get("prompt")
                or ""
            )
            if not isinstance(query, str):
                query = json.dumps(query, default=str)
            label = "Web search" if tool_name == AgentTool.WEB_SEARCH else "Reading page"
            _research_pending.append((sid, label))
            await emit({
                "event":      ContentEvent.STEP_STARTED,
                "session_id": session_id,
                "step_id":    sid,
                "label":      label,
                "summary":    query[:140],
                "status": StepStatus.RUNNING,
            })
            return PermissionResultAllow(updated_input=input_data)

        # AskUserQuestion: bridge to the SSE consumer via asyncio.Future. Give the
        # user a realistic budget to answer (see _ASK_USER_TIMEOUT_SECS) — the
        # shared 120s default is too tight for an interactive chat and makes the
        # model proceed with empty answers.
        if tool_name == AgentTool.ASK_USER_QUESTION:
            updated = await bridge_ask_user_question(
                session, session_id, input_data, emit,
                timeout=_ASK_USER_TIMEOUT_SECS, log_prefix="content",
            )
            return PermissionResultAllow(updated_input=updated)

        # Everything else is allowed by allowed_tools; pass through.
        return PermissionResultAllow(updated_input=input_data)

    async def _pre_tool_hook(input_data: dict, tool_use_id: str, context: Any) -> dict:
        # Forensics: log every tool the agent runs with its full input, paired by
        # tool_use_id to the tool_result recorded in _record_tool_result_hook.
        # Best-effort — persistence must never block or fail a tool call.
        _rec = getattr(session, "recorder", None)
        if _rec is not None:
            try:
                await _rec.record_tool_use(
                    name=input_data.get("tool_name", ""),
                    tool_input=input_data.get("tool_input", input_data),
                    tool_use_id=tool_use_id,
                )
            except Exception:
                logger.debug("content: tool_use persistence failed", exc_info=True)
        return {"continue_": True}

    async def _record_tool_result_hook(input_data: dict, tool_use_id: str, context: Any) -> dict:
        # Global PostToolUse companion to _pre_tool_hook: log every tool's output.
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
                logger.debug("content: tool_result persistence failed", exc_info=True)
        return {"continue_": True}

    async def _post_agent_hook(input_data: dict, tool_use_id: str, context: Any) -> dict:
        # The SDK passes the tool result + the model's invocation. Key names
        # vary across SDK versions; we look at a few likely candidates.
        sub_name = _extract_subagent_name(input_data.get("tool_input") or input_data)
        result = (
            input_data.get("tool_response")
            or input_data.get("tool_result")
            or input_data.get("response")
            or ""
        )
        if not isinstance(result, str):
            result = json.dumps(result, default=str)
        await emit({
            "event":      ContentEvent.STEP_FINISHED,
            "session_id": session_id,
            "step_id":    f"{ContentStep.DISPATCH_SUBAGENT.value}:{sub_name}",
            "label":      f"Sub-agent · {sub_name}",
            "summary":    result[:240],
            "status": StepStatus.SUCCESS,
        })
        return {"continue_": True}

    async def _post_web_hook(input_data: dict, tool_use_id: str, context: Any) -> dict:
        # Close out the oldest open research step (FIFO). Web searches are quick,
        # so even under parallelism the display stays close to reality.
        if _research_pending:
            sid, label = _research_pending.popleft()
            await emit({
                "event":      ContentEvent.STEP_FINISHED,
                "session_id": session_id,
                "step_id":    sid,
                "label":      label,
                "status": StepStatus.SUCCESS,
            })
        return {"continue_": True}

    # ------------------------------------------------------------------
    # SDK env + MCP server
    # ------------------------------------------------------------------

    from config import get_configs, sentry_otel_env
    _cfg = get_configs()

    # Subprocess env hygiene (clears IDE session/debugger vars and blank auth
    # keys, isolates a per-session CLAUDE_CONFIG_DIR, wires tracing) is shared
    # with audit — see agents/core/claude_sdk.build_sdk_env.
    _sdk_env, _config_dir = _sdk.build_sdk_env(
        service_name="duct-content",
        api_key=api_key,
        oauth_token=_cfg.claude_code_oauth_token,
        config_env_var="DUCT_CONTENT_CLAUDE_CONFIG_DIR",
        config_suffix="duct-content",
        log_prefix="content",
        session_id=session_id,
        sentry_env=sentry_otel_env(_cfg),
        # Fixed, small tool set → load schemas eagerly instead of via ToolSearch.
        # Mirrors audit; also stops the model narrating "let me load the tools".
        enable_tool_search=False,
    )

    # Bounded ring buffer of recent stderr lines. The SDK reads stderr on a
    # detached task that gets cancelled during teardown, so on a fast startup
    # crash the per-line logs below can be lost before they flush — keeping our
    # own copy lets _connect_with_retry attach the real reason to the error.
    _stderr_buf: deque[str] = deque(maxlen=100)

    def _on_subprocess_stderr(line: str) -> None:
        stripped = line.rstrip()
        _stderr_buf.append(stripped)
        logger.error("content subprocess stderr [%s]: %s", session_id, stripped)

    _cli_path = shutil.which("claude") or None
    _mcp = build_content_mcp_server(project_id, emit, session)

    # ------------------------------------------------------------------
    # ClaudeAgentOptions
    # ------------------------------------------------------------------

    options = ClaudeAgentOptions(
        model=_resolve_anthropic_model(ModelName.CLAUDE_SONNET),
        permission_mode=AgentPermissionMode.DONT_ASK,
        allowed_tools=[
            AgentTool.ASK_USER_QUESTION,
            AgentTool.TODO_WRITE,
            AgentTool.WEB_SEARCH,
            AgentTool.WEB_FETCH,
            AgentTool.AGENT,
            ContentTool.SUBMIT_PLAN,
            ContentTool.SUBMIT_POST_DRAFT,
            ContentTool.EDIT_SLIDE,
            ContentTool.FETCH_BRAND_CONTEXT,
            ContentTool.FETCH_TOPIC_BANK,
            ContentTool.FETCH_FORMAT_LIBRARY,
            ContentTool.FETCH_AVATAR_LIBRARY,
            ContentTool.FETCH_CONTENT_HISTORY,
            ContentTool.FETCH_CONTENT_ASSETS,
            ContentTool.FETCH_DISCOVERED_REFERENCES,
            ContentTool.FETCH_POST,
            ContentTool.RENDER_SLIDE,
            ContentTool.GENERATE_IMAGE,
            ContentTool.EDIT_IMAGE,
            ContentTool.PUBLISH_POST,
            ContentTool.MARK_POSTED,
            ContentTool.LOG_METRICS,
        ],
        agents={
            "research_pillar":    RESEARCH_PILLAR_AGENT,
            "draft_post":         DRAFT_POST_AGENT,
        },
        can_use_tool=_can_use_tool,
        hooks={
            "PreToolUse":  [HookMatcher(matcher=None,    hooks=[_pre_tool_hook])],
            "PostToolUse": [
                HookMatcher(matcher=None,                  hooks=[_record_tool_result_hook]),
                HookMatcher(matcher=AgentTool.AGENT,       hooks=[_post_agent_hook]),
                HookMatcher(matcher=AgentTool.WEB_SEARCH,  hooks=[_post_web_hook]),
                HookMatcher(matcher=AgentTool.WEB_FETCH,   hooks=[_post_web_hook]),
            ],
        },
        max_turns=max_turns,
        system_prompt=system_prompt,
        include_partial_messages=True,
        thinking=ThinkingConfigAdaptive(type=ThinkingMode.ADAPTIVE) if adaptive_thinking else None,
        effort=effort,
        env=_sdk_env,
        stderr=_on_subprocess_stderr,
        setting_sources=[],
        cli_path=_cli_path,
        mcp_servers={"duct_content": _mcp},
    )

    # ------------------------------------------------------------------
    # Message generator — initial prompt then chat queue
    # ------------------------------------------------------------------

    async def _initial_prompt_gen():
        # Yield the initial prompt ONCE and return so the generator COMPLETES.
        # The SDK only flushes a streaming-input turn to the model when its input
        # generator ends; the old single message_gen yielded the prompt then
        # blocked forever on chat_queue, so the stream never closed, the first
        # turn was never sent, and the model never replied — the run hung forever
        # at "Loading project". Follow-up turns are now discrete query() calls in
        # the main loop (mirrors the audit runner).
        yield {"type": "user", "message": {"role": "user", "content": initial_prompt}}

    # ------------------------------------------------------------------
    # Streaming <duct_report> tag parser
    # ------------------------------------------------------------------

    _first_token_at: float | None = None

    # <duct_report> streaming is handled by the shared parser (core/stream).
    # Content streams JSON and branches on the payload's "type" in _handle_close.
    async def _on_text(text: str) -> None:
        await emit({"event": ContentEvent.AGENT_MESSAGE_CHUNK, "text": text})

    async def _on_report_chunk(text: str) -> None:
        await emit({"event": ContentEvent.REPORT_CHUNK, "text": text})

    async def _on_report_open() -> None:
        elapsed = (perf_counter() - _first_token_at) if _first_token_at else 0.0
        logger.info(
            "content: <duct_report> opened — JSON streaming started (%.1fs after first token)",
            elapsed,
        )

    async def _handle_close(raw_json: str) -> None:
        """Parse the JSON inside the closed <duct_report> tag, emit the
        matching event, and validate against PlanDraft / PostDraft.

        Validation failures are logged but do NOT raise — the writer @tool
        will revalidate and surface a clear error to the model on the next
        turn, which is the right place for retry logic to live.
        """
        payload = _parse_report_json(raw_json)
        if payload is None:
            logger.warning("content: <duct_report> JSON parse failed; nothing emitted")
            return
        kind = payload.get("type", "")
        if kind == "plan":
            try:
                PlanDraft.model_validate(payload)
            except Exception as exc:
                logger.warning("content: PlanDraft validation failed (will let writer re-validate): %s", exc)
            await emit({
                "event":       ContentEvent.PLAN_GENERATED,
                "session_id":  session_id,
                "payload":     payload,
                "source":      "duct_report",
            })
        elif kind == "post":
            try:
                PostDraft.model_validate(payload)
            except Exception as exc:
                logger.warning("content: PostDraft validation failed (will let writer re-validate): %s", exc)
            await emit({
                "event":       ContentEvent.POST_DRAFT_UPDATED,
                "session_id":  session_id,
                "payload":     payload,
                "source":      "duct_report",
            })
        else:
            logger.warning(
                "content: <duct_report> missing 'type' discriminator (got %r); "
                "no event emitted", kind,
            )

    async def _on_report_close(raw_json: str, _turn_text: str) -> None:
        await _handle_close(raw_json)

    parser = DuctReportStreamParser(
        on_text=_on_text,
        on_report_chunk=_on_report_chunk,
        on_report_close=_on_report_close,
        on_open=_on_report_open,
        log_prefix="content",
    )

    # ------------------------------------------------------------------
    # Per-message pump callbacks. The shared StreamEvent decode lives in
    # agents/core/stream.pump_stream_event; the outer loop (with the streaming
    # startup watchdog) stays below, agent-specific.
    # ------------------------------------------------------------------

    async def _on_thinking(text: str) -> None:
        await emit({"event": ContentEvent.THINKING_CHUNK, "text": text})

    async def _on_text_delta(text: str) -> None:
        nonlocal _first_token_at
        if _first_token_at is None:
            _first_token_at = perf_counter()
            logger.info("content: first text token received")
        await parser.feed(text)

    async def _on_msg_stop() -> None:
        await parser.flush()
        parser.turn_text.clear()
        await emit({"event": ContentEvent.MESSAGE_STOP})

    async def _on_result(result_msg: Any) -> None:
        # End of a turn-group: the model has stopped and is now idle awaiting the
        # next user message. If it finished without persisting the deliverable,
        # nudge it once (audit's recovery pattern) before it sits idle until the
        # chat timeout and the run reports a hollow "finished". The main loop's
        # chat turn pops this off the chat queue and sends it as the next turn.
        nonlocal _nudged
        if not _artifact_produced() and not _nudged:
            _nudged = True
            logger.warning(
                "content: turn ended with no %s persisted for session %s "
                "(stop_reason=%s) — sending one recovery nudge",
                "plan" if _is_plan else "post", session_id, result_msg.stop_reason,
            )
            await session.chat_queue.put({
                "role": "user",
                "content": _RECOVERY_NUDGE_PLAN if _is_plan else _RECOVERY_NUDGE_POST,
            })

    async def _on_todo(todos: list) -> None:
        session.todos = todos
        await emit({"event": ContentEvent.TODO_UPDATE, "todos": todos})

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    client: ClaudeSDKClient | None = None
    try:
        client = await _sdk.connect_with_retry(
            options,
            stderr_buf=_stderr_buf,
            session_id=session_id,
            agent="content",
            agent_label="content engine",
            mode=session.mode,
        )
        async def _receive_one_turn(*, bound_first_output: bool = False) -> None:
            # Consume one full receive_response() turn. On the first turn we bound
            # time-to-first-*model*-output: not the first message (that's the init
            # SystemMessage, which arrives in ~0.1s and would disarm the guard
            # before the model ever speaks), but the first NON-system message. If
            # the subprocess connects yet never produces a turn, this raises
            # (→ PIPELINE_FAILED) instead of hanging forever. Once the model is
            # talking, subsequent waits are unbounded: mid-turn silences
            # (AskUserQuestion, a long research sub-agent, image gen) are
            # legitimate and tearing the SDK down during one surfaces a bogus
            # stall error plus a "hook_0: AbortError".
            responses = client.receive_response()
            armed = bound_first_output
            while True:
                try:
                    if armed:
                        msg = await asyncio.wait_for(
                            responses.__anext__(), timeout=_STALL_TIMEOUT_SECS
                        )
                    else:
                        msg = await responses.__anext__()
                except StopAsyncIteration:
                    break
                except asyncio.TimeoutError as exc:
                    captured = _captured_stderr(_stderr_buf, None)
                    raise RuntimeError(
                        f"Content agent produced no output for {_STALL_TIMEOUT_SECS:.0f}s — "
                        "the run stalled before completing (the subprocess connected "
                        "but emitted nothing)."
                        + (f"\n  subprocess stderr:\n{captured}" if captured else
                           " No subprocess stderr was captured.")
                    ) from exc
                if armed and type(msg).__name__ != "SystemMessage":
                    armed = False  # model is responding — disarm the startup guard
                await pump_stream_event(
                    msg,
                    on_text=_on_text_delta,
                    on_thinking=_on_thinking,
                    on_message_stop=_on_msg_stop,
                    on_result=_on_result,
                    on_todo=_on_todo,
                )

        # Turn 1: the initial synthesis prompt, sent as a COMPLETING generator so
        # the SDK actually flushes it to the model (see _initial_prompt_gen).
        # SKIPPED on resume — resuming must NOT make the agent speak; it just
        # waits for the user's first message (which carries the restored context).
        if not resume:
            await client.query(_initial_prompt_gen())
            await _receive_one_turn(bound_first_output=True)

        # Follow-up turns: recovery nudges (queued by _on_result when a turn ends
        # with no artifact persisted) and user chat / AskUserQuestion answers,
        # each sent as its own discrete query() — mirrors the audit runner's
        # multi-turn loop. The connected client keeps the subprocess alive across
        # query() + receive_response() cycles.
        while True:
            try:
                chat_msg = await asyncio.wait_for(
                    session.chat_queue.get(), timeout=chat_idle_timeout
                )
            except asyncio.TimeoutError:
                logger.info("content: session %s chat idle timeout", session_id)
                break
            if chat_msg is None:
                break

            async def _chat_gen(m=chat_msg):
                yield {"type": "user", "message": m}

            await client.query(_chat_gen())
            await _receive_one_turn()
    except Exception:
        logger.exception("content v3: run failed for session %s", session_id)
        raise
    finally:
        if client is not None:
            with suppress(Exception):
                await client.disconnect()
        # The subprocess is gone; remove this run's throwaway per-session config dir.
        _sdk.cleanup_session_config_dir(_config_dir, log_prefix="content")


# ---------------------------------------------------------------------------
# Public runner
# ---------------------------------------------------------------------------


class ClaudeContentRunner:
    """High-level entrypoint used by routes/content.py.

    Effort + adaptive_thinking are per-call so the route layer (and a
    future UI) can dial them per request. Defaults are tuned for cost:
    MEDIUM with adaptive thinking lets the model spend more on hard
    turns (plan synthesis) without paying HIGH on every routine turn.
    """

    # Defaults — overridable per-call from routes/content.py and the UI.
    DEFAULT_PLAN_EFFORT  = AgentEffort.MEDIUM
    DEFAULT_DRAFT_EFFORT = AgentEffort.MEDIUM
    DEFAULT_PLAN_MAX_TURNS  = 120
    DEFAULT_DRAFT_MAX_TURNS = 60

    def __init__(self, api_key: str) -> None:
        # An empty api_key is allowed when a Claude OAuth path is available: a
        # CLAUDE_CODE_OAUTH_TOKEN (self-hosted) or a local `claude` login. The
        # SDK env injection in run_plan/run_draft only sets ANTHROPIC_API_KEY
        # when non-empty, so an empty key cleanly defers to OAuth.
        from config import claude_oauth_available

        if not api_key and not claude_oauth_available():
            raise ValueError("ANTHROPIC_API_KEY is required for ClaudeContentRunner.")
        self._api_key = api_key

    async def run_plan(
        self,
        session_id: str,
        project_id: UUID,
        emit: EmitFn,
        *,
        effort: AgentEffort | None = None,
        adaptive_thinking: bool = True,
        max_turns: int | None = None,
        chat_idle_timeout: float = 1800.0,
    ) -> None:
        """Run a plan_month session end-to-end.

        Args:
          effort: per-call effort override; defaults to DEFAULT_PLAN_EFFORT.
          adaptive_thinking: when True the model decides per-turn depth.
          max_turns: SDK turn ceiling; defaults to DEFAULT_PLAN_MAX_TURNS.
        """
        session = get_session(session_id) or create_plan_session(session_id, project_id)

        # ── Resume: restore + ready, NEVER a greeting turn (see run_draft). ──
        # Skip enrichment + the pipeline entirely; just load brand for the system
        # prompt, stash the restored context for the user's first message, and go
        # READY immediately so the input unlocks with no "working" state.
        if getattr(session, "resume", False) and getattr(session, "conversation_id", None):
            brand = await asyncio.to_thread(_load_brand_context, project_id)
            system_prompt = build_orchestrator_system_prompt(brand, "plan_month")
            from agents.content.persistence import build_reprime_context
            session.resume_primer = await build_reprime_context(session, self._api_key)
            session.needs_reprime = True
            await emit({
                "event":      ContentEvent.PIPELINE_FINISHED,
                "session_id": session_id,
                "mode":       "plan_month",
                "plan_id":    str(session.plan_id) if session.plan_id else None,
                "resumed":    True,
            })
            try:
                await _run(
                    session, system_prompt, "", emit, self._api_key,
                    effort=effort or self.DEFAULT_PLAN_EFFORT,
                    adaptive_thinking=adaptive_thinking,
                    chat_idle_timeout=chat_idle_timeout,
                    max_turns=max_turns or self.DEFAULT_PLAN_MAX_TURNS,
                    resume=True,
                )
            except Exception as exc:
                await emit({"event": ContentEvent.PIPELINE_FAILED, "session_id": session_id, "error": str(exc)})
                raise
            return

        # Emit the first events BEFORE loading brand context so the UI leaves its
        # "Starting session…" state immediately. _load_brand_context is a SYNC DB
        # read that opens a fresh connection through the Railway proxy — running it
        # directly here would block the event loop (and therefore the SSE stream,
        # so the just-queued events couldn't even be delivered) until it returns.
        # Two concurrent sessions (e.g. a dev StrictMode double-mount) would block
        # the loop in series and the UI would hang at "Starting session…". Run it
        # off the loop via asyncio.to_thread so the stream stays live.
        await emit({
            "event":    ContentEvent.PIPELINE_STARTED,
            "session_id": session_id,
            "mode":     "plan_month",
        })
        await emit({
            "event":   ContentEvent.STEP_STARTED,
            "step_id": ContentStep.LOAD_PROJECT,
            "label":   STEP_LABELS[ContentStep.LOAD_PROJECT],
            "status": StepStatus.RUNNING,
        })
        brand = await asyncio.to_thread(_load_brand_context, project_id)
        await emit({
            "event":   ContentEvent.STEP_FINISHED,
            "step_id": ContentStep.LOAD_PROJECT,
            "label":   STEP_LABELS[ContentStep.LOAD_PROJECT],
            "status": StepStatus.SUCCESS,
            "payload": {"project_name": brand.project_name, "pillars": len(brand.pillars)},
        })

        # ── Enrichment: local scan + optional Haiku trend research ─────────
        await emit({
            "event":   ContentEvent.STEP_STARTED,
            "step_id": ContentStep.ENRICHING,
            "label":   STEP_LABELS[ContentStep.ENRICHING],
            "status": StepStatus.RUNNING,
        })
        from agents.content.enrichment import enrich_content_context
        research = await enrich_content_context(brand, self._api_key)
        await emit({
            "event":   ContentEvent.STEP_FINISHED,
            "step_id": ContentStep.ENRICHING,
            "label":   STEP_LABELS[ContentStep.ENRICHING],
            "status": StepStatus.SUCCESS,
            "payload": {
                "pillar_history":   len(research.pillar_history),
                "trending_sounds":  len(research.trending_sounds),
                "trending_hashtags": len(research.trending_hashtags),
                "trending_hooks":   len(research.trending_hooks),
                "trending_styles":  len(research.trending_styles),
            },
        })

        system_prompt = build_orchestrator_system_prompt(brand, "plan_month")
        initial_prompt = build_plan_user_prompt(
            brand, history=[], formats=[], avatars=[], research=research,
        )

        try:
            await _run(
                session,
                system_prompt,
                initial_prompt,
                emit,
                self._api_key,
                effort=effort or self.DEFAULT_PLAN_EFFORT,
                adaptive_thinking=adaptive_thinking,
                chat_idle_timeout=chat_idle_timeout,
                max_turns=max_turns or self.DEFAULT_PLAN_MAX_TURNS,
            )
            if session.plan_id is not None:
                await emit({
                    "event":      ContentEvent.PIPELINE_FINISHED,
                    "session_id": session_id,
                    "mode":       "plan_month",
                    "plan_id":    str(session.plan_id),
                })
            else:
                # The session ended without ever persisting a plan — even the
                # recovery nudge didn't recover it. Surface a real failure
                # instead of a hollow "finished" with plan_id: null (which the
                # UI would render as success with nothing to open).
                logger.error("content: plan session %s ended with no plan persisted", session_id)
                await emit({
                    "event":      ContentEvent.PIPELINE_FAILED,
                    "session_id": session_id,
                    "error":      "The content engine finished without producing a plan. "
                                  "This is usually transient — please try again.",
                })
        except Exception as exc:
            await emit({
                "event":      ContentEvent.PIPELINE_FAILED,
                "session_id": session_id,
                "error":      str(exc),
            })
            raise

    async def run_draft(
        self,
        session_id: str,
        project_id: UUID,
        emit: EmitFn,
        *,
        day: Day | None = None,
        topic: str | None = None,
        pillar: str | None = None,
        format_slug: str = "",
        channel: str | None = None,
        effort: AgentEffort | None = None,
        adaptive_thinking: bool = True,
        max_turns: int | None = None,
        chat_idle_timeout: float = 1800.0,
    ) -> None:
        """Run a draft_post session end-to-end."""
        from agents.content.channels import resolve as resolve_channel
        session = get_session(session_id) or create_draft_session(session_id, project_id)
        ch = resolve_channel(channel)  # sync, no DB — safe before the first emit

        is_resume = bool(getattr(session, "resume", False) and getattr(session, "conversation_id", None))

        # ── Resume: restore + ready, NEVER a greeting turn ──────────────────
        # Reload/refresh/reconnect must just bring the session back to life — the
        # agent stays silent until the user sends their next message. We load the
        # brand silently (needed for the system prompt), stash the restored
        # context for that first message, and signal READY immediately so the
        # input unlocks. No PIPELINE_STARTED/steps → no "working" state, no greeting.
        if is_resume:
            brand = await asyncio.to_thread(_load_brand_context, project_id)
            system_prompt = build_orchestrator_system_prompt(brand, "draft_post", channel=ch)
            from agents.content.persistence import build_reprime_context
            session.resume_primer = await build_reprime_context(session, self._api_key)
            session.needs_reprime = True
            await emit({
                "event":      ContentEvent.PIPELINE_FINISHED,
                "session_id": session_id,
                "mode":       "draft_post",
                "post_id":    str(session.post_id) if session.post_id else None,
                "resumed":    True,
            })
            try:
                await _run(
                    session, system_prompt, "", emit, self._api_key,
                    effort=effort or self.DEFAULT_DRAFT_EFFORT,
                    adaptive_thinking=adaptive_thinking,
                    chat_idle_timeout=chat_idle_timeout,
                    max_turns=max_turns or self.DEFAULT_DRAFT_MAX_TURNS,
                    resume=True,
                )
            except Exception as exc:
                await emit({"event": ContentEvent.PIPELINE_FAILED, "session_id": session_id, "error": str(exc)})
                raise
            return

        # ── Fresh draft: run the generation pipeline ────────────────────────
        # Emit lifecycle + the first step BEFORE the (blocking) brand-context load
        # so the UI leaves "Starting session…" immediately; load off the event
        # loop so it can't block the loop / SSE stream. (See run_plan for why.)
        await emit({
            "event":             ContentEvent.PIPELINE_STARTED,
            "session_id":        session_id,
            "mode":              "draft_post",
            "channel":           ch.id,
            "channel_label":     ch.label,
            "channel_supported": ch.supported,
        })
        await emit({
            "event":   ContentEvent.STEP_STARTED,
            "step_id": ContentStep.LOAD_PROJECT,
            "label":   STEP_LABELS[ContentStep.LOAD_PROJECT],
            "status": StepStatus.RUNNING,
        })
        brand = await asyncio.to_thread(_load_brand_context, project_id)
        await emit({
            "event":   ContentEvent.STEP_FINISHED,
            "step_id": ContentStep.LOAD_PROJECT,
            "label":   STEP_LABELS[ContentStep.LOAD_PROJECT],
            "status": StepStatus.SUCCESS,
            "payload": {"project_name": brand.project_name, "pillars": len(brand.pillars)},
        })

        system_prompt = build_orchestrator_system_prompt(brand, "draft_post", channel=ch)
        initial_prompt = build_post_user_prompt(
            brand,
            day,
            topic=topic,
            pillar=pillar,
            format_slug=format_slug,
            avatar=None,
            recent_posts=[],
            channel=ch,
        )

        try:
            await _run(
                session,
                system_prompt,
                initial_prompt,
                emit,
                self._api_key,
                effort=effort or self.DEFAULT_DRAFT_EFFORT,
                adaptive_thinking=adaptive_thinking,
                chat_idle_timeout=chat_idle_timeout,
                max_turns=max_turns or self.DEFAULT_DRAFT_MAX_TURNS,
            )
            if session.post_id is not None:
                await emit({
                    "event":      ContentEvent.PIPELINE_FINISHED,
                    "session_id": session_id,
                    "mode":       "draft_post",
                    "post_id":    str(session.post_id),
                })
            else:
                # Ended without persisting a post draft — even the recovery nudge
                # didn't recover it. Surface a real failure rather than a hollow
                # "finished" with post_id: null.
                logger.error("content: draft session %s ended with no post persisted", session_id)
                await emit({
                    "event":      ContentEvent.PIPELINE_FAILED,
                    "session_id": session_id,
                    "error":      "The content engine finished without producing a post draft. "
                                  "This is usually transient — please try again.",
                })
        except Exception as exc:
            await emit({
                "event":      ContentEvent.PIPELINE_FAILED,
                "session_id": session_id,
                "error":      str(exc),
            })
            raise


__all__ = [
    "ClaudeContentRunner",
    "close_session",
    "create_draft_session",
    "create_plan_session",
    "get_session",
]
