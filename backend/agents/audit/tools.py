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

from agents.audit.schema import (
    AuditCategory,
    AuditReportFinalize,
    AuditReportStart,
    CrawlResult,
    PageSignals,
    StructuredAuditData,
)
from service.crawl.extractor import extract_signals
from service.crawl.fetcher import SSRFError, fetch, make_client, validate_public_url

logger = logging.getLogger(__name__)

_MAX_URLS_PER_CALL = 10
_FULL_BODY_CHARS   = 5_000   # vs 500-char snippet in the shallow crawl


def build_audit_mcp_server(
    crawl_result: CrawlResult,
    report_mode: str = "freehand",
    on_submit_report=None,    # async (args: dict) -> dict | None
    on_category_added=None,   # async (count: int, category: dict) -> None — live progress
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
        # Incremental build accumulator — persists across the Start/Add/Finalize
        # calls within this session (the MCP server is built once per session).
        # Each tool is small, so the model fills it reliably; partial progress
        # (categories added before a mid-build failure) survives in `draft`.
        draft: dict = {"categories": []}

        def _text(payload: dict) -> dict:
            return {"content": [{"type": "text", "text": json.dumps(payload)}]}

        def _err(message: str) -> dict:
            # is_error=True signals a failed call so the agent loop CONTINUES and the
            # model can react/retry — vs an uncaught exception, which per the SDK docs
            # stops the loop and fails the whole query.
            return {
                "content": [{"type": "text", "text": json.dumps({"status": "error", "message": message})}],
                "is_error": True,
            }

        @tool(
            name="StartAuditReport",
            description=(
                "Begin the structured SEO audit report. Call this FIRST, once, after you have "
                "finished analysing the crawl and computed all 9 category scores. Provide the "
                "scorecard header (overall_score, score_band, totals, key_signals, headline). "
                "Then call AddAuditCategory once per category, and FinalizeAuditReport last. "
                "url, generated_at and crawl_summary are filled by the backend — omit them."
            ),
            input_schema=AuditReportStart.model_json_schema(),
        )
        async def start_audit_report(args: dict) -> dict:
            draft.clear()
            draft.update(args)
            draft["categories"] = []
            logger.info("audit tool: StartAuditReport — score=%s band=%s",
                        args.get("overall_score"), args.get("score_band"))
            return _text({
                "status": "started",
                "next": "Call AddAuditCategory once for each of the 9 categories, then FinalizeAuditReport.",
            })

        @tool(
            name="AddAuditCategory",
            description=(
                "Add ONE category's findings to the report in progress. Call once per category "
                "(all 9), after StartAuditReport. Each call is a single AuditCategory: id, label, "
                "score, tooltip, the four counts, and its findings[]. Order does not matter."
            ),
            input_schema=AuditCategory.model_json_schema(),
        )
        async def add_audit_category(args: dict) -> dict:
            draft.setdefault("categories", []).append(args)
            n = len(draft["categories"])
            logger.info("audit tool: AddAuditCategory '%s' (%d findings) — %d/9 categories",
                        args.get("label") or args.get("id") or "?",
                        len(args.get("findings") or []), n)
            if on_category_added:
                try:
                    await on_category_added(n, args)
                except Exception:  # noqa: BLE001 — streaming is best-effort, never fail the tool
                    logger.warning("audit tool: on_category_added emit failed", exc_info=True)
            return _text({
                "status": "category_added",
                "category": args.get("label") or args.get("id") or "",
                "categories_so_far": n,
                "next": "Add the next category, or call FinalizeAuditReport once all are in.",
            })

        @tool(
            name="FinalizeAuditReport",
            description=(
                "Finish and deliver the report. Call this LAST, once all categories have been "
                "added via AddAuditCategory. Provide the cross-cutting synthesis: top_priorities "
                "(reference category findings by id), wins, roadmap, strategic_narrative. The "
                "backend assembles, validates and publishes the full report."
            ),
            input_schema=AuditReportFinalize.model_json_schema(),
        )
        async def finalize_audit_report(args: dict) -> dict:
            if not draft.get("categories"):
                return _err(
                    "No categories recorded. Call StartAuditReport, then AddAuditCategory "
                    "for each category, before FinalizeAuditReport."
                )
            from datetime import datetime, timezone
            merged = {
                **draft,
                **args,
                "url": crawl_result.plan.root_url,
                "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
            logger.info("audit tool: FinalizeAuditReport — %d categories, %d priorities, %d roadmap phases",
                        len(draft.get("categories") or []),
                        len(args.get("top_priorities") or []),
                        len(args.get("roadmap") or []))
            try:
                if on_submit_report:
                    return _text(await on_submit_report(merged))
                return _text({"status": "received"})
            except Exception as exc:  # noqa: BLE001 — keep the agent loop alive (SDK docs)
                logger.exception("FinalizeAuditReport: report assembly failed")
                return _err(
                    f"Report assembly failed ({exc}). Re-check the fields and call "
                    "FinalizeAuditReport again."
                )

        @tool(
            name="SubmitAuditReport",
            description=(
                "Re-submit the FULL updated report as a single structured object. Use this only "
                "during chat, when the user asks for changes or you discover new evidence — it "
                "issues a new numbered version. For the initial build use StartAuditReport / "
                "AddAuditCategory / FinalizeAuditReport instead."
            ),
            input_schema=StructuredAuditData.model_json_schema(),
        )
        async def submit_audit_report(args: dict) -> dict:
            logger.info("audit tool: SubmitAuditReport (full-object path) — %d categories",
                        len(args.get("categories") or []))
            if on_submit_report:
                return _text(await on_submit_report(args))
            return _text({"status": "received"})

        tools.extend([
            start_audit_report,
            add_audit_category,
            finalize_audit_report,
            submit_audit_report,
        ])

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
