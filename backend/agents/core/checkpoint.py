"""Durable conversation state — the second implementation of the session/state port.

``agents/core/ports/__init__.py`` listed session/state as the one port with a
single implementation, with a note: "the LangGraph checkpointer is the natural
second; do not abstract before it exists." This is that second implementation.

What changes for a user: a follow-up turn survives the process that served the
first one. ``InMemorySaver`` held a thread only as long as the worker holding
it, so a Railway redeploy, an instance move, or a sidecar restart silently
dropped every open conversation back to turn one — the agent answered the next
message having forgotten the conversation it was in the middle of.

Dialect follows the install, never the other way round
------------------------------------------------------
Duct runs one FastAPI app against two databases: Postgres on Railway, and
SQLite in the desktop sidecar (``config.py`` defaults ``DATABASE_URL`` to a file
in the per-user data dir). The checkpointer follows whatever ``DATABASE_URL``
names. It never opens a database of its own and never forces a dialect:

    postgres  → ``AsyncPostgresSaver``   (psycopg_pool)
    sqlite    → ``AsyncSqliteSaver``     (aiosqlite)
    unset     → ``InMemorySaver``        (tests, and any install with no DB)

A saver that cannot be opened degrades to ``InMemorySaver`` rather than taking
the process down. Losing durability is bad; refusing to boot is worse, and a
crash-looping deploy is how a checkpoint-table race turns into an outage. The
failure is logged with a traceback so it reaches Sentry.

LangGraph owns its own tables
-----------------------------
``setup()`` creates them, and they are deliberately outside Alembic — LangGraph
migrates its own schema across versions and an Alembic revision pinning their
shape would fight it. ``db/migrate.LANGGRAPH_TABLES`` is the list, and
``alembic/env.py`` uses it to keep ``--autogenerate`` from proposing to drop
tables it can't see in ``SQLModel.metadata``.

Lifecycle
---------
Both async savers are ``@asynccontextmanager`` classmethods that hold a live
connection pool, so ownership belongs to the app lifespan (``server.py``) — not
to a runner. Building one per session would open a connection pool per chat.
The lifespan enters ``open_checkpointer`` once and publishes the result through
``set_checkpointer``; runners read it with ``get_checkpointer()``.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy.engine import make_url

logger = logging.getLogger(__name__)

# SQLAlchemy backend names that mean "Postgres", whatever driver is spelled on
# the URL (``postgresql+psycopg`` normalises to ``postgresql``).
_POSTGRES_BACKENDS = frozenset({"postgresql", "postgres"})

# Process-wide saver, published by the lifespan. None until then.
_checkpointer: Any = None

# Lazily built so importing this module never allocates one, and so every
# caller during a given process shares the same in-memory threads (a fresh
# InMemorySaver per call would lose continuity even within one run).
_fallback: Any = None


def _fallback_saver() -> Any:
    global _fallback
    if _fallback is None:
        _fallback = InMemorySaver()
    return _fallback


def get_checkpointer() -> Any:
    """The process-wide checkpointer, or an in-memory one outside a server.

    Never returns ``None``: a runner should not have to care whether a lifespan
    ran, and tests that build an agent directly get the previous behaviour.
    """
    return _checkpointer if _checkpointer is not None else _fallback_saver()


def set_checkpointer(saver: Any | None) -> None:
    """Publish (or clear) the process-wide checkpointer. Called by the lifespan."""
    global _checkpointer
    _checkpointer = saver


# ---------------------------------------------------------------------------
# URL translation
# ---------------------------------------------------------------------------

def backend_name(database_url: str) -> str:
    """SQLAlchemy backend name for a URL, or "" when it is unset/unparseable."""
    if not database_url:
        return ""
    try:
        return make_url(database_url).get_backend_name()
    except Exception:
        logger.warning("checkpoint: could not parse DATABASE_URL; using in-memory state")
        return ""


def psycopg_dsn(database_url: str) -> str:
    """Render a SQLAlchemy URL as a plain libpq DSN.

    ``db/session.py`` normalises Postgres URLs to ``postgresql+psycopg://`` for
    SQLAlchemy's benefit. psycopg itself does not understand the ``+driver``
    suffix, so it is stripped back off here rather than handing SQLAlchemy's
    spelling to a driver that rejects it.
    """
    return make_url(database_url).set(drivername="postgresql").render_as_string(
        hide_password=False
    )


def sqlite_path(database_url: str) -> str:
    """Filesystem path behind a sqlite URL, or "" for in-memory / no file.

    ``:memory:`` returns "" deliberately: aiosqlite would open a *second*,
    unrelated in-memory database, so the honest answer is to fall back to
    ``InMemorySaver`` and keep one source of truth.
    """
    database = make_url(database_url).database or ""
    return "" if database == ":memory:" else database


# ---------------------------------------------------------------------------
# Opening
# ---------------------------------------------------------------------------

async def _enter_sqlite(stack: AsyncExitStack, path: str) -> Any | None:
    try:
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

        saver = await stack.enter_async_context(AsyncSqliteSaver.from_conn_string(path))
        await saver.setup()
    except Exception:
        logger.exception("checkpoint: sqlite saver unavailable (%s)", path)
        return None
    logger.info("checkpoint: durable conversation state on sqlite (%s)", path)
    return saver


async def _enter_postgres(stack: AsyncExitStack, dsn: str) -> Any | None:
    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        saver = await stack.enter_async_context(AsyncPostgresSaver.from_conn_string(dsn))
        await saver.setup()
    except Exception:
        # Never log the DSN — it carries the password.
        logger.exception("checkpoint: postgres saver unavailable")
        return None
    logger.info("checkpoint: durable conversation state on postgres")
    return saver


@asynccontextmanager
async def open_checkpointer(database_url: str) -> AsyncIterator[Any]:
    """Open the checkpointer for this install and hold it for the app's life.

    The ``yield`` sits outside every ``except`` on purpose: an exception raised
    by the caller's body must propagate to the exit stack (so the pool closes)
    rather than being mistaken for a startup failure and swallowed.
    """
    backend = backend_name(database_url)
    async with AsyncExitStack() as stack:
        saver: Any | None = None
        if backend == "sqlite":
            path = sqlite_path(database_url)
            if path:
                saver = await _enter_sqlite(stack, path)
        elif backend in _POSTGRES_BACKENDS:
            saver = await _enter_postgres(stack, psycopg_dsn(database_url))

        if saver is None:
            logger.warning(
                "checkpoint: no durable saver for DATABASE_URL (%s); conversations "
                "will not survive a restart",
                backend or "unset",
            )
            saver = _fallback_saver()
        yield saver
