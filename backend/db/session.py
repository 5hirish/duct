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
    if database_url.startswith("sqlite"):
        # Desktop/local mode. The Postgres tuning below is psycopg-specific and
        # errors out on this driver, so SQLite takes its own path:
        #   check_same_thread=False — FastAPI serves requests on a thread pool,
        #     and agent tool calls run in worker threads via asyncio.to_thread.
        #   WAL — lets the agent write while a request reads, instead of
        #     "database is locked" under concurrent streaming sessions.
        engine = create_engine(
            database_url,
            connect_args={"check_same_thread": False},
        )
        with engine.connect() as conn:
            conn.exec_driver_sql("PRAGMA journal_mode=WAL")
            conn.exec_driver_sql("PRAGMA foreign_keys=ON")
        return engine
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


def get_session_optional() -> Generator[Session | None, None, None]:
    """A session when one can exist, ``None`` when the app has no database.

    For dependencies that run *before* anyone has been authenticated. FastAPI
    resolves the whole dependency tree before calling the endpoint, so a hard
    ``Depends(get_session)`` on the auth dependency means an unauthenticated
    request raises "DATABASE_URL is not configured" instead of 401 — the caller
    is told about our configuration rather than about their missing token, and
    a property that should hold unconditionally ("the API key is not a gate")
    becomes a property of the environment.

    Consumers must still refuse to proceed on ``None``: this widens *when* the
    failure is reported, never whether it is.
    """
    engine = get_engine()
    if engine is None:
        yield None
        return
    with Session(engine) as session:
        yield session


def init_db() -> None:
    """Initialize tables for local/test runs when migrations are not applied."""
    engine = get_engine()
    if engine is None:
        return
    SQLModel.metadata.create_all(engine)



# Storage locations reported to the browser. Same two answers the UI badges use.
STORAGE_LOCAL = "local"
STORAGE_CLOUD = "cloud"


def storage_location() -> str:
    """Where rows written through this engine physically live.

    The honest test is the database, not the process. `duct_local` is true for
    every sidecar, and `isLocalBackendActive()` in the browser only says a
    sidecar answered the request — but a sidecar pointed at a deployment's
    Postgres (`DUCT_ENV_FILE=…/.env.local`, which is how the desktop build is
    tested against staging) stores nothing on the machine it runs on. Labelling
    that "This device" tells the user their credentials never left the laptop
    when they are in fact in a shared database, which is exactly backwards and
    the sort of claim they might rely on.

    So this asks the one question with a truthful answer: SQLite is a file this
    machine owns, anything reached over a network is not. It is the same test
    `db/migrate._owns_database` uses to decide what this install may migrate,
    for the same reason — ownership of the data follows the database, never the
    process that happens to be serving.
    """
    engine = get_engine()
    if engine is None:
        return STORAGE_LOCAL
    return STORAGE_LOCAL if engine.dialect.name == "sqlite" else STORAGE_CLOUD
