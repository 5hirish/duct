"""Auth user persistence helpers."""

from __future__ import annotations

from typing import NamedTuple


from sqlalchemy import select
from sqlmodel import Session

from db.session import get_engine
from models.auth import AuthIdentity, User
from utils.dates import utcnow


class GoogleUpsert(NamedTuple):
    """What the caller needs from an upsert: was this a signup, and who is it."""

    created: bool
    user_id: str


def upsert_google_user(
    *,
    provider_user_id: str,
    email: str,
    name: str,
    picture: str,
    raw_profile: dict,
) -> GoogleUpsert:
    """Upsert user + Google identity. No-op when DB is unconfigured.

    `created` is True only when this call made the row — the one moment a
    sign-in is a sign-up. Nothing downstream can work that out later: the JWT is
    issued on every sign-in and lives for a week, so `created_at` read at render
    time would report a signup every day for seven days.

    `user_id` is the row's UUID, which is what analytics identifies people by.
    Deliberately not the email, even though the JWT's `sub` is: an email is
    personal data and GA4 forbids receiving it.

    Both are empty when the database is unconfigured. We do not know, and a
    metric that invents activations is worse than one that misses them.
    """
    engine = get_engine()
    if engine is None:
        return GoogleUpsert(created=False, user_id="")
    normalized_email = email.strip().lower()

    now = utcnow()
    with Session(engine) as session:
        user = session.execute(select(User).where(User.email == normalized_email)).scalars().first()
        created = user is None
        if user is None:
            user = User(
                email=normalized_email,
                full_name=name or None,
                avatar_url=picture or None,
                last_sign_in_at=now,
                created_at=now,
                updated_at=now,
            )
            session.add(user)
            session.flush()
        else:
            user.full_name = name or user.full_name
            user.avatar_url = picture or user.avatar_url
            user.last_sign_in_at = now
            user.updated_at = now
            session.add(user)

        identity = session.execute(
            select(AuthIdentity).where(
                AuthIdentity.provider == "google",
                AuthIdentity.provider_user_id == provider_user_id,
            )
        ).scalars().first()
        if identity is None:
            identity = AuthIdentity(
                user_id=user.id,
                provider="google",
                provider_user_id=provider_user_id,
                provider_email=normalized_email,
                raw_profile=raw_profile,
                created_at=now,
                updated_at=now,
            )
        else:
            identity.user_id = user.id
            identity.provider_email = normalized_email
            identity.raw_profile = raw_profile
            identity.updated_at = now
        session.add(identity)
        # Read inside the session: the instance is expired on commit, and
        # touching `user.id` afterwards would re-query a closed session.
        user_id = str(user.id)
        session.commit()

    return GoogleUpsert(created=created, user_id=user_id)

