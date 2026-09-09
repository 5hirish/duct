"""Durable OAuth state store with in-memory fallback."""

from __future__ import annotations

import logging
import time
from datetime import timedelta
from typing import NamedTuple

from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session

from db.session import get_engine
from models.auth import OAuthState
from utils.dates import utcnow

# state → (issued_at, code_verifier, flow, link_user_id, remember)
_memory_states: dict[str, tuple[float, str | None, str, str | None, bool]] = {}
logger = logging.getLogger(__name__)


class ConsumedState(NamedTuple):
    """What a consumed state row carried: the flow it belonged to, the PKCE
    verifier, which guest to link (for a sign-in a guest started), and whether
    the login page's "keep me signed in" box was ticked."""

    flow: str | None
    code_verifier: str | None
    link_user_id: str | None
    remember: bool = False


_NOTHING = ConsumedState(None, None, None, False)


def save_state(
    state: str,
    code_verifier: str | None,
    flow: str,
    ttl_seconds: int,
    *,
    link_user_id: str | None = None,
    remember: bool = False,
) -> None:
    engine = get_engine()
    if engine is None:
        _memory_states[state] = (time.time(), code_verifier, flow, link_user_id, remember)
        return
    now = utcnow()
    try:
        with Session(engine) as session:
            session.execute(delete(OAuthState).where(OAuthState.state == state))
            session.add(
                OAuthState(
                    state=state,
                    flow=flow,
                    code_verifier=code_verifier,
                    link_user_id=link_user_id,
                    remember=remember,
                    issued_at=now,
                    expires_at=now + timedelta(seconds=ttl_seconds),
                )
            )
            session.commit()
    except SQLAlchemyError:
        logger.warning("OAuth state DB unavailable; falling back to in-memory state store.")
        _memory_states[state] = (time.time(), code_verifier, flow, link_user_id, remember)


def _consume_memory_state_for_flows(
    state: str, flows: set[str], ttl_seconds: int
) -> ConsumedState:
    entry = _memory_states.get(state)
    if entry is None:
        return _NOTHING
    issued_at, code_verifier, stored_flow, link_user_id, remember = entry
    if stored_flow not in flows or (time.time() - issued_at) > ttl_seconds:
        return _NOTHING
    _memory_states.pop(state, None)
    return ConsumedState(stored_flow, code_verifier, link_user_id, remember)


def consume_state(state: str, flow: str, ttl_seconds: int) -> tuple[bool, str | None]:
    consumed = consume_state_full(state, (flow,), ttl_seconds)
    return consumed.flow is not None, consumed.code_verifier


def consume_state_for_flows(
    state: str, allowed_flows: tuple[str, ...], ttl_seconds: int
) -> tuple[str | None, str | None]:
    consumed = consume_state_full(state, allowed_flows, ttl_seconds)
    return consumed.flow, consumed.code_verifier


def consume_state_full(
    state: str, allowed_flows: tuple[str, ...], ttl_seconds: int
) -> ConsumedState:
    """Consume ``state`` if it belongs to one of ``allowed_flows`` and is live.

    The two older shapes above delegate here; this is the one the sign-in
    callback reads, because it is the only caller that needs ``link_user_id``.
    """
    allowed = set(allowed_flows)
    if not allowed:
        return _NOTHING

    engine = get_engine()
    if engine is None:
        return _consume_memory_state_for_flows(state, allowed, ttl_seconds)

    now = utcnow()
    try:
        with Session(engine) as session:
            stmt = select(OAuthState).where(OAuthState.state == state)
            oauth_state = session.execute(stmt).scalars().first()
            if oauth_state is None:
                return _NOTHING
            if oauth_state.flow not in allowed:
                return _NOTHING
            if oauth_state.consumed_at is not None:
                return _NOTHING
            if oauth_state.expires_at <= now:
                return _NOTHING

            consumed = ConsumedState(
                oauth_state.flow,
                oauth_state.code_verifier,
                oauth_state.link_user_id,
                oauth_state.remember,
            )
            oauth_state.consumed_at = now
            session.add(oauth_state)
            session.commit()
            return consumed
    except SQLAlchemyError:
        logger.warning("OAuth state DB unavailable while consuming state for allowed flows.")
        return _consume_memory_state_for_flows(state, allowed, ttl_seconds)


def cleanup_expired_states() -> int:
    engine = get_engine()
    if engine is None:
        return 0
    now = utcnow()
    try:
        with Session(engine) as session:
            stmt = delete(OAuthState).where(
                (OAuthState.expires_at < now) | (OAuthState.consumed_at.is_not(None))
            )
            result = session.execute(stmt)
            session.commit()
            return result.rowcount or 0
    except SQLAlchemyError:
        logger.warning("OAuth state DB unavailable during expired-state cleanup.")
        return 0
