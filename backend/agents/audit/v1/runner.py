"""Audit synthesis on the LangChain 1.x agent stack (V1 engine).

Runs alongside `agents/audit/v3/runner.py`, which stays the production path
until V1 earns confidence (`backend/CLAUDE.md`). Nothing here modifies V3.

What is reused rather than reimplemented — the reason this file is short:

* ``agents/core/lc.py`` — the LangChain adapter: ``resolve_chat_model`` (model
  transport) and ``stream_agent`` (the stream → ``AgentEvent`` translation, built
  on the framework-neutral ``<duct_artifact>`` parser). Both lived here until
  insights became the second V1 runner that needed them.
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

from agents.audit.schema import CrawlResult
from agents.audit.scoring import calibrate
from agents.audit.v1.tools import build_audit_tools
from agents.core.lc import build_ask_user_tool, resolve_chat_model, stream_agent
from agents.core.memory_tools import build_memory_tools_lc
from agents.core.session import BaseAgentSession
from agents.models import ModelName, Provider

logger = logging.getLogger(__name__)

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
    project_id=None,          # UUID | None — mounts the memory tools when set
    user_id=None,             # UUID | None — attribution for memory writes
    conversation_id=None,     # UUID | None — provenance for memory writes
    on_memory: Callable | None = None,  # async (entry: dict) -> None
    remember: bool = True,    # False = a session the user asked not to be remembered
):
    """Assemble the audit agent: crawl/report tools plus optional mid-run questions."""
    tools = build_audit_tools(
        crawl_result,
        report_mode=report_mode,
        on_submit_report=on_submit_report,
        on_category_added=on_category_added,
    )
    # project_id arrives already membership-checked (routes/agents.py stamps it
    # on the session only after verifying the caller belongs to the project).
    # An unremembered session gets no memory tools: the agent cannot write what
    # it cannot reach.
    if remember:
        tools += build_memory_tools_lc(
            project_id,
            user_id=user_id,
            conversation_id=conversation_id,
            agent_type="audit_seo",
            on_memory=on_memory,
        )
    if session is not None and emit is not None:
        tools.append(build_ask_user_tool(session, session_id, emit))

    return create_agent(model=llm, tools=tools, system_prompt=system_prompt)


# ---------------------------------------------------------------------------
# Pipeline runner — drop-in for ClaudeAuditRunner
# ---------------------------------------------------------------------------

class LangChainAuditRunner:
    """Full SEO audit pipeline on the LangChain stack (V1 engine).

    Mirrors ``ClaudeAuditRunner.run_pipeline``'s signature so ``routes/audit.py``
    selects an engine and changes nothing else. V3 remains the default.

    Engine-neutral pieces are imported from the V3 module rather than copied:
    ``run_crawl`` is plain HTTP crawling and ``create_audit_session`` /
    ``get_session`` are the shared registry. Only synthesis differs.
    """

    def __init__(
        self,
        api_key: str,
        provider: Provider = Provider.ANTHROPIC,
        model: ModelName = ModelName.CLAUDE_SONNET,
        temperature: float = 1.0,
    ) -> None:
        self.provider = provider
        self.model = model
        self._api_key = api_key
        self._temperature = temperature

    async def run_pipeline(
        self,
        session_id: str,
        url: str,
        business_context: Any,
        emit: Callable,
        max_blog_posts: int = 5,
        crawl_depth: str = "deep",
        chat_idle_timeout: float = 1800.0,
        user_preferences: Any = None,
        report_mode: str = "freehand",
        template_id: str = "seo_v1",
        lead_magnet: bool = False,
        extra_context: str = "",
    ) -> Any:
        # Imported lazily: the V3 module pulls in claude_agent_sdk, and V1 should
        # not require it at import time once V3 is eventually retired.
        from agents.audit.events import AuditEvent as _E, AuditStep, STEP_LABELS
        from agents.audit.prompts import build_audit_user_prompt, build_unified_system_prompt
        from agents.audit.schema import AuditReport, CrawlDepth, StructuredAuditData
        from agents.audit.v3.runner import get_session, run_crawl

        session = get_session(session_id)
        if session:
            session.report_mode = report_mode
            session.template_id = template_id

        await emit({
            "event": _E.STEP_STARTED,
            "step_id": AuditStep.FETCH_SITEMAP,
            "label": STEP_LABELS[AuditStep.FETCH_SITEMAP],
            "status": "running",
        })
        crawl_result = await run_crawl(
            url,
            max_blog_posts=max_blog_posts,
            light=(crawl_depth == CrawlDepth.LIGHT),
            emit=emit,
        )
        await emit({
            "event": _E.STEP_FINISHED,
            "step_id": AuditStep.FETCH_SITEMAP,
            "label": STEP_LABELS[AuditStep.FETCH_SITEMAP],
            "status": "success",
        })

        report_holder: dict[str, Any] = {"report": None}

        async def _on_submit(args: dict) -> dict:
            """Validate and publish a report version.

            A validation failure is returned to the model, not raised — same
            contract as V3, so a malformed report is retried rather than fatal.
            """
            from datetime import datetime, timezone
            try:
                structured = StructuredAuditData.model_validate(args)
            except Exception as exc:  # noqa: BLE001 — reported back to the model
                return {
                    "status": "validation_error",
                    "message": f"Report validation failed — fix these issues and resubmit: {exc}",
                }
            # Scores, counts and crawl figures follow from the findings and the
            # crawl, never from the model's own tally (agents/audit/scoring.py).
            calibrate(structured, crawl_result)
            version_id = len(getattr(session, "report_versions", []) or []) + 1
            report = AuditReport(
                url=crawl_result.plan.root_url,
                generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                update_label="Initial audit" if version_id == 1 else f"Update {version_id}",
                executive_summary=" · ".join(structured.key_signals) if structured.key_signals else "",
                report_mode=report_mode,
                template_id=template_id,
                structured_data=structured,
            )
            report_holder["report"] = report
            await emit({
                "event": _E.ARTIFACT_VERSION,
                "version_id": version_id,
                "payload": report.model_dump(),
            })
            return {"status": "received", "version_id": version_id}

        llm = resolve_chat_model(self.provider, self.model, self._api_key, self._temperature)
        agent = build_audit_agent(
            crawl_result=crawl_result,
            llm=llm,
            system_prompt=build_unified_system_prompt(
                report_mode=report_mode, template_id=template_id
            ),
            session=session,
            session_id=session_id,
            emit=emit,
            report_mode=report_mode,
            on_submit_report=_on_submit,
        )

        await emit({
            "event": _E.STEP_STARTED,
            "step_id": AuditStep.SYNTHESIZE_AUDIT,
            "label": STEP_LABELS[AuditStep.SYNTHESIZE_AUDIT],
            "status": "running",
        })

        async def _on_artifact_close(raw: str, turn_text: str) -> None:
            """Freehand mode delivers the report inline rather than via tools."""
            import json as _json
            try:
                await _on_submit(_json.loads(raw))
            except Exception:  # noqa: BLE001 — a malformed inline payload is not fatal
                logger.warning("audit-v1: could not parse inline <duct_artifact> payload", exc_info=True)

        await stream_agent(
            agent,
            build_audit_user_prompt(crawl_result, business_context, extra_context=extra_context),
            emit,
            on_artifact_close=_on_artifact_close,
            log_prefix="audit-v1",
            provider=self.provider,
            model=self.model,
            conversation_id=session_id,
        )

        await emit({
            "event": _E.STEP_FINISHED,
            "step_id": AuditStep.SYNTHESIZE_AUDIT,
            "label": STEP_LABELS[AuditStep.SYNTHESIZE_AUDIT],
            "status": "success",
        })
        return report_holder["report"]
