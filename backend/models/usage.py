"""What each model call cost, kept.

Duct already measures this. ``UsageTracker`` in ``agents/core/lc.py`` turns a
stream's ``usage_metadata`` into one ``TOKEN_USAGE`` event per model call,
complete with cached-token split and a dollar figure — and then it goes to two
places that cannot answer a user's question. The browser accumulates it for the
session and forgets on reload; ``record_usage`` puts it on an OTel span bound
for Sentry, which is an engineer's tool. Nobody could ask "what did Duct spend
on my account this month, and on which model".

That question is not idle curiosity under bring-your-own-key. It is the user's
own bill. And it is what makes the tier ladder legible without ever explaining
tiers: seeing that the expensive model was 2% of the month and wrote the brief
is the whole argument, made once, in numbers the user already trusts.

One row per model call, not per run: a run fans out into subagents and a
summariser, and the interesting question ("what is actually expensive here") is
answered by the shape of the calls rather than their total. ``scope``
distinguishes them, mirroring the event's own field.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy import Column, ForeignKey, Index, Integer, String
from sqlmodel import Field, SQLModel

from models.columns import utc_datetime
from utils.dates import utcnow


class ModelUsage(SQLModel, table=True):
    __tablename__ = "model_usage"
    __table_args__ = (
        # The two reads this table exists for: "my usage over a window" and
        # "this project's usage over a window". Both are always time-bounded,
        # so the timestamp belongs in the index rather than beside it.
        Index("ix_model_usage_user_created", "user_id", "created_at"),
        Index("ix_model_usage_project_created", "project_id", "created_at"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True, nullable=False)

    # Nullable for the same reason ActivityLog's are: a lead-magnet audit and a
    # pre-project run still cost money and still belong in the total.
    user_id: UUID | None = Field(
        default=None,
        sa_column=Column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
    )
    project_id: UUID | None = Field(
        default=None,
        sa_column=Column(ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True),
    )
    # Polymorphic link to agent_conversations — no FK, the artifacts convention.
    conversation_id: UUID | None = Field(
        default=None,
        sa_column=Column(sa.dialects.postgresql.UUID(as_uuid=True), nullable=True, index=True),
    )

    # Which agent's run this call belonged to: insights / audit / content.
    agent_type: str = Field(default="", sa_column=Column(String, nullable=False, server_default=""))
    provider: str = Field(default="", sa_column=Column(String, nullable=False, server_default=""))
    # The model the provider says answered, which is not always the one asked
    # for — a fallback step or an alias resolves here. Recording the response's
    # model is what makes a step-down visible in the numbers afterwards.
    model: str = Field(default="", sa_column=Column(String, nullable=False, server_default=""))
    # The rung this call ran on, when the run resolved through the tier ladder.
    # Empty for a run that did not, which is most of them until the ladder is
    # wired into every agent.
    tier: str = Field(default="", sa_column=Column(String, nullable=False, server_default=""))
    # thread / subagent / compaction — see `_usage_scope` in agents/core/lc.py.
    scope: str = Field(default="thread", sa_column=Column(String, nullable=False, server_default="thread"))

    input_tokens: int = Field(default=0, sa_column=Column(Integer, nullable=False, server_default="0"))
    output_tokens: int = Field(default=0, sa_column=Column(Integer, nullable=False, server_default="0"))
    cache_read_tokens: int = Field(default=0, sa_column=Column(Integer, nullable=False, server_default="0"))
    cache_creation_tokens: int = Field(default=0, sa_column=Column(Integer, nullable=False, server_default="0"))

    # Micro-dollars, as an integer. A float column would invite SUM() over
    # binary floating point and hand someone a total ending in 0.30000000000004
    # on a page whose entire job is to be trusted about money. NULL where the
    # price table does not know the model — the UI then shows tokens without a
    # dollar figure rather than a made-up zero, matching what the live tooltip
    # already does.
    cost_micros: int | None = Field(default=None, sa_column=Column(sa.BigInteger(), nullable=True))

    created_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(utc_datetime(), nullable=False, index=True),
    )
