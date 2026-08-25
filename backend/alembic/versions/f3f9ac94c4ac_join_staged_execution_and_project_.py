"""join staged-execution and project-members heads

PR #41 (staged execution change sets) and PR #42 (project members + invitations)
each branched from e9a1c3b7d540 and merged independently, leaving two heads. That
makes `alembic upgrade head` fail with "Multiple head revisions are present", so
any new migration had to pick a side and fork the lineage further.

This is a no-op merge: it only rejoins the two branches so there is a single head
again. No schema change, nothing to reverse.

Revision ID: f3f9ac94c4ac
Revises: a7d2e5f8c941, f1c7b4d92a08
Create Date: 2026-08-22 19:06:06.108521
"""
from __future__ import annotations


# revision identifiers, used by Alembic.
revision = 'f3f9ac94c4ac'
down_revision = ('a7d2e5f8c941', 'f1c7b4d92a08')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

