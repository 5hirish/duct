"""projects: fold drafted pillars into the one pillar list

Revision ID: 7f3b9c1d2e4a
Revises: b8e2d4f1a913
Create Date: 2026-11-09 18:00:00.000000

Data only. Pillars had two homes. A draft (the crawl, the person's files, an
outside agent through the MCP server) wrote ``brand_channels.content_pillars``,
a list of names; the Brand tab wrote ``content_pillars.items``, rows with an id
and a description; the content planner read only the second. Pillars an agent
wrote for a project never reached its plans. ``service/project_draft.py`` now
lands drafts in ``content_pillars.items``, and this moves what the old key
holds there, per project:

* no rows yet: the drafted names become rows, and keep the label that says
  where they came from;
* rows already: the rows win, being what every plan so far was made from and
  what the person edits. The label described the names, so it goes, and the
  rows count as the person's, as an unlabelled filled field does (rule 3);
* either way the old key is removed.

The row shape and the id rule are frozen here, as a migration's must be
(``service.project_draft.pillar_rows`` is the live copy). SQLite-safe: the
desktop sidecar runs this too.
"""
from __future__ import annotations

import re

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision = '7f3b9c1d2e4a'
down_revision = 'b8e2d4f1a913'
branch_labels = None
depends_on = None

_KEY = "content_pillars"


def _json():
    return sa.JSON().with_variant(JSONB(astext_type=sa.Text()), "postgresql")


_projects = sa.table(
    "projects",
    sa.column("id"),
    sa.column("brand_channels", _json()),
    sa.column("content_pillars", _json()),
    sa.column("provenance", _json()),
)


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:60].rstrip("_")


def _rows(names) -> list[dict]:
    rows, seen = [], set()
    for raw in names if isinstance(names, list) else []:
        name = str(raw or "").strip()
        if name and name.lower() not in seen:
            seen.add(name.lower())
            rows.append({"id": _slug(name), "name": name, "description": ""})
    return rows


def upgrade() -> None:
    conn = op.get_bind()
    for row in conn.execute(sa.select(_projects)).fetchall():
        channels = dict(row.brand_channels or {})
        if _KEY not in channels:
            continue
        drafted = _rows(channels.pop(_KEY))
        stored = row.content_pillars
        # A seeded project may hold bare rows; the planner reads both shapes.
        pillars = dict(stored) if isinstance(stored, dict) else {"items": stored} if isinstance(stored, list) else {}
        labels = dict(row.provenance or {})
        if pillars.get("items"):
            labels.pop(_KEY, None)
        elif drafted:
            pillars["items"] = drafted
        else:
            labels.pop(_KEY, None)
        conn.execute(
            _projects.update()
            .where(_projects.c.id == row.id)
            .values(brand_channels=channels, content_pillars=pillars, provenance=labels)
        )


def downgrade() -> None:
    # The previous code's drafts read and wrote the names under the old key;
    # the rows stay, since that code's planner reads them.
    conn = op.get_bind()
    for row in conn.execute(sa.select(_projects)).fetchall():
        stored = row.content_pillars
        items = stored.get("items") if isinstance(stored, dict) else stored if isinstance(stored, list) else None
        names = [str(p.get("name")) for p in items or [] if isinstance(p, dict) and p.get("name")]
        if not names:
            continue
        conn.execute(
            _projects.update()
            .where(_projects.c.id == row.id)
            .values(brand_channels={**(row.brand_channels or {}), _KEY: names})
        )
