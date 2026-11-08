"""memory: growth stage is a status with its label

Revision ID: f72fc0f0ffc2
Revises: d315e87ea41a
Create Date: 2026-11-08 16:44:49.377409

Data only. The project profile's growth stage was mirrored into memory as a
``milestone`` titled with its stored code ("Next growth milestone:
0_pre_customer"). A milestone is an event and never supersedes, so every
edit of the field added another row. The seed now writes a ``status`` under
``business:growth_stage`` with the option's label (service/memory.py); this
rewrites the rows already written to match. Per project the newest becomes
the current status and the older ones are archived, which keeps them in the
table and out of every reader.

The content hash is recomputed with the same formula as
``service.memory.content_hash`` (frozen here, as a migration must be), so the
next save of an unchanged profile finds this row instead of writing a twin.
SQLite-safe: plain UPDATEs, because the desktop sidecar runs this too.
"""
from __future__ import annotations

import hashlib
import re
import uuid

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f72fc0f0ffc2'
down_revision = 'd315e87ea41a'
branch_labels = None
depends_on = None

_OLD_PREFIX = "Next growth milestone: "
_LABELS = {
    "0_pre_customer": "No customers or active users yet",
    "1_first_users": "First active users/customers (1-10)",
    "2_early_revenue": "Early repeat usage or revenue (10-100 customers)",
    "3_repeatable_growth": "Repeatable growth motion (100+ customers or steady MoM growth)",
    "4_scaling": "Scaling across channels or segments with predictable performance",
}
_ENTITY, _ATTRIBUTE = "business:growth_stage", "stage"


def _hash(project_id, title: str) -> str:
    normalized = re.sub(r"\s+", " ", title.strip().lower())
    parts = ["project", str(uuid.UUID(str(project_id))), "status", normalized, _ENTITY, _ATTRIBUTE, ""]
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT id, project_id, title FROM project_memories "
            "WHERE scope = 'project' AND kind = 'milestone' AND title LIKE :prefix "
            "ORDER BY project_id, observed_at"
        ),
        {"prefix": _OLD_PREFIX + "%"},
    ).fetchall()

    by_project: dict = {}
    for row in rows:
        by_project.setdefault(row.project_id, []).append(row)

    for project_id, entries in by_project.items():
        *older, newest = entries
        for row in older:
            conn.execute(
                sa.text("UPDATE project_memories SET status = 'archived' WHERE id = :id"),
                {"id": row.id},
            )
        code = newest.title[len(_OLD_PREFIX):].strip()
        title = f"Growth stage: {_LABELS.get(code, code)}"
        conn.execute(
            sa.text(
                "UPDATE project_memories SET kind = 'status', title = :title, "
                "entity_key = :entity, attribute = :attribute, state_key = :state_key, "
                "content_hash = :hash WHERE id = :id"
            ),
            {
                "id": newest.id,
                "title": title,
                "entity": _ENTITY,
                "attribute": _ATTRIBUTE,
                "state_key": f"{_ENTITY}|{_ATTRIBUTE}|",
                "hash": _hash(project_id, title),
            },
        )


def downgrade() -> None:
    # Nothing to undo that matters: the old shape was the bug. The rewritten
    # rows stay valid memory under the previous code, which reads any kind.
    pass
