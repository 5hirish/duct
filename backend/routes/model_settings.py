"""The user's model choices: the tier map, and the fallback switch.

Two verbs and one row. The interesting decision is that this exists at all —
the map used to live only in ``localStorage``, which meant the scheduled brief,
the one run whose owner is definitely not watching, could not read the
preference its owner had set. See ``models/settings.py``.

Scoped to the caller by ``get_current_user``: there is no path here that takes
a user id from the request. That is the rule the route-auth boundary test
enforces, and it is the whole security model of this endpoint — the row *is*
the user.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from models.auth import User
from service.auth import get_current_user
from service.model_settings import get_model_settings, save_model_settings

router = APIRouter(tags=["model-settings"])


class ModelSettingsBody(BaseModel):
    """Every field optional — the page saves one control at a time.

    A whole-object PUT would let a tab that loaded before the switch was
    flipped write the old value back on the next tier change.
    """

    model_config = ConfigDict(extra="ignore")

    tiers: dict[str, str] | None = None
    auto_fallback: bool | None = None
    engine: str | None = None


def _payload(settings) -> dict:
    return {
        "tiers": settings.tiers,
        "auto_fallback": settings.auto_fallback,
        "engine": settings.engine,
    }


@router.get("")
def read_model_settings(user: User = Depends(get_current_user)) -> dict:
    return _payload(get_model_settings(user.id))


@router.put("")
def write_model_settings(
    body: ModelSettingsBody, user: User = Depends(get_current_user)
) -> dict:
    return _payload(
        save_model_settings(
            user.id,
            tiers=body.tiers,
            auto_fallback=body.auto_fallback,
            engine=body.engine,
        )
    )
