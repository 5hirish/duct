"""Integration tests for the SEO audit pipeline.

Three levels of coverage:

  test_crawl_real_page
    Crawls a real public URL (getduct.ai) with no Claude involved.
    Verifies the crawl layer works end-to-end: HTTP fetch, sitemap discovery,
    HTML parsing, PageSignals extraction.
    Skipped when network is unavailable.

  test_run_synthesis_catches_planted_issues
    No network crawl. Uses a local HTML fixture with 5 deliberately planted
    SEO issues and calls run_synthesis() with a real ClaudeSDKClient.
    Verifies the synthesis layer catches each known issue.
    Requires ANTHROPIC_API_KEY.

  test_full_pipeline_real_page
    Full end-to-end: real crawl of getduct.ai + real Claude synthesis.
    The only test that exercises both layers together.
    Requires ANTHROPIC_API_KEY and network access to getduct.ai.
"""

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_HAS_API_KEY = bool(os.environ.get("ANTHROPIC_API_KEY"))
_AUDIT_URL = "https://getduct.ai"


def _network_available(url: str = _AUDIT_URL) -> bool:
    """Quick TCP check — returns False if the host is unreachable."""
    import socket
    from urllib.parse import urlparse
    p = urlparse(url)
    host = p.hostname or ""
    port = p.port or (443 if p.scheme == "https" else 80)
    try:
        socket.setdefaulttimeout(3)
        socket.create_connection((host, port)).close()
        return True
    except OSError:
        return False


_HAS_NETWORK = _network_available()

# ---------------------------------------------------------------------------
# Fixture — SaaS homepage with 5 planted SEO issues (no network needed)
# ---------------------------------------------------------------------------

_FIXTURE_URL = "https://acme-test-fixture.io/"

_FIXTURE_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Acme CRM — The Best Customer Relationship Management Tool for SaaS Startups in 2025</title>
  <meta property="og:title" content="Acme CRM">
  <meta property="og:description" content="The best CRM for startups.">
  <meta property="og:type" content="website">
  <meta name="twitter:card" content="summary">
</head>
<body>
  <h1>The Best CRM for SaaS Startups</h1>
  <h2>Features</h2><h2>Pricing</h2><h2>Integrations</h2>
  <img src="hero.png"><img src="screenshot.png"><img src="team.jpg">
  <a href="/features">Features</a>
  <a href="/pricing">Pricing</a>
  <a href="/about">About</a>
  <a href="https://twitter.com/acmecrm">Twitter</a>
  <p>Acme CRM is a powerful customer relationship management tool built for fast-growing SaaS companies.
     Manage leads, track deals, automate follow-ups and close more revenue with our AI-powered pipeline.
     Trusted by over 500 startups worldwide. Start your free 14-day trial today.</p>
</body>
</html>"""

# Planted issues:
#  A. Title is 83 chars (too long, ideal <60-70)
#  B. Meta description completely absent
#  C. No JSON-LD structured data
#  D. Missing og:image
#  E. All 3 images missing alt text


# ---------------------------------------------------------------------------
# Test 1 — Crawl only (no Claude)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _HAS_NETWORK, reason="getduct.ai unreachable from this environment")
async def test_crawl_real_page():
    """Crawls getduct.ai and verifies the crawl layer produces sensible output."""
    from agents.audit.v3.runner import run_crawl

    result = await run_crawl(_AUDIT_URL, max_blog_posts=3)

    # Root URL must be in landing pages
    assert _AUDIT_URL in result.plan.landing_pages or result.plan.root_url == _AUDIT_URL, \
        "root URL not found in landing pages"

    # At least the root page was crawled successfully
    assert len(result.pages) >= 1, "no pages crawled"
    root_page = next((p for p in result.pages if _AUDIT_URL in p.url), None)
    assert root_page is not None, f"root page missing from results. Pages: {[p.url for p in result.pages]}"

    # Root page must have returned a live HTTP response
    assert root_page.http_status == 200, f"root page returned HTTP {root_page.http_status}"

    # Must have extracted a title and at least one heading
    assert root_page.title != "", "root page has no <title>"
    assert len(root_page.h1s) >= 1, "root page has no <h1>"

    # Word count sanity — a real page has meaningful content
    assert root_page.word_count_approx >= 50, \
        f"suspiciously low word count: {root_page.word_count_approx}"

    print(f"\nCrawled {len(result.pages)} page(s) from {_AUDIT_URL}")
    print(f"  root title:    {root_page.title!r}")
    print(f"  http status:   {root_page.http_status}")
    print(f"  word count:    {root_page.word_count_approx}")
    print(f"  sitemap:       {result.plan.sitemap_url or 'not found'}")
    print(f"  landing pages: {result.plan.landing_pages}")
    print(f"  blog posts:    {result.plan.blog_posts}")


# ---------------------------------------------------------------------------
# Test 2 — Synthesis only, planted fixture (no network crawl)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _HAS_API_KEY, reason="ANTHROPIC_API_KEY not set")
async def test_run_synthesis_catches_planted_issues():
    """Feeds a known-bad HTML fixture to Claude and asserts it catches each planted issue."""
    from agents.audit.schema import AuditBusinessContext, CrawlPlan, CrawlResult
    from agents.audit.v3.runner import close_session, create_audit_session, run_synthesis
    from agents.models import Provider
    from service.crawl.extractor import extract_signals

    page = extract_signals(_FIXTURE_HTML, _FIXTURE_URL, "landing_page")

    # Verify fixture signals before calling Claude
    assert len(page.title) > 60,          "planted: title too long"
    assert page.meta_description == "",   "planted: meta description absent"
    assert page.has_schema_org is False,  "planted: no structured data"
    assert page.og_image == "",           "planted: missing og:image"
    assert page.images_missing_alt == 3,  "planted: 3 images without alt"

    plan = CrawlPlan(
        root_url=_FIXTURE_URL,
        sitemap_url="",
        robots_txt_url=f"{_FIXTURE_URL}robots.txt",
        llms_txt_url=f"{_FIXTURE_URL}llms.txt",
        landing_pages=[_FIXTURE_URL],
        blog_posts=[],
        total_sitemap_urls=1,
    )
    crawl_result = CrawlResult(plan=plan, pages=[page])
    business_context = AuditBusinessContext(
        business_name="Acme CRM",
        business_description="A CRM tool for SaaS startups.",
        business_goals="Improve organic search visibility and drive signups.",
    )

    session_id = "integration-fixture-test"
    create_audit_session(session_id)
    events: list[dict] = []

    async def collect(event: dict) -> None:
        events.append(event)
        if event.get("event") == "report_updated":
            close_session(session_id)

    report = await run_synthesis(
        session_id=session_id,
        crawl_result=crawl_result,
        business_context=business_context,
        model_str="claude-haiku-4-5-20251001",
        api_key=os.environ["ANTHROPIC_API_KEY"],
        provider=Provider.ANTHROPIC,
        emit=collect,
    )

    assert report is not None, "run_synthesis returned None"
    assert report.url == _FIXTURE_URL
    assert 0 <= report.overall_score <= 100
    assert len(report.findings) > 0
    assert report.executive_summary != ""
    assert any(e.get("event") == "report_updated" for e in events)

    findings_summary = [(f.finding_id, f.title) for f in report.findings]

    # A. Title too long
    assert any(
        "title" in (f.title + f.detail).lower()
        and any(w in (f.title + f.detail).lower() for w in ("long", "length", "character", "exceed", "70", "60"))
        for f in report.findings
    ), f"Agent missed: title too long. Findings: {findings_summary}"

    # B. Missing meta description
    assert any(
        "description" in (f.title + f.detail).lower()
        and any(w in (f.title + f.detail).lower() for w in ("missing", "absent", "no meta", "not found", "empty", "lacking"))
        for f in report.findings
    ), f"Agent missed: missing meta description. Findings: {findings_summary}"

    # C. No structured data
    assert any(
        any(w in (f.title + f.detail).lower() for w in ("schema", "structured data", "json-ld", "markup"))
        for f in report.findings
    ), f"Agent missed: no JSON-LD. Findings: {findings_summary}"

    # D. Missing og:image
    assert any(
        "image" in (f.title + f.detail).lower()
        and any(w in (f.title + f.detail).lower() for w in ("og", "open graph", "social", "missing", "absent"))
        for f in report.findings
    ), f"Agent missed: missing og:image. Findings: {findings_summary}"

    # E. Images missing alt text
    assert any(
        "alt" in (f.title + f.detail).lower()
        for f in report.findings
    ), f"Agent missed: images without alt text. Findings: {findings_summary}"


# ---------------------------------------------------------------------------
# Test 3 — Full pipeline: real crawl + real synthesis
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not (_HAS_API_KEY and _HAS_NETWORK),
    reason="requires ANTHROPIC_API_KEY and network access to getduct.ai",
)
async def test_full_pipeline_real_page():
    """End-to-end: crawls getduct.ai then runs Claude synthesis on the real crawl result."""
    from agents.audit.schema import AuditBusinessContext
    from agents.audit.v3.runner import (
        ClaudeAuditRunner,
        close_session,
        create_audit_session,
        get_session,
    )
    from agents.models import ModelName, Provider

    session_id = "integration-full-pipeline"
    create_audit_session(session_id)
    events: list[dict] = []

    async def collect(event: dict) -> None:
        events.append(event)
        if event.get("event") == "report_updated":
            close_session(session_id)

    runner = ClaudeAuditRunner(
        api_key=os.environ["ANTHROPIC_API_KEY"],
        provider=Provider.ANTHROPIC,
        model=ModelName.CLAUDE_HAIKU,
    )
    business_context = AuditBusinessContext(
        business_name="Duct",
        business_description="AI-powered SEO audit tool for SaaS companies.",
        business_goals="Rank for SEO audit and AIO-related keywords.",
    )

    report = await runner.run_pipeline(
        session_id=session_id,
        url=_AUDIT_URL,
        business_context=business_context,
        emit=collect,
        max_blog_posts=2,
    )

    # Crawl events must have fired
    step_ids = [e.get("step_id") for e in events if e.get("event") == "step_finished"]
    assert "fetch_sitemap" in step_ids, f"fetch_sitemap step missing. Steps fired: {step_ids}"
    assert "crawl_pages" in step_ids,   f"crawl_pages step missing. Steps fired: {step_ids}"

    # Report must be valid
    assert report is not None, "full pipeline returned no report"
    assert report.url == _AUDIT_URL
    assert 0 <= report.overall_score <= 100
    assert len(report.findings) >= 3, f"suspiciously few findings: {len(report.findings)}"
    assert report.executive_summary != ""

    print(f"\nFull pipeline result for {_AUDIT_URL}")
    print(f"  overall score: {report.overall_score}")
    print(f"  findings:      {len(report.findings)}")
    print(f"  top priorities:{report.top_priorities[:3]}")
    print(f"  summary:       {report.executive_summary[:120]}...")
