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
from agents.core.memory_tools import build_memory_tools_sdk
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
    project_id=None,          # UUID | None — mounts the artifact + memory tools when set
    artifact_user_id=None,    # UUID | None — attribution for artifact writes
    artifact_conversation_id=None,  # UUID | None — chat linkage for artifact writes
    on_artifact=None,         # async (card: dict) -> None — in-chat artifact card emit
    on_memory=None,           # async (entry: dict) -> None — "Remembered: …" line emit
) -> McpSdkServerConfig:
    """Build the in-process MCP server scoped to this audit session's site.

    The returned config is passed to ClaudeAgentOptions.mcp_servers so the
    agent can call FetchPages during chat without making arbitrary HTTP requests.

    project_id comes from the session's membership-checked artifact scope
    (routes.agents stamps it only after verifying the caller belongs to the
    project) — it gates the prior-artifact read tools.
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
    if project_id is not None:
        tools.extend(_build_artifact_tools(
            project_id,
            user_id=artifact_user_id,
            conversation_id=artifact_conversation_id,
            on_artifact=on_artifact,
        ))
        # Memory is cross-agent, so the tools come from agents/core rather than
        # being redefined per agent type.
        tools.extend(build_memory_tools_sdk(
            project_id,
            user_id=artifact_user_id,
            conversation_id=artifact_conversation_id,
            agent_type="audit_seo",
            on_memory=on_memory,
        ))

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


def _artifact_card(row) -> dict:
    """Compact card payload for ARTIFACT_UPDATED SSE events + tool results."""
    return {
        "artifact_id": str(row.id),
        "group_id": str(row.group_id),
        "slug": row.slug,
        "kind": row.kind,
        "content_type": row.content_type,
        "title": row.title,
        "version": row.version,
        "label": (row.meta or {}).get("label", ""),
    }


def _build_artifact_tools(project_id, *, user_id=None, conversation_id=None, on_artifact=None) -> list:
    """Prior-artifact read tools + generic artifact write tools, scoped to one
    membership-checked project.

    Write model (industry convention): full-version snapshots in storage;
    UpdateArtifact's exact-string edits are a token-saving transport with
    aggressive fallback to RewriteArtifact on any failed/ambiguous match.
    Reports are excluded from the write tools — they have their own validated
    revision flow (SubmitAuditReport). DB access runs in a thread (sync
    SQLModel session) so tool calls never block the streaming event loop.
    on_artifact: async callback(card: dict) — emits the in-chat artifact card.
    """

    @tool(
        name="ListArtifacts",
        description=(
            "List stored artifacts for this project (prior audit reports, documents) — "
            "id, title, kind, version, date, and an AI summary of each. Use it to recall "
            "what earlier audits found before repeating analysis, or to compare then vs now. "
            "Pass kind='report' for audit reports only, or an empty kind for everything."
        ),
        input_schema={
            "kind": Annotated[str, "Filter by artifact kind ('report', 'document', …). Empty = all kinds."],
        },
    )
    async def list_artifacts(args: dict) -> dict:
        kind = (args.get("kind") or "").strip() or None

        def _query() -> list[dict]:
            from db.session import get_session as db_session
            from service.artifact_store import recent_artifact_summaries

            with next(db_session()) as db:
                rows = recent_artifact_summaries(db, project_id, kind=kind, limit=10)
                return [
                    {
                        "artifact_id": str(r.id),
                        "title": r.title,
                        "kind": r.kind,
                        "version": r.version,
                        "created_at": r.created_at.isoformat() if r.created_at else "",
                        "summary": r.summary or "(no summary yet)",
                        "meta": r.meta,
                    }
                    for r in rows
                ]

        try:
            rows = await asyncio.to_thread(_query)
        except Exception as exc:  # noqa: BLE001 — tool errors return text, never raise
            return {"content": [{"type": "text", "text": f"Artifact listing failed: {exc}"}]}
        return {"content": [{"type": "text", "text": json.dumps({"artifacts": rows}, indent=2)}]}

    @tool(
        name="GetArtifact",
        description=(
            "Fetch one stored artifact's full structured payload by artifact_id (from "
            "ListArtifacts or the <prior_reports> block). Returns the structured report "
            "data plus metadata — use it to cite specific prior findings or scores."
        ),
        input_schema={
            "artifact_id": Annotated[str, "The artifact id (UUID) to fetch."],
        },
    )
    async def get_artifact(args: dict) -> dict:
        raw_id = (args.get("artifact_id") or "").strip()

        def _query() -> dict | None:
            from uuid import UUID as _UUID

            from db.session import get_session as db_session
            from models.artifact import Artifact

            with next(db_session()) as db:
                row = db.get(Artifact, _UUID(raw_id))
                # Scope check: only artifacts of THIS session's project.
                if row is None or row.project_id != project_id:
                    return None
                return {
                    "artifact_id": str(row.id),
                    "title": row.title,
                    "kind": row.kind,
                    "version": row.version,
                    "created_at": row.created_at.isoformat() if row.created_at else "",
                    "summary": row.summary,
                    "meta": row.meta,
                    "structured_json": row.structured_json,
                }

        try:
            payload = await asyncio.to_thread(_query)
        except Exception as exc:  # noqa: BLE001
            return {"content": [{"type": "text", "text": f"Artifact fetch failed: {exc}"}]}
        if payload is None:
            return {"content": [{"type": "text", "text": f"No artifact {raw_id!r} in this project."}]}
        return {"content": [{"type": "text", "text": json.dumps(payload, indent=2)}]}

    # ------------------------------------------------------------------
    # Write tools — create / update (patch transport) / rewrite
    # ------------------------------------------------------------------

    async def _emit_card(row) -> dict:
        card = _artifact_card(row)
        if on_artifact is not None:
            try:
                await on_artifact(card)
            except Exception:  # noqa: BLE001 — the card is UI sugar, never fatal
                logger.debug("artifact card emit failed", exc_info=True)
        return card

    _TYPES_LINE = (
        "Allowed content types: text/markdown (memos/plans/briefs), text/html "
        "(self-contained page), text/csv, text/vnd.mermaid (diagram source), "
        "application/vnd.duct.table+json ({\"columns\": [...], \"rows\": [[...]]}), "
        "application/vnd.duct.chart+json (chart spec the app renders), "
        "application/vnd.duct.diff+json (proposed-change preview)."
    )

    @tool(
        name="CreateArtifact",
        description=(
            "Create a durable artifact for this project — a memo, dataset, diagram, "
            "or page the user can open, version, and download from their library. "
            "Choose a short kebab-case slug you will reuse to reference it later. "
            + _TYPES_LINE
            + " Audit reports are NOT created here — they go through the report flow."
        ),
        input_schema={
            "slug": Annotated[str, "Short kebab-case identifier you coin, e.g. 'keyword-gap-plan'. Reused to address this artifact later."],
            "title": Annotated[str, "Human-readable title shown in the library."],
            "kind": Annotated[str, "Semantic kind: 'memo' | 'plan' | 'dataset' | 'diagram' | 'document' | 'change_preview'."],
            "content_type": Annotated[str, "MIME type from the allowed list."],
            "content": Annotated[str, "The complete artifact source content."],
        },
    )
    async def create_artifact(args: dict) -> dict:
        from service.artifact_store import AGENT_WRITABLE_TYPES

        content_type = (args.get("content_type") or "").strip()
        if content_type not in AGENT_WRITABLE_TYPES:
            return {"content": [{"type": "text", "text": f"Unsupported content_type {content_type!r}. {_TYPES_LINE}"}]}
        if (args.get("kind") or "") == "report":
            return {"content": [{"type": "text", "text": "Reports are produced via the report flow, not CreateArtifact."}]}

        def _create():
            from db.session import get_session as db_session
            from service.artifact_store import create_artifact_group

            with next(db_session()) as db:
                return create_artifact_group(
                    db,
                    project_id=project_id,
                    user_id=user_id,
                    agent_type="audit_seo",
                    kind=(args.get("kind") or "document").strip() or "document",
                    content_type=content_type,
                    title=(args.get("title") or "").strip(),
                    content=str(args.get("content") or ""),
                    slug=(args.get("slug") or "").strip(),
                    conversation_id=conversation_id,
                )

        try:
            row = await asyncio.to_thread(_create)
        except ValueError as exc:
            return {"content": [{"type": "text", "text": f"Create failed: {exc}"}]}
        except Exception as exc:  # noqa: BLE001
            return {"content": [{"type": "text", "text": f"Create failed unexpectedly: {exc}"}]}
        card = await _emit_card(row)
        return {"content": [{"type": "text", "text": json.dumps({"created": card}, indent=2)}]}

    def _resolve_writable(db, ref: str):
        from service.artifact_store import resolve_reference

        head = resolve_reference(db, project_id, ref)
        if head is None:
            return None, f"No artifact matching {ref!r} in this project."
        if head.kind == "report":
            return None, "Reports are revised through the report flow, not the artifact write tools."
        return head, None

    @tool(
        name="UpdateArtifact",
        description=(
            "Apply small targeted edits to an existing artifact (NOT reports). Each edit "
            "replaces one exact, unique old_str with new_str — include enough surrounding "
            "context to make old_str unique, matching whitespace exactly. Use for changes "
            "touching a few places; for anything larger, or if edits fail to match, use "
            "RewriteArtifact instead. Every successful update stores a new full version."
        ),
        input_schema={
            "artifact": Annotated[str, "Slug, artifact id, or artifact URL to update."],
            "edits": Annotated[list[dict], "List of {old_str, new_str} exact-string replacements."],
            "label": Annotated[str, "Short human label for this version, e.g. 'tightened intro'."],
            "expected_version": Annotated[int, "The version you last read (optimistic concurrency; 0 to skip the check)."],
        },
    )
    async def update_artifact(args: dict) -> dict:
        def _update():
            from db.session import get_session as db_session
            from service.artifact_store import (
                ArtifactConflict,
                apply_text_edits,
                artifact_text_content,
                revise_artifact,
            )

            with next(db_session()) as db:
                head, err = _resolve_writable(db, str(args.get("artifact") or ""))
                if err:
                    return None, err
                source = artifact_text_content(head)
                patched, edit_errors = apply_text_edits(source, args.get("edits") or [])
                if edit_errors:
                    return None, (
                        "Edits not applied:\n- " + "\n- ".join(edit_errors)
                        + "\nFix the edits or fall back to RewriteArtifact with the full content."
                    )
                expected = int(args.get("expected_version") or 0) or None
                try:
                    row = revise_artifact(
                        db, head, content=patched,
                        label=(args.get("label") or "").strip(),
                        expected_version=expected,
                        user_id=user_id, conversation_id=conversation_id,
                    )
                except ArtifactConflict as exc:
                    return None, str(exc)
                except ValueError as exc:
                    return None, f"Update rejected: {exc}"
                return row, None

        try:
            row, err = await asyncio.to_thread(_update)
        except Exception as exc:  # noqa: BLE001
            return {"content": [{"type": "text", "text": f"Update failed unexpectedly: {exc}"}]}
        if err:
            return {"content": [{"type": "text", "text": err}]}
        card = await _emit_card(row)
        return {"content": [{"type": "text", "text": json.dumps({"updated": card}, indent=2)}]}

    @tool(
        name="RewriteArtifact",
        description=(
            "Replace an existing artifact's entire content with a new full version "
            "(NOT reports). Use when changes are broad, or when UpdateArtifact edits "
            "failed to match. Stores a new version; history is preserved."
        ),
        input_schema={
            "artifact": Annotated[str, "Slug, artifact id, or artifact URL to rewrite."],
            "content": Annotated[str, "The complete replacement content."],
            "label": Annotated[str, "Short human label for this version."],
            "expected_version": Annotated[int, "The version you last read (0 to skip the check)."],
        },
    )
    async def rewrite_artifact(args: dict) -> dict:
        def _rewrite():
            from db.session import get_session as db_session
            from service.artifact_store import ArtifactConflict, revise_artifact

            with next(db_session()) as db:
                head, err = _resolve_writable(db, str(args.get("artifact") or ""))
                if err:
                    return None, err
                expected = int(args.get("expected_version") or 0) or None
                try:
                    row = revise_artifact(
                        db, head, content=str(args.get("content") or ""),
                        label=(args.get("label") or "").strip(),
                        expected_version=expected,
                        user_id=user_id, conversation_id=conversation_id,
                    )
                except ArtifactConflict as exc:
                    return None, str(exc)
                except ValueError as exc:
                    return None, f"Rewrite rejected: {exc}"
                return row, None

        try:
            row, err = await asyncio.to_thread(_rewrite)
        except Exception as exc:  # noqa: BLE001
            return {"content": [{"type": "text", "text": f"Rewrite failed unexpectedly: {exc}"}]}
        if err:
            return {"content": [{"type": "text", "text": err}]}
        card = await _emit_card(row)
        return {"content": [{"type": "text", "text": json.dumps({"rewritten": card}, indent=2)}]}

    return [list_artifacts, get_artifact, create_artifact, update_artifact, rewrite_artifact]


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
