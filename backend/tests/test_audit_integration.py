"""Integration tests for the SEO audit pipeline — every one marked ``live``.

Nothing here runs from a plain ``pytest``: each test crawls a real site or
spends real tokens, for minutes. Opt in with ``pytest -m live``.

Two levels of coverage:

  test_crawl_real_page
    Crawls a real public URL (getduct.ai) with no model involved.
    Verifies the crawl layer works end-to-end: HTTP fetch, sitemap discovery,
    HTML parsing, PageSignals extraction.
    Skipped when network is unavailable.

  test_full_pipeline_real_page
    Full end-to-end: real crawl of getduct.ai + real synthesis.
    The only test that exercises both layers together.
    Requires ANTHROPIC_API_KEY and network access to getduct.ai.

A third test drove ``run_synthesis`` against a mocked-transport SDK client on a
planted-issue fixture. It went with V3, and is not replaced here: what it
covered — the model finding known issues in known HTML — is what the audit eval
grades against a rubric, on a real site, on every provider.

Notes on the shape:
  - The report is assembled from StartAuditReport / AddAuditCategory /
    FinalizeAuditReport tool calls in template mode.
  - ARTIFACT_CHUNK is emitted per-token inside <duct_artifact> in freehand mode.
  - The run stays open for follow-up chat, so a driver passes a short
    ``chat_idle_timeout`` or closes the session.

All tests have a 5-minute (300s) outer timeout.
"""

import logging
import time
from pathlib import Path

import pytest

from config import get_configs

ROOT = Path(__file__).resolve().parents[1]
logger = logging.getLogger(__name__)

_cfg = get_configs()
_HAS_API_KEY = bool(_cfg.anthropic_api_key)
_AUDIT_URL = "https://getduct.ai"
_OUTPUTS = ROOT / "tests" / "outputs"

_TIMEOUT = 900  # 15 minutes: enrichment sub-agent (~90s) + synthesis (~300-600s)


def _network_available(url: str = _AUDIT_URL) -> bool:
    """HTTP check — returns False if the host is unreachable or returns a non-2xx status.

    TCP-only checks pass even when Cloudflare answers the handshake but returns 403;
    an HTTP GET lets us detect that case so the real-network tests are properly skipped.
    """
    import urllib.request
    # Use the same Googlebot UA as the crawler — Cloudflare WAF blocks it on CI runner IPs,
    # which returns 403, so the check correctly returns False and tests are skipped.
    _GOOGLEBOT_UA = (
        "Mozilla/5.0 (Linux; Android 6.0.1; Nexus 5X Build/MMB29P) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36 "
        "(compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _GOOGLEBOT_UA})
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status < 400
    except Exception:
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
# Shared helpers
# ---------------------------------------------------------------------------

def _log_event_summary(events: list[dict]) -> None:
    """Log a compact breakdown of all SSE events received."""
    from collections import Counter
    counts = Counter(e.get("event", "?") for e in events)
    logger.info("SSE event summary:")
    for evt, n in sorted(counts.items()):
        logger.info("  %-32s × %d", evt, n)


def _stamped(stem: str, ext: str) -> str:
    """Return filename with a datetime stamp so runs never overwrite each other."""
    stamp = time.strftime("%Y%m%d_%H%M%S")
    return f"{stem}_{stamp}.{ext}"


def _save_report(stem: str, content: str, ext: str = "html") -> Path:
    _OUTPUTS.mkdir(parents=True, exist_ok=True)
    out = _OUTPUTS / _stamped(stem, ext)
    out.write_text(content, encoding="utf-8")
    return out


_COMPONENT_PATH = ROOT.parent / "app" / "src" / "components" / "audit" / "AuditReportV1.jsx"


def _save_html_preview(data: dict, stem: str) -> Path:
    """Wrap AuditReportV1.jsx in a self-contained CDN HTML page for visual inspection.

    Strips the Next.js 'use client' directive and 'export default' so the
    component runs directly under React CDN + Babel. Open the output file in
    any browser — no build step needed.
    """
    import json as _json
    import re as _re

    src = _COMPONENT_PATH.read_text(encoding="utf-8")
    # Strip Next.js directive, ES module imports (bundler handles these; CDN shims below),
    # and make the export a plain function declaration.
    src = src.replace('"use client";\n', "").replace("'use client';\n", "")
    src = _re.sub(r"^import\s+.*?;\n", "", src, flags=_re.MULTILINE)
    src = _re.sub(r"^export default function ", "function ", src, count=1, flags=_re.MULTILINE)

    # CDN shims — replace bundler imports with window globals exposed by the UMD scripts.
    # Note: window.lucide (base pkg) exports SVG data arrays, NOT React components.
    # Assign no-ops so icon-bearing components render without errors in standalone preview.
    cdn_shims = (
        "// CDN shims: replaces ES module imports stripped above\n"
        "const { BarChart, Bar, XAxis, YAxis, Cell, ResponsiveContainer, LabelList } = window.Recharts || {};\n"
        "const _noIcon = () => null;\n"
        "const AlertTriangle = _noIcon, CheckCircle2 = _noIcon, Calendar = _noIcon,\n"
        "      Activity = _noIcon, Target = _noIcon, BarChart2 = _noIcon,\n"
        "      Zap = _noIcon, Clock = _noIcon, TrendingUp = _noIcon;\n\n"
    )
    src = cdn_shims + src

    data_json = _json.dumps(data, ensure_ascii=False)
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Audit Report Preview</title>
  <script src="https://unpkg.com/react@18/umd/react.development.js"></script>
  <script src="https://unpkg.com/react-dom@18/umd/react-dom.development.js"></script>
  <script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://unpkg.com/recharts@2/umd/Recharts.js"></script>
  <script src="https://unpkg.com/lucide@latest/dist/umd/lucide.js"></script>
</head>
<body>
  <div id="root"></div>
  <script>window.__AUDIT_DATA__ = {data_json};</script>
  <script type="text/babel" data-presets="react">
{src}
    ReactDOM.createRoot(document.getElementById("root")).render(
      <AuditReportV1 data={{window.__AUDIT_DATA__}} />
    );
  </script>
</body>
</html>"""

    return _save_report(stem, html, ext="html")


# ---------------------------------------------------------------------------
# Test 1 — Crawl only (no Claude)
# ---------------------------------------------------------------------------

# `live`: crawls the real production site. The two tests below are already
# marked, and this one belongs with them — the _HAS_NETWORK probe uses urllib
# while the crawler uses httpx, so a probe that passes does not guarantee the
# crawl will (it returned HTTP 0 behind an egress proxy that let the probe through).
@pytest.mark.live
@pytest.mark.skipif(not _HAS_NETWORK, reason="getduct.ai unreachable from this environment")
async def test_crawl_real_page():
    """Crawls getduct.ai and verifies the crawl layer produces sensible output."""
    import asyncio
    from agents.audit.crawl import run_crawl

    logger.info("[crawl] target: %s", _AUDIT_URL)
    t0 = time.perf_counter()
    result = await asyncio.wait_for(run_crawl(_AUDIT_URL, max_blog_posts=3), timeout=60)
    elapsed = time.perf_counter() - t0
    logger.info("[crawl] done in %.1fs — %d page(s) crawled", elapsed, len(result.pages))

    # Root URL must be present
    assert _AUDIT_URL in result.plan.landing_pages or result.plan.root_url == _AUDIT_URL, \
        "root URL not found in landing pages"

    assert len(result.pages) >= 1, "no pages crawled"
    root_page = next((p for p in result.pages if _AUDIT_URL in p.url), None)
    assert root_page is not None, \
        f"root page missing. Pages: {[p.url for p in result.pages]}"
    assert root_page.http_status == 200, \
        f"root page returned HTTP {root_page.http_status}"
    assert root_page.title != "", "root page has no <title>"
    assert len(root_page.h1s) >= 1, "root page has no <h1>"
    assert root_page.word_count_approx >= 50, \
        f"suspiciously low word count: {root_page.word_count_approx}"

    # ------------------------------------------------------------------
    # New Googlebot-accurate signals
    # ------------------------------------------------------------------
    assert isinstance(root_page.ttfb_ms, float) and root_page.ttfb_ms > 0, \
        f"ttfb_ms not measured (got {root_page.ttfb_ms})"
    assert isinstance(root_page.redirect_chain, list), \
        "redirect_chain must be a list"
    assert isinstance(root_page.is_spa_suspected, bool), \
        "is_spa_suspected must be a bool"

    logger.info("  title:          %r", root_page.title)
    logger.info("  http status:    %s", root_page.http_status)
    logger.info("  ttfb_ms:        %.1f ms", root_page.ttfb_ms)
    logger.info("  redirect_chain: %s", root_page.redirect_chain or "(none)")
    logger.info("  x_robots_tag:   %r", root_page.x_robots_tag or "(none)")
    logger.info("  vary_header:    %r", root_page.vary_header or "(none)")
    logger.info("  word count:     %s", root_page.word_count_approx)
    logger.info("  canonical:      %s", root_page.canonical or "(none)")
    logger.info("  h1s:            %s", root_page.h1s)
    logger.info("  has schema:     %s %s", root_page.has_schema_org, root_page.schema_types)
    logger.info("  microdata:      %s", root_page.microdata_types or "(none)")
    logger.info("  spa_suspected:  %s  framework=%r", root_page.is_spa_suspected, root_page.spa_framework or "(none)")
    logger.info("  amp_url:        %s", root_page.amp_url or "(none)")
    logger.info("  preload_hints:  %d", root_page.preload_hints)
    logger.info("  noscript:       %r", root_page.noscript_content[:80] if root_page.noscript_content else "(none)")
    logger.info("  sitemap:        %s", result.plan.sitemap_url or "(not found)")
    logger.info("  robots_txt:     %d chars", len(result.robots_txt))
    logger.info("  llms_txt:       %d chars", len(result.llms_txt))
    logger.info("  landing pages:  %s", result.plan.landing_pages)
    logger.info("  blog posts:     %s", result.plan.blog_posts)
    logger.info("  crawl errors:   %s", result.crawl_errors or "none")


# ---------------------------------------------------------------------------
# Test 2 — Synthesis only, planted fixture (no network crawl)
# ---------------------------------------------------------------------------

# `live`: a real synthesis call, minutes long and paid for. The skipif alone was
# the gate before, and `get_configs()` reads backend/.env.local — so a developer
# (or an agent) with a key there fired this from `make test`.
@pytest.mark.live
@pytest.mark.skipif(
    not (_HAS_API_KEY and _HAS_NETWORK),
    reason="requires ANTHROPIC_API_KEY and network access to getduct.ai (HTTP 200)",
)
async def test_full_pipeline_real_page(duct_business_context):
    """End-to-end: crawls getduct.ai then runs Claude synthesis in template mode.

    Uses report_mode='template' — the agent calls SubmitAuditReport with structured
    JSON instead of emitting <duct_artifact> HTML tags. The React component AuditReportV1
    renders the structured data visually.
    """
    import asyncio
    import json as _json
    from agents.audit.crawl import create_audit_session
    from agents.audit.v1.runner import LangChainAuditRunner
    from agents.core.session import close_session
    from agents.models import ModelName, Provider

    session_id = "integration-full-pipeline"
    create_audit_session(session_id)
    events: list[dict] = []

    async def collect(event: dict) -> None:
        events.append(event)
        evt = event.get("event")
        if evt == "artifact_chunk":
            pass  # template mode emits no report_chunk — counted in summary
        elif evt == "step_started":
            logger.info("[step] ▶ %s — %s", event.get("step_id"), event.get("label", ""))
        elif evt == "step_finished":
            pages = event.get("payload", {}).get("pages", [])
            suffix = f"({len(pages)} pages)" if pages else ""
            logger.info("[step] ✓ %s %s — %s", event.get("step_id"), suffix, event.get("status", ""))
        elif evt == "artifact_version":
            payload = event.get("payload", {})
            sd = payload.get("structured_data")
            info = (
                f"score={sd['overall_score']} band={sd['score_band']} "
                f"categories={len(sd.get('categories', []))}"
                if sd else "no structured_data"
            )
            logger.info("[event] report_updated v%s — %s", event.get("version_id"), info)
            close_session(session_id)
        elif evt == "agent_message_chunk":
            pass  # accumulated in full_agent_text below
        elif evt == "message_stop":
            full_text = "".join(e.get("text", "") for e in events if e.get("event") == "agent_message_chunk")
            logger.info("[event] message_stop — agent text so far (%d chars): %.300r", len(full_text), full_text)
        elif evt == "thinking_chunk":
            pass  # noisy; counted in summary

    runner = LangChainAuditRunner(
        api_key=_cfg.anthropic_api_key,
        provider=Provider.ANTHROPIC,
        model=ModelName.CLAUDE_SONNET,
        gemini_api_key=_cfg.gemini_api_key,
    )
    business_context = duct_business_context

    logger.info("[pipeline] target: %s  crawl_depth=deep  model=sonnet  mode=template", _AUDIT_URL)
    t0 = time.perf_counter()

    report = await asyncio.wait_for(
        runner.run_pipeline(
            session_id=session_id,
            url=_AUDIT_URL,
            business_context=business_context,
            emit=collect,
            max_blog_posts=2,
            crawl_depth="deep",
            chat_idle_timeout=30.0,
            report_mode="template",
            template_id="seo_v1",
        ),
        timeout=_TIMEOUT,
    )

    elapsed = time.perf_counter() - t0
    logger.info("[pipeline] done in %.1fs", elapsed)

    # ------------------------------------------------------------------
    # Crawl step events
    # ------------------------------------------------------------------
    step_ids = [e.get("step_id") for e in events if e.get("event") == "step_finished"]
    assert "fetch_sitemap" in step_ids,    f"fetch_sitemap step missing. Got: {step_ids}"
    assert "crawl_pages" in step_ids,      f"crawl_pages step missing. Got: {step_ids}"
    assert "synthesize_audit" in step_ids, f"synthesize_audit step missing. Got: {step_ids}"

    # ------------------------------------------------------------------
    # Report presence and mode
    # ------------------------------------------------------------------
    assert report is not None, "full pipeline returned no report — SubmitAuditReport not called"
    assert report.report_mode == "template", f"expected report_mode=template, got {report.report_mode!r}"
    assert report.template_id == "seo_v1",  f"expected template_id=seo_v1, got {report.template_id!r}"
    assert report.url == _AUDIT_URL
    assert report.html_report == "",        "html_report should be empty in template mode"
    assert isinstance(report.executive_summary, str) and report.executive_summary, \
        "executive_summary must be a non-empty string"

    # ------------------------------------------------------------------
    # Structured data integrity
    # ------------------------------------------------------------------
    sd = report.structured_data
    assert sd is not None, "structured_data is None — SubmitAuditReport validation failed"

    assert 0 <= sd.overall_score <= 100, \
        f"overall_score out of range: {sd.overall_score}"
    assert sd.score_band in ("healthy", "good", "needs_work", "critical"), \
        f"unexpected score_band: {sd.score_band!r}"
    assert sd.pages_crawled > 0, "pages_crawled must be > 0"
    # total_sitemap_urls may be 0 when no XML sitemap is found; otherwise must be >= pages_crawled
    assert sd.total_sitemap_urls == 0 or sd.total_sitemap_urls >= sd.pages_crawled, \
        f"total_sitemap_urls ({sd.total_sitemap_urls}) < pages_crawled ({sd.pages_crawled})"

    assert len(sd.categories) == 9, \
        f"expected 9 categories, got {len(sd.categories)}: {[c.id for c in sd.categories]}"

    expected_category_ids = {
        "on_page_seo", "technical_foundation", "blog_content_strategy",
        "internal_linking", "eeat_signals", "geo_aio",
        "structured_data", "open_graph_social", "off_page_authority",
    }
    actual_ids = {c.id for c in sd.categories}
    missing = expected_category_ids - actual_ids
    assert not missing, f"missing categories: {missing}"

    for cat in sd.categories:
        assert 0 <= cat.score <= 100, \
            f"category {cat.id!r} score out of range: {cat.score}"
        for finding in cat.findings:
            assert finding.severity in ("fail", "warn", "pass", "opportunity"), \
                f"invalid severity {finding.severity!r} in {cat.id}/{finding.id}"

    assert len(sd.top_priorities) > 0, "top_priorities is empty"

    # ------------------------------------------------------------------
    # Narrative fields — headline / wins / roadmap / key_signals
    # ------------------------------------------------------------------
    assert sd.headline, \
        "headline is empty — model did not follow SubmitAuditReport instructions"
    assert len(sd.key_signals) == 3, \
        f"key_signals must be exactly 3 strings, got {len(sd.key_signals)}: {sd.key_signals!r}"
    assert all(isinstance(s, str) and s for s in sd.key_signals), \
        f"key_signals must be non-empty strings: {sd.key_signals!r}"
    assert len(sd.wins) >= 1, \
        f"wins is empty — model must include at least one positive finding (got {sd.wins!r})"
    assert len(sd.roadmap) >= 1, \
        f"roadmap is empty — model must include at least one phase (got {sd.roadmap!r})"
    for phase in sd.roadmap:
        assert phase.tasks, f"roadmap phase {phase.label!r} has no tasks"

    # ------------------------------------------------------------------
    # Crawl summary — computed by runner from raw page signals
    # ------------------------------------------------------------------
    assert sd.crawl_summary is not None, \
        "crawl_summary is None — runner failed to compute it from CrawlResult"

    # ------------------------------------------------------------------
    # SSE event contract
    # ------------------------------------------------------------------
    report_events = [e for e in events if e.get("event") == "artifact_version"]
    assert report_events, "ARTIFACT_VERSION never fired"
    assert report_events[0]["version_id"] == 1, "initial report must have version_id=1"

    agent_chunks = [e for e in events if e.get("event") == "agent_message_chunk"]
    assert len(agent_chunks) > 0, \
        "no AGENT_MESSAGE_CHUNK — model didn't stream analysis text before SubmitAuditReport"

    # template mode: no <duct_artifact> tag streaming
    artifact_chunks = [e for e in events if e.get("event") == "artifact_chunk"]
    assert len(artifact_chunks) == 0, \
        f"unexpected ARTIFACT_CHUNK events in template mode ({len(artifact_chunks)} received)"

    assert not any(e.get("event") == "synthesis_chunk" for e in events), \
        "legacy SYNTHESIS_CHUNK still being emitted"

    # ------------------------------------------------------------------
    # Save outputs for visual inspection + comparison
    # ------------------------------------------------------------------
    json_str = _json.dumps(sd.model_dump(), indent=2, ensure_ascii=False)
    json_out  = _save_report("pipeline_report_template", json_str, ext="json")
    html_out  = _save_html_preview(sd.model_dump(), "pipeline_report_preview")

    thinking_events = [e for e in events if e.get("event") == "thinking_chunk"]
    _log_event_summary(events)
    logger.info("overall_score:      %d (%s)", sd.overall_score, sd.score_band)
    logger.info("pages_crawled:      %d / %d sitemap URLs", sd.pages_crawled, sd.total_sitemap_urls)
    logger.info("categories:         %s", [(c.id, c.score) for c in sd.categories])
    logger.info("top_priorities:     %d", len(sd.top_priorities))
    logger.info("key_signals:        %r", sd.key_signals)
    logger.info("headline:           %.120r", sd.headline)
    logger.info("wins:               %d item(s): %s", len(sd.wins), sd.wins[:2])
    logger.info("roadmap:            %d phase(s): %s",
                len(sd.roadmap), [f"{p.label}/{p.theme}({len(p.tasks)}t)" for p in sd.roadmap])
    logger.info("crawl_summary:      %s", sd.crawl_summary)
    logger.info("agent_msg_chunks:   %d", len(agent_chunks))
    logger.info("thinking_chunks:    %d", len(thinking_events))
    logger.info("json saved to:      %s", json_out)
    logger.info("html preview:       %s", html_out)
