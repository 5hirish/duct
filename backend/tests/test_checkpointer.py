"""The durable-state gate.

``agents/core/checkpoint.py`` is the second implementation of the session/state
port. The property it exists for is not "a checkpointer is configured" but "a
thread outlives the process that opened it", so that is what these assert —
against a real SQLite file, with a genuinely new saver instance on the second
read, because an in-process cache would pass a weaker test.

The other half is the Alembic guard. LangGraph creates and migrates its own
tables inside Duct's database; ``db.migrate.LANGGRAPH_TABLES`` is what stops
``--autogenerate`` proposing to drop them. That list is a hardcoded copy of
LangGraph's schema, so it goes stale silently on an upgrade — the last test
reads the installed package and fails when it does.
"""

from __future__ import annotations

import pathlib
import re
from typing import TypedDict

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import START, StateGraph

from agents.core import checkpoint
from agents.core.checkpoint import (
    backend_name,
    get_checkpointer,
    open_checkpointer,
    psycopg_dsn,
    set_checkpointer,
    sqlite_path,
)
from db.migrate import LANGGRAPH_TABLES


# ---------------------------------------------------------------------------
# URL translation
# ---------------------------------------------------------------------------

def test_psycopg_dsn_drops_the_sqlalchemy_driver_suffix():
    """psycopg rejects `postgresql+psycopg://`; db/session.py produces it."""
    dsn = psycopg_dsn("postgresql+psycopg://u:pw@host:5432/duct")
    assert dsn.startswith("postgresql://")
    assert "+psycopg" not in dsn
    # The password has to survive — it is how the saver authenticates.
    assert "pw" in dsn


def test_psycopg_dsn_leaves_a_plain_url_alone():
    assert psycopg_dsn("postgresql://u@host/duct").startswith("postgresql://")


def test_sqlite_path_is_the_file_aiosqlite_should_open():
    assert sqlite_path("sqlite:////var/data/duct.db") == "/var/data/duct.db"


def test_sqlite_memory_is_not_a_durable_target():
    """`:memory:` would open a *second*, unrelated database — say so instead."""
    assert sqlite_path("sqlite:///:memory:") == ""


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("postgresql+psycopg://u@h/d", "postgresql"),
        ("postgresql://u@h/d", "postgresql"),
        ("sqlite:////tmp/x.db", "sqlite"),
        ("", ""),
        ("not a url at all", ""),
    ],
)
def test_backend_name_survives_every_url_shape(url, expected):
    """Including the unparseable one: a bad DATABASE_URL degrades, never raises."""
    assert backend_name(url) == expected


# ---------------------------------------------------------------------------
# Durability — the property the module exists for
# ---------------------------------------------------------------------------

class _Counter(TypedDict):
    n: int


def _counter_graph():
    graph = StateGraph(_Counter)
    graph.add_node("bump", lambda state: {"n": state["n"] + 1})
    graph.add_edge(START, "bump")
    return graph


async def test_a_thread_outlives_the_saver_that_wrote_it(tmp_path):
    """The whole point: a redeploy must not reset an open conversation."""
    url = f"sqlite:///{tmp_path / 'duct.db'}"
    config = {"configurable": {"thread_id": "conversation-1"}}
    graph = _counter_graph()

    async with open_checkpointer(url) as saver:
        assert not isinstance(saver, InMemorySaver)
        await graph.compile(checkpointer=saver).ainvoke({"n": 0}, config)

    # A new saver, a new connection, the same file — this is the restart.
    async with open_checkpointer(url) as saver:
        state = await graph.compile(checkpointer=saver).aget_state(config)

    assert state.values["n"] == 1


async def test_threads_do_not_bleed_into_each_other(tmp_path):
    """Durable state is per conversation; the thread_id is the session id."""
    url = f"sqlite:///{tmp_path / 'duct.db'}"
    graph = _counter_graph()

    async with open_checkpointer(url) as saver:
        app = graph.compile(checkpointer=saver)
        await app.ainvoke({"n": 0}, {"configurable": {"thread_id": "a"}})
        other = await app.aget_state({"configurable": {"thread_id": "b"}})

    assert other.values == {}


async def test_no_database_falls_back_instead_of_failing_to_boot(tmp_path):
    """An install with no DATABASE_URL still serves; it just forgets on restart."""
    async with open_checkpointer("") as saver:
        assert isinstance(saver, InMemorySaver)


async def test_an_unusable_url_degrades_rather_than_raising(monkeypatch):
    """A crash-looping deploy is worse than a non-durable one."""
    # The pool keeps retrying an unreachable host until its open timeout; a
    # second is plenty to prove the point without slowing the suite.
    monkeypatch.setattr(checkpoint, "_POOL_OPEN_TIMEOUT_SECONDS", 1.0)
    async with open_checkpointer("postgresql://nobody@127.0.0.1:1/nope") as saver:
        assert isinstance(saver, InMemorySaver)


class _FakePool:
    """Records how the saver's pool is built, opened and closed."""

    instances: list["_FakePool"] = []

    def __init__(self, conninfo, **kwargs):
        self.conninfo = conninfo
        self.kwargs = kwargs
        self.opened = None
        self.closed = False
        _FakePool.instances.append(self)

    async def open(self, *, wait=False, timeout=None):
        self.opened = {"wait": wait, "timeout": timeout}

    async def close(self):
        self.closed = True

    @staticmethod
    async def check_connection(conn):  # the real one is a staticmethod too
        raise AssertionError("not called at build time")


class _FakeSaver:
    def __init__(self, conn):
        self.conn = conn

    async def setup(self):
        pass


async def test_postgres_connections_are_pooled_and_checked(monkeypatch):
    """One unchecked connection for the process's life is how 2026-11-08 went:
    the proxy dropped it after four idle hours and every agent run after that
    failed in ``aget_tuple`` until a restart. The pool must probe a connection
    before lending it out, retire idle ones itself, and ask the OS for TCP
    keepalives, so a dropped socket costs one reconnect rather than the day."""
    import psycopg_pool
    from langgraph.checkpoint.postgres import aio as saver_module

    _FakePool.instances.clear()
    monkeypatch.setattr(psycopg_pool, "AsyncConnectionPool", _FakePool)
    monkeypatch.setattr(saver_module, "AsyncPostgresSaver", _FakeSaver)

    async with open_checkpointer("postgresql+psycopg://u:p@db.example/duct") as saver:
        assert isinstance(saver, _FakeSaver)
        (pool,) = _FakePool.instances
        assert saver.conn is pool
        assert pool.kwargs["check"] is _FakePool.check_connection
        assert pool.kwargs["open"] is False
        assert pool.kwargs["max_idle"] < 600, "must retire before a proxy's idle timeout"
        assert pool.opened == {"wait": True, "timeout": checkpoint._POOL_OPEN_TIMEOUT_SECONDS}
        # What from_conn_string set, and what the saver's SQL relies on.
        assert pool.kwargs["kwargs"]["autocommit"] is True
        assert pool.kwargs["kwargs"]["prepare_threshold"] == 0
        assert "keepalives=1" in pool.conninfo
        assert "+psycopg" not in pool.conninfo, "libpq does not know SQLAlchemy's driver suffix"
        assert not pool.closed
    assert pool.closed, "the lifespan's exit must close the pool"


# ---------------------------------------------------------------------------
# Publication — what a runner actually receives
# ---------------------------------------------------------------------------

def test_get_checkpointer_never_returns_none():
    """Runners must not have to care whether a lifespan ran."""
    set_checkpointer(None)
    assert get_checkpointer() is not None


def test_the_fallback_is_one_saver_not_one_per_call():
    """A fresh InMemorySaver per call would lose continuity mid-conversation."""
    set_checkpointer(None)
    assert get_checkpointer() is get_checkpointer()


def test_the_insights_runner_uses_the_published_saver():
    """The lifespan publishes; build_agent must not quietly make its own."""
    from agents.insights.v1.runner import AutonomousInsightsRunner

    published = InMemorySaver()
    set_checkpointer(published)
    try:
        agent = AutonomousInsightsRunner(api_key="unused-no-network").build_agent(
            llm=FakeMessagesListChatModel(responses=[AIMessage(content="ok")]),
        )
        assert agent.checkpointer is published
    finally:
        set_checkpointer(None)


# ---------------------------------------------------------------------------
# The Alembic guard
# ---------------------------------------------------------------------------

def test_langgraph_table_list_still_matches_the_installed_package():
    """Fails when a LangGraph upgrade adds a checkpoint table.

    A table missing from `LANGGRAPH_TABLES` is invisible to the `include_object`
    filter in `alembic/env.py`, so the next `--autogenerate` writes an
    `op.drop_table` for it — a revision that deletes live conversations on
    deploy. Catching it here costs one upgrade-time test failure instead.
    """
    import langgraph.checkpoint as pkg

    # A namespace package: the postgres and sqlite savers ship as separate
    # distributions that both land under `langgraph.checkpoint`, so there is no
    # single `__file__` — walk every path entry the import system found.
    created: set[str] = set()
    for root in pkg.__path__:
        for path in pathlib.Path(root).rglob("*.py"):
            created.update(
                re.findall(
                    r"CREATE TABLE IF NOT EXISTS (\w+)", path.read_text(), flags=re.I
                )
            )

    assert created, "no CREATE TABLE found — did langgraph restructure?"
    missing = created - LANGGRAPH_TABLES
    assert not missing, (
        f"LangGraph now creates {sorted(missing)}, which db.migrate.LANGGRAPH_TABLES "
        "does not list. Add them, or autogenerate will propose dropping them."
    )
