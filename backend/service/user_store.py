"""Auth user persistence: Google sign-in, and the guest that precedes it.

A guest is a real ``users`` row. Onboarding runs an audit before anyone signs
in, and every table that audit writes to — projects, conversations, artifacts,
memberships, stored provider keys — requires an owner. Loosening those columns
would put a "no owner" branch in every route-auth boundary; a synthetic user
puts one in none of them. The row carries a synthetic email under
``GUEST_EMAIL_DOMAIN`` and an ``auth_identities`` row of provider ``guest``
keyed on the install id, so relaunching the app resumes the same guest.

Sign-in is then a *link* or a *merge*:

* the Google email is unknown → **link**: the guest row becomes the account
  (email replaced, Google identity attached, guest identity dropped). The user
  id never changes, so nothing downstream — analytics identity included — has
  to be re-keyed.
* the Google email already has an account → **merge**: every row the guest
  owns is reassigned to that account in one transaction and the guest row is
  deleted (``absorb_guest``). This is the case that orphans data if it is not
  designed in, which is why it walks the schema rather than a hand-kept list.
"""

from __future__ import annotations

import logging
import re
from datetime import timedelta
from typing import NamedTuple
from uuid import UUID

from sqlalchemy import and_, delete, exists, select, update
from sqlmodel import Session, SQLModel

from db.session import get_engine
from models.auth import AuthIdentity, User
from utils.dates import utcnow

logger = logging.getLogger(__name__)

GUEST_PROVIDER = "guest"
GOOGLE_PROVIDER = "google"
# Reserved, never delivered to: it exists so the email column's NOT NULL and
# UNIQUE hold for a user who has not told us an address yet.
GUEST_EMAIL_DOMAIN = "guest.getduct.ai"
# Guests with no other identity are swept after this. Long enough that a
# weekend or a holiday does not lose a report; short enough that an install
# that never came back does not accumulate.
GUEST_TTL_DAYS = 30
# Lowercase so the users.email lowercase check holds by construction; bounded
# so a client cannot mint a kilobyte of identifier.
INSTALL_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{7,63}$")


class GoogleUpsert(NamedTuple):
    """What the caller needs from an upsert: was this a signup, and who is it."""

    created: bool
    user_id: str


class GuestUpsert(NamedTuple):
    created: bool
    user_id: str
    email: str


def guest_email(install_id: str) -> str:
    return f"guest+{install_id}@{GUEST_EMAIL_DOMAIN}"


def is_guest_user(user: User | None) -> bool:
    """A guest is recognisable from the row alone, so a JWT claim and a
    template can both ask without a second query."""
    return bool(user) and str(user.email or "").endswith(f"@{GUEST_EMAIL_DOMAIN}")


def get_or_create_guest(install_id: str) -> GuestUpsert:
    """The guest for this install, minting it on first sight.

    Idempotent on ``install_id``: the desktop shell presents the same id on
    every launch and gets the same row back, which is what makes "your audit
    is still here" true after a relaunch.
    """
    install_id = str(install_id or "").strip().lower()
    if not INSTALL_ID_PATTERN.match(install_id):
        raise ValueError("install_id must be 8–64 characters of [a-z0-9-].")
    engine = get_engine()
    if engine is None:
        raise RuntimeError("DATABASE_URL is not configured.")

    now = utcnow()
    email = guest_email(install_id)
    with Session(engine) as session:
        identity = session.execute(
            select(AuthIdentity).where(
                AuthIdentity.provider == GUEST_PROVIDER,
                AuthIdentity.provider_user_id == install_id,
            )
        ).scalars().first()
        if identity is not None:
            user = session.get(User, identity.user_id)
            if user is not None:
                user.last_sign_in_at = now
                user.updated_at = now
                session.add(user)
                user_id, user_email = str(user.id), user.email
                session.commit()
                return GuestUpsert(created=False, user_id=user_id, email=user_email)
            # An identity whose user is gone (a sweep raced a relaunch): fall
            # through and mint a fresh row under the same install id.
            session.delete(identity)
            session.flush()

        user = User(
            email=email,
            full_name="Guest",
            last_sign_in_at=now,
            created_at=now,
            updated_at=now,
        )
        session.add(user)
        session.flush()
        session.add(
            AuthIdentity(
                user_id=user.id,
                provider=GUEST_PROVIDER,
                provider_user_id=install_id,
                created_at=now,
                updated_at=now,
            )
        )
        user_id = str(user.id)
        session.commit()
    return GuestUpsert(created=True, user_id=user_id, email=email)


def upsert_google_user(
    *,
    provider_user_id: str,
    email: str,
    name: str,
    picture: str,
    raw_profile: dict,
    link_user_id: str | None = None,
) -> GoogleUpsert:
    """Upsert user + Google identity. No-op when DB is unconfigured.

    `created` is True only when this call made the row — the one moment a
    sign-in is a sign-up. Nothing downstream can work that out later: the JWT is
    issued on every sign-in and lives for a week, so `created_at` read at render
    time would report a signup every day for seven days. A linked guest counts
    as created: it is the first time this person has an account, even though
    the row predates the click.

    `user_id` is the row's UUID, which is what analytics identifies people by.
    Deliberately not the email, even though the JWT's `sub` is: an email is
    personal data and GA4 forbids receiving it.

    `link_user_id` names the guest that started this sign-in. Ignored unless it
    resolves to a guest row — a stale or forged id must not be able to hijack
    someone else's account by naming it here.

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
        guest = _live_guest(session, link_user_id)
        created = user is None

        if user is None and guest is not None:
            # Link: the guest row becomes the account. Same id, new email.
            user = guest
            user.email = normalized_email
            session.execute(
                delete(AuthIdentity).where(
                    AuthIdentity.user_id == guest.id,
                    AuthIdentity.provider == GUEST_PROVIDER,
                )
            )
            logger.info("guest %s linked to a new Google account", guest.id)
        elif user is None:
            user = User(email=normalized_email, created_at=now)
            session.add(user)
            session.flush()
        elif guest is not None and guest.id != user.id:
            # Merge: the address already has an account; everything the guest
            # made moves there and the guest row goes.
            absorb_guest(session, guest.id, user.id)
            logger.info("guest %s merged into existing user %s", guest.id, user.id)

        user.full_name = name or user.full_name
        user.avatar_url = picture or user.avatar_url
        user.last_sign_in_at = now
        user.updated_at = now
        session.add(user)

        identity = session.execute(
            select(AuthIdentity).where(
                AuthIdentity.provider == GOOGLE_PROVIDER,
                AuthIdentity.provider_user_id == provider_user_id,
            )
        ).scalars().first()
        if identity is None:
            identity = AuthIdentity(
                user_id=user.id,
                provider=GOOGLE_PROVIDER,
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


def _live_guest(session: Session, user_id: str | None) -> User | None:
    """The guest row for ``user_id``, or None when it is absent or not a guest."""
    if not user_id:
        return None
    try:
        row = session.get(User, UUID(str(user_id)))
    except ValueError:
        return None
    return row if is_guest_user(row) else None


def _user_fk_columns():
    """Every column in the schema that points at ``users.id``.

    Walked from metadata rather than listed by hand: a table added next month
    with an owner column is then merged correctly without anyone remembering
    this function exists. ``tests/test_guest_users.py`` asserts the walk finds
    what a hand list would.
    """
    import models  # noqa: F401 — registers every table on the shared metadata

    for table in SQLModel.metadata.sorted_tables:
        if table.name == "users":
            continue
        for column in table.columns:
            for fk in column.foreign_keys:
                if fk.column.table.name == "users" and fk.column.name == "id":
                    yield table, column


def absorb_guest(session: Session, guest_id: UUID, into_user_id: UUID) -> None:
    """Move everything ``guest_id`` owns to ``into_user_id`` and delete the guest.

    Runs inside the caller's transaction so a failure anywhere leaves both
    accounts as they were. Where a table is unique on the owner plus other
    columns (a membership, a stored key for one provider), a guest row that
    would collide with one the target already has is dropped rather than
    moved: the target's own row is the one they chose.
    """
    if guest_id == into_user_id:
        return
    for table, column in _user_fk_columns():
        if table.name == "auth_identities":
            # The guest identity itself does not survive — its user is gone.
            session.execute(
                delete(table).where(
                    and_(column == guest_id, table.c.provider == GUEST_PROVIDER)
                )
            )
        for constraint in table.constraints:
            columns = list(getattr(constraint, "columns", []))
            if not columns or column not in columns or len(columns) == 1:
                continue
            if not _is_unique(constraint):
                continue
            others = [c for c in columns if c is not column]
            target = table.alias("target")
            clash = exists().where(
                and_(
                    target.c[column.name] == into_user_id,
                    *[target.c[c.name] == table.c[c.name] for c in others],
                )
            )
            session.execute(delete(table).where(and_(column == guest_id, clash)))
        session.execute(update(table).where(column == guest_id).values({column.name: into_user_id}))
    guest = session.get(User, guest_id)
    if guest is not None:
        session.delete(guest)
    session.flush()


def _is_unique(constraint) -> bool:
    from sqlalchemy import PrimaryKeyConstraint, UniqueConstraint

    return isinstance(constraint, (UniqueConstraint, PrimaryKeyConstraint))


def sweep_stale_guests(session: Session, *, older_than_days: int = GUEST_TTL_DAYS) -> int:
    """Delete guests nobody came back for. Cascade removes what they made."""
    cutoff = utcnow() - timedelta(days=older_than_days)
    stale = session.execute(
        select(User).where(
            User.email.like(f"%@{GUEST_EMAIL_DOMAIN}"),
            User.created_at < cutoff,
        )
    ).scalars().all()
    for row in stale:
        session.delete(row)
    session.flush()
    return len(stale)
