"""RunPython: the insights agent's arithmetic, run in the person's own app.

The agent reads connector rows as text, and before this existed every derived
figure in a brief (a total, a share, a median) was the model's own arithmetic
over that text. A replay of a GA4 brief on 2026-09-24 got the method right and
the numbers wrong: 2,504 sessions for a table that summed to 2,681, rows counted
as sessions. The trust protocol forbids exactly that, and a prompt cannot
enforce it; an interpreter can.

The code runs in the browser, in a Web Worker holding Pyodide, not on this
server. Model-written code is shaped by text other people wrote (page titles,
search queries, referrers), and this process holds every customer's OAuth
tokens. The browser is the strongest sandbox available and costs nothing per
run. The price is that somebody's app must be open, so the tool is mounted for
interactive sessions only, and it reports ``unavailable`` rather than hanging
when nobody answers.

Framework-free on purpose: this module holds the contract (what the browser is
sent, what comes back, what the model reads) and ``data_tools.py`` binds it.
The transport is the one ``render_slide`` uses in the content agent: a Future
the browser resolves over its own route, inside the turn. Not the checkpointed
pause: a pause ends the streamed turn and marks the run "paused" on every call,
which is right for a question to a human and wrong for a computation.
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Callable
from uuid import uuid4

from agents.core.events import AgentEvent

logger = logging.getLogger(__name__)

# The person's settings move these within the ceilings, never past them. The
# ceilings are about what a browser tab survives, not about trust: 500k rows of
# a dozen columns is a few hundred MB once pandas has it, the edge of what an
# 8 GB laptop gives one tab.
DEFAULT_MAX_INPUT_ROWS = 50_000
MAX_INPUT_ROWS_CEILING = 500_000
DEFAULT_TIMEOUT_SECONDS = 60
TIMEOUT_CEILING_SECONDS = 300

# The first run in a tab downloads the interpreter and pandas (tens of MB,
# cached after). The person's time limit is for their code, so the server
# waits this much longer before it gives up on the browser.
LOAD_GRACE_SECONDS = 60

MAX_CODE_CHARS = 20_000
# What the model gets back. Output is for aggregates; a script that prints the
# whole frame is told it was cut, and the next one prints less.
MAX_OUTPUT_CHARS = 20_000
MAX_ERROR_CHARS = 4_000

# A pull's row arrays live under one of these keys when there is one table;
# the same three ``activity._row_count`` recognises.
_PRIMARY_KEYS = ("rows", "items", "results")
# The lossless fold (agents/core/compaction.py) writes a table as
# "[N]{col:type,...}\n" followed by CSV. Replays seed FetchData with those
# bodies, so a replayed pull reaches the store in that shape.
_FOLDED = re.compile(r"^\[(\d+)\]\{([^}]*)\}\n", re.S)


@dataclass(frozen=True)
class PythonLimits:
    """The person's limits for one run, clamped to what a tab survives."""

    enabled: bool = True
    max_input_rows: int = DEFAULT_MAX_INPUT_ROWS
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS

    @classmethod
    def of(cls, enabled: bool, max_input_rows: int, timeout_seconds: int) -> "PythonLimits":
        return cls(
            enabled=bool(enabled),
            max_input_rows=max(1, min(int(max_input_rows), MAX_INPUT_ROWS_CEILING)),
            timeout_seconds=max(1, min(int(timeout_seconds), TIMEOUT_CEILING_SECONDS)),
        )


@dataclass(frozen=True)
class Table:
    columns: list[str]
    rows: list[list[Any]]


class FetchedTables:
    """Every successful pull of a session, as tables RunPython can name.

    Fed by FetchData's ``on_fetch`` hook, which sees the raw result before it
    is folded for the model. Each pull is stored under
    ``<entity_id>:<date_from>:<date_to>`` and the bare ``<entity_id>`` names
    the latest one, because the fetch protocol asks for the window before as
    well as the window asked, and a store keyed on the entity alone would keep
    only one of the two a comparison needs.
    """

    def __init__(self) -> None:
        self._tables: dict[str, Table] = {}

    def record(self, entity_id: str, result: dict) -> None:
        if not isinstance(result, dict) or result.get("status") != "ok":
            return
        entity = (entity_id or "").strip()
        if not entity:
            return
        window = f"{entity}:{result.get('date_from') or ''}:{result.get('date_to') or ''}"
        for suffix, table in _tables_in(result.get("data")).items():
            self._tables[window + suffix] = table
            self._tables[entity + suffix] = table

    def names(self) -> list[str]:
        return sorted(self._tables)

    def get(self, name: str) -> Table | None:
        return self._tables.get(name)


def _tables_in(data: Any) -> dict[str, Table]:
    """The row arrays in a pull's ``data``, keyed by a name suffix.

    One array is the pull itself (suffix ""); any others keep their key
    (``".campaigns"``), so a payload carrying two tables loses neither.
    """
    found: dict[str, Table] = {}
    if isinstance(data, list):
        table = _table_of(data)
        if table is not None:
            found[""] = table
        return found
    if not isinstance(data, dict):
        return found
    for key, value in data.items():
        table = _table_of(value)
        if table is None:
            continue
        found["" if key in _PRIMARY_KEYS else f".{key}"] = table
    if "" not in found and len(found) == 1:
        found = {"": next(iter(found.values()))}
    return found


def _table_of(value: Any) -> Table | None:
    if isinstance(value, str):
        return _unfold(value)
    if not isinstance(value, list) or not value or not all(isinstance(r, dict) for r in value):
        return None
    columns: list[str] = []
    for row in value:
        for key in row:
            if key not in columns:
                columns.append(key)
    return Table(columns=columns, rows=[[row.get(c) for c in columns] for row in value])


_CASTS: dict[str, Callable[[str], Any]] = {"int": int, "float": float, "bool": lambda v: v == "true"}


def _unfold(text: str) -> Table | None:
    """A folded table back into rows. ``None`` for any other string."""
    header = _FOLDED.match(text)
    if not header:
        return None
    spec = [part.split(":", 1) for part in header.group(2).split(",") if ":" in part]
    columns = [name for name, _ in spec]
    casts = [_CASTS.get(kind) for _, kind in spec]
    rows: list[list[Any]] = []
    for record in csv.reader(io.StringIO(text[header.end():])):
        if not record:
            continue
        row: list[Any] = []
        for raw, cast in zip(record, casts):
            try:
                row.append(cast(raw) if cast and raw != "" else (raw if raw != "" else None))
            except ValueError:
                row.append(raw)
        rows.append(row)
    return Table(columns=columns, rows=rows)


def select_tables(
    store: FetchedTables, requested: list[str], max_rows: int
) -> tuple[dict[str, Table], list[str], list[str]]:
    """The tables to send, the names that were cut to fit, and the unknown names.

    An empty request means every pull the session has made, latest window per
    entity. The row limit is shared across tables in the order asked, so a
    script that names one big table gets all of it.
    """
    names = requested or [n for n in store.names() if ":" not in n]
    chosen: dict[str, Table] = {}
    cut: list[str] = []
    unknown: list[str] = []
    budget = max_rows
    for name in dict.fromkeys(n.strip() for n in names if n.strip()):
        table = store.get(name)
        if table is None:
            unknown.append(name)
            continue
        if len(table.rows) > budget:
            cut.append(name)
            table = Table(columns=table.columns, rows=table.rows[:budget])
        chosen[name] = table
        budget -= len(table.rows)
    return chosen, cut, unknown


def _clip(text: Any, limit: int) -> tuple[str, bool]:
    value = text if isinstance(text, str) else ("" if text is None else str(text))
    return (value[:limit], True) if len(value) > limit else (value, False)


def answer_for_model(answer: dict, *, tables: dict[str, Table], cut: list[str]) -> str:
    """What the model reads back: the output, bounded, with how it was bounded."""
    stdout, stdout_cut = _clip(answer.get("stdout"), MAX_OUTPUT_CHARS)
    result, result_cut = _clip(answer.get("result"), MAX_OUTPUT_CHARS)
    error, _ = _clip(answer.get("error"), MAX_ERROR_CHARS)
    body: dict[str, Any] = {
        "status": "ok" if answer.get("ok") else "error",
        "tables": {name: len(t.rows) for name, t in tables.items()},
        "duration_ms": answer.get("duration_ms"),
    }
    if stdout:
        body["stdout"] = stdout
    if result:
        body["result"] = result
    if error:
        body["error"] = error
    if cut:
        body["rows_cut"] = (
            f"{', '.join(cut)} exceeded the person's row limit and arrived truncated. "
            "Say so beside any figure computed from them."
        )
    if stdout_cut or result_cut:
        body["output_cut"] = f"Output past {MAX_OUTPUT_CHARS:,} characters was dropped. Print aggregates, not rows."
    return json.dumps(body, default=str)


def _error(message: str, **extra: Any) -> str:
    return json.dumps({"status": "error", "error": message, **extra})


async def run_python(
    *,
    session: Any,
    emit: Callable[[dict], Any],
    store: FetchedTables,
    limits: PythonLimits,
    code: str,
    tables: list[str] | None = None,
) -> str:
    """Send ``code`` and its tables to the person's app and wait for the output.

    Never raises: every outcome, including nobody answering, is a payload the
    model can reason about, because a tool that throws ends a run that may
    already have spent minutes fetching.
    """
    code = (code or "").strip()
    if not code:
        return _error("code is required.")
    if len(code) > MAX_CODE_CHARS:
        return _error(f"code is {len(code):,} characters; the limit is {MAX_CODE_CHARS:,}.")
    chosen, cut, unknown = select_tables(store, list(tables or []), limits.max_input_rows)
    if unknown:
        return _error(
            f"No fetched table named {', '.join(unknown)}. Fetch it with FetchData first.",
            available=store.names(),
        )

    futures: dict[str, asyncio.Future] = getattr(session, "python_futures", None)
    if futures is None:
        return json.dumps({"status": "unavailable", "error": "This session has no app to run code in."})
    run_id = str(uuid4())
    fut: asyncio.Future = asyncio.get_running_loop().create_future()
    futures[run_id] = fut
    try:
        await emit({
            "event": AgentEvent.PYTHON_RUN_REQUESTED,
            "session_id": getattr(session, "session_id", ""),
            "run_id": run_id,
            "code": code,
            "tables": {name: {"columns": t.columns, "rows": t.rows} for name, t in chosen.items()},
            "timeout_seconds": limits.timeout_seconds,
        })
        try:
            answer = await asyncio.wait_for(
                asyncio.shield(fut), timeout=limits.timeout_seconds + LOAD_GRACE_SECONDS
            )
        except asyncio.TimeoutError:
            return json.dumps({
                "status": "unavailable",
                "error": (
                    "The person's app did not run the code in time: it is closed, "
                    "offline or still loading. Say which figures are uncomputed and carry on."
                ),
            })
    finally:
        futures.pop(run_id, None)
    if not isinstance(answer, dict):
        return _error("The app returned no result.")
    return answer_for_model(answer, tables=chosen, cut=cut)


def resolve_run(session: Any, run_id: str, answer: dict) -> bool:
    """Hand the browser's answer to the waiting tool. False when none waits."""
    futures = getattr(session, "python_futures", None) or {}
    fut = futures.get(run_id)
    if fut is None or fut.done():
        return False
    fut.set_result(answer)
    return True
