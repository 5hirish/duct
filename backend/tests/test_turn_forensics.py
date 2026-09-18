"""Where a turn's time went, and which request it belonged to.

Both exist because answering "why was that brief slow" took an evening with a
SQL script against the transcript table. The clock prints the answer at the
end of every turn; the request id makes every line of one run one grep.
"""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

from agents.core.lc import TurnClock


def test_turn_clock_names_the_slowest_tools_and_the_rest():
    clock = TurnClock()
    clock.tool_started("FetchData", "a")
    clock.tool_started("task", "b")
    time.sleep(0.02)
    clock.tool_finished("FetchData", "a")
    clock.tool_finished("task", "b")
    # A result whose call was never seen (a replayed thread) still counts.
    clock.tool_finished("ListDataSources", "orphan")
    line = clock.summary()
    assert line.startswith("turn ")
    assert "3 tool calls" in line
    assert "slowest FetchData" in line or "slowest task" in line
    assert "model+overhead" in line


def test_turn_clock_without_tools():
    assert TurnClock().summary().endswith("no tool calls")


def test_request_id_is_minted_echoed_and_honoured():
    from server import app

    with TestClient(app) as client:
        minted = client.get("/health").headers["x-request-id"]
        assert len(minted) == 8 and all(c in "0123456789abcdef" for c in minted)
        echoed = client.get("/health", headers={"X-Request-Id": "trace-42"}).headers["x-request-id"]
        assert echoed == "trace-42"
        # Garbage in a header stays out of the logs: a fresh id is minted instead.
        hostile = client.get("/health", headers={"X-Request-Id": "x" * 200}).headers["x-request-id"]
        assert hostile != "x" * 200 and len(hostile) == 8
