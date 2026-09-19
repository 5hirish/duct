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

    # Which model draws, when the user picked one. Empty means "whichever of my
    # keys can draw", resolved in IMAGE_PROVIDER_ORDER — the behaviour every
    # install had before this column, so an empty string is not a missing
    # setting, it is the answer most people want.
    #
    # A preference, not a guarantee: a pick whose provider has no spendable key
    # falls through to that same order rather than failing the run. Same rule
    # the tier ladder follows, for the same reason — a content session is worth
    # having without the exact model you asked for.
    image_model: str = Field(
        default="", sa_column=Column(String, nullable=False, server_default="")
    )

    updated_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(utc_datetime(), nullable=False)
    )


class UserProfile(SQLModel, table=True):
    """Who the operator is, and how they want to be written to.

    Same argument as ``UserModelSettings`` above, applied to a different kind of
    preference: this used to live only in ``localStorage``
    (``app/src/lib/userPreferences.js``) and travel on each agent request, which
    meant a laptop and a phone disagreed and the scheduled brief — the one run
    whose owner is definitely not watching — could read none of it.

    One row per user. Everything is optional and an empty row is exactly the
    behaviour of an account that never opened the page: no name, Duct's default
    voice, and the language of whatever the person wrote.
    """

    __tablename__ = "user_profile"

    user_id: UUID = Field(
        sa_column=Column(
            ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, nullable=False
        ),
    )

    # What to call them. Not the account's full name: this is the one they
    # answer to, and it is the only field here that shows up verbatim in
    # generated text.
    display_name: str = Field(
        default="", sa_column=Column(String, nullable=False, server_default="")
    )

    # Their job, from the shipped list. Free text is accepted too — the list is
    # a convenience, and a role the list does not have is still worth knowing.
    role: str = Field(default="", sa_column=Column(String, nullable=False, server_default=""))

    # How Duct writes: "executive" | "practitioner" | "technical". One control
    # rather than the two (style and depth) that shipped before it, because
    # almost nobody wants executive tone with exhaustive evidence, and the
    # person who does can say so in `notes`. Both older fields are still
    # derived from this one, so every prompt that reads them is unchanged.
    writing_preset: str = Field(
        default="practitioner",
        sa_column=Column(String, nullable=False, server_default="practitioner"),
    )

    # The language Duct writes *to them* in. Empty means "match the language
    # they wrote in", which is the default because it is right more often than
    # any fixed choice and because it never makes someone set a preference to
    # get the behaviour they already had.
    #
    # Not the same field as a project's output language (the deliverable
    # written for a client) and not the interface language. See the precedence
    # rule in `service/profile.py`.
    communication_language: str = Field(
        default="", sa_column=Column(String, nullable=False, server_default="")
    )

    # The language the *interface* is rendered in: a BCP 47 tag from the
    # catalogue list in `app/src/i18n/locales.js` ("es", "pt-BR", ...), or ""
    # for "follow the browser". Server-owned for the same reason as the rest
    # of the row: a phone should open in the language the laptop chose.
    #
    # The third language field, and the only one that names a *translation*
    # rather than a model instruction. `communication_language` can be any
    # language a model speaks; this one can only be a language the app has a
    # catalogue for, which is why the two lists are kept apart.
    interface_language: str = Field(
        default="", sa_column=Column(String, nullable=False, server_default="")
    )

    # IANA zone name ("Europe/Madrid"). Empty means UTC, which is what every
    # date window resolved to before this column existed.
    #
    # Not cosmetic: an agent asked about "last week" has to pick seven days,
    # and in Valencia those are not the same seven days as in UTC. Stored as
    # the IANA name rather than an offset because an offset is wrong twice a
    # year.
    timezone: str = Field(
        default="", sa_column=Column(String, nullable=False, server_default="")
    )

    # Anything the controls above cannot hold: house rules, the metric they
    # care about, how they want to be argued with. It outranks the preset when
    # the two disagree, and it is capped at NOTES_MAX_CHARS because it rides in
    # every prompt this account ever runs.
    notes: str = Field(default="", sa_column=Column(String, nullable=False, server_default=""))

    updated_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(utc_datetime(), nullable=False)
    )
