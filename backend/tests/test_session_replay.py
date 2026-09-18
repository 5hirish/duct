"""Replaying a stored session on its own data must be hermetic.

The seed is keyed on the call's arguments, a miss answers with a status the
model can act on instead of a network call, and the runner threads the seed
through untouched. The offline suite's socket guard is what proves the last
part: a replay that leaked would fail here, not in production."""

from __future__ import annotations

import importlib.util
import json
import sys
import uuid
from pathlib import Path

from agents.insights.data_tools import build_data_tools_lc

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "session_replay.py"
spec = importlib.util.spec_from_file_location("session_replay", SCRIPT)
session_replay = importlib.util.module_from_spec(spec)
sys.modules["session_replay"] = session_replay
spec.loader.exec_module(session_replay)


def _fetch_tool(tools):
    return next(t for t in tools if t.name == "FetchData")


async def test_a_seeded_pull_is_served_and_an_unseeded_one_never_leaves_the_process():
    seed = {("ga4_traffic", "2026-08-20", "2026-09-17"): json.dumps({"status": "ok", "data": "sessions\n10"})}
    finished: list[tuple[str, dict]] = []

    async def on_fetch(entity_id: str, result: dict) -> None:
        finished.append((entity_id, result))

    tool = _fetch_tool(build_data_tools_lc(uuid.uuid4(), user_id=uuid.uuid4(), replay=seed, on_fetch=on_fetch))

    hit = json.loads(await tool.ainvoke({"entity_id": "ga4_traffic", "date_from": "2026-08-20", "date_to": "2026-09-17"}))
    miss = json.loads(await tool.ainvoke({"entity_id": "gsc_queries", "date_from": "2026-08-20", "date_to": "2026-09-17"}))

    assert hit["status"] == "ok" and hit["data"] == "sessions\n10"
    assert miss["status"] == "not_in_replay" and miss["entity_id"] == "gsc_queries"
    assert "not made in the original run" in miss["message"]
    # The hit is silent (a cache hit, as in a live session); the miss is a step.
    assert [(e, r["connector_id"]) for e, r in finished] == [("gsc_queries", "replay")]


def test_the_seed_is_keyed_on_what_the_model_asked_for():
    events = [
        {"kind": "tool_use", "data": {"name": "FetchData", "tool_use_id": "a", "input": {"entity_id": "ga4_traffic", "date_from": "2026-08-20", "date_to": "2026-09-17"}}},
        {"kind": "tool_result", "data": {"name": "FetchData", "tool_use_id": "a", "output": "{\"status\": \"ok\"}"}},
        # A repeat of the same pull (the session cache answered it) does not overwrite.
        {"kind": "tool_use", "data": {"name": "FetchData", "tool_use_id": "b", "input": {"entity_id": "ga4_traffic", "date_from": "2026-08-20", "date_to": "2026-09-17"}}},
        {"kind": "tool_result", "data": {"name": "FetchData", "tool_use_id": "b", "output": "{\"status\": \"ok\", \"second\": true}"}},
        # Defaults left blank are part of the key, because that is how the cache saw them.
        {"kind": "tool_use", "data": {"name": "FetchData", "tool_use_id": "c", "input": {"entity_id": "gsc_queries"}}},
        {"kind": "tool_result", "data": {"name": "FetchData", "tool_use_id": "c", "output": {"status": "ok", "rows": 3}}},
        {"kind": "tool_use", "data": {"name": "ListDataSources", "tool_use_id": "d", "input": {}}},
        {"kind": "tool_result", "data": {"name": "ListDataSources", "tool_use_id": "d", "output": "[]"}},
    ]
    seed = session_replay.replay_seed(events)
    assert set(seed) == {("ga4_traffic", "2026-08-20", "2026-09-17"), ("gsc_queries", "", "")}
    assert "second" not in seed[("ga4_traffic", "2026-08-20", "2026-09-17")]
    assert json.loads(seed[("gsc_queries", "", "")])["rows"] == 3
