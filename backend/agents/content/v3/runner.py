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
from collections import deque
from collections.abc import Awaitable, Callable
from contextlib import suppress
from time import perf_counter
from typing import Any
from uuid import UUID

from agents.content.events import ContentEvent, ContentStep, STEP_LABELS, StepStatus
from agents.content.prompts import (
    build_clone_user_prompt,
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
    PostType,
    make_session,
)
from agents.content.subagents import (
    DRAFT_POST_AGENT,
    RESEARCH_PILLAR_AGENT,
    REVIEW_POST_AGENT,
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


def create_clone_session(
    session_id: str,
    project_id: UUID,
    *,
    plan_id: UUID | None = None,
    post_id: UUID | None = None,
) -> ContentSession:
    """Session for clone_post — drafts a post by modeling a proven reference.
    The pending post (carrying clone_source) is created up front by the Add-post
    flow; post_id points the runner at it so the clone UPDATES that row."""
    session = make_session(session_id, project_id, "clone_post")
    if plan_id is not None:
        session.plan_id = plan_id
    if post_id is not None:
        session.post_id = post_id
    return register_session(session)


# ---------------------------------------------------------------------------
# Brand context loader
# ---------------------------------------------------------------------------


def _resolve_session_post_type(session: ContentSession, day: Day | None = None) -> PostType:
    """Resolve the content type for this draft session: the plan day's type if
    given, else the bound post's type, else SLIDESHOW. Sync — call via
    asyncio.to_thread. Drives whether _run wires the Higgsfield video MCP."""
    raw: str | None = None
    if day is not None and getattr(day, "post_type", ""):
        raw = day.post_type
    elif session.post_id is not None:
        from sqlmodel import Session

        from db.session import get_engine
        from models.content import ContentPost

        engine = get_engine()
        if engine is not None:
            with Session(engine) as db:
                row = db.get(ContentPost, session.post_id)
                if row is not None and row.post_type:
                    raw = row.post_type
    try:
        return PostType(raw) if raw else PostType.SLIDESHOW
    except ValueError:
        return PostType.SLIDESHOW


def _resolve_higgsfield_token(project_id: UUID) -> str:
    """Resolve the Higgsfield bearer token for the project's owner (or env
    fallback). Sync — call via asyncio.to_thread. "" means "not connected", and
    the runner then skips wiring the video MCP (the run fails soft)."""
    from sqlmodel import Session

    from db.session import get_engine
    from models.project import Project
    from service.higgsfield.auth import higgsfield_token_for_user

    engine = get_engine()
    if engine is None:
        return ""
    with Session(engine) as db:
        proj = db.get(Project, project_id)
        user_id = proj.user_id if proj is not None else None
        return higgsfield_token_for_user(user_id, db)


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
            competition=_compose_blob(proj.competition),
            competitor_handles=[
                str(h) for h in (brand_blob.get("tiktok_competitors") or []) if h
            ],
            targets=_compose_blob(proj.targets),
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


def _compose_blob(blob: dict | None) -> str:
    """Render a small JSONB context dict (project.competition / .targets) into a
    compact prompt line. Returns "" when nothing usable is set."""
    if not isinstance(blob, dict) or not blob:
        return ""
    parts: list[str] = []
    for key, value in blob.items():
        if value in (None, "", [], {}):
            continue
        if isinstance(value, (list, tuple)):
            rendered = ", ".join(str(v) for v in value if v not in (None, ""))
        elif isinstance(value, dict):
            rendered = "; ".join(f"{k}: {v}" for k, v in value.items() if v not in (None, ""))
        else:
            rendered = str(value)
        if rendered:
            parts.append(f"{str(key).replace('_', ' ')}: {rendered}")
    return " | ".join(parts)


# ---------------------------------------------------------------------------
# Helpers (mirrors audit/v3/runner.py)
# ---------------------------------------------------------------------------


def _resolve_anthropic_model(model: ModelName) -> str:
    if model not in (ModelName.CLAUDE_SONNET_4_6, ModelName.CLAUDE_HAIKU_4_5):
        return ModelName.CLAUDE_SONNET_4_6.value
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


# Friendly progress-chip labels per sub-agent — these are what the user sees in
# the chat step tray (ContentStepProgress renders dispatch_subagent:* chips).
# Unknown names fall back to a humanised form of the raw name.
_SUBAGENT_LABELS: dict[str, str] = {
    "research_pillar": "Researching topics",
    "draft_post":      "Drafting post",
    "review_post":     "Reviewing before publish",
}


def _subagent_label(name: str) -> str:
    return _SUBAGENT_LABELS.get(name) or f"Sub-agent · {name.replace('_', ' ')}"


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
        # Global library refs ('/static/references/...') are resolved from
        # disk by the tool, not the DB — keep them out of the UUID-typed
        # request model so validation doesn't reject them. They still count
        # toward the max-3 cap checked above.
        from service.content_references import disk_path_for_public_url
        payload["input_asset_ids"] = [
            x for x in merged_ids if disk_path_for_public_url(str(x)) is None
        ]
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
    initial_prompt: str | list,   # str, or a list of content blocks (clone_post attaches reference images)
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
                "label":    _subagent_label(sub_name),
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
            "label":      _subagent_label(sub_name),
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

    _mcp = build_content_mcp_server(project_id, emit, session)

    # Video posts also get Higgsfield's hosted MCP wired in as a REMOTE HTTP
    # server, authenticated with the user's stored bearer (frontend OAuth) or the
    # HIGGSFIELD_API_TOKEN env fallback. The Claude Agent SDK doesn't run OAuth —
    # it just replays the bearer (see service/higgsfield/auth). Only attached for
    # post_type == "video" so slideshow sessions don't pay the connect/tool cost.
    # If no token is connected we skip it and the agent reports it can't generate
    # video (fails soft rather than crashing).
    mcp_servers: dict = {"duct_content": _mcp}
    _video_allowed_tools: list = []
    if session.post_type == PostType.VIDEO:
        _hf_token = await asyncio.to_thread(_resolve_higgsfield_token, project_id)
        if _hf_token:
            from service.higgsfield.auth import higgsfield_mcp_config
            mcp_servers["higgsfield"] = higgsfield_mcp_config(_hf_token)
            _video_allowed_tools = ["mcp__higgsfield__*"]
            logger.info("content: Higgsfield video MCP attached (session %s)", session_id)
        else:
            logger.warning(
                "content: video post but Higgsfield is not connected (session %s) — "
                "agent will lack video-generation tools", session_id,
            )

    # ------------------------------------------------------------------
    # ClaudeAgentOptions
    # ------------------------------------------------------------------

    options = ClaudeAgentOptions(
        model=_resolve_anthropic_model(ModelName.CLAUDE_SONNET_4_6),
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
            ContentTool.FETCH_POST,
            ContentTool.FETCH_SLIDE_CONTEXT,
            ContentTool.RENDER_SLIDE,
            ContentTool.GENERATE_IMAGE,
            ContentTool.EDIT_IMAGE,
            # Attaches a finished Higgsfield clip to a video post. Harmless for
            # slideshow sessions (the model only calls it for post_type='video').
            ContentTool.ATTACH_POST_VIDEO,
            # Deconstructs a reference clip via Gemini video understanding. Cheap +
            # cached (reads clone_source.video_analysis); the clone agent calls it
            # before drafting a video clone. Harmless outside clone sessions.
            ContentTool.UNDERSTAND_VIDEO,
            # Generates the clip IN-HOUSE with Veo (no Higgsfield needed). The model
            # only calls it for post_type='video'; harmless for slideshow sessions.
            ContentTool.GENERATE_VIDEO_CLIP,
            # Higgsfield's remote MCP tools (only present when wired above).
            *_video_allowed_tools,
            # Owned by the review_post sub-agent (it runs the whole pre-publish
            # review). Kept in the parent allow-list because every sub-agent tool
            # is also gated here — the orchestrator is told (in the prompt) not to
            # call these directly; the sub-agent finalises via submit_assessment.
            ContentTool.CHECK_POST_SANITY,
            ContentTool.SUBMIT_ASSESSMENT,
        ],
        agents={
            "research_pillar":    RESEARCH_PILLAR_AGENT,
            "draft_post":         DRAFT_POST_AGENT,
            "review_post":        REVIEW_POST_AGENT,
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
        # Do NOT override cli_path — let the SDK use its own bundled binary, which
        # is version-matched to the SDK. Passing shutil.which("claude") here would
        # use the system-installed CLI, which may be a different (incompatible)
        # version (mirrors agents/audit/v3/runner.py).
        mcp_servers=mcp_servers,
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
        post_type: str | None = None,
        effort: AgentEffort | None = None,
        adaptive_thinking: bool = True,
        max_turns: int | None = None,
        chat_idle_timeout: float = 1800.0,
    ) -> None:
        """Run a draft_post session end-to-end."""
        from agents.content.channels import resolve as resolve_channel
        session = get_session(session_id) or create_draft_session(session_id, project_id)
        ch = resolve_channel(channel)  # sync, no DB — safe before the first emit
        # Resolve content type up front so _run knows whether to wire the
        # Higgsfield video MCP for this session. Authoritative order: plan day /
        # bound post (DB) wins; an explicit request post_type only seeds the
        # no-day, no-post case (a standalone "draft now" video).
        _resolved_type = await asyncio.to_thread(_resolve_session_post_type, session, day)
        if _resolved_type == PostType.SLIDESHOW and post_type:
            _resolved_type = post_type
        session.post_type = _resolved_type

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
            post_type=session.post_type,
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

    async def run_clone(
        self,
        session_id: str,
        project_id: UUID,
        emit: EmitFn,
        *,
        post_id: UUID,
        plan_id: UUID | None = None,
        channel: str | None = None,
        effort: AgentEffort | None = None,
        adaptive_thinking: bool = True,
        max_turns: int | None = None,
        chat_idle_timeout: float = 1800.0,
    ) -> None:
        """Run a clone_post session: ingest the reference (deferred, cached),
        then model it into an original PostDraft for this brand.

        The pending post (carrying clone_source) already exists — `post_id` points
        at it. The ingest runs as deterministic opening steps (resolve▸scrape▸
        media▸analyze), is cached back onto clone_source so a re-draft never
        re-charges Apify, then the agent writes the clone onto the SAME post_dir_slug
        (pending → draft)."""
        import base64
        from datetime import datetime, timezone

        from sqlmodel import Session

        from agents.content.channels import primary_channel, resolve as resolve_channel
        from db.session import get_engine
        from models.content import ContentPost
        from service import storage
        from service.discovery import ingest_reference

        session = get_session(session_id) or create_clone_session(
            session_id, project_id, plan_id=plan_id, post_id=post_id
        )
        session.post_id = post_id
        # Clones inherit the reference's type (slideshow | video) — resolve from
        # the bound post so a video clone wires the Higgsfield MCP in _run.
        session.post_type = await asyncio.to_thread(_resolve_session_post_type, session, None)
        engine = get_engine()
        if engine is None:
            raise RuntimeError("DATABASE_URL is not configured.")

        def _load_post() -> tuple[dict, str, list]:
            with Session(engine) as db:
                p = db.get(ContentPost, post_id)
                if p is None:
                    raise ValueError(f"Post {post_id} not found.")
                return (dict(p.clone_source or {}), p.post_dir_slug, list(p.platforms or []))

        clone_source, post_dir_slug, platforms = await asyncio.to_thread(_load_post)
        ch = resolve_channel(channel or (primary_channel(platforms) if platforms else None))

        await emit({
            "event":      ContentEvent.PIPELINE_STARTED,
            "session_id": session_id,
            "mode":       "clone_post",
            "channel":    getattr(ch, "id", "tiktok"),
            "channel_label": getattr(ch, "label", "TikTok"),
        })

        # ── Ingest the reference (the expensive step — cached on clone_source) ──
        _CLONE_STEP_LABELS = {
            "resolving": "Resolving the reference",
            "scraping":  "Scraping TikTok (metadata + media)",
            "media":     "Saving cover & slide images",
            "analyzing": "Reading why it worked",
        }

        async def _on_step(sid: str, status: str, msg: str = "") -> None:
            label = _CLONE_STEP_LABELS.get(sid, sid)
            if status == "running":
                await emit({"event": ContentEvent.STEP_STARTED, "step_id": f"clone_{sid}",
                            "label": label, "status": StepStatus.RUNNING})
            else:
                await emit({"event": ContentEvent.STEP_FINISHED, "step_id": f"clone_{sid}",
                            "label": label,
                            "status": StepStatus.SUCCESS if status == "ok" else StepStatus.ERROR,
                            "payload": {"message": msg}})

        try:
            reference = await ingest_reference(project_id, clone_source, on_step=_on_step)
        except Exception as exc:
            await emit({"event": ContentEvent.PIPELINE_FAILED, "session_id": session_id,
                        "error": f"Couldn't fetch the reference: {exc}"})
            raise
        if reference.get("error"):
            await emit({"event": ContentEvent.PIPELINE_FAILED, "session_id": session_id,
                        "error": "Couldn't fetch this TikTok reference — check the URL and try again."})
            return

        # The reference's type wins: a video reference clones into a VIDEO post,
        # a carousel into a carousel. `is_slideshow is False` is the same test the
        # planner/card use; a missing flag (None) defaults to slideshow.
        sp = reference.get("scraped_post") or {}
        ref_post_type = (
            PostType.VIDEO if sp.get("is_slideshow") is False else PostType.SLIDESHOW
        )

        # Cache the ingest onto the post so a second Draft-now is free.
        def _cache() -> None:
            with Session(engine) as db:
                p = db.get(ContentPost, post_id)
                if p is None:
                    return
                cs = dict(p.clone_source or {})
                cs.update({
                    "ingested":    True,
                    "scraped_post": sp,
                    "media":       reference.get("media") or {},
                    "diagnostic":  reference.get("diagnostic") or {},
                    # Director-grade Gemini deconstruction of the clip (video refs);
                    # persisted on the post so the agent reads it while drafting and a
                    # re-draft never re-watches. media.video carries the stable mp4 URL.
                    "video_analysis": reference.get("video_analysis") or "",
                    "tiktok_url":  reference.get("tiktok_url") or cs.get("url"),
                    "reference_asset_id": cs.get("reference_asset_id") or reference.get("asset_id"),
                    "ingested_at": datetime.now(timezone.utc).isoformat(),
                })
                p.clone_source = cs
                p.post_type = ref_post_type
                db.add(p)
                db.commit()

        await asyncio.to_thread(_cache)

        # Update the SESSION's type to match BEFORE _run reads it to decide whether
        # to wire the Higgsfield MCP. The pending post was created as the default
        # slideshow, so session.post_type (resolved at the top from that row) is
        # stale once ingest reveals a video reference — without this, a video clone
        # would run without Higgsfield's analyser / image-to-video tools.
        session.post_type = ref_post_type

        # ── Build the agent kickoff: clone prompt + reference images ────────────
        brand = await asyncio.to_thread(_load_brand_context, project_id)
        system_prompt = build_orchestrator_system_prompt(brand, "clone_post", channel=ch)
        clone_text = build_clone_user_prompt(
            brand, reference=reference, post_dir_slug=post_dir_slug, channel=ch,
        )
        content_blocks: list = [{"type": "text", "text": clone_text}]
        media = reference.get("media") or {}
        img_urls = ([media["cover"]] if media.get("cover") else []) + list(media.get("slides") or [])[:5]
        for u in img_urls:
            data = await asyncio.to_thread(storage.get_bytes, u)
            if data:
                content_blocks.append({
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/jpeg",
                               "data": base64.b64encode(data).decode("ascii")},
                })

        try:
            await _run(
                session,
                system_prompt,
                content_blocks,
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
                    "mode":       "clone_post",
                    "post_id":    str(session.post_id),
                })
            else:
                logger.error("content: clone session %s ended with no post persisted", session_id)
                await emit({
                    "event":      ContentEvent.PIPELINE_FAILED,
                    "session_id": session_id,
                    "error":      "The content engine finished without producing a clone draft. "
                                  "This is usually transient — please try again.",
                })
        except Exception as exc:
            await emit({"event": ContentEvent.PIPELINE_FAILED, "session_id": session_id, "error": str(exc)})
            raise


__all__ = [
    "ClaudeContentRunner",
    "close_session",
    "create_clone_session",
    "create_draft_session",
    "create_plan_session",
    "get_session",
]
