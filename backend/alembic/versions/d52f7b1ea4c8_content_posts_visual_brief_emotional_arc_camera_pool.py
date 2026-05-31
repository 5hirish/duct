"""content_posts: visual_brief + emotional_arc + camera_ref_pool columns

Revision ID: d52f7b1ea4c8
Revises: b8d4f1a3c9e2
Create Date: 2026-05-31 00:00:00.000000

Adds three Text/String columns to capture the reference-study output of
the rewritten draft_post sub-agent (Phase 8.5, ported from
nomadapps/.claude/skills/tiktok-gen/skill.md Step 3):

  - visual_brief — the per-post brief written BEFORE copy or prompts:
    lighting, posture, skin texture, gesture arc, copy voice. Drives
    both copy voice (Step 4) and image prompts (Step 5). Persisted so
    revise-loops + the slides sub-agent can read it back.
  - emotional_arc — the 5-slide energy arc the sub-agent writes out
    before per-slide prompts (Hook quiet → Rising → Peak → Vulnerable
    → Still warm). Plain text, one line per slide.
  - camera_ref_pool — the camera reference subtype the post needs:
    'selfie-talking' | 'lifestyle' | 'closeup' (or ''). Lets the
    orchestrator route Pattern 7 multi-image reference selection
    without re-derivation.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = 'd52f7b1ea4c8'
down_revision = 'b8d4f1a3c9e2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'content_posts',
        sa.Column('visual_brief', sa.Text(), nullable=False, server_default=''),
    )
    op.add_column(
        'content_posts',
        sa.Column('emotional_arc', sa.Text(), nullable=False, server_default=''),
    )
    op.add_column(
        'content_posts',
        sa.Column('camera_ref_pool', sa.String(), nullable=False, server_default=''),
    )


def downgrade() -> None:
    op.drop_column('content_posts', 'camera_ref_pool')
    op.drop_column('content_posts', 'emotional_arc')
    op.drop_column('content_posts', 'visual_brief')
