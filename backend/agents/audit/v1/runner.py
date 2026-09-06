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
from agents.core.artifact_tools import build_artifact_tools_lc
from agents.core.events import AgentEvent
from agents.core.checkpoint import get_checkpointer
from agents.core.deep_session import DeepSession, RunLimits
from agents.core.lc import build_ask_user_tool, resolve_chat_model
from agents.core.memory_tools import build_memory_tools_lc
from agents.core.session import BaseAgentSession
from agents.tools.execution_tools import build_execution_tools_lc
from agents.models import ModelName, Provider
from service.crawl.fetcher import SiteUnreachableError

logger = logging.getLogger(__name__)


def _record_version(session: Any, report: Any, version_id: int) -> None:
    """Keep the session's version list in step with what was published.

    The next version's number is read off this list, so a session that never
    records one numbers every revision 1 — invisible until V1 could revise a
    report at all, which it now can. It is also what the route rehydrates on
    resume and what the UI's version picker reads.
    """
    if session is None:
        return
    from agents.audit.schema import VersionedReport

    session.report_versions.append(VersionedReport(
        version_id=version_id,
        label=report.update_label,
        report=report,
        created_at=report.generated_at,
    ))

# One audit is a long single turn (nine categories, a tool call each) followed
# by short chat turns. The recursion ceiling derives from the model-call guard
# rather than being picked by hand — see RunLimits.
LIMITS = RunLimits(
    model_calls_per_run=40,
    model_calls_per_thread=200,
    tool_calls_per_run=60,
    tool_calls_per_thread=300,
    tool_result_prune_trigger=40,
    tool_results_kept=12,
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
    project_id=None,          # UUID | None — mounts the memory tools when set
    user_id=None,             # UUID | None — attribution for memory writes
    conversation_id=None,     # UUID | None — provenance for memory writes
    on_memory: Callable | None = None,      # async (entry: dict) -> None
    on_artifact: Callable | None = None,    # async (card: dict) -> None
    on_change_set: Callable | None = None,  # async (change_set: dict) -> None
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
    # The project library and the staged-execution tools: both no-op without a
    # membership-checked project, so an ephemeral or lead-magnet run mounts
    # neither and the same call is safe on every path.
    tools += build_artifact_tools_lc(
        project_id,
        user_id=user_id,
        conversation_id=conversation_id,
        agent_type="audit_seo",
        on_artifact=on_artifact,
    )
    tools += build_execution_tools_lc(
        user_id=user_id,
        project_id=project_id,
        conversation_id=conversation_id,
        agent_type="audit_seo",
        on_change_set=on_change_set,
        log_prefix="audit-v1",
    )
    if session is not None and emit is not None:
        tools.append(build_ask_user_tool(session, session_id, emit))

    # Checkpointed: without a saver the graph has no memory between turns, so
    # follow-up chat would re-ask the model to audit a site it just audited,
    # and a resumed conversation would start blank beside its own transcript.
    return create_agent(
        model=llm,
        tools=tools,
        system_prompt=system_prompt,
        checkpointer=get_checkpointer(),
    )


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
        gemini_api_key: str = "",
    ) -> None:
        self.provider = provider
        self.model = model
        self._api_key = api_key
        self._temperature = temperature
        # Backs Duct's own WebSearch when the run's provider has no usable
        # built-in one; without it the research pass degrades to local signals.
        self._gemini_api_key = gemini_api_key

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
        # Imported lazily only to keep the module import graph shallow; nothing
        # here pulls in another engine.
        from agents.audit.events import AuditEvent as _E, AuditStep, STEP_LABELS, StepStatus
        from agents.audit.prompts import build_audit_user_prompt, build_unified_system_prompt
        from agents.audit.schema import AuditReport, CrawlDepth, StructuredAuditData
        from agents.audit.crawl import run_crawl
        from agents.core.session import get_session

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
        try:
            crawl_result = await run_crawl(
                url,
                max_blog_posts=max_blog_posts,
                light=(crawl_depth == CrawlDepth.LIGHT),
                emit=emit,
            )
        except SiteUnreachableError as exc:
            # The step closes as an error so the UI stops spinning; the route
            # turns the raise into PIPELINE_FAILED with this message.
            await emit({
                "event": _E.STEP_FINISHED,
                "step_id": AuditStep.FETCH_SITEMAP,
                "label": STEP_LABELS[AuditStep.FETCH_SITEMAP],
                "status": StepStatus.ERROR,
                "error": str(exc),
            })
            raise
        await emit({
            "event": _E.STEP_FINISHED,
            "step_id": AuditStep.FETCH_SITEMAP,
            "label": STEP_LABELS[AuditStep.FETCH_SITEMAP],
            "status": "success",
        })

        # Research the competitive landscape before synthesis. Skipped for the
        # lead-magnet teaser (it must stay fast) and when there is no business
        # context at all, which leaves the pass nothing to look for.
        # One model for the whole run: synthesis and the research pass share it,
        # so a test's fake reaches both and production builds one client.
        llm = resolve_chat_model(self.provider, self.model, self._api_key, self._temperature)

        research_context = None
        wants_research = not lead_magnet and bool(
            business_context.competitors
            or business_context.industry
            or business_context.business_description
            or business_context.business_name
        )
        if wants_research:
            from agents.audit.enrichment import enrich_context

            await emit({
                "event": _E.STEP_STARTED,
                "step_id": AuditStep.ENRICHING,
                "label": STEP_LABELS[AuditStep.ENRICHING],
                "status": StepStatus.RUNNING,
            })
            research_context = await enrich_context(
                root_url=url,
                business_context=business_context,
                crawl_result=crawl_result,
                api_key=self._api_key,
                provider=self.provider,
                model=self.model,
                llm=llm,
                gemini_api_key=self._gemini_api_key,
            )
            await emit({
                "event": _E.STEP_FINISHED,
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
                        for c in research_context.competitors
                    ],
                    "content_gaps":     research_context.content_gaps,
                    "enrichment_notes": research_context.enrichment_notes,
                    # Why it found nothing, when it found nothing. On the chip
                    # and in the log; never in the prompt.
                    "degraded_reason":  research_context.degraded_reason,
                },
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
            _record_version(session, report, version_id)
            await emit({
                "event": _E.ARTIFACT_VERSION,
                "version_id": version_id,
                "payload": report.model_dump(),
            })
            return {"status": "received", "version_id": version_id}

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
            **self._project_wiring(session, emit),
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

        loop = self._session_loop(
            agent, llm, session, emit, session_id,
            on_artifact_close=_on_artifact_close,
            # PIPELINE_FINISHED is the route's to emit once it has the report in
            # hand; DeepSession would otherwise send it as soon as synthesis
            # ends, and the UI would leave "working" before the report exists.
            announce_finish=False,
        )
        await loop.turn(
            build_audit_user_prompt(
                crawl_result,
                business_context,
                research_context=research_context,
                extra_context=extra_context,
            )
        )

        await emit({
            "event": _E.STEP_FINISHED,
            "step_id": AuditStep.SYNTHESIZE_AUDIT,
            "label": STEP_LABELS[AuditStep.SYNTHESIZE_AUDIT],
            "status": "success",
        })
        # Synthesis is over; the session stays open for follow-up questions on
        # the same thread until the user goes quiet. Without this the audit
        # answered once and every later message hit a closed session.
        if report_holder["report"] is not None:
            await emit({"event": _E.PIPELINE_FINISHED, "status": StepStatus.SUCCESS})
            await loop.chat_loop(chat_idle_timeout)
        return report_holder["report"]

    def _session_loop(
        self,
        agent: Any,
        llm: Any,
        session: Any,
        emit: Callable,
        session_id: str,
        *,
        on_artifact_close: Callable,
        announce_finish: bool,
    ) -> DeepSession:
        """The audit's window onto its durable thread.

        Everything multi-turn — the chat loop, a resumed thread's parked
        question, one emergency compaction when the request outgrows the
        window — is DeepSession's, shared with content and insights. The audit
        used to have none of it: its runner streamed one turn and returned.
        """
        loop = DeepSession(
            agent,
            session=session,
            emit=emit,
            thread_id=session_id,
            limits=LIMITS,
            provider=self.provider,
            model=self.model,
            log_prefix="audit-v1",
            summariser=llm,
            on_artifact_close=on_artifact_close,
        )
        loop.opened = not announce_finish
        return loop

    def _project_wiring(self, session: Any, emit: Callable) -> dict:
        """Project-scoped tool wiring, read off the session.

        routes/agents.py stamps artifact_project_id only after verifying
        membership, so its presence *is* the authorisation: no project means an
        ephemeral or lead-magnet run, and every binder below returns nothing.
        """
        project_id = getattr(session, "artifact_project_id", None)
        remember = project_id is not None and not getattr(session, "memory_off", False)

        async def on_memory(entry: dict) -> None:
            # The quiet "Remembered: …" line under the turn, with undo.
            await emit({"event": AgentEvent.MEMORY_WRITTEN, "memory": entry})

        async def on_artifact(card: dict) -> None:
            # A compact chip in chat that opens the artifact viewer.
            await emit({"event": AgentEvent.ARTIFACT_UPDATED, "artifact": card})

        async def on_change_set(card: dict) -> None:
            # Change-set card in chat; the UI upserts by change_set_id.
            await emit({"event": AgentEvent.EXECUTION_PROPOSED, "change_set": card})

        return {
            "project_id": project_id,
            "user_id": getattr(session, "user_id", None),
            "conversation_id": getattr(session, "conversation_id", None),
            "remember": remember,
            "on_memory": on_memory,
            "on_artifact": on_artifact,
            "on_change_set": on_change_set,
        }

    async def run_resume(
        self,
        session_id: str,
        url: str,
        emit: Callable,
        chat_idle_timeout: float = 1800.0,
        user_preferences: Any = None,
        report_mode: str = "freehand",
        template_id: str = "seo_v1",
    ) -> None:
        """Continue a persisted audit conversation — chat only, no re-crawl.

        The caller (routes/agents.py) rehydrates the report versions from the
        artifact store and sets the resume primer before calling. The crawl
        stub carries only root_url, which is all FetchPages' same-origin check
        and the working-report context need.
        """
        from agents.audit.crawl import run_crawl  # noqa: F401 — kept symmetric with run_pipeline
        from agents.audit.events import AuditEvent as _E, StepStatus
        from agents.audit.prompts import build_unified_system_prompt
        from agents.audit.schema import AuditReport, CrawlPlan, StructuredAuditData
        from agents.core.session import get_session

        session = get_session(session_id)
        if session:
            session.report_mode = report_mode
            session.template_id = template_id
        crawl_result = CrawlResult(plan=CrawlPlan(root_url=url))

        async def _on_submit(args: dict) -> dict:
            """A revision published during chat — a new numbered version."""
            from datetime import datetime, timezone
            try:
                structured = StructuredAuditData.model_validate(args)
            except Exception as exc:  # noqa: BLE001 — reported back to the model
                return {
                    "status": "validation_error",
                    "message": f"Report validation failed — fix these issues and resubmit: {exc}",
                }
            calibrate(structured, crawl_result)
            version_id = len(getattr(session, "report_versions", []) or []) + 1
            report = AuditReport(
                url=url,
                generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                update_label=f"Update {version_id}",
                executive_summary=" · ".join(structured.key_signals) if structured.key_signals else "",
                report_mode=report_mode,
                template_id=template_id,
                structured_data=structured,
            )
            _record_version(session, report, version_id)
            await emit({
                "event": _E.ARTIFACT_VERSION,
                "version_id": version_id,
                "payload": report.model_dump(),
            })
            return {"status": "received", "version_id": version_id}

        async def _on_artifact_close(raw: str, turn_text: str) -> None:
            import json as _json
            try:
                await _on_submit(_json.loads(raw))
            except Exception:  # noqa: BLE001 — a malformed inline payload is not fatal
                logger.warning("audit-v1: could not parse inline <duct_artifact> payload", exc_info=True)

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
            **self._project_wiring(session, emit),
        )
        loop = self._session_loop(
            agent, llm, session, emit, session_id,
            on_artifact_close=_on_artifact_close,
            announce_finish=True,
        )
        # resume=True: a thread parked on a question re-raises it, one cut
        # mid-run continues from its checkpoint, an idle one just waits.
        await loop.open("", resume=True)
        await emit({"event": _E.PIPELINE_FINISHED, "status": StepStatus.SUCCESS})
        await loop.chat_loop(chat_idle_timeout)
