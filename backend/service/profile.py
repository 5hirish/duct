"""Read and write the operator's profile: who they are, how Duct writes to them.

Small on purpose, like ``service/model_settings.py`` beside it. This owns where
the profile is kept and what an absent one means. What a profile *does* to a
run is owned by the prompt builders that read it.

Three rules worth knowing before changing anything here:

1. **The server row is the truth, the request payload is a fallback.** Clients
   have sent ``user_preferences`` from ``localStorage`` on every agent request
   since before this table existed, and old clients still do. ``resolve`` picks
   the row when there is one and the payload when there is not, so a signed-out
   run and a stale desktop build both keep working.
2. **Every read is best-effort.** A profile is a preference; no preference is
   worth turning a brief into an error page. A failed read degrades to
   ``DEFAULTS``.
3. **The preset is one control that still feeds two fields.** ``UserPreferences``
   carries ``communication_style`` and ``report_depth`` and several prompts read
   both. The page asks once and this derives the pair, so the prompt contract
   did not have to change when the control did.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from uuid import UUID

from db.session import get_session as db_session
from models.settings import UserProfile
from utils.dates import utcnow

logger = logging.getLogger(__name__)

#: The free-text box rides in every prompt this account ever runs, so it is
#: capped. Uncapped, it is a context leak that costs money on every call and
#: that nobody would ever attribute to a settings page they filled in once.
NOTES_MAX_CHARS = 1000

#: How Duct writes, and what each preset means for the two older fields. The
#: depth in each pair is a default, not a lock: someone who wants executive
#: framing with all the evidence says so in `notes`, which outranks the preset.
WRITING_PRESETS: dict[str, tuple[str, str]] = {
    "executive": ("executive", "summary"),
    "practitioner": ("practitioner", "balanced"),
    "technical": ("technical", "detailed"),
}

DEFAULT_PRESET = "practitioner"


@dataclass(frozen=True)
class Profile:
    """What a run needs to know about the person it is answering."""

    display_name: str = ""
    role: str = ""
    writing_preset: str = DEFAULT_PRESET
    #: Empty means "match the language they wrote in".
    communication_language: str = ""
    notes: str = ""

    @property
    def communication_style(self) -> str:
        return WRITING_PRESETS.get(self.writing_preset, WRITING_PRESETS[DEFAULT_PRESET])[0]

    @property
    def report_depth(self) -> str:
        return WRITING_PRESETS.get(self.writing_preset, WRITING_PRESETS[DEFAULT_PRESET])[1]


#: What an account that has never opened the page gets — and byte-for-byte the
#: behaviour that shipped before this table.
DEFAULTS = Profile()


def _clean_preset(value: object) -> str:
    text = str(value or "").strip().lower()
    return text if text in WRITING_PRESETS else DEFAULT_PRESET


def _clean_text(value: object, *, limit: int) -> str:
    return str(value or "").strip()[:limit]


def get_profile(user_id: UUID | None) -> Profile:
    """The saved profile, or the defaults for an anonymous caller or a failure."""
    if user_id is None:
        return DEFAULTS
    try:
        with next(db_session()) as db:
            row = db.get(UserProfile, user_id)
            if row is None:
                return DEFAULTS
            return Profile(
                display_name=str(row.display_name or ""),
                role=str(row.role or ""),
                writing_preset=_clean_preset(row.writing_preset),
                communication_language=str(row.communication_language or ""),
                notes=str(row.notes or ""),
            )
    except Exception:
        logger.warning("profile unavailable — using defaults", exc_info=True)
        return DEFAULTS


def save_profile(
    user_id: UUID,
    *,
    display_name: str | None = None,
    role: str | None = None,
    writing_preset: str | None = None,
    communication_language: str | None = None,
    notes: str | None = None,
) -> Profile:
    """Upsert the fields the caller sent, leaving the rest alone.

    Partial by design, for the same reason ``save_model_settings`` is: the page
    saves each control as it is touched, and a whole-object write would let a
    tab loaded before a change put the old value back.
    """
    with next(db_session()) as db:
        row = db.get(UserProfile, user_id)
        if row is None:
            row = UserProfile(user_id=user_id)
            db.add(row)
        if display_name is not None:
            row.display_name = _clean_text(display_name, limit=80)
        if role is not None:
            row.role = _clean_text(role, limit=80)
        if writing_preset is not None:
            row.writing_preset = _clean_preset(writing_preset)
        if communication_language is not None:
            row.communication_language = _clean_text(communication_language, limit=40)
        if notes is not None:
            row.notes = _clean_text(notes, limit=NOTES_MAX_CHARS)
        row.updated_at = utcnow()
        db.commit()
        return Profile(
            display_name=str(row.display_name or ""),
            role=str(row.role or ""),
            writing_preset=_clean_preset(row.writing_preset),
            communication_language=str(row.communication_language or ""),
            notes=str(row.notes or ""),
        )


def resolve(user_id: UUID | None, request_preferences: object = None) -> Profile:
    """The profile a run should use: the saved row, else what the client sent.

    The payload path is not legacy support to be removed on a tidy-up day — a
    signed-out audit has no row to read and still deserves the voice the person
    picked in the browser before signing up.
    """
    saved = get_profile(user_id)
    if saved != DEFAULTS or request_preferences is None:
        return saved

    style = str(getattr(request_preferences, "communication_style", "") or "")
    depth = str(getattr(request_preferences, "report_depth", "") or "")
    preset = next(
        (name for name, pair in WRITING_PRESETS.items() if pair == (style, depth)),
        style if style in WRITING_PRESETS else DEFAULT_PRESET,
    )
    return replace(
        DEFAULTS,
        role=str(getattr(request_preferences, "role", "") or ""),
        writing_preset=preset,
    )
