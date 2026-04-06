"""Durable OAuth state store with in-memory fallback."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session

from db.session import get_engine
from models.auth import OAuthState

_memory_states: dict[str, tuple[float, str | None, str]] = {}
logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def save_state(state: str, code_verifier: str | None, flow: str, ttl_seconds: int) -> None:
    engine = get_engine()
    if engine is None:
        _memory_states[state] = (time.time(), code_verifier, flow)
        return
    now = _utcnow()
    try:
        with Session(engine) as session:
            session.execute(delete(OAuthState).where(OAuthState.state == state))
            session.add(
                OAuthState(
                    state=state,
                    flow=flow,
                    code_verifier=code_verifier,
                    issued_at=now,
                    expires_at=now + timedelta(seconds=ttl_seconds),
                )
            )
            session.commit()
    except SQLAlchemyError:
        logger.warning("OAuth state DB unavailable; falling back to in-memory state store.")
        _memory_states[state] = (time.time(), code_verifier, flow)


def consume_state(state: str, flow: str, ttl_seconds: int) -> tuple[bool, str | None]:
    engine = get_engine()
    if engine is None:
        entry = _memory_states.pop(state, None)
        if entry is None:
            return False, None
        issued_at, code_verifier, stored_flow = entry
        if stored_flow != flow or (time.time() - issued_at) > ttl_seconds:
            return False, None
        return True, code_verifier

    now = _utcnow()
    try:
        with Session(engine) as session:
            stmt = select(OAuthState).where(OAuthState.state == state)
            oauth_state = session.execute(stmt).scalars().first()
            if oauth_state is None:
                return False, None
            if oauth_state.flow != flow:
                return False, None
            if oauth_state.consumed_at is not None:
                return False, None
            if oauth_state.expires_at <= now:
                return False, None

            code_verifier = oauth_state.code_verifier
            oauth_state.consumed_at = now
            session.add(oauth_state)
            session.commit()
            return True, code_verifier
    except SQLAlchemyError:
        logger.warning("OAuth state DB unavailable while consuming state.")
        entry = _memory_states.pop(state, None)
        if entry is None:
            return False, None
        issued_at, code_verifier, stored_flow = entry
        if stored_flow != flow or (time.time() - issued_at) > ttl_seconds:
            return False, None
        return True, code_verifier


def cleanup_expired_states() -> int:
    engine = get_engine()
    if engine is None:
        return 0
    now = _utcnow()
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
