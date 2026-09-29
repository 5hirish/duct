"""Read and write a user's model choices.

Small on purpose: the resolver (``agents/engines.resolve_job_run``) already
owns every rule about what a tier map *means*. This owns only where it is kept.
Nothing here validates a model id — an unknown pick degrades to the tier's
default inside ``agents.tiers.tier_pick``, and rejecting it at write time would
mean this module needed its own copy of the catalogue.

Every read is best-effort. A settings row that cannot be loaded must degrade to
the shipped defaults rather than fail a run: the map is a preference, and no
preference is worth turning a brief into an error page.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from agents.models import current_model_id
from agents.tiers import TIER_ORDER
from db.session import get_session as db_session
from models.settings import UserModelSettings
from utils.dates import utcnow

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModelSettings:
    """What a run needs to know about the user's choices."""

    tiers: dict[str, str]
    #: May a run step down the ladder when its tier is out of quota?
    auto_fallback: bool = True
    engine: str = ""
    #: Which model draws. Empty = whichever key can, in IMAGE_PROVIDER_ORDER.
    image_model: str = ""
    #: Which model makes clips. Empty = whichever key can, in VIDEO_PROVIDER_ORDER.
    video_model: str = ""


#: What an install that has never opened the settings page gets. Empty map, so
#: resolution is byte-for-byte the behaviour that shipped before this table.
DEFAULTS = ModelSettings(tiers={}, auto_fallback=True, engine="", image_model="", video_model="")


def _clean(tiers: object) -> dict[str, str]:
    """Only the three known tiers, only non-empty string picks.

    A pick the catalogue has since retired reads back as its successor, so
    the settings page names the model that will actually run rather than one
    it no longer lists (``agents.models.RETIRED_MODELS``).
    """
    if not isinstance(tiers, dict):
        return {}
    return {
        tier.value: current_model_id(str(tiers[tier.value]))
        for tier in TIER_ORDER
        if str(tiers.get(tier.value) or "").strip()
    }


def get_model_settings(user_id: UUID | None) -> ModelSettings:
    """The user's saved choices, or the defaults.

    Returns the defaults for an anonymous caller and for any failure — see the
    module docstring: this is a preference, not a gate.
    """
    if user_id is None:
        return DEFAULTS
    try:
        with next(db_session()) as db:
            row = db.get(UserModelSettings, user_id)
            if row is None:
                return DEFAULTS
            return _settings_of(row)
    except Exception:
        logger.warning("model settings unavailable — using defaults", exc_info=True)
        return DEFAULTS


def save_model_settings(
    user_id: UUID,
    *,
    tiers: object = None,
    auto_fallback: bool | None = None,
    engine: str | None = None,
    image_model: str | None = None,
    video_model: str | None = None,
) -> ModelSettings:
    """Upsert the fields the caller sent, leaving the rest alone.

    Partial by design: the settings page saves a tier the moment it is picked
    and the switch the moment it is flipped, and a whole-object PUT would let
    one stale tab overwrite the other control.
    """
    with next(db_session()) as db:
        row = db.get(UserModelSettings, user_id)
        if row is None:
            row = UserModelSettings(user_id=user_id)
            db.add(row)
        if tiers is not None:
            row.tiers = _clean(tiers)
        if auto_fallback is not None:
            row.auto_fallback = bool(auto_fallback)
        if engine is not None:
            row.engine = str(engine or "").strip()
        if image_model is not None:
            row.image_model = str(image_model or "").strip()
        if video_model is not None:
            row.video_model = str(video_model or "").strip()
        row.updated_at = utcnow()
        db.commit()
        return _settings_of(row)


def _settings_of(row: UserModelSettings) -> ModelSettings:
    return ModelSettings(
        tiers=_clean(row.tiers),
        auto_fallback=bool(row.auto_fallback),
        engine=str(row.engine or ""),
        image_model=str(row.image_model or ""),
        video_model=str(row.video_model or ""),
    )
