"""In-process MCP tools exposed to the SEO audit agent.

The FetchPages tool lets the agent fetch full content for specific pages
during a chat session — e.g. to verify a finding, assess body text for
content quality, or deep-dive into pages the business goals flag as important.

The tool runs inside the Python process (no subprocess), fetches URLs
concurrently via asyncio.gather, and returns compact structured signals.

Security: only same-origin URLs from the session's discovered sitemap are
allowed. validate_public_url() blocks SSRF at the IP-address level.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Annotated
from urllib.parse import urlparse

from claude_agent_sdk import create_sdk_mcp_server, tool
from claude_agent_sdk.types import McpSdkServerConfig

from agents.audit.schema import CrawlResult, PageSignals, StructuredAuditData
from service.crawl.extractor import extract_signals
from service.crawl.fetcher import SSRFError, fetch, make_client, validate_public_url

logger = logging.getLogger(__name__)

_MAX_URLS_PER_CALL = 10
_FULL_BODY_CHARS   = 5_000   # vs 500-char snippet in the shallow crawl


def build_audit_mcp_server(
    crawl_result: CrawlResult,
    report_mode: str = "freehand",
    on_submit_report=None,  # async (args: dict) -> dict | None
) -> McpSdkServerConfig:
    """Build the in-process MCP server scoped to this audit session's site.

    The returned config is passed to ClaudeAgentOptions.mcp_servers so the
    agent can call FetchPages during chat without making arbitrary HTTP requests.
    """
    root_host = urlparse(crawl_result.plan.root_url).netloc.lower().removeprefix("www.")

    @tool(
        name="FetchPages",
        description=(
            "Fetch full page signals for one or more URLs from the audited site. "
            "Returns structured SEO signals plus up to 5 000 chars of body text — "
            "significantly more than the 500-char snippet available from the initial crawl. "
            "Use this during chat to: verify a finding with fresh data, assess full body "
            "text for content quality or E-E-A-T evidence, or deep-dive into pages the "
            "business goals flag as important. "
            "All URLs are fetched in parallel. Max 10 per call."
        ),
        input_schema={
            "urls": Annotated[
                list[str],
                (
                    "List of page URLs to fetch. Must belong to the audited site. "
                    f"Maximum {_MAX_URLS_PER_CALL} URLs per call."
                ),
            ]
        },
    )
    async def fetch_pages(args: dict) -> dict:
        urls: list[str] = args.get("urls", [])[:_MAX_URLS_PER_CALL]

        valid: list[str] = []
        errors: list[str] = []

        for url in urls:
            host = urlparse(url).netloc.lower().removeprefix("www.")
            if host != root_host:
                errors.append(f"{url}: not from audited site (expected {root_host})")
                continue
            try:
                validate_public_url(url)
                valid.append(url)
            except SSRFError as exc:
                errors.append(f"{url}: {exc}")

        async def _fetch_one(url: str) -> PageSignals:
            async with make_client() as client:
                result = await fetch(client, url)
            signals = extract_signals(result.text, url, "landing_page", response_headers=result.headers)
            signals.http_status = result.status
            signals.ttfb_ms = result.ttfb_ms
            signals.redirect_chain = result.redirect_chain
            signals.body_text_snippet = result.text[:_FULL_BODY_CHARS]
            return signals

        fetched = await asyncio.gather(
            *[_fetch_one(u) for u in valid],
            return_exceptions=True,
        )

        pages = []
        for url, result in zip(valid, fetched):
            if isinstance(result, Exception):
                logger.warning("FetchPages: failed to fetch %s: %s", url, result)
                errors.append(f"{url}: {result}")
            else:
                pages.append(_compact(result))

        payload: dict = {"pages": pages}
        if errors:
            payload["errors"] = errors

        return {"content": [{"type": "text", "text": json.dumps(payload, indent=2)}]}

    tools = [fetch_pages]

    if report_mode == "template":
        @tool(
            name="SubmitAuditReport",
            description=(
                "Submit the completed SEO audit report as structured data. "
                "Call once after finishing the full 9-category analysis to deliver the initial report. "
                "During chat, call again with the full updated data whenever you want to issue a new "
                "version based on user feedback or new findings. Each call creates a numbered snapshot."
            ),
            input_schema=StructuredAuditData.model_json_schema(),
        )
        async def submit_audit_report(args: dict) -> dict:
            if on_submit_report:
                result = await on_submit_report(args)
                return {"content": [{"type": "text", "text": json.dumps(result)}]}
            return {"content": [{"type": "text", "text": '{"status": "received"}'}]}

        tools.append(submit_audit_report)

    return create_sdk_mcp_server("duct_crawl", tools=tools)


def _compact(s: PageSignals) -> dict:
    """Compact signal dict — structured enough for the model, lean on tokens."""
    d: dict = {
        "url":                s.url,
        "http_status":        s.http_status,
        "ttfb_ms":            s.ttfb_ms,
        "redirect_chain":     s.redirect_chain,
        "title":              s.title,
        "title_len":          len(s.title),
        "meta_description":   s.meta_description,
        "meta_desc_len":      len(s.meta_description),
        "canonical":          s.canonical,
        "is_noindex":         s.is_noindex,
        "x_robots_tag":       s.x_robots_tag,
        "vary_header":        s.vary_header,
        "h1s":                s.h1s,
        "h2s":                s.h2s[:10],
        "word_count":         s.word_count_approx,
        "body_text":          s.body_text_snippet,
        "has_schema":         s.has_schema_org,
        "schema_types":       s.schema_types,
        "schema_json_ld":     s.schema_json_ld,
        "microdata_types":    s.microdata_types,
        "og_image":           s.og_image,
        "images_missing_alt": s.images_missing_alt,
        "internal_links":     len(s.internal_links),
        "external_links":     len(s.external_links),
        "lastmod":            s.lastmod,
        "amp_url":            s.amp_url,
        "preload_hints":      s.preload_hints,
        "is_spa_suspected":   s.is_spa_suspected,
        "spa_framework":      s.spa_framework,
        "noscript_content":   s.noscript_content,
    }
    # omit empty/zero values to reduce token use
    return {k: v for k, v in d.items() if v not in (None, "", [], {}, 0, 0.0, False)}
