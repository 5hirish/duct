"""The app's wire vocabulary is the backend's, read from the app's own files.

``app/src/lib/agentEvents.js`` calls itself a mirror of ``agents/core/events.py``
and ``agents/core/errors.py``; ``insightsEvents.js`` mirrors ``AgentStep``; and
the fixtures under ``app/src/lib/__fixtures__`` are recorded SSE streams the
reducer tests replay. Nothing checked that any of them still agreed with the
enums here — a fixture carried a memory kind the backend has never emitted,
and both sides could add a member the other never learns about. This parses
the JavaScript with a regex (the files are frozen object literals, not code
that needs evaluating) and holds each side to the other.

Backend and app deploy separately, app first, so the app is allowed to know
legacy wire values the backend no longer sends. It is not allowed to be
missing one the backend does send: that is a card that never renders.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from agents.core.activity import ACTIVITY_TOOLS, ActivityKind
from agents.core.errors import ErrorCode
from agents.core.events import AgentEvent, AgentStep
from models.memory import MEMORY_KINDS

APP_LIB = Path(__file__).resolve().parents[2] / "app" / "src" / "lib"
_MEMBER = re.compile(r'^\s*([A-Z][A-Z0-9_]*)\s*:\s*"([^"]+)"', re.M)


def _frozen_object(source: str, name: str) -> dict[str, str]:
    """``export const NAME = Object.freeze({ KEY: "value", ... })`` → mapping."""
    match = re.search(rf"export const {name} = Object\.freeze\(\{{(.*?)\n\}}\);", source, re.S)
    assert match, f"{name} not found as a frozen object literal"
    return dict(_MEMBER.findall(match.group(1)))


@pytest.fixture(scope="module")
def app_events() -> dict[str, str]:
    return _frozen_object((APP_LIB / "agentEvents.js").read_text(), "AgentEvent")


def test_every_backend_event_is_known_to_the_app(app_events):
    backend = {member.value for member in AgentEvent}
    missing = backend - set(app_events.values())
    assert not missing, f"backend emits events the app cannot render: {sorted(missing)}"


def test_the_app_names_no_event_the_backend_has_never_emitted(app_events):
    backend = {member.value for member in AgentEvent}
    legacy = {value for key, value in app_events.items() if key.startswith("LEGACY_")}
    unknown = set(app_events.values()) - backend - legacy
    assert not unknown, f"app expects events no backend enum defines: {sorted(unknown)}"


def test_error_codes_match_exactly():
    source = (APP_LIB / "agentEvents.js").read_text()
    app_codes = set(_frozen_object(source, "ErrorCode").values())
    assert app_codes == {member.value for member in ErrorCode}


def test_activity_kinds_match_exactly():
    """A kind the app cannot draw is a silent card; one the backend never
    sends is dead code. Both sides freeze the same six."""
    source = (APP_LIB / "agentEvents.js").read_text()
    app_kinds = set(_frozen_object(source, "ActivityKind").values())
    assert app_kinds == {member.value for member in ActivityKind}


def test_the_two_tool_allowlists_agree():
    """The backend decides what a live run shows; the app rebuilds the same
    rows from stored tool traffic on a reopened thread. Two lists, one
    contract — drift means a thread that looks different after a reload than
    it did while it ran."""
    source = (APP_LIB / "toolActivity.js").read_text()
    block = re.search(r"export const ACTIVITY_TOOLS = Object\.freeze\(\{(.*?)\n\}\);", source, re.S)
    assert block, "ACTIVITY_TOOLS not found as a frozen object literal"
    app_tools = dict(re.findall(r"^\s*([A-Za-z_][A-Za-z0-9_]*):\s*ActivityKind\.([A-Z_]+)", block.group(1), re.M))
    assert set(app_tools) == set(ACTIVITY_TOOLS), "the app and the backend allowlist different tools"
    for tool, kind_name in app_tools.items():
        start, _finish = ACTIVITY_TOOLS[tool]
        assert start({})["kind"] == getattr(ActivityKind, kind_name), f"{tool} maps to two kinds"


def test_insights_step_ids_exist_on_the_backend():
    source = (APP_LIB / "insightsEvents.js").read_text()
    steps = set(_frozen_object(source, "InsightsStep").values())
    assert steps <= {member.value for member in AgentStep}


def _fixture_events():
    for path in sorted(APP_LIB.glob("__fixtures__/*.json")):
        for frame in json.loads(path.read_text()):
            if isinstance(frame, dict) and frame.get("event"):
                yield path.name, frame


def test_every_fixture_event_is_a_backend_event():
    backend = {member.value for member in AgentEvent}
    stray = sorted({(name, f["event"]) for name, f in _fixture_events() if f["event"] not in backend})
    assert not stray, f"fixtures replay events the backend does not emit: {stray}"


def test_fixture_memory_kinds_are_real_kinds():
    """The memory chips render by kind; a kind the backend never stores is a
    fixture that proves nothing about the real stream."""
    seen: list[tuple[str, str]] = []
    for name, frame in _fixture_events():
        if frame["event"] == AgentEvent.MEMORY_RECALLED:
            seen += [(name, m.get("kind", "")) for m in frame.get("memories", [])]
        elif frame["event"] == AgentEvent.MEMORY_WRITTEN:
            memory = frame.get("memory") or {}
            if "kind" in memory:
                seen.append((name, memory["kind"]))
    unknown = sorted({pair for pair in seen if pair[1] not in MEMORY_KINDS})
    assert not unknown, f"fixture memory kinds the backend does not know: {unknown}"
