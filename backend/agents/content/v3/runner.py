"""ClaudeContentRunner — Content Marketing agent (Claude Agent SDK, v3 engine).

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
from collections.abc import Awaitable, Callable
from time import perf_counter
from typing import Any
from uuid import UUID

from agents.content.events import ContentEvent, ContentStep, STEP_LABELS
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
    ContentVisualAssets,
    Day,
    PlanDraft,
    PostDraft,
    make_session,
)
from agents.content.subagents import (
    BUILD_SLIDES_AGENT,
    DRAFT_POST_AGENT,
    RESEARCH_PILLAR_AGENT,
)
from agents.content.tools import build_content_mcp_server
from agents.models import (
    AgentEffort,
    AgentPermissionMode,
    AgentTool,
    ModelName,
    ThinkingMode,
)

logger = logging.getLogger(__name__)

EmitFn = Callable[[dict[str, Any]], Awaitable[None]]

# Module-level session registry — in-process only.
_sessions: dict[str, ContentSession] = {}


# ---------------------------------------------------------------------------
# Session registry
# ---------------------------------------------------------------------------


def get_session(session_id: str) -> ContentSession | None:
    return _sessions.get(session_id)


def create_plan_session(session_id: str, project_id: UUID) -> ContentSession:
    session = make_session(session_id, project_id, "plan_month")
    _sessions[session_id] = session
    return session


def create_draft_session(
    session_id: str,
    project_id: UUID,
    *,
    plan_id: UUID | None = None,
) -> ContentSession:
    session = make_session(session_id, project_id, "draft_post")
    if plan_id is not None:
        session.plan_id = plan_id
    _sessions[session_id] = session
    return session


def close_session(session_id: str) -> None:
    session = _sessions.pop(session_id, None)
    if session is None:
        return
    try:
        session.chat_queue.put_nowait(None)
    except Exception:
        pass


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
    return {
        ModelName.CLAUDE_SONNET: "claude-sonnet-4-6",
        ModelName.CLAUDE_HAIKU:  "claude-haiku-4-5-20251001",
    }.get(model, "claude-sonnet-4-6")


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


def _is_todo_write(block: Any) -> bool:
    return (
        getattr(block, "type", None) == "tool_use"
        and getattr(block, "name", None) == AgentTool.TODO_WRITE
        and isinstance(getattr(block, "input", None), dict)
    )


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
        StreamEvent,
        ThinkingConfigAdaptive,
    )

    session_id = session.session_id
    project_id = session.project_id

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
                "status":   "running",
            })
            return PermissionResultAllow(updated_input=input_data)

        # ---- Writer-tool upfront validation ------------------------------
        # Validating here (rather than letting the @tool body return
        # is_error=true) gives the model a tight feedback loop: the
        # corrective message arrives BEFORE any DB or API work runs, and
        # the SDK surfaces it as a permission denial which the model
        # treats as authoritative. Pattern borrowed from audit's
        # SubmitAuditReport handler.

        if tool_name == "mcp__duct_content__submit_plan":
            deny = _validate_submit_plan(input_data, project_id)
            if deny is not None:
                return deny
            return PermissionResultAllow(updated_input=input_data)

        if tool_name == "mcp__duct_content__submit_post_draft":
            deny = _validate_submit_post_draft(input_data, project_id)
            if deny is not None:
                return deny
            return PermissionResultAllow(updated_input=input_data)

        if tool_name == "mcp__duct_content__generate_image":
            deny = _validate_generate_image(input_data)
            if deny is not None:
                return deny
            return PermissionResultAllow(updated_input=input_data)

        if tool_name == "mcp__duct_content__edit_image":
            deny = _validate_edit_image(input_data)
            if deny is not None:
                return deny
            return PermissionResultAllow(updated_input=input_data)

        # AskUserQuestion: bridge to the SSE consumer via asyncio.Future.
        if tool_name == AgentTool.ASK_USER_QUESTION:
            loop = asyncio.get_event_loop()
            fut: asyncio.Future = loop.create_future()
            session.answer_future = fut
            await emit({
                "event":     ContentEvent.QUESTIONS_REQUIRED,
                "session_id": session_id,
                "questions": input_data.get("questions", []),
            })
            try:
                answers = await asyncio.wait_for(asyncio.shield(fut), timeout=120.0)
            except asyncio.TimeoutError:
                logger.warning("content: AskUserQuestion timed out for session %s", session_id)
                answers = {}
            finally:
                session.answer_future = None
            return PermissionResultAllow(updated_input={
                "questions": input_data.get("questions", []),
                "answers":   answers,
            })

        # Everything else is allowed by allowed_tools; pass through.
        return PermissionResultAllow(updated_input=input_data)

    async def _pre_tool_hook(input_data: dict, tool_use_id: str, context: Any) -> dict:
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
            "status":     "success",
        })
        return {"continue_": True}

    # ------------------------------------------------------------------
    # SDK env + MCP server
    # ------------------------------------------------------------------

    from config import get_configs, sentry_otel_env
    _cfg = get_configs()

    _sdk_env: dict[str, str] = {
        "OTEL_SERVICE_NAME": "duct-content",
        "ENABLE_PROMPT_CACHING_1H": "1",
        **sentry_otel_env(_cfg),
    }
    if api_key:
        _sdk_env["ANTHROPIC_API_KEY"] = api_key

    def _on_subprocess_stderr(line: str) -> None:
        logger.error("content subprocess stderr [%s]: %s", session_id, line.rstrip())

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
            "mcp__duct_content__submit_plan",
            "mcp__duct_content__submit_post_draft",
            "mcp__duct_content__fetch_brand_context",
            "mcp__duct_content__fetch_topic_bank",
            "mcp__duct_content__fetch_format_library",
            "mcp__duct_content__fetch_avatar_library",
            "mcp__duct_content__fetch_content_history",
            "mcp__duct_content__fetch_content_assets",
            "mcp__duct_content__fetch_discovered_references",
            "mcp__duct_content__generate_image",
            "mcp__duct_content__edit_image",
            "mcp__duct_content__publish_post",
            "mcp__duct_content__mark_posted",
            "mcp__duct_content__log_metrics",
        ],
        agents={
            "research_pillar":    RESEARCH_PILLAR_AGENT,
            "draft_post":         DRAFT_POST_AGENT,
            "build_slides_html":  BUILD_SLIDES_AGENT,
        },
        can_use_tool=_can_use_tool,
        hooks={
            "PreToolUse":  [HookMatcher(matcher=None,    hooks=[_pre_tool_hook])],
            "PostToolUse": [HookMatcher(matcher="Agent", hooks=[_post_agent_hook])],
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

    async def message_gen():
        yield {"type": "user", "message": {"role": "user", "content": initial_prompt}}
        while True:
            try:
                msg = await asyncio.wait_for(session.chat_queue.get(), timeout=chat_idle_timeout)
            except asyncio.TimeoutError:
                logger.info("content: session %s chat queue idle", session_id)
                break
            if msg is None:
                break
            yield {"type": "user", "message": msg}

    # ------------------------------------------------------------------
    # Streaming <duct_report> tag parser
    # ------------------------------------------------------------------

    _OPEN_TAG = "<duct_report>"
    _CLOSE_TAG = "</duct_report>"

    _in_tag = False
    _buf = ""
    _holdback = ""
    _turn_text: list[str] = []
    _first_token_at: float | None = None
    _open_tag_at: float | None = None
    _chunk_count = 0

    async def _flush_holdback() -> None:
        nonlocal _holdback
        if _holdback:
            await emit({"event": ContentEvent.AGENT_MESSAGE_CHUNK, "text": _holdback})
            _turn_text.append(_holdback)
            _holdback = ""

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

    async def _process_text(chunk: str) -> None:
        nonlocal _in_tag, _buf, _holdback, _open_tag_at, _chunk_count

        if _in_tag:
            if _CLOSE_TAG in chunk:
                safe, _, remainder = chunk.partition(_CLOSE_TAG)
                if safe:
                    _chunk_count += 1
                    _buf += safe
                    await emit({"event": ContentEvent.REPORT_CHUNK, "text": safe})
                _in_tag = False
                raw = _buf
                _buf = ""
                await _handle_close(raw)
                if remainder:
                    await _process_text(remainder)
            else:
                _buf += chunk
                if _CLOSE_TAG in _buf:
                    raw, _, remainder = _buf.partition(_CLOSE_TAG)
                    _in_tag = False
                    _buf = ""
                    await _handle_close(raw)
                    if remainder:
                        await _process_text(remainder)
                elif chunk:
                    _chunk_count += 1
                    if _chunk_count % 50 == 0:
                        logger.info(
                            "content: <duct_report> streaming — %d chunks, ~%d chars buffered",
                            _chunk_count, len(_buf),
                        )
                    await emit({"event": ContentEvent.REPORT_CHUNK, "text": chunk})
            return

        working = _holdback + chunk
        _holdback = ""

        if _OPEN_TAG in working:
            before, _, after = working.partition(_OPEN_TAG)
            if before:
                await emit({"event": ContentEvent.AGENT_MESSAGE_CHUNK, "text": before})
                _turn_text.append(before)
            _in_tag = True
            _buf = ""
            _open_tag_at = perf_counter()
            elapsed = (_open_tag_at - _first_token_at) if _first_token_at else 0.0
            logger.info(
                "content: <duct_report> opened — JSON streaming started (%.1fs after first token)",
                elapsed,
            )
            if after:
                await _process_text(after)
        else:
            holdback_len = len(_OPEN_TAG) - 1
            if len(working) > holdback_len:
                safe = working[:-holdback_len]
                _holdback = working[-holdback_len:]
                await emit({"event": ContentEvent.AGENT_MESSAGE_CHUNK, "text": safe})
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
                                await emit({
                                    "event": ContentEvent.THINKING_CHUNK,
                                    "text":  thinking_text,
                                })
                        elif delta_type == "text_delta":
                            text_chunk = delta.get("text", "")
                            if text_chunk:
                                if _first_token_at is None:
                                    _first_token_at = perf_counter()
                                    logger.info("content: first text token received")
                                await _process_text(text_chunk)
                    elif ev_type == "message_stop":
                        await _flush_holdback()
                        _turn_text.clear()
                        await emit({"event": ContentEvent.MESSAGE_STOP})
                    continue

                if hasattr(msg, "content") and msg.content:
                    for block in msg.content:
                        if _is_todo_write(block):
                            todos = block.input.get("todos", [])
                            session.todos = todos
                            await emit({
                                "event": ContentEvent.TODO_UPDATE,
                                "todos": todos,
                            })
    except Exception:
        logger.exception("content v3: run failed for session %s", session_id)
        raise


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
        if not api_key:
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
        session = _sessions.get(session_id) or create_plan_session(session_id, project_id)
        brand = _load_brand_context(project_id)

        await emit({
            "event":    ContentEvent.PIPELINE_STARTED,
            "session_id": session_id,
            "mode":     "plan_month",
        })
        await emit({
            "event":   ContentEvent.STEP_STARTED,
            "step_id": ContentStep.LOAD_PROJECT,
            "label":   STEP_LABELS[ContentStep.LOAD_PROJECT],
            "status":  "running",
        })
        await emit({
            "event":   ContentEvent.STEP_FINISHED,
            "step_id": ContentStep.LOAD_PROJECT,
            "label":   STEP_LABELS[ContentStep.LOAD_PROJECT],
            "status":  "success",
            "payload": {"project_name": brand.project_name, "pillars": len(brand.pillars)},
        })

        # ── Enrichment: local scan + optional Haiku trend research ─────────
        await emit({
            "event":   ContentEvent.STEP_STARTED,
            "step_id": ContentStep.ENRICHING,
            "label":   STEP_LABELS[ContentStep.ENRICHING],
            "status":  "running",
        })
        from agents.content.enrichment import enrich_content_context
        research = await enrich_content_context(brand, self._api_key)
        await emit({
            "event":   ContentEvent.STEP_FINISHED,
            "step_id": ContentStep.ENRICHING,
            "label":   STEP_LABELS[ContentStep.ENRICHING],
            "status":  "success",
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
            await emit({
                "event":      ContentEvent.PIPELINE_FINISHED,
                "session_id": session_id,
                "mode":       "plan_month",
                "plan_id":    str(session.plan_id) if session.plan_id else None,
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
        format_style: str = "D",
        effort: AgentEffort | None = None,
        adaptive_thinking: bool = True,
        max_turns: int | None = None,
        chat_idle_timeout: float = 1800.0,
    ) -> None:
        """Run a draft_post session end-to-end."""
        session = _sessions.get(session_id) or create_draft_session(session_id, project_id)
        brand = _load_brand_context(project_id)

        await emit({
            "event":      ContentEvent.PIPELINE_STARTED,
            "session_id": session_id,
            "mode":       "draft_post",
        })

        system_prompt = build_orchestrator_system_prompt(brand, "draft_post")
        initial_prompt = build_post_user_prompt(
            brand,
            day,
            topic=topic,
            pillar=pillar,
            format_style=format_style,
            avatar=None,
            recent_posts=[],
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
            await emit({
                "event":      ContentEvent.PIPELINE_FINISHED,
                "session_id": session_id,
                "mode":       "draft_post",
                "post_id":    str(session.post_id) if session.post_id else None,
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
