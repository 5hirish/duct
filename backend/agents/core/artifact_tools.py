"""Prior-artifact reads and generic artifact writes, as LangChain tools.

The binder half of ``agents/core/memory_tools.py``'s pattern, for the project
artifact library rather than project memory: read what earlier runs produced,
and write memos, datasets, diagrams and pages the user can open, version and
download. Scoped to one already-membership-checked project.

Write model, which is the industry convention and worth stating because the
tool descriptions depend on it: storage always holds full-version snapshots,
and ``UpdateArtifact``'s exact-string edits are a token-saving *transport* over
that, with a documented fallback to ``RewriteArtifact`` whenever a match fails
or is ambiguous. Reports are excluded from the write tools throughout — they
have their own validated revision flow, and letting a free-text edit touch one
would bypass the scoring the report depends on.

DB access runs in a thread: the sessions are sync SQLModel, and a tool call
must never block the streaming event loop. Every failure comes back as tool
*text* rather than an exception, so the model can read the problem and retry
instead of the run ending.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable
from uuid import UUID

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_TYPES_LINE = (
    "Allowed content types: text/markdown (memos/plans/briefs), text/html "
    "(self-contained page), text/csv, text/vnd.mermaid (diagram source), "
    'application/vnd.duct.table+json ({"columns": [...], "rows": [[...]]}), '
    "application/vnd.duct.chart+json (chart spec the app renders), "
    "application/vnd.duct.diff+json (proposed-change preview)."
)


# ---------------------------------------------------------------------------
# Argument schemas — the contract the model sees
# ---------------------------------------------------------------------------

class ListArtifactsArgs(BaseModel):
    kind: str = Field(
        "", description="Filter by artifact kind ('report', 'document', …). Empty = all kinds."
    )


class GetArtifactArgs(BaseModel):
    artifact_id: str = Field(description="The artifact id (UUID) to fetch.")


class CreateArtifactArgs(BaseModel):
    slug: str = Field(
        description="Short kebab-case identifier you coin, e.g. 'keyword-gap-plan'. "
                    "Reused to address this artifact later."
    )
    title: str = Field(description="Human-readable title shown in the library.")
    kind: str = Field(
        "document",
        description="Semantic kind: 'memo' | 'plan' | 'dataset' | 'diagram' | 'document' | 'change_preview'.",
    )
    content_type: str = Field(description="MIME type from the allowed list.")
    content: str = Field(description="The complete artifact source content.")


class TextEdit(BaseModel):
    old_str: str = Field(description="Exact, unique text to replace, whitespace included.")
    new_str: str = Field(description="What replaces it.")


class UpdateArtifactArgs(BaseModel):
    artifact: str = Field(description="Slug, artifact id, or artifact URL to update.")
    edits: list[TextEdit] = Field(
        min_length=1, description="Exact-string replacements to apply in order."
    )
    label: str = Field("", description="Short human label for this version, e.g. 'tightened intro'.")
    expected_version: int = Field(
        0, description="The version you last read (optimistic concurrency; 0 to skip the check)."
    )


class RewriteArtifactArgs(BaseModel):
    artifact: str = Field(description="Slug, artifact id, or artifact URL to rewrite.")
    content: str = Field(description="The complete replacement content.")
    label: str = Field("", description="Short human label for this version.")
    expected_version: int = Field(0, description="The version you last read (0 to skip the check).")


# ---------------------------------------------------------------------------

def artifact_card(row: Any) -> dict:
    """Compact card payload for ARTIFACT_UPDATED events and tool results."""
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


def build_artifact_tools_lc(
    project_id: UUID | None,
    *,
    user_id: UUID | None = None,
    conversation_id: UUID | None = None,
    agent_type: str = "",
    on_artifact: Callable[[dict], Any] | None = None,
) -> list:
    """The five artifact tools as ``StructuredTool``s, or none without a project."""
    from langchain_core.tools import StructuredTool

    if project_id is None:
        return []

    async def _emit_card(row: Any) -> dict:
        card = artifact_card(row)
        if on_artifact is not None:
            try:
                await on_artifact(card)
            except Exception:  # noqa: BLE001 — the card is UI sugar, never fatal
                logger.debug("artifact card emit failed", exc_info=True)
        return card

    def _resolve_writable(db: Any, ref: str):
        from service.artifact_store import resolve_reference

        head = resolve_reference(db, project_id, ref)
        if head is None:
            return None, f"No artifact matching {ref!r} in this project."
        if head.kind == "report":
            return None, "Reports are revised through the report flow, not the artifact write tools."
        return head, None

    # -- reads ---------------------------------------------------------------

    async def list_artifacts(kind: str = "") -> str:
        wanted = (kind or "").strip() or None

        def _query() -> list[dict]:
            from db.session import get_session as db_session
            from service.artifact_store import recent_artifact_summaries

            with next(db_session()) as db:
                rows = recent_artifact_summaries(db, project_id, kind=wanted, limit=10)
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
            return f"Artifact listing failed: {exc}"
        return json.dumps({"artifacts": rows}, indent=2)

    async def get_artifact(artifact_id: str) -> str:
        raw_id = (artifact_id or "").strip()

        def _query() -> dict | None:
            from db.session import get_session as db_session
            from models.artifact import Artifact

            with next(db_session()) as db:
                row = db.get(Artifact, UUID(raw_id))
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
            return f"Artifact fetch failed: {exc}"
        if payload is None:
            return f"No artifact {raw_id!r} in this project."
        return json.dumps(payload, indent=2)

    # -- writes --------------------------------------------------------------

    async def create_artifact(
        slug: str, title: str, content_type: str, content: str, kind: str = "document"
    ) -> str:
        from service.artifact_store import AGENT_WRITABLE_TYPES

        ctype = (content_type or "").strip()
        if ctype not in AGENT_WRITABLE_TYPES:
            return f"Unsupported content_type {ctype!r}. {_TYPES_LINE}"
        if (kind or "") == "report":
            return "Reports are produced via the report flow, not CreateArtifact."

        def _create():
            from db.session import get_session as db_session
            from service.artifact_store import create_artifact_group

            with next(db_session()) as db:
                return create_artifact_group(
                    db,
                    project_id=project_id,
                    user_id=user_id,
                    agent_type=agent_type,
                    kind=(kind or "document").strip() or "document",
                    content_type=ctype,
                    title=(title or "").strip(),
                    content=str(content or ""),
                    slug=(slug or "").strip(),
                    conversation_id=conversation_id,
                )

        try:
            row = await asyncio.to_thread(_create)
        except ValueError as exc:
            return f"Create failed: {exc}"
        except Exception as exc:  # noqa: BLE001
            return f"Create failed unexpectedly: {exc}"
        return json.dumps({"created": await _emit_card(row)}, indent=2)

    async def update_artifact(
        artifact: str, edits: list, label: str = "", expected_version: int = 0
    ) -> str:
        # LangChain hands nested models as instances; the store wants plain dicts.
        payload = [e if isinstance(e, dict) else e.model_dump() for e in (edits or [])]

        def _update():
            from db.session import get_session as db_session
            from service.artifact_store import (
                ArtifactConflict,
                apply_text_edits,
                artifact_text_content,
                revise_artifact,
            )

            with next(db_session()) as db:
                head, err = _resolve_writable(db, str(artifact or ""))
                if err:
                    return None, err
                patched, edit_errors = apply_text_edits(artifact_text_content(head), payload)
                if edit_errors:
                    return None, (
                        "Edits not applied:\n- " + "\n- ".join(edit_errors)
                        + "\nFix the edits or fall back to RewriteArtifact with the full content."
                    )
                try:
                    row = revise_artifact(
                        db, head, content=patched, label=(label or "").strip(),
                        expected_version=int(expected_version or 0) or None,
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
            return f"Update failed unexpectedly: {exc}"
        if err:
            return err
        return json.dumps({"updated": await _emit_card(row)}, indent=2)

    async def rewrite_artifact(
        artifact: str, content: str, label: str = "", expected_version: int = 0
    ) -> str:
        def _rewrite():
            from db.session import get_session as db_session
            from service.artifact_store import ArtifactConflict, revise_artifact

            with next(db_session()) as db:
                head, err = _resolve_writable(db, str(artifact or ""))
                if err:
                    return None, err
                try:
                    row = revise_artifact(
                        db, head, content=str(content or ""), label=(label or "").strip(),
                        expected_version=int(expected_version or 0) or None,
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
            return f"Rewrite failed unexpectedly: {exc}"
        if err:
            return err
        return json.dumps({"rewritten": await _emit_card(row)}, indent=2)

    return [
        StructuredTool.from_function(
            coroutine=list_artifacts,
            name="ListArtifacts",
            description=(
                "List stored artifacts for this project (prior audit reports, documents) — "
                "id, title, kind, version, date, and an AI summary of each. Use it to recall "
                "what earlier runs found before repeating analysis, or to compare then vs now. "
                "Pass kind='report' for audit reports only, or an empty kind for everything."
            ),
            args_schema=ListArtifactsArgs,
        ),
        StructuredTool.from_function(
            coroutine=get_artifact,
            name="GetArtifact",
            description=(
                "Fetch one stored artifact's full structured payload by artifact_id (from "
                "ListArtifacts or the <prior_reports> block). Returns the structured report "
                "data plus metadata — use it to cite specific prior findings or scores."
            ),
            args_schema=GetArtifactArgs,
        ),
        StructuredTool.from_function(
            coroutine=create_artifact,
            name="CreateArtifact",
            description=(
                "Create a durable artifact for this project — a memo, dataset, diagram, "
                "or page the user can open, version, and download from their library. "
                "Choose a short kebab-case slug you will reuse to reference it later. "
                + _TYPES_LINE
                + " Audit reports are NOT created here — they go through the report flow."
            ),
            args_schema=CreateArtifactArgs,
        ),
        StructuredTool.from_function(
            coroutine=update_artifact,
            name="UpdateArtifact",
            description=(
                "Apply small targeted edits to an existing artifact (NOT reports). Each edit "
                "replaces one exact, unique old_str with new_str — include enough surrounding "
                "context to make old_str unique, matching whitespace exactly. Use for changes "
                "touching a few places; for anything larger, or if edits fail to match, use "
                "RewriteArtifact instead. Every successful update stores a new full version."
            ),
            args_schema=UpdateArtifactArgs,
        ),
        StructuredTool.from_function(
            coroutine=rewrite_artifact,
            name="RewriteArtifact",
            description=(
                "Replace an existing artifact's entire content with a new full version "
                "(NOT reports). Use when changes are broad, or when UpdateArtifact edits "
                "failed to match. Stores a new version; history is preserved."
            ),
            args_schema=RewriteArtifactArgs,
        ),
    ]


__all__ = ["artifact_card", "build_artifact_tools_lc"]
