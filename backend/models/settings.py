"""The model choices a user made, on the server rather than in one browser.

The tier map shipped in ``localStorage`` (``app/src/lib/modelTiers.js``) and
travelled on each agent request. That works for a person sitting in front of
the app and fails for everything else Duct runs on their behalf: the scheduled
brief has no browser attached, so it could never read the map, and the desktop
shell and the web app were two independent copies of the same preference.

A setting the user believes is global has to be global, or the first time it
silently does not apply is the time they stop trusting the control. So it lives
here, keyed by user, and the browser's copy becomes a cache of this rather than
the truth.

One row per user, not per project. The three picks are a statement about the
keys they hold and the money they are willing to spend — both user-level facts.
A project-level override is a real feature, and it is not this one; when it
arrives it gets its own table rather than a nullable column here.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import Column, ForeignKey, String
from sqlmodel import Field, SQLModel

from models.columns import json_column, utc_datetime
from utils.dates import utcnow


class UserModelSettings(SQLModel, table=True):
    __tablename__ = "user_model_settings"

    # The user *is* the key. A second row for the same user is not a state this
    # table has a meaning for, so the database says so rather than the service.
    user_id: UUID = Field(
        sa_column=Column(
            ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, nullable=False
        ),
    )

    # {"heavy": "<model id>", ...}. Partial is normal and an absent tier means
    # "unset", which resolves to the shipped default — so an empty map is
    # byte-for-byte the behaviour of an install that never opened this page.
    tiers: dict = Field(default_factory=dict, sa_column=Column(json_column(), nullable=False))

    # Whether a run may step down the ladder when the tier it wanted is out of
    # quota. On by default: the alternative is a scheduled brief that does not
    # arrive, and a brief on the Standard model beats no brief. Off is for
    # someone who would rather see the failure than a quieter model — a
    # legitimate choice, and one they have to make deliberately.
    auto_fallback: bool = Field(
        default=True, sa_column=Column(sa.Boolean(), nullable=False, server_default=sa.true())
    )

    # The harness a run uses, when the user pinned one. Empty means the
    # instance default, which is what almost every install wants.
    engine: str = Field(default="", sa_column=Column(String, nullable=False, server_default=""))

    updated_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(utc_datetime(), nullable=False)
    )
