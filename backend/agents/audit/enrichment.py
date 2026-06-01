"""Context enrichment pre-flight for the SEO Audit Agent.

Runs between crawl and synthesis. Uses a Claude sub-agent (Haiku) with built-in
WebSearch and WebFetch tools to research competitors and extract content gaps.
Brand signals are extracted for free from the already-crawled pages.
"""

from __future__ import annotations

import logging
import os
from collections import Counter

from agents.audit.schema import (
    AuditBusinessContext,
    AuditResearchContext,
    CrawlResult,
)

logger = logging.getLogger(__name__)

_HAIKU_MODEL = "claude-haiku-4-5-20251001"

# Set AUDIT_VERBOSE_LOGGING=1 to log per-message SDK events and costs to terminal
_VERBOSE = os.environ.get("AUDIT_VERBOSE_LOGGING", "").lower() in ("1", "true")


# ---------------------------------------------------------------------------
# Brand signal extraction (from already-crawled data — no network cost)
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


# ---------------------------------------------------------------------------
# Sub-agent enrichment
# ---------------------------------------------------------------------------

async def enrich_context(
    root_url: str,
    business_context: AuditBusinessContext,
    crawl_result: CrawlResult,
    api_key: str,
    model: str = _HAIKU_MODEL,
    timeout: float = 90.0,
) -> AuditResearchContext | None:
    """Run a lightweight Claude sub-agent to research competitors and content gaps.

    Returns None if the sub-agent fails or returns no structured output — the
    caller should treat None as "no enrichment available" and proceed without it.
    """
    try:
        from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query
        from claude_agent_sdk import AssistantMessage
    except ImportError:
        logger.warning("enrichment: claude_agent_sdk not available; skipping")
        return None

    brand_pillars = _extract_brand_pillars(crawl_result)
    brand_schema_types = _extract_brand_schema_types(crawl_result)

    if business_context.competitors:
        competitors_hint = f"Competitors to research (fetch their homepages): {', '.join(business_context.competitors[:4])}"
    else:
        industry_hint = business_context.industry or business_context.business_description or root_url
        competitors_hint = f"Search the web to find the top 3 competitors for: {industry_hint}"

    prompt = f"""Research the SEO competitive landscape for {root_url}.
Business: {business_context.business_name or root_url}
{f"Industry: {business_context.industry}" if business_context.industry else ""}
{f"Description: {business_context.business_description}" if business_context.business_description else ""}

{competitors_hint}

For each competitor (max 4 total):
1. Fetch their homepage using WebFetch
2. Extract their main value proposition and target audience
3. Identify their top 3 content themes/pillars
4. Note 1–2 things they do better or differently versus {root_url}

Then identify 3–5 content gap topics: subjects competitors clearly cover that {root_url} likely does not.

Write 2–3 enrichment notes: short, coach-style observations about competitive opportunity.

Brand signals already extracted from the target site's crawl (do NOT re-research these):
- content_pillars: {brand_pillars}
- schema_types: {brand_schema_types}

Be concise. Each field should be a short string or short list item, not a paragraph."""

    env: dict[str, str] = {"ENABLE_PROMPT_CACHING_1H": "1"}
    if api_key:
        env["ANTHROPIC_API_KEY"] = api_key

    options = ClaudeAgentOptions(
        model=model,
        allowed_tools=["WebSearch", "WebFetch"],
        permission_mode="bypassPermissions",
        max_turns=10,
        env=env,
        setting_sources=[],
        output_format={
            "type": "json_schema",
            "schema": AuditResearchContext.model_json_schema(),
        },
    )

    async def _run() -> AuditResearchContext | None:
        async for message in query(prompt=prompt, options=options):
            if _VERBOSE:
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if hasattr(block, "name"):
                            logger.info("enrichment [tool_use]: %s", block.name)
                        elif hasattr(block, "text") and block.text:
                            logger.info("enrichment [text]: %s", block.text[:120].replace("\n", " "))

            if isinstance(message, ResultMessage):
                cost = message.total_cost_usd or 0
                if message.is_error:
                    logger.warning(
                        "enrichment: result is_error=True subtype=%s cost=$%.4f",
                        message.subtype, cost,
                    )
                    return None
                if message.structured_output:
                    logger.info("enrichment: success cost=$%.4f", cost)
                    context = AuditResearchContext.model_validate(message.structured_output)
                    if not context.brand_content_pillars:
                        context.brand_content_pillars = brand_pillars
                    if not context.brand_schema_types:
                        context.brand_schema_types = brand_schema_types
                    logger.info(
                        "enrichment: got %d competitors, %d content gaps",
                        len(context.competitors),
                        len(context.content_gaps),
                    )
                    return context
                logger.warning(
                    "enrichment: result ok but no structured_output subtype=%s cost=$%.4f",
                    message.subtype, cost,
                )
        return None

    try:
        import asyncio
        result = await asyncio.wait_for(_run(), timeout=timeout)
        if result is not None:
            return result
    except TimeoutError:
        logger.warning("enrichment: sub-agent timed out after %.0fs; using local signals only", timeout)
    except Exception as exc:
        logger.warning("enrichment: sub-agent failed (%s); using local signals only", exc)

    # Return a minimal context with just the locally-extracted brand signals
    return AuditResearchContext(
        brand_content_pillars=brand_pillars,
        brand_schema_types=brand_schema_types,
    )
