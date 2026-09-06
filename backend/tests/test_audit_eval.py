"""Live audit eval — score a real audit against the audit rubric, per model.

Answers the two questions that gate the migration
(the engine consolidation review (duct-cloud, private) §6.6, §9.4a):

  1. **Which models may we offer customers?** BYO-key means a weak model
     produces a bad audit that gets blamed on Duct. Run this per candidate and
     admit only the models that pass.
  2. **Is the audit still worth shipping?** Same rubric, same site, run before
     a change that could move it.

Marked ``live``: it crawls a real site and spends real tokens, so it is excluded
from the default suite. Run it explicitly:

    # the default provider
    poetry run pytest tests/test_audit_eval.py -m live

    # a candidate model
    DUCT_EVAL_PROVIDER=google_genai \\
    DUCT_EVAL_MODEL=gemini-3.8-flash \\
    DUCT_EVAL_OUTPUT=scorecard-gemini.json \\
    poetry run pytest tests/test_audit_eval.py -m live

Needs the provider's key in the environment, plus GEMINI_API_KEY for the judge
(see tests/eval/client.py). Point DUCT_EVAL_URL at a site you own.
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from pathlib import Path

import pytest

from agents.audit.schema import AuditBusinessContext
from agents.engines import Engine, resolve_engine, resolve_engine_model, resolve_engine_provider
from tests.eval.assertions import assert_scorecard
from tests.eval.judge import evaluate
from tests.eval.rubrics.audit_report import audit_report_rubric, render_audit_artifact

# Duct's own site by default — safe to crawl, and we know what "good" looks like.
DEFAULT_URL = "https://getduct.ai"

# Long enough that a slow last tool call still lands, short enough that the
# eval is not waiting on a conversation nobody is having.
_CHAT_IDLE_TIMEOUT = 5.0


def _emit_scorecard(scorecard, label: str) -> None:
    """Write the scorecard to disk and echo it, mirroring the content eval."""
    out_path = os.environ.get("DUCT_EVAL_OUTPUT", "audit-eval-scorecard.json")
    payload = scorecard.as_dict()
    payload["run_label"] = label
    try:
        Path(out_path).write_text(json.dumps(payload, indent=2))
    except Exception:
        pass
    markdown = scorecard.as_markdown()
    print(f"\n### {label}\n{markdown}\n")
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        try:
            with open(summary, "a", encoding="utf-8") as fh:
                fh.write(f"\n\n### {label}\n{markdown}\n")
        except Exception:
            pass


def _resolve_run_config() -> tuple[Engine, object, object, str]:
    """Engine / provider / model for this run, from DUCT_EVAL_* env vars."""
    from config import get_configs
    from agents.engines import PROVIDER_CONFIG_ATTR

    engine = resolve_engine(os.environ.get("DUCT_EVAL_ENGINE") or "v1")
    provider = resolve_engine_provider(engine, os.environ.get("DUCT_EVAL_PROVIDER"))
    model = resolve_engine_model(engine, provider, os.environ.get("DUCT_EVAL_MODEL"))
    api_key = os.environ.get("DUCT_EVAL_API_KEY") or getattr(
        get_configs(), PROVIDER_CONFIG_ATTR[provider], ""
    )
    return engine, provider, model, api_key


def _gemini_key() -> str:
    """The Gemini key Duct's own WebSearch runs on."""
    from config import get_configs

    return (
        os.environ.get("GEMINI_API_KEY", "")
        or os.environ.get("GOOGLE_API_KEY", "")
        or getattr(get_configs(), "gemini_api_key", "")
    ).strip()


@pytest.mark.live
def test_audit_report_passes_rubric():
    """Run one real audit and gate the report on the audit rubric.

    The scorecard is the deliverable — a failure here is a signal about the
    model or engine under test, not necessarily a broken build. Compare
    scorecards across runs rather than reading any single one in isolation.
    """
    engine, provider, model, api_key = _resolve_run_config()
    if not api_key:
        pytest.skip(f"no API key configured for provider '{provider.value}'")

    url = os.environ.get("DUCT_EVAL_URL", DEFAULT_URL)
    label = f"{engine.value} · {provider.value} · {model.value} · {url}"

    from agents.audit.v1.runner import LangChainAuditRunner as Runner

    from agents.audit.crawl import create_audit_session
    from agents.core.session import close_session

    session_id = str(uuid.uuid4())
    create_audit_session(session_id)
    events: list[dict] = []

    async def emit(event: dict) -> None:
        events.append(event)

    async def _run():
        # gemini_api_key backs the research pass's WebSearch off Anthropic;
        # without it the eval would grade a report that never saw a competitor.
        runner = Runner(
            api_key=api_key, provider=provider, model=model, gemini_api_key=_gemini_key(),
        )
        return await runner.run_pipeline(
            session_id=session_id,
            url=url,
            business_context=AuditBusinessContext(
                business_name="Duct",
                business_description="AI-powered SEO audit and organic growth intelligence",
                business_goals="Rank for SEO audit and organic growth keywords",
            ),
            emit=emit,
            max_blog_posts=3,
            report_mode="template",
            # The run stays open for follow-up chat once the report lands, and
            # this harness never sends one. Without a short idle timeout the
            # eval would sit in the chat loop for the full 30 minutes.
            chat_idle_timeout=_CHAT_IDLE_TIMEOUT,
        )

    try:
        report = asyncio.run(_run())
    finally:
        close_session(session_id)

    assert report is not None, (
        f"{label}: the agent produced no report. Emitted events: "
        f"{[e.get('event') for e in events]}"
    )

    scorecard = evaluate(audit_report_rubric(), render_audit_artifact(report))
    _emit_scorecard(scorecard, label)
    assert_scorecard(scorecard)
