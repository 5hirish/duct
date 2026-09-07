"""The audit's competitor research, on whichever model the customer brought.

This pass was a Claude sub-agent, which is why a Gemini or OpenAI audit simply
had no competitive context. The port is the content pass's shape: one bounded
create_agent loop with web tools and a structured answer, and a context that
always comes back — degraded, with a reason, rather than missing.

No network: the research call is replaced at its seam.
"""

from __future__ import annotations

import asyncio

import pytest

import agents.audit.enrichment as enrichment
from agents.audit.enrichment import enrich_context
from agents.audit.schema import (
    AuditBusinessContext,
    CompetitorSignals,
    CrawlPlan,
    CrawlResult,
    EnrichmentOutput,
    PageSignals,
)
from agents.models import Provider

URL = "https://getduct.ai"


def _crawl() -> CrawlResult:
    return CrawlResult(
        plan=CrawlPlan(root_url=URL),
        pages=[
            PageSignals(
                url=URL, h2s=["Organic growth", "SEO audits", "Organic growth"],
                schema_types=["SoftwareApplication"],
            ),
            PageSignals(url=f"{URL}/pricing", h2s=["Organic growth"], schema_types=["WebPage"]),
        ],
    )


def _context() -> AuditBusinessContext:
    return AuditBusinessContext(business_name="Duct", industry="SEO tooling")


@pytest.fixture
def searchable(monkeypatch):
    """A provider that has web search, with the tools stubbed out."""
    monkeypatch.setattr(enrichment, "web_search_available", lambda *_a, **_k: True)
    monkeypatch.setattr(enrichment, "build_web_tools_lc", lambda *_a, **_k: [])


async def _enrich(**over):
    return await enrich_context(
        URL, _context(), _crawl(), api_key="k", llm=object(),
        provider=Provider.GOOGLE_GENAI, **over,
    )


# ---------------------------------------------------------------------------
# Brand signals come from the crawl, free and deterministic
# ---------------------------------------------------------------------------

async def test_brand_signals_come_from_the_crawl_not_the_model(monkeypatch):
    monkeypatch.setattr(enrichment, "web_search_available", lambda *_a, **_k: False)

    result = await _enrich()

    assert result.brand_content_pillars[0] == "Organic growth", "the most repeated H2 leads"
    assert result.brand_schema_types == ["SoftwareApplication", "WebPage"]


# ---------------------------------------------------------------------------
# A research pass that worked
# ---------------------------------------------------------------------------

async def test_findings_layer_on_top_of_the_crawls_own_signals(searchable, monkeypatch):
    found = EnrichmentOutput(
        competitors=[CompetitorSignals(domain="ahrefs.com", positioning="the incumbent")],
        content_gaps=["programmatic SEO"],
        enrichment_notes=["they own the glossary long tail"],
    )

    async def _research(_prompt, _llm, _tools):
        return found

    monkeypatch.setattr(enrichment, "_research", _research)

    result = await _enrich()

    assert [c.domain for c in result.competitors] == ["ahrefs.com"]
    assert result.content_gaps == ["programmatic SEO"]
    assert result.brand_content_pillars, "crawl signals survive the merge"
    assert result.degraded_reason == ""


# ---------------------------------------------------------------------------
# Every way it can fail returns a context, and says why
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "outcome, expected",
    [
        ("timeout", "timed out"),
        ("raises", "research pass failed"),
        ("none", "no structured result"),
        ("empty", "found nothing"),
    ],
)
async def test_a_failed_pass_degrades_with_a_reason(searchable, monkeypatch, outcome, expected):
    async def _research(_prompt, _llm, _tools):
        if outcome == "timeout":
            await asyncio.sleep(9)
        if outcome == "raises":
            raise RuntimeError("provider refused tool_choice")
        if outcome == "none":
            return None
        return EnrichmentOutput()

    monkeypatch.setattr(enrichment, "_research", _research)

    result = await _enrich(timeout=0.05)

    assert expected in result.degraded_reason
    assert result.brand_content_pillars, "the crawl's signals still come through"
    assert result.competitors == []


async def test_a_provider_without_web_search_says_so(monkeypatch):
    monkeypatch.setattr(enrichment, "web_search_available", lambda *_a, **_k: False)

    result = await _enrich()

    assert "no web search available" in result.degraded_reason


async def test_no_key_and_no_model_is_not_a_degradation(monkeypatch):
    """Nothing was attempted, so there is nothing to explain."""
    result = await enrich_context(URL, _context(), _crawl(), api_key="")

    assert result.degraded_reason == ""
    assert result.brand_content_pillars


# ---------------------------------------------------------------------------
# The reason never reaches the model
# ---------------------------------------------------------------------------

async def test_the_degraded_reason_stays_out_of_the_prompt(searchable, monkeypatch):
    """enrichment_notes is rendered into the audit prompt; an internal error
    string there reads to the model as an observation about the site."""
    from agents.audit.prompts import build_audit_user_prompt

    async def _research(_prompt, _llm, _tools):
        raise RuntimeError("provider refused tool_choice")

    monkeypatch.setattr(enrichment, "_research", _research)
    result = await _enrich()

    prompt = build_audit_user_prompt(_crawl(), _context(), research_context=result)

    assert "provider refused tool_choice" not in prompt
    assert "local signals only" not in prompt
