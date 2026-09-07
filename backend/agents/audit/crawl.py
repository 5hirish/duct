"""The audit's engine-neutral core: the session, the crawl, and report parsing.

None of this depends on which harness runs synthesis. It lived in
``agents/audit/v3/runner.py`` because V3 was the only engine when it was
written, which left V1 importing from the module it was meant to replace — and
would have taken a working crawler down with the Claude Agent SDK.

``get_session`` and ``close_session`` are not re-exported here: they are
``agents.core.session``'s, shared with every other agent, and callers should
say so.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any

from agents.audit.schema import AuditReport, AuditSession, CrawlResult
from agents.core.session import register_session
from service.crawl.extractor import extract_signals
from service.crawl.fetcher import SiteUnreachableError, fetch, fetch_text, make_client
from service.crawl.sitemap import fetch_crawl_plan

logger = logging.getLogger(__name__)

EmitFn = Callable[[dict[str, Any]], Awaitable[None]]


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------

def create_audit_session(session_id: str, agent_type: str = "audit_seo") -> AuditSession:
    """Create and register a new AuditSession with both queues.

    Call this before starting run_pipeline so the SSE stream endpoint can
    connect to event_queue independently of when the pipeline starts.
    """
    session = AuditSession(
        session_id=session_id,
        agent_type=agent_type,
        event_queue=asyncio.Queue(),   # agent → SSE consumer
        chat_queue=asyncio.Queue(),    # user messages → agent
        answer_future=None,
    )
    return register_session(session)


# ---------------------------------------------------------------------------
# Crawl
# ---------------------------------------------------------------------------

async def _fetch_and_extract(client: Any, url: str, page_type: str) -> Any:
    result = await fetch(client, url)
    signals = extract_signals(result.text, url, page_type, response_headers=result.headers)
    signals.http_status = result.status
    signals.ttfb_ms = result.ttfb_ms
    signals.redirect_chain = result.redirect_chain
    return signals


async def run_crawl(
    root_url: str,
    max_blog_posts: int = 5,
    light: bool = False,
    emit: EmitFn | None = None,
) -> CrawlResult:
    async with make_client() as client:
        plan = await fetch_crawl_plan(client, root_url, max_blog_posts=max_blog_posts, light=light)

        # Fetch robots.txt + llms.txt concurrently. llms.txt may not exist; SPAs
        # often return a 200 HTML page for unknown paths, so treat an HTML
        # response as "not found".
        from service.crawl.sitemap import _is_html_body
        robots_coro = fetch_text(client, plan.robots_txt_url)
        llms_coro = fetch_text(client, plan.llms_txt_url)
        (robots_text, _), (llms_raw, _) = await asyncio.gather(robots_coro, llms_coro)
        llms_text = "" if _is_html_body(llms_raw) else llms_raw

        all_urls = (
            [(url, "landing_page") for url in plan.landing_pages]
            + [(url, "blog_post") for url in plan.blog_posts]
        )
        tasks = [_fetch_and_extract(client, url, ptype) for url, ptype in all_urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    pages = []
    errors = []
    for idx, result in enumerate(results):
        if isinstance(result, Exception):
            url = all_urls[idx][0]
            logger.warning("crawl: failed to fetch %s: %s", url, result)
            errors.append(f"{url}: {result}")
        else:
            pages.append(result)

    # `fetch` swallows connection failures into status 0 so one dead page
    # cannot sink a crawl. The root is different: with no response from it
    # there is no site to audit, and synthesis would score an empty page
    # (it did — 84 "good" for a homepage that never answered).
    root = next((p for p in pages if p.url == plan.root_url), None)
    if root is None or root.http_status == 0:
        raise SiteUnreachableError(plan.root_url)

    return CrawlResult(
        plan=plan,
        robots_txt=robots_text,
        llms_txt=llms_text,
        pages=pages,
        crawl_errors=errors,
    )


# ---------------------------------------------------------------------------
# Report parsing — freehand mode delivers the report as text, not tool calls
# ---------------------------------------------------------------------------

def parse_report(text: str) -> AuditReport | None:
    """Parse an AuditReport out of model output, repairing what models get wrong.

    A plain ``json.loads`` fails on the one mistake models reliably make here:
    ``html_report`` is a whole HTML document, and its quotes come back
    unescaped. Falling back to stripping that field keeps the rest of the
    report rather than losing a finished audit to its cover page.
    """
    stripped = text.strip()

    fenced = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", stripped, re.DOTALL)
    if fenced:
        stripped = fenced.group(1).strip()

    start = stripped.find("{")
    end = stripped.rfind("}") + 1
    if start == -1 or end == 0:
        logger.error("audit: no JSON object found in synthesis output (len=%d)", len(stripped))
        return None

    candidate = stripped[start:end]

    try:
        return AuditReport.model_validate_json(candidate)
    except Exception:
        pass

    try:
        return AuditReport.model_validate(json.loads(candidate))
    except Exception as exc:
        logger.warning("audit: standard JSON parse failed (%s) — trying html_report strip", exc)

    html_stripped = re.sub(
        r',?\s*"html_report"\s*:\s*"(?:[^"\\]|\\.)*"',
        "",
        candidate,
        flags=re.DOTALL,
    )
    try:
        raw = json.loads(html_stripped)
        raw.setdefault("html_report", "")
        report = AuditReport.model_validate(raw)
        logger.info("audit: parsed report after stripping html_report field")
        return report
    except Exception as exc2:
        logger.error("audit: all parse attempts failed: %s", exc2)
        return None


def extract_report_update(text: str, base: AuditReport | None = None) -> AuditReport | None:
    """Pull revised HTML out of an <audit_report_update> tag in a chat turn."""
    match = re.search(r"<audit_report_update>\s*([\s\S]+?)\s*</audit_report_update>", text)
    if not match:
        return None
    return AuditReport(
        url=base.url if base else "",
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        update_label="",
        executive_summary="",
        html_report=match.group(1).strip(),
    )


__all__ = [
    "EmitFn",
    "create_audit_session",
    "extract_report_update",
    "parse_report",
    "run_crawl",
]
