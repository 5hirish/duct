"""RunPython: the agent's arithmetic, run in the person's app.

What these pin: the browser is sent exactly the rows the session fetched and
no more than the person's limit; nobody answering is an ``unavailable`` the
model can reason about, never a hang or a raise; the result route is owned
like the messages route; and the tool exists only where an app can answer.
No browser here: the tests resolve the Future the way the route does.
"""

from __future__ import annotations

import asyncio
import json
import uuid

import pytest
from fastapi import HTTPException

from agents.core.activity import ACTIVITY_TOOLS, ActivityKind, RUN_PYTHON_TOOL
from agents.core.events import AgentEvent
from agents.insights import data_tools, python_run
from agents.insights.python_run import FetchedTables, PythonLimits, resolve_run, run_python
from agents.insights.schema import create_insights_session
from agents.insights.v1.runner import AutonomousInsightsRunner
from routes.agents import PythonRunResult, submit_python_result
from tests.fakes import fake_llm, tool_names

RUNNER = AutonomousInsightsRunner(api_key="unused-no-network")

PULL = {
    "status": "ok",
    "date_from": "2026-08-18",
    "date_to": "2026-09-16",
    "data": {
        "row_count": 3,
        "rows": [
            {"page_path": "/a", "sessions": 800, "conversions": 3.0},
            {"page_path": "/b", "sessions": 566, "conversions": 39.0},
            {"page_path": "/c", "sessions": 262},
        ],
    },
}


@pytest.fixture
def session():
    return create_insights_session(str(uuid.uuid4()))


def _store(*pulls: tuple[str, dict]) -> FetchedTables:
    store = FetchedTables()
    for entity, result in pulls:
        store.record(entity, result)
    return store


# ---------------------------------------------------------------------------
# What the browser is sent
# ---------------------------------------------------------------------------

def test_a_pull_is_a_table_by_entity_and_by_window():
    store = _store(("ga4_landing_pages", PULL))

    latest = store.get("ga4_landing_pages")
    assert latest is store.get("ga4_landing_pages:2026-08-18:2026-09-16")
    assert latest.columns == ["page_path", "sessions", "conversions"]
    # A key missing from one row is a gap in that row, not a dropped column.
    assert latest.rows[2] == ["/c", 262, None]


def test_the_window_before_survives_the_window_asked():
    before = {**PULL, "date_from": "2026-07-18", "date_to": "2026-08-17"}
    store = _store(("ga4_landing_pages", before), ("ga4_landing_pages", PULL))

    assert store.get("ga4_landing_pages:2026-07-18:2026-08-17") is not None
    assert store.get("ga4_landing_pages") is store.get("ga4_landing_pages:2026-08-18:2026-09-16")


def test_a_failed_pull_is_not_a_table():
    store = _store(("ga4_landing_pages", {"status": "fetch_failed", "message": "nope"}))
    assert store.names() == []


def test_a_folded_replay_body_reads_back_as_rows():
    """Replays seed FetchData with the compacted bodies; the store must read
    them back value for value or a replayed run computes on strings."""
    folded = {
        **PULL,
        "data": {"rows": "[2]{page_path:string,sessions:int,rate:float}\n/a,802,0.5\n/b,566,\n"},
    }
    table = _store(("ga4_landing_pages", folded)).get("ga4_landing_pages")

    assert table.columns == ["page_path", "sessions", "rate"]
    assert table.rows == [["/a", 802, 0.5], ["/b", 566, None]]


def test_the_row_limit_is_shared_across_tables_in_the_order_asked():
    store = _store(("one", PULL), ("two", PULL))

    chosen, cut, unknown = python_run.select_tables(store, ["one", "two", "nope"], max_rows=4)

    assert [len(t.rows) for t in chosen.values()] == [3, 1]
    assert cut == ["two"]
    assert unknown == ["nope"]


def test_limits_are_clamped_rather_than_refused():
    limits = PythonLimits.of(True, 10**9, 0)
    assert limits.max_input_rows == python_run.MAX_INPUT_ROWS_CEILING
    assert limits.timeout_seconds == 1


# ---------------------------------------------------------------------------
# The round trip
# ---------------------------------------------------------------------------

async def _answer_when_asked(session, emitted, answer: dict) -> dict:
    """Play the browser: wait for the request, then resolve it as the route does."""
    for _ in range(200):
        asked = [e for e in emitted.events if e["event"] == AgentEvent.PYTHON_RUN_REQUESTED]
        if asked:
            assert resolve_run(session, asked[0]["run_id"], answer)
            return asked[0]
        await asyncio.sleep(0.005)
    raise AssertionError("the tool never asked the browser")


async def test_code_and_rows_go_to_the_browser_and_its_output_comes_back(session, emitted):
    store = _store(("ga4_landing_pages", PULL))
    browser = asyncio.create_task(_answer_when_asked(
        session, emitted, {"ok": True, "stdout": "total 1628", "duration_ms": 41}
    ))

    out = json.loads(await run_python(
        session=session, emit=emitted, store=store, limits=PythonLimits(),
        code="print('total', data['ga4_landing_pages'].sessions.sum())",
    ))
    asked = await browser

    assert asked["tables"]["ga4_landing_pages"]["rows"][0] == ["/a", 800, 3.0]
    assert asked["timeout_seconds"] == python_run.DEFAULT_TIMEOUT_SECONDS
    assert out == {"status": "ok", "tables": {"ga4_landing_pages": 3}, "duration_ms": 41, "stdout": "total 1628"}
    assert session.python_futures == {}, "a finished run must not leave its Future behind"


async def test_a_table_cut_to_the_limit_says_so(session, emitted):
    store = _store(("ga4_landing_pages", PULL))
    browser = asyncio.create_task(_answer_when_asked(session, emitted, {"ok": True, "stdout": "x"}))

    out = json.loads(await run_python(
        session=session, emit=emitted, store=store, limits=PythonLimits.of(True, 2, 5), code="print(1)",
    ))
    await browser

    assert out["tables"] == {"ga4_landing_pages": 2}
    assert "row limit" in out["rows_cut"]


async def test_output_past_the_cap_is_cut_and_the_model_is_told(session, emitted):
    browser = asyncio.create_task(_answer_when_asked(
        session, emitted, {"ok": True, "stdout": "9" * (python_run.MAX_OUTPUT_CHARS + 50)}
    ))

    out = json.loads(await run_python(
        session=session, emit=emitted, store=FetchedTables(), limits=PythonLimits(), code="print(9)",
    ))
    await browser

    assert len(out["stdout"]) == python_run.MAX_OUTPUT_CHARS
    assert "output_cut" in out


async def test_nobody_answering_is_unavailable_not_a_hang(session, emitted, monkeypatch):
    monkeypatch.setattr(python_run, "LOAD_GRACE_SECONDS", 0)

    out = json.loads(await run_python(
        session=session, emit=emitted, store=FetchedTables(),
        limits=PythonLimits.of(True, 10, 1), code="print(1)",
    ))

    assert out["status"] == "unavailable"
    assert session.python_futures == {}


async def test_an_unfetched_table_is_refused_before_the_browser_is_asked(session, emitted):
    out = json.loads(await run_python(
        session=session, emit=emitted, store=_store(("ga4_landing_pages", PULL)),
        limits=PythonLimits(), code="print(1)", tables=["gsc_queries"],
    ))

    assert out["status"] == "error"
    assert "ga4_landing_pages" in out["available"]
    assert emitted.events == []


# ---------------------------------------------------------------------------
# The result route
# ---------------------------------------------------------------------------

async def test_the_route_resolves_the_waiting_run(session):
    fut = asyncio.get_running_loop().create_future()
    session.python_futures["run_1"] = fut

    out = await submit_python_result(
        "insights", session.session_id, PythonRunResult(run_id="run_1", ok=True, stdout="42"), user=None
    )

    assert out == {"status": "ok"}
    assert fut.result()["stdout"] == "42"


async def test_a_result_nobody_waits_for_is_a_conflict(session):
    with pytest.raises(HTTPException) as err:
        await submit_python_result(
            "insights", session.session_id, PythonRunResult(run_id="gone", ok=True), user=None
        )
    assert err.value.status_code == 409


async def test_another_users_session_is_not_found(session):
    session.user_id = uuid.uuid4()
    session.python_futures["run_1"] = asyncio.get_running_loop().create_future()

    class Stranger:
        id = uuid.uuid4()

    with pytest.raises(HTTPException) as err:
        await submit_python_result(
            "insights", session.session_id, PythonRunResult(run_id="run_1", ok=True), user=Stranger()
        )
    assert err.value.status_code == 404
    assert not session.python_futures["run_1"].done()


def test_the_result_body_refuses_fields_it_does_not_know():
    with pytest.raises(ValueError):
        PythonRunResult(run_id="r", ok=True, files=["/etc/passwd"])


# ---------------------------------------------------------------------------
# Where the tool exists
# ---------------------------------------------------------------------------

def test_mounted_only_for_an_interactive_session_that_has_not_switched_it_off(session, emitted):
    def names(**kw):
        return tool_names(RUNNER.build_agent(
            llm=fake_llm("ok"), session=session, session_id=session.session_id, emit=emitted, **kw
        ))

    assert RUN_PYTHON_TOOL in names(python=PythonLimits())
    assert RUN_PYTHON_TOOL not in names(python=PythonLimits(enabled=False))
    assert RUN_PYTHON_TOOL not in names(python=PythonLimits(), interactive=False)
    assert RUN_PYTHON_TOOL not in names()


def test_the_prompt_describes_it_only_when_it_is_mounted(session, emitted):
    prompts: list[str] = []
    for python in (PythonLimits(), None):
        RUNNER.build_agent(
            llm=fake_llm("ok"), session=session, session_id=session.session_id, emit=emitted,
            python=python, on_system_prompt=prompts.append,
        )
    assert "**RunPython**" in prompts[0]
    assert "RunPython" not in prompts[1]


async def test_fetch_data_feeds_the_store(monkeypatch):
    monkeypatch.setattr(data_tools, "fetch_entity", lambda entity_id, **kw: dict(PULL))
    store = FetchedTables()
    tools = data_tools.build_data_tools_lc(uuid.uuid4(), user_id=uuid.uuid4(), on_fetch=store.record)
    fetch = next(t for t in tools if t.name == "FetchData")

    await fetch.ainvoke({"entity_id": "ga4_landing_pages"})

    assert len(store.get("ga4_landing_pages").rows) == 3


# ---------------------------------------------------------------------------
# The card
# ---------------------------------------------------------------------------

def test_the_card_carries_the_script_and_never_the_output():
    start, finish = ACTIVITY_TOOLS[RUN_PYTHON_TOOL]
    args = {"code": "import pandas\nprint(data['x'].sum())", "tables": ["x"]}
    result = json.dumps({"status": "ok", "tables": {"x": 3}, "duration_ms": 12, "stdout": "SECRET 1628"})

    card = finish(args, result, False)

    assert start(args)["kind"] == ActivityKind.CODE
    assert card["meta"]["code"] == args["code"]
    assert card["meta"]["lines"] == 2
    assert card["meta"]["rows"] == 3
    assert "SECRET" not in json.dumps(card)


def test_an_unavailable_run_is_an_error_card_that_says_why():
    _, finish = ACTIVITY_TOOLS[RUN_PYTHON_TOOL]
    card = finish({"code": "print(1)"}, json.dumps({"status": "unavailable", "error": "closed"}), False)

    assert card["status"] == "error"
    assert card["meta"]["unavailable"] is True
