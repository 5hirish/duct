"""Audit tools as LangChain tools (V1 engine).

Port of ``agents/audit/tools.py``, which builds the same tools as a
Claude-Agent-SDK in-process MCP server. LangChain takes plain Python callables,
so the MCP server, its bootstrap and its hand-written JSON Schema all go away —
see `the engine consolidation review (duct-cloud, private)` §9.4.

What is deliberately identical to the SDK version:

* the tool names and descriptions the model sees (behaviour parity),
* the ``draft`` accumulator that lets the model build a report incrementally
  across StartAuditReport → AddAuditCategory → FinalizeAuditReport,
* the ``on_submit_report`` / ``on_category_added`` callbacks the runner uses to
  publish versions and stream live progress,
* returning an error *payload* rather than raising, so a bad call lets the agent
  loop continue and retry instead of failing the whole run.

What differs: tools take typed Pydantic arguments instead of ``args: dict``
(the schemas already existed — they were being converted to JSON Schema by
hand), and they return a JSON string, which is LangChain's tool-result type.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import urlparse

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

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
_FULL_BODY_CHARS = 5_000  # vs the 500-char snippet in the shallow crawl


class FetchPagesArgs(BaseModel):
    """Arguments for FetchPages — the only audit tool without an existing schema."""

    urls: list[str] = Field(
        description=(
            "List of page URLs to fetch. Must belong to the audited site. "
            f"Maximum {_MAX_URLS_PER_CALL} URLs per call."
        )
    )


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


def _ok(payload: dict) -> str:
    return json.dumps(payload)


def _err(message: str) -> str:
    """Error result the model can react to.

    Returned, not raised: an exception propagates out of the tool node and ends
    the run, whereas a payload lets the model read the problem and retry.
    """
    return json.dumps({"status": "error", "message": message})


def build_audit_tools(
    crawl_result: CrawlResult,
    report_mode: str = "freehand",
    on_submit_report: Callable[[dict], Any] | None = None,
    on_category_added: Callable[[int, dict], Any] | None = None,
) -> list[StructuredTool]:
    """Build the audit tools scoped to this session's site.

    Returns a list for ``create_agent(tools=...)``. ``report_mode="template"``
    adds the incremental report-building tools; ``"freehand"`` exposes only
    FetchPages.
    """
    root_host = urlparse(crawl_result.plan.root_url).netloc.lower().removeprefix("www.")

    async def fetch_pages(urls: list[str]) -> str:
        capped = urls[:_MAX_URLS_PER_CALL]
        valid: list[str] = []
        errors: list[str] = []

        for url in capped:
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
            signals = extract_signals(
                result.text, url, "landing_page", response_headers=result.headers
            )
            signals.http_status = result.status
            signals.ttfb_ms = result.ttfb_ms
            signals.redirect_chain = result.redirect_chain
            signals.body_text_snippet = result.text[:_FULL_BODY_CHARS]
            return signals

        fetched = await asyncio.gather(
            *[_fetch_one(u) for u in valid], return_exceptions=True
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
        return json.dumps(payload, indent=2)

    tools: list[StructuredTool] = [
        StructuredTool.from_function(
            coroutine=fetch_pages,
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
            args_schema=FetchPagesArgs,
        )
    ]

    if report_mode != "template":
        return tools

    # Incremental build accumulator, shared across the Start/Add/Finalize calls
    # for this session. Partial progress survives a mid-build failure.
    draft: dict = {"categories": []}

    async def start_audit_report(**args: Any) -> str:
        draft.clear()
        draft.update(args)
        draft["categories"] = []
        logger.info(
            "audit tool: StartAuditReport — score=%s band=%s",
            args.get("overall_score"), args.get("score_band"),
        )
        return _ok({
            "status": "started",
            "next": "Call AddAuditCategory once for each of the 9 categories, then FinalizeAuditReport.",
        })

    async def add_audit_category(**args: Any) -> str:
        draft.setdefault("categories", []).append(args)
        n = len(draft["categories"])
        logger.info(
            "audit tool: AddAuditCategory '%s' (%d findings) — %d/9 categories",
            args.get("label") or args.get("id") or "?",
            len(args.get("findings") or []), n,
        )
        if on_category_added:
            try:
                await on_category_added(n, args)
            except Exception:  # noqa: BLE001 — streaming is best-effort, never fail the tool
                logger.warning("audit tool: on_category_added emit failed", exc_info=True)
        return _ok({
            "status": "category_added",
            "category": args.get("label") or args.get("id") or "",
            "categories_so_far": n,
        })

    async def finalize_audit_report(**args: Any) -> str:
        if not draft.get("categories"):
            return _err(
                "No categories recorded. Call StartAuditReport, then AddAuditCategory "
                "for each category, before FinalizeAuditReport."
            )
        merged = {
            **draft,
            **args,
            "url": crawl_result.plan.root_url,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        logger.info(
            "audit tool: FinalizeAuditReport — %d categories, %d priorities, %d roadmap phases",
            len(draft.get("categories") or []),
            len(args.get("top_priorities") or []),
            len(args.get("roadmap") or []),
        )
        try:
            if on_submit_report:
                return _ok(await on_submit_report(merged))
            return _ok({"status": "received"})
        except Exception as exc:  # noqa: BLE001 — keep the agent loop alive
            logger.exception("FinalizeAuditReport: report assembly failed")
            return _err(
                f"Report assembly failed ({exc}). Re-check the fields and call "
                "FinalizeAuditReport again."
            )

    async def submit_audit_report(**args: Any) -> str:
        logger.info(
            "audit tool: SubmitAuditReport (full-object path) — %d categories",
            len(args.get("categories") or []),
        )
        if on_submit_report:
            return _ok(await on_submit_report(args))
        return _ok({"status": "received"})

    tools.extend([
        StructuredTool.from_function(
            coroutine=start_audit_report,
            name="StartAuditReport",
            description=(
                "Begin the structured SEO audit report. Call this FIRST, once, after you have "
                "finished analysing the crawl and computed all 9 category scores. Provide the "
                "scorecard header (overall_score, score_band, totals, key_signals, headline). "
                "Then call AddAuditCategory once per category, and FinalizeAuditReport last. "
                "url, generated_at and crawl_summary are filled by the backend — omit them."
            ),
            args_schema=AuditReportStart,
        ),
        StructuredTool.from_function(
            coroutine=add_audit_category,
            name="AddAuditCategory",
            description=(
                "Add ONE category's findings to the report in progress. Call once per category "
                "(all 9), after StartAuditReport. Each call is a single AuditCategory: id, label, "
                "score, tooltip, the four counts, and its findings[]. Order does not matter."
            ),
            args_schema=AuditCategory,
        ),
        StructuredTool.from_function(
            coroutine=finalize_audit_report,
            name="FinalizeAuditReport",
            description=(
                "Finish and deliver the report. Call this LAST, once all categories have been "
                "added via AddAuditCategory. Provide the cross-cutting synthesis: top_priorities "
                "(reference category findings by id), wins, roadmap, strategic_narrative. The "
                "backend assembles, validates and publishes the full report."
            ),
            args_schema=AuditReportFinalize,
        ),
        StructuredTool.from_function(
            coroutine=submit_audit_report,
            name="SubmitAuditReport",
            description=(
                "Re-submit the FULL updated report as a single structured object. Use this only "
                "during chat, when the user asks for changes or you discover new evidence — it "
                "issues a new numbered version. For the initial build use StartAuditReport / "
                "AddAuditCategory / FinalizeAuditReport instead."
            ),
            args_schema=StructuredAuditData,
        ),
    ])
    return tools
