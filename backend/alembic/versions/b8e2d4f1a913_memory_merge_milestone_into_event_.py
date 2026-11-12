"""memory: merge milestone into event, process and tooling into method

Revision ID: b8e2d4f1a913
Revises: f72fc0f0ffc2
Create Date: 2026-11-08 17:22:44.002024

Data only. Three kinds were merged into the one they could not be told apart
from (models/memory.py, LEGACY_KINDS): a milestone is an event with a date,
and method, process and tooling were three names for "how I work". This moves
the rows already stored. Neither old kind took part in supersession in a way
the merge changes (milestones never superseded, and a private row's state key
holds no kind), so only the kind and the content hash move.

The hash is recomputed with the formula in ``service.memory.content_hash``,
frozen here as a migration must be: it covers the kind, and a row left under
its old hash would let the same fact written again land as a twin.
SQLite-safe: plain UPDATEs, because the desktop sidecar runs this too.
"""
from __future__ import annotations

import hashlib
import re
import uuid

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b8e2d4f1a913'
down_revision = 'f72fc0f0ffc2'
branch_labels = None
depends_on = None

_MERGED = {"milestone": "event", "process": "method", "tooling": "method"}


def _uuid(value) -> str:
    return str(uuid.UUID(str(value))) if value else ""


def _hash(row, kind: str) -> str:
    owner = _uuid(row.user_id) if row.scope == "user" else _uuid(row.project_id)
    normalized = re.sub(r"\s+", " ", (row.title or "").strip().lower())
    parts = [row.scope, owner, kind, normalized, row.entity_key or "", row.attribute or "", row.period or ""]
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT id, scope, project_id, user_id, kind, title, entity_key, attribute, period "
            "FROM project_memories WHERE kind IN ('milestone', 'process', 'tooling')"
        )
    ).fetchall()
    for row in rows:
        kind = _MERGED[row.kind]
        conn.execute(
            sa.text("UPDATE project_memories SET kind = :kind, content_hash = :hash WHERE id = :id"),
            {"id": row.id, "kind": kind, "hash": _hash(row, kind)},
        )


def downgrade() -> None:
    # Which of the three a merged row used to be is not recorded, and the
    # previous code reads the merged kinds without complaint.
    pass
