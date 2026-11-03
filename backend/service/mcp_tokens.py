"""Credentials for Duct's MCP server: mint, connect, renew, resolve, list, revoke.

Two kinds share one table. A **personal token** is minted in the app and
pasted into an agent's config. A **connected agent** signed in through the
browser (``service/mcp_server/oauth``): an hour-long access token it renews
with a refresh token. See ``models.auth.McpToken`` for why either is accepted
on ``/mcp`` only and stored as a hash. Everything that turns a bearer string
into a user for the MCP server goes through ``resolve``.
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

# A connected agent renews itself unattended, so its access token can be
# short: a copy lifted from an agent's store stops working within the hour.
ACCESS_LIFETIME = timedelta(hours=1)
# Pushed forward on every renewal: an agent in use never signs in again, and
# one left unused for a quarter has to.
CONNECTION_LIFETIME = timedelta(days=90)
# Connecting never fails on the count. Adding Duct to an agent again
# registers a new client, so a cap that refused would lock out someone who
# reinstalled their tools; the agent used least recently is disconnected
# instead.
MAX_CONNECTED_AGENTS = 10
REFRESH_PREFIX = "duct_mcpr_"
# What a connected agent is called when its client gave no name.
UNNAMED_AGENT = "AI agent"

# Writing last_used_at on every call would make each read a write. A token
# list only needs to say "used today" or "never used".
_LAST_USED_RESOLUTION = timedelta(minutes=10)


class TokenLimitReached(Exception):
    pass


def _digest(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _new_secret(prefix: str) -> str:
    return prefix + secrets.token_urlsafe(32)


def _active(now):
    """A credential ``/mcp`` accepts right now."""
    return (McpToken.revoked_at.is_(None)) & (McpToken.expires_at > now)


def _personal(now):
    return McpToken.client_id.is_(None) & _active(now)


def _connected(now):
    """A signed-in agent that can still renew, whatever its access token's age."""
    return (
        McpToken.client_id.is_not(None)
        & McpToken.revoked_at.is_(None)
        & (McpToken.refresh_expires_at > now)
    )


def active_tokens(user: User, session: Session) -> list[McpToken]:
    """Personal tokens and connected agents, newest first."""
    now = utcnow()
    return list(
        session.execute(
            select(McpToken)
            .where(McpToken.user_id == user.id, _personal(now) | _connected(now))
            .order_by(McpToken.created_at.desc())
        ).scalars().all()
    )


def is_connected_agent(row: McpToken) -> bool:
    return row.client_id is not None


def mint(user: User, name: str, session: Session) -> tuple[McpToken, str]:
    """A new token for ``user``. Returns the row and the plaintext, which is
    never stored and cannot be shown again."""
    now = utcnow()
    count = session.execute(
        select(func.count()).select_from(McpToken).where(McpToken.user_id == user.id, _personal(now))
    ).scalar_one()
    if count >= MAX_ACTIVE_TOKENS:
        raise TokenLimitReached
    raw = _new_secret(TOKEN_PREFIX)
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


def _issue(row: McpToken, now) -> tuple[str, str]:
    """Fresh access and refresh tokens on ``row``, replacing any it held, so
    a refresh token works once."""
    access, refresh = _new_secret(TOKEN_PREFIX), _new_secret(REFRESH_PREFIX)
    row.token_hash = _digest(access)
    row.hint = access[-4:]
    row.expires_at = now + ACCESS_LIFETIME
    row.refresh_hash = _digest(refresh)
    row.refresh_expires_at = now + CONNECTION_LIFETIME
    return access, refresh


def connect_agent(
    user: User, *, client_id: str, client_name: str, session: Session
) -> tuple[McpToken, str, str]:
    """A connection for an agent the person allowed. Returns the row, the
    access token and the refresh token; only their hashes are stored."""
    now = utcnow()
    live = session.execute(
        select(McpToken)
        .where(McpToken.user_id == user.id, _connected(now))
        .order_by(func.coalesce(McpToken.last_used_at, McpToken.created_at).desc())
    ).scalars().all()
    for stale in live[MAX_CONNECTED_AGENTS - 1:]:
        stale.revoked_at = now
        session.add(stale)
    row = McpToken(
        user_id=user.id,
        name=(client_name.strip() or UNNAMED_AGENT)[:NAME_MAX_CHARS],
        client_id=client_id,
        created_at=now,
        token_hash="",
        hint="",
        expires_at=now,
    )
    access, refresh = _issue(row, now)
    session.add(row)
    session.commit()
    session.refresh(row)
    return row, access, refresh


def renew_agent(raw_refresh: str, client_id: str, session: Session) -> tuple[McpToken, str, str] | None:
    """New tokens for a refresh token, or None. The refresh token is bound to
    the client it was issued to (RFC 6749 §6) and spent by the renewal."""
    if not raw_refresh.startswith(REFRESH_PREFIX) or not client_id:
        return None
    now = utcnow()
    row = session.execute(
        select(McpToken).where(McpToken.refresh_hash == _digest(raw_refresh), _connected(now))
    ).scalars().first()
    if row is None or row.client_id != client_id:
        return None
    access, refresh = _issue(row, now)
    session.add(row)
    session.commit()
    session.refresh(row)
    return row, access, refresh


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
