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
) -> None:
    """Upsert user + Google identity. No-op when DB is unconfigured."""
    engine = get_engine()
    if engine is None:
        return
    normalized_email = email.strip().lower()

    now = utcnow()
    with Session(engine) as session:
        user = session.execute(select(User).where(User.email == normalized_email)).scalars().first()
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

