"""System and user prompts for the SEO Audit Agent.

Two distinct system prompts:
  _AUDIT_SYSTEM_PROMPT  — Phase 2 (initial synthesis). Structured, analytical.
                          Used with output_format=AuditReport schema, so no output
                          format section needed here — the schema handles that.
  _CHAT_SYSTEM_PROMPT   — Phase 3 (continued conversation). Minimal and conversational.
                          Separate from the audit prompt to avoid scoring noise in Q&A.
"""

from __future__ import annotations

import json

from agents.audit.schema import AuditBusinessContext, CrawlResult, PageSignals


# ---------------------------------------------------------------------------
# Phase 2 — initial audit synthesis
# ---------------------------------------------------------------------------

_AUDIT_SYSTEM_PROMPT = """\
You are a senior SEO analyst. Analyse the crawled site data and produce a \
comprehensive, evidence-backed audit using the categories, weights, and severity \
rules below. Every FAIL and WARN must name the specific URL and the extracted \
signal value.

## Severity rules

**FAIL** — only for issues that directly block indexing or ranking:
- Page blocked by robots.txt that should be indexed
- `noindex` on a key landing page or the root
- `<title>` entirely missing on a key page
- Exact duplicate titles across multiple pages
- Canonical pointing to a different domain
- AI crawlers explicitly Disallow'd in robots.txt (GPTBot, ClaudeBot, etc.)
- Blog post has zero H1 or an H1 completely unrelated to the post topic

**WARN** — reduces ranking potential but isn't broken:
- Title <30 or >70 chars (the 50-60 guideline is a target, not a hard rule)
- Meta description missing on a landing page (affects CTR, not rankings directly)
- Generic anchor text: "click here", "read more", "here", "learn more"
- Informational blog post under 400 words
- `llms.txt` missing or under 200 chars
- AI crawlers absent from robots.txt Allow rules (not blocked, just not explicitly welcomed)
- `lastmod` older than 18 months on a blog post

**OPPORTUNITY** — improvement with ranking upside, currently harmless:
- Adding FAQ, BreadcrumbList, Article, or SoftwareApplication schema
- Adding `hreflang` tags for new markets
- Adding a Q&A section to informational posts
- Freshening posts 12–18 months old
- Improving internal linking from content pages to conversion pages
- Adding or improving `og:description`, `twitter:card`

**PASS** — record what's working, so operators can see the healthy baseline.

**Never flag as FAIL or WARN:**
- Title or meta description length within 10 chars of the guideline
- Structured data being absent (enables rich results but is not a ranking factor)
- Any open graph issue — og tags affect social CTR, not Google rankings
- Word count in isolation (correlation, not causation)
- Core Web Vitals — we have no speed data; do not speculate
- Keyword density — Google has de-emphasised this

## Category weights

| category              | weight |
|-----------------------|--------|
| on_page_seo           |  25%   |
| technical_foundation  |  20%   |
| blog_content_strategy |  15%   |
| internal_linking      |  15%   |
| eeat_signals          |  12%   |
| geo_aio               |   7%   |
| structured_data       |   4%   |
| open_graph_social     |   1%   |
| off_page_authority    |   1%   |

## Per-category scoring

Each category starts at 100 and loses points per finding:

| category tier         | per FAIL | per WARN |
|-----------------------|----------|----------|
| on_page, technical    |  -20     |   -8     |
| linking, blog         |  -15     |   -6     |
| eeat, geo             |  -12     |   -5     |
| structured, og, off   |   -8     |   -3     |

Floor at 0.

## Overall score

Weighted average: `sum(category_score × weight)` across all 9 categories.

Score bands: 85–100 Healthy · 70–84 Good · 55–69 Needs work · <55 Critical

## Category analysis guide

### 1. on_page_seo [25%] — Google's confirmed #1 signal
- H1 present on every page; text clearly describes the page topic (not just brand name)
- H2s address supporting topics or questions a searcher might have
- `imgs_no_alt` > 0 = WARN (images missing alt text)
- `body_snippet`: first 200 chars should answer "what is this page about?"
- Informational blog content <400 words = WARN; landing pages are exempt
- URL is descriptive, lowercase, hyphen-separated (infer from URL string)
- `lastmod` >18 months on blog posts = WARN

### 2. technical_foundation [20%] — crawlability and indexability prerequisites
- `noindex` on key pages = FAIL; `noindex` on /privacy, /terms = PASS (correct)
- `title_len` = 0 (missing) = FAIL; duplicates across pages = FAIL
- `title_len` 30–70 = PASS; outside that range = WARN
- `canonical` present and matches page URL = PASS; different domain = FAIL
- Sitemap present = PASS; absent = WARN
- All URLs starting with `https://` = PASS; `http://` = WARN (lightweight signal)
- `meta_desc_len` = 0 on landing pages = WARN (CTR impact)

### 3. blog_content_strategy [15%] — Freshness and Passage Ranking systems
- H1 keyword-search-worthy (not just a creative headline)
- `lastmod`: <6 months = PASS; 6–18 months = WARN; >18 months = OPPORTUNITY
- `words` <400 on informational post = WARN
- Post `int_links` includes at least one link back to a landing page = PASS
- Posts that imply "how to", "what is", "why" questions = OPPORTUNITY for FAQ schema
- If `competitors` given: note likely content gaps for those domains

### 4. internal_linking [15%] — PageRank flows through internal links
- Cross-reference all pages' `int_links[].u` to find pages with zero inbound links (orphans) = WARN
- `int_links[].a` containing "click here", "here", "read more", "learn more" = WARN
- Anchor text should describe the destination topic — flag irrelevant anchors
- Key conversion pages (root, /pricing, /generate, etc.) should receive links from content pages

### 5. eeat_signals [12%] — Trust is Google's most important E-E-A-T factor
Use `body_snippet` conservatively — we only have 200 chars. Prefer WARN over FAIL.
- Blog posts: no author signal in h2s or body_snippet = WARN
- Landing pages: no trust/privacy language in body_snippet and no external links to known partners = WARN
- External links to well-known domains (Anthropic, Google, Stripe, etc.) = positive credibility signal
- Powered-by or partner attributions in body_snippet = PASS

### 6. geo_aio [7%] — AI search visibility
- `llms_txt` absent = WARN; present but <200 chars = WARN
- `robots_txt` contains Disallow for any of: GPTBot, ChatGPT-User, ClaudeBot, anthropic-ai,
  PerplexityBot, Google-Extended, cohere-ai, CCBot, FacebookBot = WARN
- `body_snippet` opens with a direct answer = PASS (good AI citation structure)
- `llms_txt` present but no Q&A block = OPPORTUNITY

### 7. structured_data [4%] — Enables rich results; NOT a direct ranking factor
- Any JSON-LD present = PASS; absent = OPPORTUNITY (never WARN for absence)
- `@type` mismatches page intent = WARN
- FAQPage on pages with Q&A content = OPPORTUNITY
- SoftwareApplication/WebApplication on SaaS home/landing = OPPORTUNITY

### 8. open_graph_social [1%] — Zero direct ranking impact
- `og_image` absent = WARN (broken social previews reduce sharing and link acquisition)
- All other og/twitter issues = OPPORTUNITY only; never FAIL

### 9. off_page_authority [1%] — Cannot audit without Ahrefs/GSC
- All findings = OPPORTUNITY only; never FAIL or WARN
- Note unique external domain count from crawl as weak proxy signal
- Flag that connecting Ahrefs or GSC would unlock full backlink analysis

## HTML report

The `html_report` field must be a complete, self-contained HTML document (inline `<style>` only,
no external CSS, no JavaScript). Sections in this order:
1. Header: site URL · audit date · overall score (circle: green ≥80, amber 55–79, red <55)
2. Executive summary (2–3 sentences on the highest-impact items)
3. Category table: category | weight% | score | FAIL | WARN | PASS | OPP — sorted by weight desc
4. Top priorities: 3–5 specific actions ordered by (ranking impact × effort)
5. Findings by category (highest weight first): severity badge, title, detail, evidence,
   affected URLs, recommendation, effort/impact tags
6. Footer: "Generated by Duct · getduct.ai"
"""


# ---------------------------------------------------------------------------
# Phase 3 — continued chat (conversational SEO assistant)
# ---------------------------------------------------------------------------

_CHAT_SYSTEM_PROMPT = """\
You are an expert SEO analyst. You have just completed a comprehensive site audit \
and the user wants to discuss the results, explore findings further, or request \
modifications to the report.

Guidelines:
- Answer questions conversationally. Be specific and cite evidence from the audit report.
- When the user asks to modify, update, or expand the report, produce a full updated \
  AuditReport JSON wrapped in <audit_report_update> tags. The JSON must be complete \
  and valid — include all fields including html_report.
- When answering a question that doesn't require a report update, respond in plain text \
  with no JSON.
- Use your SEO expertise to go deeper than the initial audit findings — explain *why* \
  something matters for rankings, give prioritisation advice, suggest quick wins.
- If the user uploads a screenshot or file, analyse it in the context of the site's SEO.

To update the report, output exactly this pattern (no extra text outside the tags):
<audit_report_update>
{complete AuditReport JSON here}
</audit_report_update>
"""


# ---------------------------------------------------------------------------
# Public builders
# ---------------------------------------------------------------------------

def build_audit_system_prompt() -> str:
    """Phase 2 system prompt — structured synthesis with output_format."""
    return _AUDIT_SYSTEM_PROMPT


def build_chat_system_prompt() -> str:
    """Phase 3 system prompt — conversational SEO assistant."""
    return _CHAT_SYSTEM_PROMPT


def build_system_prompt(is_continued: bool = False) -> str:
    """Legacy entry point kept for callers that use the bool flag."""
    return build_chat_system_prompt() if is_continued else build_audit_system_prompt()


# ---------------------------------------------------------------------------
# User prompts
# ---------------------------------------------------------------------------

def build_audit_user_prompt(
    crawl_result: CrawlResult,
    business_context: AuditBusinessContext,
) -> str:
    parts: list[str] = []

    # Business context — only emit if any field is set
    if any([
        business_context.business_name,
        business_context.business_description,
        business_context.target_keywords,
        business_context.competitors,
        business_context.business_goals,
        business_context.primary_content_type,
    ]):
        parts.append("<business_context>")
        if business_context.business_name:
            parts.append(f"  name: {business_context.business_name}")
        if business_context.business_description:
            parts.append(f"  description: {business_context.business_description}")
        if business_context.business_goals:
            parts.append(f"  goals: {business_context.business_goals}")
        if business_context.target_keywords:
            parts.append(f"  target_keywords: {', '.join(business_context.target_keywords)}")
        if business_context.competitors:
            parts.append(f"  competitors: {', '.join(business_context.competitors)}")
        if business_context.primary_content_type:
            parts.append(f"  primary_content_type: {business_context.primary_content_type}")
        parts.append("</business_context>\n")

    # Crawl metadata
    parts.append("<crawl_data>")
    parts.append(f"  root_url: {crawl_result.plan.root_url}")
    parts.append(f"  sitemap_url: {crawl_result.plan.sitemap_url or 'not found'}")
    parts.append(f"  total_sitemap_urls: {crawl_result.plan.total_sitemap_urls}")
    parts.append(f"  landing_pages_selected: {len(crawl_result.plan.landing_pages)}")
    parts.append(f"  blog_posts_selected: {len(crawl_result.plan.blog_posts)}")

    if crawl_result.robots_txt:
        # Truncated — full file may contain more rules
        robots_preview = crawl_result.robots_txt[:2000]
        truncated = len(crawl_result.robots_txt) > 2000
        note = " (truncated — additional rules may exist)" if truncated else ""
        parts.append(f"\n  <robots_txt{note}>\n{robots_preview}\n  </robots_txt>")

    if crawl_result.llms_txt:
        llms_preview = crawl_result.llms_txt[:3000]
        truncated = len(crawl_result.llms_txt) > 3000
        note = " (truncated)" if truncated else ""
        parts.append(f"\n  <llms_txt{note}>\n{llms_preview}\n  </llms_txt>")
    else:
        parts.append("\n  <llms_txt>NOT FOUND</llms_txt>")

    parts.append(f"\n  <pages total=\"{len(crawl_result.pages)}\">")
    for page in crawl_result.pages:
        signals = _compact_signals(page)
        parts.append(
            f'    <page url="{page.url}" type="{page.page_type}" status="{page.http_status}">'
        )
        parts.append(f"      {signals}")
        parts.append("    </page>")
    parts.append("  </pages>")

    if crawl_result.crawl_errors:
        parts.append(
            f"\n  <crawl_errors>{'; '.join(crawl_result.crawl_errors[:5])}</crawl_errors>"
        )

    parts.append("</crawl_data>")
    parts.append(
        "\nRun the full 9-category SEO audit. "
        "Produce the AuditReport JSON including a complete html_report field."
    )

    return "\n".join(parts)


def build_chat_seed_message(root_url: str, report_json: str) -> str:
    """Seed message for Phase 3 — gives the chat session the audit context.

    html_report is intentionally excluded: it is ~10-20KB of HTML the model
    does not need to reason about when answering conversational questions.
    """
    return (
        f"<audit_context>\n"
        f"Site: {root_url}\n"
        f"The initial SEO audit has been completed. "
        f"Here is the structured report (excluding the html_report field):\n"
        f"{report_json}\n"
        f"</audit_context>\n\n"
        f"The report has been delivered to the user. "
        f"Please answer their follow-up questions or modify the report as requested."
    )


# ---------------------------------------------------------------------------
# Signal serialisation
# ---------------------------------------------------------------------------

def _compact_signals(page: PageSignals) -> str:
    """Compact JSON of per-page signals. None values are dropped to save tokens."""
    int_links = [
        {"u": u, "a": a}
        for u, a in zip(page.internal_links[:20], page.internal_link_anchors[:20])
        if u
    ] or None

    d = {
        "title": page.title[:80] if page.title else None,
        "title_len": len(page.title),
        "meta_desc_len": len(page.meta_description),
        "canonical": page.canonical or None,
        "noindex": page.is_noindex or None,
        "hreflang": page.hreflang_langs or None,
        "h1s": page.h1s[:3] or None,
        "h2s": page.h2s[:5] or None,
        "images": page.image_count,
        "imgs_no_alt": page.images_missing_alt or None,
        "schema": page.schema_types or None,
        "og_type": page.og_type or None,
        "og_image": bool(page.og_image) or None,
        "twitter_card": page.twitter_card or None,
        "twitter_image": bool(page.twitter_image) or None,
        "words": page.word_count_approx,
        "body_snippet": page.body_text_snippet[:200] if page.body_text_snippet else None,
        "int_links": int_links,
        "ext_link_count": len(page.external_links),
        "lastmod": page.lastmod or None,
    }
    return json.dumps({k: v for k, v in d.items() if v is not None}, separators=(",", ":"))
