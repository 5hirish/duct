"""SQLModel engine + session helpers."""

from __future__ import annotations

from functools import lru_cache
from typing import Generator

from sqlmodel import Session, SQLModel, create_engine

from config import get_configs


def _normalize_database_url(url: str) -> str:
    if not url:
        return ""
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


@lru_cache
def get_engine():
    database_url = _normalize_database_url(get_configs().database_url)
    if not database_url:
        return None
    # We reach Postgres through a cloud TCP proxy (Railway) that silently drops
    # idle connections. pool_pre_ping alone isn't enough: validating a half-dead
    # socket can cascade ("can't change autocommit ... transaction ACTIVE") and
    # poison the whole pool. So we also recycle connections before the proxy's
    # idle cutoff and enable TCP keepalives so dead sockets are detected fast.
    return create_engine(
        database_url,
        pool_pre_ping=True,
        pool_recycle=280,
        connect_args={
            "keepalives": 1,
            "keepalives_idle": 30,
            "keepalives_interval": 10,
            "keepalives_count": 5,
        },
    )


def get_session() -> Generator[Session, None, None]:
    engine = get_engine()
    if engine is None:
        raise RuntimeError("DATABASE_URL is not configured.")
    with Session(engine) as session:
        yield session


def init_db() -> None:
    """Initialize tables for local/test runs when migrations are not applied."""
    engine = get_engine()
    if engine is None:
        return
    SQLModel.metadata.create_all(engine)

