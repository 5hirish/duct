"""Every agent graph gets the shared middleware stack, or a test fails.

The audit was built with a bare ``create_agent`` from 2026-08-16 to 09-27. Its
``RunLimits`` were declared and never enforced, Anthropic never cached its prefix, and a
provider outage mid-report had no fallback, because the middleware that does
all of that was mounted only by ``build_deep_session_agent``. Nothing failed:
a graph without middleware runs fine. These make it fail.
"""

from __future__ import annotations

import ast
import functools
import pathlib

from langchain.agents.middleware import (
    ContextEditingMiddleware,
    ModelCallLimitMiddleware,
    ToolCallLimitMiddleware,
)
from langchain_anthropic.middleware import AnthropicPromptCachingMiddleware

import agents.core.deep_session as deep_session
from agents.audit.schema import CrawlPlan, CrawlResult
from agents.audit.v1.runner import LIMITS, build_audit_agent
from agents.core.lc import ReportedRetryMiddleware
from tests.fakes import fake_llm

BACKEND = pathlib.Path(__file__).resolve().parent.parent
SOURCE_ROOTS = ("agents", "routes", "service", "models", "utils")
GRAPH_BUILDERS = ("create_agent", "create_deep_agent")

# The one module that assembles a session's graph, on either rung.
ASSEMBLY = "agents/core/deep_session.py"

# Bounded one-shot loops with a structured answer: no thread, no session, no
# chat. They may build their own graph, but must pass middleware (caching at
# least). A durable, multi-turn agent never belongs on this list: it goes
# through build_session_agent or build_deep_session_agent.
ONE_SHOT: dict[str, str] = {
    "agents/core/research.py": "the competitor and trending research passes",
}


@functools.cache
def _graph_builds() -> tuple[tuple[str, ast.Call], ...]:
    found = []
    for root in SOURCE_ROOTS:
        for path in (BACKEND / root).rglob("*.py"):
            rel = path.relative_to(BACKEND).as_posix()
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
                if name in GRAPH_BUILDERS:
                    found.append((rel, node))
    return tuple(found)


def test_session_graphs_are_built_by_the_shared_assembly():
    stray = [
        f"{rel}:{node.lineno}"
        for rel, node in _graph_builds()
        if rel != ASSEMBLY and rel not in ONE_SHOT
    ]
    assert not stray, (
        "build the agent with agents/core/deep_session.build_session_agent (create_agent "
        "rung) or build_deep_session_agent: they mount the limits, retry, fallback and "
        f"prompt caching a bare graph silently lacks. Found: {', '.join(stray)}"
    )


def test_one_shot_passes_mount_middleware():
    bare = [
        f"{rel}:{node.lineno}"
        for rel, node in _graph_builds()
        if rel in ONE_SHOT and not any(kw.arg == "middleware" for kw in node.keywords)
    ]
    assert not bare, (
        "a one-shot pass must pass middleware=agents.core.lc.prompt_caching_middleware() "
        f"at least, or Anthropic re-bills every fetched page on each call: {', '.join(bare)}"
    )


def test_one_shot_list_is_not_stale():
    builders = {rel for rel, _node in _graph_builds()}
    assert set(ONE_SHOT) <= builders, "ONE_SHOT names a module that no longer builds a graph"


def test_the_audit_graph_carries_the_shared_stack(monkeypatch):
    captured: dict = {}

    def capture(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(deep_session, "create_agent", capture)
    build_audit_agent(
        crawl_result=CrawlResult(plan=CrawlPlan(root_url="https://getduct.ai")),
        llm=fake_llm("ok"),
        system_prompt="audit",
    )

    middleware = captured["middleware"]
    kinds = {type(m) for m in middleware}
    assert {
        ContextEditingMiddleware,
        ModelCallLimitMiddleware,
        ToolCallLimitMiddleware,
        ReportedRetryMiddleware,
        AnthropicPromptCachingMiddleware,
    } <= kinds
    # The audit's own limits, not somebody else's.
    call_limit = next(m for m in middleware if isinstance(m, ModelCallLimitMiddleware))
    assert call_limit.run_limit == LIMITS.model_calls_per_run
    # Caching innermost, where deepagents puts it, so it marks the request a
    # fallback model actually sends.
    assert isinstance(middleware[-1], AnthropicPromptCachingMiddleware)
    assert captured["checkpointer"] is not None


def test_no_sub_agent_of_either_runner_carries_a_writer():
    """Enforced by which names are on each list, not by prompt. The harness's
    `general-purpose` default (every tool of the parent) is why both runners
    supply their own. Content's test said this for content; this says it for
    every deep runner, so the third one cannot forget."""
    from agents.content.schema import ContentTool
    from agents.content.subagents import (
        DRAFT_POST_TOOLS,
        GENERAL_PURPOSE_TOOLS as CONTENT_GP_TOOLS,
        RESEARCH_PILLAR_TOOLS,
        REVIEW_POST_TOOLS,
    )
    from agents.insights.subagents import GENERAL_PURPOSE_TOOLS as INSIGHTS_GP_TOOLS

    shared_writers = {
        "ProposeChanges", "RollbackChangeSet", "RememberFact", "CreateArtifact",
        "UpdateArtifact", "RewriteArtifact", "AskUserQuestion", "RequestConnection", "SelectAccount",
    }
    content_writers = {
        ContentTool.SUBMIT_PLAN.value, ContentTool.SUBMIT_POST_DRAFT.value, ContentTool.EDIT_SLIDE.value,
        ContentTool.GENERATE_IMAGE.value, ContentTool.EDIT_IMAGE.value, ContentTool.PUBLISH_POST.value,
        ContentTool.MARK_POSTED.value, ContentTool.RENDER_SLIDE.value, ContentTool.SUBMIT_ASSESSMENT.value,
    }
    for name, tools in (
        ("insights general-purpose", INSIGHTS_GP_TOOLS),
        ("content general-purpose", CONTENT_GP_TOOLS),
        ("content research_pillar", RESEARCH_PILLAR_TOOLS),
        ("content draft_post", DRAFT_POST_TOOLS),
        ("content review_post", REVIEW_POST_TOOLS),
    ):
        assert not (shared_writers | content_writers) & set(tools), name


def test_every_sub_agent_carries_the_loops_guards(monkeypatch, emitted):
    """Rulebook gap 5. A sub-agent ran with no guard at all: no call limits,
    so a looping verifier fetched until the parent's recursion ceiling, and
    no retry, so one 429 inside it ended the analyst's turn as a tool
    error. Each spec now mounts the loop's run limits, its reporting retry
    and the tool-error middleware."""
    from langchain.agents.middleware import (
        ModelCallLimitMiddleware,
        ToolCallLimitMiddleware,
        ToolErrorMiddleware,
    )

    import uuid

    from agents.content.v1.runner import ContentRunner, create_draft_session
    from agents.core.session import close_session
    from agents.insights.v1.runner import AutonomousInsightsRunner

    specs: list[dict] = []
    original = deep_session.build_deep_session_agent

    def _capture(**kwargs):
        specs.extend(kwargs.get("subagents") or [])
        return original(**kwargs)

    monkeypatch.setattr("agents.insights.v1.runner.build_deep_session_agent", _capture)
    monkeypatch.setattr("agents.content.v1.runner.build_deep_session_agent", _capture)
    AutonomousInsightsRunner(api_key="unused-no-network").build_agent(llm=fake_llm("ok"))
    # Content mounts its sub-agents only for a real session with a project.
    session = create_draft_session(str(uuid.uuid4()), uuid.uuid4())
    try:
        ContentRunner(api_key="unused").build_agent(
            llm=fake_llm("ok"), session=session, session_id=session.session_id,
            emit=emitted, project_id=session.project_id, mode=session.mode,
        )
    finally:
        close_session(session.session_id)

    assert {s["name"] for s in specs} >= {"verify", "general-purpose", "research_pillar", "draft_post", "review_post"}
    for spec in specs:
        kinds = {type(m) for m in spec.get("middleware", [])}
        assert {ModelCallLimitMiddleware, ToolCallLimitMiddleware, ToolErrorMiddleware, ReportedRetryMiddleware} <= kinds, spec["name"]


def test_the_loop_mounts_the_tool_error_middleware():
    from langchain.agents.middleware import ToolErrorMiddleware

    mounted = [m for m in deep_session.session_middleware(LIMITS) if isinstance(m, ToolErrorMiddleware)]
    assert len(mounted) == 1
