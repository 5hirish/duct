"""Personal tokens for Duct's MCP server: mint, resolve, list, revoke.

See ``models.auth.McpToken`` for why a token is accepted on ``/mcp`` only and
stored as a hash. Everything that turns a bearer string into a user for the
MCP server goes through ``resolve``.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlmodel import Session

from models.auth import McpToken, User
from utils.dates import utcnow

# Recognisable on sight, by a person reading a config file and by secret
# scanners that key on a prefix, so a leaked token gets flagged and revoked.
TOKEN_PREFIX = "duct_mcp_"

# A year: long enough that an agent's config does not break mid-quarter, short
# enough that a token forgotten in an old laptop's dotfiles stops working.
TOKEN_LIFETIME = timedelta(days=365)

# Enough for every agent on every machine one person uses. A cap exists so a
# script cannot fill the table through a guest account, which anyone can mint.
MAX_ACTIVE_TOKENS = 10

NAME_MAX_CHARS = 60

# Writing last_used_at on every call would make each read a write. A token
# list only needs to say "used today" or "never used".
_LAST_USED_RESOLUTION = timedelta(minutes=10)


class TokenLimitReached(Exception):
    pass


def _digest(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _active(now):
    return (McpToken.revoked_at.is_(None)) & (McpToken.expires_at > now)


def active_tokens(user: User, session: Session) -> list[McpToken]:
    now = utcnow()
    return list(
        session.execute(
            select(McpToken)
            .where(McpToken.user_id == user.id, _active(now))
            .order_by(McpToken.created_at.desc())
        ).scalars().all()
    )


def mint(user: User, name: str, session: Session) -> tuple[McpToken, str]:
    """A new token for ``user``. Returns the row and the plaintext, which is
    never stored and cannot be shown again."""
    now = utcnow()
    count = session.execute(
        select(func.count()).select_from(McpToken).where(McpToken.user_id == user.id, _active(now))
    ).scalar_one()
    if count >= MAX_ACTIVE_TOKENS:
        raise TokenLimitReached
    raw = TOKEN_PREFIX + secrets.token_urlsafe(32)
    row = McpToken(
        user_id=user.id,
        name=name.strip()[:NAME_MAX_CHARS],
        token_hash=_digest(raw),
        hint=raw[-4:],
        created_at=now,
        expires_at=now + TOKEN_LIFETIME,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row, raw


def revoke(user: User, token_id: UUID, session: Session) -> bool:
    """Revoke one of the caller's own tokens. False when it is not theirs, so
    the route answers a stranger's id exactly as it answers a made-up one."""
    row = session.get(McpToken, token_id)
    if row is None or row.user_id != user.id:
        return False
    if row.revoked_at is None:
        row.revoked_at = utcnow()
        session.add(row)
        session.commit()
    return True


def resolve(raw: str, session: Session) -> tuple[McpToken, User] | None:
    """The live token and its user for a bearer string, or None.

    None for anything that is not one of ours, so a sign-in JWT sent to
    ``/mcp`` fails here the same way a mistyped token does.
    """
    if not raw.startswith(TOKEN_PREFIX):
        return None
    now = utcnow()
    row = session.execute(
        select(McpToken).where(McpToken.token_hash == _digest(raw), _active(now))
    ).scalars().first()
    if row is None:
        return None
    user = session.get(User, row.user_id)
    if user is None:
        return None
    if row.last_used_at is None or now - row.last_used_at > _LAST_USED_RESOLUTION:
        row.last_used_at = now
        session.add(row)
        session.commit()
    return row, user
