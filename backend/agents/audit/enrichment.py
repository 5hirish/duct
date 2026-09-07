"""Context enrichment pre-flight for the SEO Audit Agent.

Runs between crawl and synthesis: research the competitive landscape so the
report can say something about *this* market rather than this site alone.
Brand signals come free from the pages already crawled; only the competitor
research costs a call.

Ported from a Claude sub-agent to ``create_agent`` so it runs on whichever
model the customer brought, the same way ``agents/content/enrichment.py`` does.
A whole class of hazard left with the subprocess: no CLI, so no config-dir
contention, no NODE_OPTIONS injection to neutralise, and no default Bash tool
one prompt injection away from ``backend/.env``. The remaining posture is the
one that matters — this pass carries web tools and nothing else. Its prompt
interpolates H2 text scraped off the site under audit, and its results are
competitor pages: both attacker-authored, and neither can reach a session, a
key or a writer from here.
"""

from __future__ import annotations

import asyncio
import logging
from collections import Counter
from typing import Any

from agents.audit.schema import (
    AuditBusinessContext,
    AuditResearchContext,
    CrawlResult,
    EnrichmentOutput,
)
from agents.core.web_tools import build_web_tools_lc, web_search_available
from agents.models import ModelName, Provider

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 150.0
# Three competitor fetches, the searches that find them, and the structured
# answer. Derived rather than picked: this graph is create_agent + ToolStrategy,
# which costs 2 supersteps per model call, not the 7 an assembled deep agent does.
_RESEARCH_MAX_MODEL_CALLS = 16
_RESEARCH_SUPERSTEPS_PER_MODEL_CALL = 2
_RESEARCH_RECURSION_LIMIT = _RESEARCH_MAX_MODEL_CALLS * _RESEARCH_SUPERSTEPS_PER_MODEL_CALL + 4


# ---------------------------------------------------------------------------
# Brand signals — from the crawl, so free and deterministic
# ---------------------------------------------------------------------------

def _extract_brand_pillars(crawl_result: CrawlResult, top_n: int = 5) -> list[str]:
    """Cluster H2 headings from all crawled pages into top content themes."""
    counter: Counter[str] = Counter()
    for page in crawl_result.pages:
        for h2 in page.h2s:
            cleaned = h2.strip()
            if cleaned and len(cleaned) > 3:
                counter[cleaned] += 1
    return [h2 for h2, _ in counter.most_common(top_n)]


def _extract_brand_schema_types(crawl_result: CrawlResult) -> list[str]:
    seen: set[str] = set()
    for page in crawl_result.pages:
        seen.update(page.schema_types)
    return sorted(seen)


def _local_signals(crawl_result: CrawlResult) -> AuditResearchContext:
    return AuditResearchContext(
        brand_content_pillars=_extract_brand_pillars(crawl_result),
        brand_schema_types=_extract_brand_schema_types(crawl_result),
    )


def _degraded(base: AuditResearchContext, why: str) -> AuditResearchContext:
    """Local signals only, and the reason it stayed that way.

    The reason goes on ``degraded_reason`` — for the step chip and the log,
    never the prompt. ``enrichment_notes`` is rendered to the model, and an
    internal error string there reads to it as an observation about the site.
    """
    return base.model_copy(update={"degraded_reason": f"local signals only: {why}"})


def _build_research_prompt(
    root_url: str, business_context: AuditBusinessContext, base: AuditResearchContext
) -> str:
    if business_context.competitors:
        competitors_hint = (
            "Competitors to research (fetch their homepages): "
            + ", ".join(business_context.competitors[:3])
        )
    else:
        industry_hint = (
            business_context.industry or business_context.business_description or root_url
        )
        competitors_hint = f"Search the web to find the top 3 competitors for: {industry_hint}"

    return f"""Research the SEO competitive landscape for {root_url}.
Business: {business_context.business_name or root_url}
{f"Industry: {business_context.industry}" if business_context.industry else ""}
{f"Description: {business_context.business_description}" if business_context.business_description else ""}

{competitors_hint}

For each competitor (max 3 total):
1. Fetch their homepage
2. Extract their main value proposition and target audience
3. Identify their top 3 content themes/pillars
4. Note 1–2 things they do better or differently versus {root_url}

Then identify 3–5 content gap topics: subjects competitors clearly cover that \
{root_url} likely does not.

Write 2–3 enrichment notes: short, coach-style observations about competitive opportunity.

Brand signals already extracted from the target site's crawl (do NOT re-research these):
- content_pillars: {base.brand_content_pillars}
- schema_types: {base.brand_schema_types}

Be concise. Each field should be a short string or short list item, not a paragraph."""


async def _research(prompt: str, llm: Any, web_tools: list[Any]) -> EnrichmentOutput | None:
    """One bounded agent loop: search, fetch, then the structured answer.

    ``ToolStrategy`` makes ``create_agent`` force ``tool_choice``, which is why
    this pass can only carry tools it fully controls — see the note in
    ``agents/content/enrichment.py`` for the two providers that push back on
    that and degrade to local signals through the caller's except.
    """
    from langchain.agents import create_agent
    from langchain.agents.structured_output import ToolStrategy

    agent = create_agent(
        model=llm,
        # No session, no keys, no writers: the open web is attacker-authored by
        # construction, and the only thing an injected instruction can reach
        # from here is another page.
        tools=list(web_tools),
        response_format=ToolStrategy(EnrichmentOutput),
    )
    result = await agent.ainvoke(
        {"messages": [{"role": "user", "content": prompt}]},
        {"recursion_limit": _RESEARCH_RECURSION_LIMIT},
    )
    found = result.get("structured_response") if isinstance(result, dict) else None
    return found if isinstance(found, EnrichmentOutput) else None


async def enrich_context(
    root_url: str,
    business_context: AuditBusinessContext,
    crawl_result: CrawlResult,
    api_key: str,
    *,
    provider: Provider = Provider.ANTHROPIC,
    model: ModelName | str = ModelName.CLAUDE_HAIKU,
    llm: Any = None,
    timeout: float = _DEFAULT_TIMEOUT,
    gemini_api_key: str = "",
) -> AuditResearchContext:
    """Research the competitive landscape, layered on the crawl's own signals.

    Always returns a context: on failure, timeout, or a provider with no web
    search, the brand signals come through unchanged and ``degraded_reason``
    says why nothing was added. ``llm`` lets a caller (or a test) hand in the
    model instead of resolving one.
    """
    base = _local_signals(crawl_result)

    if not api_key and llm is None:
        logger.info("enrichment: no api_key; returning local signals only")
        return base

    if not web_search_available(provider, model, gemini_api_key):
        logger.info(
            "enrichment: no web search available on %s; local signals only",
            getattr(provider, "value", provider),
        )
        return _degraded(base, "no web search available for this provider")

    web_tools = build_web_tools_lc(provider, model, gemini_api_key)

    if llm is None:
        from agents.core.lc import resolve_chat_model

        llm = resolve_chat_model(provider, model, api_key)

    prompt = _build_research_prompt(root_url, business_context, base)
    try:
        found = await asyncio.wait_for(_research(prompt, llm, web_tools), timeout=timeout)
    except asyncio.TimeoutError:
        logger.warning("enrichment: research pass timed out after %.0fs; local signals only", timeout)
        return _degraded(base, f"research pass timed out after {timeout:.0f}s")
    except Exception as exc:  # noqa: BLE001 — enrichment must never fail a run
        logger.warning("enrichment: research pass failed (%s); local signals only", exc)
        return _degraded(base, f"research pass failed: {str(exc)[:160]}")

    if found is None:
        logger.warning("enrichment: research pass returned no structured result; local signals only")
        return _degraded(base, "research pass returned no structured result")

    if not found.competitors and not found.content_gaps and not found.enrichment_notes:
        logger.warning("enrichment: research pass came back empty")
        return _degraded(base, "research pass found nothing")

    logger.info(
        "enrichment: %d competitors, %d content gaps",
        len(found.competitors), len(found.content_gaps),
    )
    return AuditResearchContext(
        # Brand signals stay the crawl's — deterministic, and the prompt told
        # the model not to research them.
        brand_content_pillars=base.brand_content_pillars,
        brand_schema_types=base.brand_schema_types,
        competitors=found.competitors,
        content_gaps=found.content_gaps,
        enrichment_notes=found.enrichment_notes,
    )


__all__ = ["enrich_context"]
