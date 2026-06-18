"""ClaudePlannerRunner — Content Planner agent (Claude Agent SDK, v3 engine).

Mirrors agents/content/v3/runner.py but trimmed to the planner's job: one mode
(update_plan), research sub-agents (trend_scout, competitor_analyst), the
planner MCP tools, and a single deliverable (a 7-day PlanDraft → submit_plan).

Reuses the shared framework (agents/core: claude_sdk, stream, session) and the
content brand loader + enrichment as a library — it does not run the content
agent. The plan it writes is the project's canonical active plan.
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
from agents.content.schema import PlanDraft
from agents.content.v3.runner import _load_brand_context, _resolve_anthropic_model
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
from agents.planner import data as _data
from agents.planner.prompts import build_planner_system_prompt, build_planner_user_prompt
from agents.planner.schema import PlannerSession, PlannerTool, make_planner_session
from agents.planner.subagents import COMPETITOR_ANALYST_AGENT, TREND_SCOUT_AGENT
from agents.planner.tools import build_planner_mcp_server

logger = logging.getLogger(__name__)

EmitFn = Callable[[dict[str, Any]], Awaitable[None]]

# See content runner for the rationale on these two timeouts.
_STALL_TIMEOUT_SECS = 120.0
_ASK_USER_TIMEOUT_SECS = 600.0

_RECOVERY_NUDGE = (
    "You analysed everything but did not persist the plan. Emit the complete "
    '<duct_report>{"type":"plan", …}</duct_report> now and then call submit_plan '
    "with the same payload — do not run more research, just produce and save the plan."
)

# A user typing this in chat triggers a full PostBridge metrics refresh. We
# rewrite it to an explicit instruction so the slash command works reliably
# regardless of SDK filesystem command discovery (the underlying tool is
# sync_all_posts; see agents/planner/commands/refresh-posts.md).
_REFRESH_COMMAND = "/refresh-posts"
_REFRESH_INSTRUCTION = (
    "Call sync_all_posts to refresh every published post's metrics from "
    "PostBridge, then call fetch_post_metrics and tell me what changed and "
    "whether it shifts the current plan."
)

get_session = _core_session.get_session
close_session = _core_session.close_session


def create_planner_session(session_id: str, project_id: UUID) -> PlannerSession:
    return register_session(make_planner_session(session_id, project_id))


def _load_prior_strategy(project_id: UUID) -> dict | None:
    """Read the active plan's strategy so the new plan continues the arc."""
    from sqlmodel import select

    from models.content import ContentPlan

    try:
        with _data._open_db() as db:
            row = db.exec(
                select(ContentPlan)
                .where(ContentPlan.project_id == project_id)
                .where(ContentPlan.status == "active")
                .order_by(ContentPlan.updated_at.desc())
            ).first()
            return dict(row.strategy) if row and row.strategy else None
    except Exception:
        logger.warning("planner: failed to load prior strategy", exc_info=True)
        return None


def _parse_report_json(raw: str) -> dict | None:
    candidate = raw.strip()
    fenced = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", candidate)
    if fenced:
        candidate = fenced.group(1).strip()
    try:
        return json.loads(candidate)
    except Exception as exc:
        logger.warning("planner: <duct_report> JSON parse failed: %s", exc)
        return None


def _extract_subagent_name(input_data: dict[str, Any]) -> str:
    for key in ("subagent_type", "agent", "agent_type", "name"):
        v = input_data.get(key)
        if isinstance(v, str) and v:
            return v
    return "unknown"


_SUBAGENT_LABELS = {
    "trend_scout":        "Researching trends",
    "competitor_analyst": "Analysing competitors",
}


def _subagent_label(name: str) -> str:
    return _SUBAGENT_LABELS.get(name) or f"Sub-agent · {name.replace('_', ' ')}"


def _chat_text(content: Any) -> str:
    """Flatten a chat message's content (str or block list) to plain text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
        )
    return ""


# ---------------------------------------------------------------------------
# Core run loop
# ---------------------------------------------------------------------------


async def _run(
    session: PlannerSession,
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
    """Drive one Claude Agent SDK session for the planner (update_plan)."""
    from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient
    from claude_agent_sdk.types import (
        HookMatcher,
        PermissionResultAllow,
        PermissionResultDeny,
        ThinkingConfigAdaptive,
    )

    session_id = session.session_id
    project_id = session.project_id

    def _artifact_produced() -> bool:
        return session.plan_id is not None

    _nudged = False
    _research_pending: deque[tuple[str, str]] = deque()
    _research_seq = [0]

    # ------------------------------------------------------------------
    # can_use_tool — Agent dispatch + web research observability,
    # submit_plan validation, AskUserQuestion bridge
    # ------------------------------------------------------------------

    async def _can_use_tool(tool_name: str, input_data: dict, context: Any):
        if tool_name == AgentTool.AGENT:
            sub_name = _extract_subagent_name(input_data)
            brief = input_data.get("prompt") or input_data.get("description") or ""
            if not isinstance(brief, str):
                brief = json.dumps(brief, default=str)
            await emit({
                "event":      ContentEvent.STEP_STARTED,
                "session_id": session_id,
                "step_id":    f"{ContentStep.DISPATCH_SUBAGENT.value}:{sub_name}",
                "label":      _subagent_label(sub_name),
                "summary":    brief[:160],
                "status":     StepStatus.RUNNING,
            })
            return PermissionResultAllow(updated_input=input_data)

        if tool_name == PlannerTool.SUBMIT_PLAN:
            payload = input_data.get("plan") if isinstance(input_data.get("plan"), dict) else input_data
            try:
                draft = PlanDraft.model_validate(payload)
            except Exception as exc:
                return PermissionResultDeny(
                    message=(
                        "PlanDraft validation failed — fix the JSON and call "
                        f"submit_plan again:\n{exc}"
                    )
                )
            if str(draft.project_id) != str(project_id):
                return PermissionResultDeny(
                    message=(
                        f"project_id mismatch: session is {project_id}, payload had "
                        f"{draft.project_id}. Use the session's project_id."
                    )
                )
            return PermissionResultAllow(updated_input=input_data)

        if tool_name in (AgentTool.WEB_SEARCH, AgentTool.WEB_FETCH):
            _research_seq[0] += 1
            sid = f"research:{_research_seq[0]}"
            query = input_data.get("query") or input_data.get("url") or ""
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
                "status":     StepStatus.RUNNING,
            })
            return PermissionResultAllow(updated_input=input_data)

        if tool_name == AgentTool.ASK_USER_QUESTION:
            updated = await bridge_ask_user_question(
                session, session_id, input_data, emit,
                timeout=_ASK_USER_TIMEOUT_SECS, log_prefix="planner",
            )
            return PermissionResultAllow(updated_input=updated)

        return PermissionResultAllow(updated_input=input_data)

    async def _pre_tool_hook(input_data: dict, tool_use_id: str, context: Any) -> dict:
        _rec = getattr(session, "recorder", None)
        if _rec is not None:
            try:
                await _rec.record_tool_use(
                    name=input_data.get("tool_name", ""),
                    tool_input=input_data.get("tool_input", input_data),
                    tool_use_id=tool_use_id,
                )
            except Exception:
                logger.debug("planner: tool_use persistence failed", exc_info=True)
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
                logger.debug("planner: tool_result persistence failed", exc_info=True)
        return {"continue_": True}

    async def _post_agent_hook(input_data: dict, tool_use_id: str, context: Any) -> dict:
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
            "status":     StepStatus.SUCCESS,
        })
        return {"continue_": True}

    async def _post_web_hook(input_data: dict, tool_use_id: str, context: Any) -> dict:
        if _research_pending:
            sid, label = _research_pending.popleft()
            await emit({
                "event":      ContentEvent.STEP_FINISHED,
                "session_id": session_id,
                "step_id":    sid,
                "label":      label,
                "status":     StepStatus.SUCCESS,
            })
        return {"continue_": True}

    # ------------------------------------------------------------------
    # SDK env + MCP server
    # ------------------------------------------------------------------

    from config import get_configs, sentry_otel_env
    _cfg = get_configs()

    _sdk_env, _config_dir = _sdk.build_sdk_env(
        service_name="duct-planner",
        api_key=api_key,
        oauth_token=_cfg.claude_code_oauth_token,
        config_env_var="DUCT_PLANNER_CLAUDE_CONFIG_DIR",
        config_suffix="duct-planner",
        log_prefix="planner",
        session_id=session_id,
        sentry_env=sentry_otel_env(_cfg),
        enable_tool_search=False,
    )

    _stderr_buf: deque[str] = deque(maxlen=100)

    def _on_subprocess_stderr(line: str) -> None:
        stripped = line.rstrip()
        _stderr_buf.append(stripped)
        logger.error("planner subprocess stderr [%s]: %s", session_id, stripped)

    _cli_path = shutil.which("claude") or None
    _mcp = build_planner_mcp_server(project_id, emit, session)

    options = ClaudeAgentOptions(
        model=_resolve_anthropic_model(ModelName.CLAUDE_SONNET),
        permission_mode=AgentPermissionMode.DONT_ASK,
        allowed_tools=[
            AgentTool.ASK_USER_QUESTION,
            AgentTool.TODO_WRITE,
            AgentTool.WEB_SEARCH,
            AgentTool.WEB_FETCH,
            AgentTool.AGENT,
            PlannerTool.SUBMIT_PLAN,
            PlannerTool.FETCH_BRAND_CONTEXT,
            PlannerTool.FETCH_PLANNER_CONFIG,
            PlannerTool.SAVE_PLANNER_CONFIG,
            PlannerTool.FETCH_POST_METRICS,
            PlannerTool.SYNC_ALL_POSTS,
        ],
        agents={
            "trend_scout":        TREND_SCOUT_AGENT,
            "competitor_analyst": COMPETITOR_ANALYST_AGENT,
        },
        can_use_tool=_can_use_tool,
        hooks={
            "PreToolUse":  [HookMatcher(matcher=None, hooks=[_pre_tool_hook])],
            "PostToolUse": [
                HookMatcher(matcher=None,                 hooks=[_record_tool_result_hook]),
                HookMatcher(matcher=AgentTool.AGENT,      hooks=[_post_agent_hook]),
                HookMatcher(matcher=AgentTool.WEB_SEARCH, hooks=[_post_web_hook]),
                HookMatcher(matcher=AgentTool.WEB_FETCH,  hooks=[_post_web_hook]),
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
        mcp_servers={"duct_planner": _mcp},
    )

    # ------------------------------------------------------------------
    # Message generators + <duct_report> parser
    # ------------------------------------------------------------------

    async def _initial_prompt_gen():
        yield {"type": "user", "message": {"role": "user", "content": initial_prompt}}

    _first_token_at: float | None = None

    async def _on_text(text: str) -> None:
        await emit({"event": ContentEvent.AGENT_MESSAGE_CHUNK, "text": text})

    async def _on_report_chunk(text: str) -> None:
        await emit({"event": ContentEvent.REPORT_CHUNK, "text": text})

    async def _handle_close(raw_json: str) -> None:
        payload = _parse_report_json(raw_json)
        if payload is None:
            return
        if payload.get("type") == "plan":
            try:
                PlanDraft.model_validate(payload)
            except Exception as exc:
                logger.warning("planner: PlanDraft validation failed (writer re-validates): %s", exc)
            await emit({
                "event":      ContentEvent.PLAN_GENERATED,
                "session_id": session_id,
                "payload":    payload,
                "source":     "duct_report",
            })

    async def _on_report_close(raw_json: str, _turn_text: str) -> None:
        await _handle_close(raw_json)

    parser = DuctReportStreamParser(
        on_text=_on_text,
        on_report_chunk=_on_report_chunk,
        on_report_close=_on_report_close,
        on_open=None,
        log_prefix="planner",
    )

    async def _on_thinking(text: str) -> None:
        await emit({"event": ContentEvent.THINKING_CHUNK, "text": text})

    async def _on_text_delta(text: str) -> None:
        nonlocal _first_token_at
        if _first_token_at is None:
            _first_token_at = perf_counter()
        await parser.feed(text)

    async def _on_msg_stop() -> None:
        await parser.flush()
        parser.turn_text.clear()
        await emit({"event": ContentEvent.MESSAGE_STOP})

    async def _on_result(result_msg: Any) -> None:
        nonlocal _nudged
        if not _artifact_produced() and not _nudged:
            _nudged = True
            logger.warning(
                "planner: turn ended with no plan persisted for session %s — one recovery nudge",
                session_id,
            )
            await session.chat_queue.put({"role": "user", "content": _RECOVERY_NUDGE})

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
            agent="planner",
            agent_label="planner engine",
            mode=session.mode,
        )

        async def _receive_one_turn(*, bound_first_output: bool = False) -> None:
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
                    captured = _sdk.captured_stderr(_stderr_buf, None)
                    raise RuntimeError(
                        f"Planner produced no output for {_STALL_TIMEOUT_SECS:.0f}s — "
                        "the run stalled before completing."
                        + (f"\n  subprocess stderr:\n{captured}" if captured else "")
                    ) from exc
                if armed and type(msg).__name__ != "SystemMessage":
                    armed = False
                await pump_stream_event(
                    msg,
                    on_text=_on_text_delta,
                    on_thinking=_on_thinking,
                    on_message_stop=_on_msg_stop,
                    on_result=_on_result,
                    on_todo=_on_todo,
                )

        if not resume:
            await client.query(_initial_prompt_gen())
            await _receive_one_turn(bound_first_output=True)

        while True:
            try:
                chat_msg = await asyncio.wait_for(
                    session.chat_queue.get(), timeout=chat_idle_timeout
                )
            except asyncio.TimeoutError:
                logger.info("planner: session %s chat idle timeout", session_id)
                break
            if chat_msg is None:
                break

            # /refresh-posts → rewrite to an explicit sync instruction so the
            # slash command works without SDK filesystem command discovery.
            if _chat_text(chat_msg.get("content")).strip().lower() == _REFRESH_COMMAND:
                chat_msg = {"role": "user", "content": _REFRESH_INSTRUCTION}

            async def _chat_gen(m=chat_msg):
                yield {"type": "user", "message": m}

            await client.query(_chat_gen())
            await _receive_one_turn()
    except Exception:
        logger.exception("planner v3: run failed for session %s", session_id)
        raise
    finally:
        if client is not None:
            with suppress(Exception):
                await client.disconnect()
        _sdk.cleanup_session_config_dir(_config_dir, log_prefix="planner")


# ---------------------------------------------------------------------------
# Public runner
# ---------------------------------------------------------------------------


class ClaudePlannerRunner:
    """High-level entrypoint used by routes/content.py's planner worker."""

    DEFAULT_EFFORT = AgentEffort.MEDIUM
    DEFAULT_MAX_TURNS = 140

    def __init__(self, api_key: str) -> None:
        from config import claude_oauth_available

        if not api_key and not claude_oauth_available():
            raise ValueError("ANTHROPIC_API_KEY is required for ClaudePlannerRunner.")
        self._api_key = api_key

    async def run_plan(
        self,
        session_id: str,
        project_id: UUID,
        emit: EmitFn,
        *,
        start_date=None,
        effort: AgentEffort | None = None,
        adaptive_thinking: bool = True,
        max_turns: int | None = None,
        chat_idle_timeout: float = 1800.0,
    ) -> None:
        """Run an update_plan session end-to-end."""
        session = get_session(session_id) or create_planner_session(session_id, project_id)

        # ── Resume: restore + ready, never a greeting turn (mirrors content). ──
        if getattr(session, "resume", False) and getattr(session, "conversation_id", None):
            system_prompt = build_planner_system_prompt()
            from agents.content.persistence import build_reprime_context
            session.resume_primer = await build_reprime_context(session, self._api_key)
            session.needs_reprime = True
            await emit({
                "event":      ContentEvent.PIPELINE_FINISHED,
                "session_id": session_id,
                "mode":       "update_plan",
                "plan_id":    str(session.plan_id) if session.plan_id else None,
                "resumed":    True,
            })
            try:
                await _run(
                    session, system_prompt, "", emit, self._api_key,
                    effort=effort or self.DEFAULT_EFFORT,
                    adaptive_thinking=adaptive_thinking,
                    chat_idle_timeout=chat_idle_timeout,
                    max_turns=max_turns or self.DEFAULT_MAX_TURNS,
                    resume=True,
                )
            except Exception as exc:
                await emit({"event": ContentEvent.PIPELINE_FAILED, "session_id": session_id, "error": str(exc)})
                raise
            return

        await emit({"event": ContentEvent.PIPELINE_STARTED, "session_id": session_id, "mode": "update_plan"})
        await emit({
            "event":   ContentEvent.STEP_STARTED,
            "step_id": ContentStep.LOAD_PROJECT,
            "label":   STEP_LABELS[ContentStep.LOAD_PROJECT],
            "status":  StepStatus.RUNNING,
        })
        brand = await asyncio.to_thread(_load_brand_context, project_id)
        config = await asyncio.to_thread(_data.load_planner_config, project_id)
        accounts = await asyncio.to_thread(_data.linked_accounts, project_id)
        performance = await asyncio.to_thread(_data.performance_summary, project_id)
        prior_strategy = await asyncio.to_thread(_load_prior_strategy, project_id)
        await emit({
            "event":   ContentEvent.STEP_FINISHED,
            "step_id": ContentStep.LOAD_PROJECT,
            "label":   STEP_LABELS[ContentStep.LOAD_PROJECT],
            "status":  StepStatus.SUCCESS,
            "payload": {"project_name": brand.project_name, "configured": config.is_complete()},
        })

        # ── Enrichment: local scan + optional Haiku trend research (reused). ──
        await emit({
            "event":   ContentEvent.STEP_STARTED,
            "step_id": ContentStep.ENRICHING,
            "label":   STEP_LABELS[ContentStep.ENRICHING],
            "status":  StepStatus.RUNNING,
        })
        from agents.content.enrichment import enrich_content_context
        try:
            research = await enrich_content_context(brand, self._api_key)
        except Exception as exc:
            logger.warning("planner: enrichment failed (%s); proceeding without", exc)
            research = None
        await emit({
            "event":   ContentEvent.STEP_FINISHED,
            "step_id": ContentStep.ENRICHING,
            "label":   STEP_LABELS[ContentStep.ENRICHING],
            "status":  StepStatus.SUCCESS,
        })

        system_prompt = build_planner_system_prompt()
        initial_prompt = build_planner_user_prompt(
            brand, config, accounts, performance,
            research=research, prior_strategy=prior_strategy, start_date=start_date,
        )

        try:
            await _run(
                session, system_prompt, initial_prompt, emit, self._api_key,
                effort=effort or self.DEFAULT_EFFORT,
                adaptive_thinking=adaptive_thinking,
                chat_idle_timeout=chat_idle_timeout,
                max_turns=max_turns or self.DEFAULT_MAX_TURNS,
            )
            if session.plan_id is not None:
                await emit({
                    "event":      ContentEvent.PIPELINE_FINISHED,
                    "session_id": session_id,
                    "mode":       "update_plan",
                    "plan_id":    str(session.plan_id),
                })
            else:
                logger.error("planner: session %s ended with no plan persisted", session_id)
                await emit({
                    "event":      ContentEvent.PIPELINE_FAILED,
                    "session_id": session_id,
                    "error":      "The planner finished without producing a plan. "
                                  "This is usually transient — please try again.",
                })
        except Exception as exc:
            await emit({"event": ContentEvent.PIPELINE_FAILED, "session_id": session_id, "error": str(exc)})
            raise


__all__ = [
    "ClaudePlannerRunner",
    "close_session",
    "create_planner_session",
    "get_session",
]
