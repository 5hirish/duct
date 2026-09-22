"""The allowlist and the cards it draws (agents/core/activity.py).

Two things are worth a test here and the rest is shape. First that a tool
nobody mapped emits **nothing** — the allowlist is a privacy boundary, not a
cosmetic one, and its failure mode is a memory read or a catalogue listing
appearing in a shared transcript. Second that a failure keeps the provider's
own sentence and the status that explains it, because that pair is what the
card turns into "Reconnect this source".
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agents.core.activity import ActivityKind, activity_hooks
from agents.core.events import AgentEvent, StepStatus


class Recorder:
    """Stands in for the hooks being wrapped, and proves they still run."""

    def __init__(self) -> None:
        self.uses: list[tuple[str, str]] = []
        self.results: list[tuple[str, bool]] = []

    async def on_use(self, name: str, tool_input, tool_use_id: str) -> None:
        self.uses.append((name, tool_use_id))

    async def on_result(self, name: str, result, tool_use_id: str, is_error: bool) -> None:
        self.results.append((name, is_error))


async def run_call(tool: str, args: dict, result, *, is_error: bool = False):
    """One tool call through the hooks; returns (emitted events, recorder)."""
    events: list[dict] = []
    rec = Recorder()

    async def emit(payload: dict) -> None:
        events.append(payload)

    use, done = activity_hooks(emit, rec.on_use, rec.on_result)
    await use(tool, args, "call-1")
    await done(tool, result, "call-1", is_error)
    return events, rec


def test_every_runner_wires_the_same_hooks():
    """A new agent gets the transcript's cards by existing, not by remembering.

    Every runner opens its thread with ``DeepSession``; this asserts each one
    passes tool hooks that go through ``activity_hooks``, so an agent added
    next year shows its data pulls, searches and images the way these three
    do. The audit runner passed no hooks at all for months — it recorded no
    tool traffic and showed none — and nothing failed, which is the whole
    argument for checking it here.
    """
    runners = sorted((Path(__file__).resolve().parents[1] / "agents").rglob("*/v1/runner.py"))
    assert runners, "no runners found — has the layout moved?"
    for runner in runners:
        source = runner.read_text()
        if "DeepSession(" not in source:
            continue
        assert "activity_hooks(" in source, (
            f"{runner.relative_to(runner.parents[3])} opens a DeepSession without activity_hooks: "
            "its tool calls would be invisible in the transcript"
        )
        assert "on_tool_use=" in source and "on_tool_result=" in source, (
            f"{runner.relative_to(runner.parents[3])} builds hooks it never passes to DeepSession"
        )


@pytest.mark.asyncio
async def test_unmapped_tool_emits_nothing_but_still_records():
    # write_todos has the todo strip; a card for the call would say it twice.
    events, rec = await run_call("write_todos", {"todos": []}, json.dumps({"status": "ok"}))
    assert events == []
    assert rec.uses == [("write_todos", "call-1")]
    assert rec.results == [("write_todos", False)]


@pytest.mark.asyncio
async def test_data_pull_is_two_events_running_then_the_verdict():
    body = json.dumps({
        "status": "ok",
        "entity_id": "ga4_landing_pages",
        "connector_id": "ga4",
        "date_from": "2026-08-18",
        "date_to": "2026-09-16",
        "data": {"rows": [1, 2, 3]},
    })
    events, _ = await run_call("FetchData", {"entity_id": "ga4_landing_pages"}, body)

    assert [e["event"] for e in events] == [AgentEvent.TOOL_ACTIVITY] * 2
    assert [e["status"] for e in events] == [StepStatus.RUNNING, StepStatus.SUCCESS]
    # Both halves carry the same id, which is what makes them one card.
    assert {e["activity_id"] for e in events} == {"call-1"}
    finished = events[1]
    assert finished["kind"] == ActivityKind.DATA
    assert finished["source"] == "ga4"
    assert finished["meta"]["rows"] == 3
    assert finished["meta"]["date_to"] == "2026-09-16"


@pytest.mark.asyncio
async def test_failed_pull_keeps_the_providers_sentence_and_its_status():
    body = json.dumps({
        "status": "reauth_required",
        "entity_id": "google_ads_campaigns",
        "connector_id": "google_ads",
        "message": "google_ads rejected its stored credential (expired or revoked).",
    })
    events, _ = await run_call("FetchData", {"entity_id": "google_ads_campaigns"}, body)
    finished = events[1]
    assert finished["status"] == StepStatus.ERROR
    assert finished["reason"] == "reauth_required"
    assert "rejected its stored credential" in finished["error"]


@pytest.mark.asyncio
async def test_search_carries_its_sources_and_nothing_it_read():
    body = json.dumps({
        "status": "ok",
        "query": "self-hosted AI gateway",
        "answer": "A long grounded answer the card must not carry.",
        "grounded": True,
        "sources": [{"title": "docs.litellm.ai", "url": "https://docs.litellm.ai/x"}],
    })
    events, _ = await run_call("WebSearch", {"query": "self-hosted AI gateway"}, body)
    finished = events[1]
    assert finished["kind"] == ActivityKind.WEB_SEARCH
    assert finished["meta"]["sources"] == [
        {"title": "docs.litellm.ai", "url": "https://docs.litellm.ai/x"}
    ]
    # The page text is the model's to read, not the transcript's to carry.
    assert "grounded answer" not in json.dumps(finished)


@pytest.mark.asyncio
async def test_image_card_carries_the_pictures():
    body = json.dumps({"asset_ids": ["a1"], "asset_urls": ["/uploads/a1.png"], "model": "gemini-image"})
    events, _ = await run_call("generate_image", {"prompt": "a kestrel over a field"}, body)
    finished = events[1]
    assert finished["kind"] == ActivityKind.IMAGE
    assert finished["meta"]["images"] == ["/uploads/a1.png"]
    assert finished["status"] == StepStatus.SUCCESS


@pytest.mark.asyncio
async def test_a_result_that_is_not_json_still_draws_a_card():
    """The recorder can hand back content blocks or an over-cap preview; the
    card then falls back to what the call asked for rather than vanishing."""
    events, _ = await run_call("WebFetch", {"url": "https://example.com/a/b"}, "<blocks>")
    finished = events[1]
    assert finished["title"] == "example.com"
    assert finished["status"] == StepStatus.SUCCESS


@pytest.mark.asyncio
async def test_a_broken_mapper_never_fails_the_run(monkeypatch):
    import agents.core.activity as activity

    def boom(*_args, **_kwargs):
        raise RuntimeError("mapper is wrong")

    monkeypatch.setitem(activity.ACTIVITY_TOOLS, "FetchData", (boom, boom))
    events, rec = await run_call("FetchData", {"entity_id": "x"}, "{}")
    assert events == []
    assert rec.results == [("FetchData", False)]


@pytest.mark.asyncio
async def test_the_audits_page_read_is_one_card_for_all_its_pages():
    body = json.dumps({"pages": [{"url": "https://acme.io/"}, {"url": "https://acme.io/pricing"}], "errors": ["https://acme.io/x: 404"]})
    events, _ = await run_call("FetchPages", {"urls": ["https://acme.io/", "https://acme.io/pricing", "https://acme.io/x"]}, body)
    finished = events[1]
    assert finished["kind"] == ActivityKind.WEB_FETCH
    assert finished["title"] == "acme.io"
    assert finished["meta"]["count"] == 2
    assert finished["meta"]["failed"] == 1
    assert finished["status"] == StepStatus.SUCCESS  # some pages came back; the row says which did not


@pytest.mark.asyncio
async def test_a_memory_search_says_what_was_asked_and_how_much_came_back():
    body = json.dumps({"count": 2, "memories": [{"title": "Pricing changed in September"}, {"title": "Mobile is the growth channel"}]})
    events, _ = await run_call("SearchMemory", {"query": "pricing"}, body)
    finished = events[1]
    assert finished["kind"] == ActivityKind.MEMORY
    assert finished["title"] == "pricing"
    assert finished["meta"] == {"count": 2}
    # The entries themselves are not on the card: they are the model's to
    # read, and the digest already drew what the turn recalled.
    assert "Pricing changed" not in json.dumps(finished)


@pytest.mark.asyncio
async def test_a_write_to_memory_is_still_not_a_card():
    """RememberFact has its own row — MEMORY_WRITTEN, with undo — so a card
    for the call would say the same thing twice."""
    events, _ = await run_call("RememberFact", {"title": "x"}, json.dumps({"status": "ok"}))
    assert events == []


@pytest.mark.asyncio
async def test_the_context_notice_records_the_row_and_draws_the_card():
    from agents.core.activity import PROJECT_CONTEXT_TOOL, announce_context

    recorded: list[dict] = []
    events: list[dict] = []

    class Recorder:
        async def record_context(self, data: dict) -> None:
            recorded.append(data)

    async def emit(payload: dict) -> None:
        events.append(payload)

    record = {"agent_type": "insights", "resume": False, "blocks": {"business_context": "Acme sells…", "memory": "", "data_sources": "ga4, gsc"}}
    await announce_context(Recorder(), emit, record)
    assert recorded == [record]
    assert len(events) == 1
    assert events[0]["tool"] == PROJECT_CONTEXT_TOOL
    assert events[0]["kind"] == ActivityKind.CONTEXT
    # Only the blocks the run actually had: an empty memory digest is not
    # something the person was told the model read.
    assert events[0]["meta"] == {"blocks": ["business_context", "data_sources"], "resume": False}


@pytest.mark.asyncio
async def test_a_recorder_that_fails_does_not_stop_the_notice():
    from agents.core.activity import announce_context

    events: list[dict] = []

    class Recorder:
        async def record_context(self, data: dict) -> None:
            raise RuntimeError("db is away")

    async def emit(payload: dict) -> None:
        events.append(payload)

    await announce_context(Recorder(), emit, {"blocks": {}})
    assert len(events) == 1


@pytest.mark.asyncio
async def test_a_resume_records_its_row_but_draws_no_notice():
    """The reopened transcript already carries the notice from the run that
    composed the context; a fresh one on every reopen would be noise."""
    from agents.core.activity import announce_context

    recorded: list[dict] = []
    events: list[dict] = []

    class Recorder:
        async def record_context(self, data: dict) -> None:
            recorded.append(data)

    async def emit(payload: dict) -> None:
        events.append(payload)

    await announce_context(Recorder(), emit, {"resume": True, "blocks": {"resume_primer": "…"}})
    assert len(recorded) == 1
    assert events == []
