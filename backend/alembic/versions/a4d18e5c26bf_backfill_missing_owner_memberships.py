"""backfill owner membership rows for projects that never got one

Revision ID: a4d18e5c26bf
Revises: c7e4b2a19d63
Create Date: 2026-09-02 00:00:00.000000

`f1c7b4d92a08` created `project_members` and backfilled one owner row per
existing project. On at least one database the table landed but the backfill
did not, leaving a project created before that migration with no member row at
all. The symptom is not a permission error, which is what makes it expensive:
`member_role` falls back to `projects.user_id`, so the owner can still open the
project by id, while `accessible_projects` inner-joins membership and drops it
from every list and picker. One missing bookkeeping row reads as a deleted
project.

The repair belongs here rather than in the query, because membership is the
authorization boundary: teaching the list query to accept ownership would put a
second, weaker rule beside the one the routes enforce. Backfilling restores the
invariant the rest of the code is entitled to assume — every project has a
complete member list.

Idempotent, so it is safe on a database that `f1c7b4d92a08` already covered.
Written through the connection with Python-side UUIDs rather than
`gen_random_uuid()`, because the desktop sidecar runs these same migrations
against SQLite, which has no such function.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = 'a4d18e5c26bf'
down_revision = 'c7e4b2a19d63'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    missing = bind.execute(
        sa.text(
            """
            SELECT p.id, p.user_id
            FROM projects p
            WHERE p.user_id IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM project_members m
                  WHERE m.project_id = p.id AND m.user_id = p.user_id
              )
            """
        )
    ).fetchall()

    if not missing:
        return

    now = datetime.now(timezone.utc)
    for project_id, user_id in missing:
        # A project that somehow has an owner row for a DIFFERENT user is left
        # alone: uq_project_members_single_owner would reject the insert, and a
        # contested owner is a decision, not a backfill.
        conflicting_owner = bind.execute(
            sa.text(
                "SELECT 1 FROM project_members "
                "WHERE project_id = :pid AND role = 'owner'"
            ),
            {"pid": project_id},
        ).first()
        if conflicting_owner is not None:
            continue
        bind.execute(
            sa.text(
                """
                INSERT INTO project_members
                    (id, project_id, user_id, role, created_at, updated_at)
                VALUES (:id, :pid, :uid, 'owner', :now, :now)
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "pid": project_id,
                "uid": user_id,
                "now": now,
            },
        )


def downgrade() -> None:
    # Deliberately empty. The rows this adds are indistinguishable from the ones
    # `f1c7b4d92a08` was meant to create, and dropping them would re-open the
    # bug on a database that only ever had the correct state.
    pass
