"""The operator's profile: their name, role, how Duct writes to them.

Two verbs and one row, the same shape as ``routes/model_settings.py``. Scoped
to the caller by ``get_current_user``; there is no path here that takes a user
id from the request, which is the whole security model of this endpoint — the
row *is* the user.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from models.auth import User
from service.auth import get_current_user
from service.profile import (
    NOTES_MAX_CHARS,
    WRITING_PRESETS,
    get_profile,
    save_profile,
)

router = APIRouter(tags=["profile"])


class ProfileBody(BaseModel):
    """Every field optional — the page saves one control at a time."""

    model_config = ConfigDict(extra="ignore")

    display_name: str | None = None
    role: str | None = None
    writing_preset: str | None = None
    communication_language: str | None = None
    notes: str | None = None


def _payload(profile) -> dict:
    # The derived pair goes over the wire too. The page never shows it, but a
    # desktop build a version behind still reads communication_style, and
    # answering with it costs nothing.
    return {
        "display_name": profile.display_name,
        "role": profile.role,
        "writing_preset": profile.writing_preset,
        "communication_language": profile.communication_language,
        "notes": profile.notes,
        "communication_style": profile.communication_style,
        "report_depth": profile.report_depth,
        "notes_max_chars": NOTES_MAX_CHARS,
        "presets": sorted(WRITING_PRESETS),
    }


@router.get("")
def read_profile(user: User = Depends(get_current_user)) -> dict:
    return _payload(get_profile(user.id))


@router.put("")
def write_profile(body: ProfileBody, user: User = Depends(get_current_user)) -> dict:
    return _payload(
        save_profile(
            user.id,
            display_name=body.display_name,
            role=body.role,
            writing_preset=body.writing_preset,
            communication_language=body.communication_language,
            notes=body.notes,
        )
    )
