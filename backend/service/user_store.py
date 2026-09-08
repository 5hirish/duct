"""Auth user persistence helpers."""

from __future__ import annotations


from sqlalchemy import select
from sqlmodel import Session

from db.session import get_engine
from models.auth import AuthIdentity, User
from utils.dates import utcnow


def upsert_google_user(
    *,
    provider_user_id: str,
    email: str,
    name: str,
    picture: str,
    raw_profile: dict,
) -> bool:
    """Upsert user + Google identity. No-op when DB is unconfigured.

    Returns True when this call created the user row — the one moment a sign-in
    is a sign-up. Nothing downstream can work that out later: the JWT is issued
    on every sign-in and lives for a week, so `created_at` on a row read at
    render time would report a signup every day for seven days.

    False when the database is unconfigured. We do not know, and a metric that
    invents activations is worse than one that misses them.
    """
    engine = get_engine()
    if engine is None:
        return False
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
        session.commit()

    return created

