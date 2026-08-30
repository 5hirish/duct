"""Unit tests for the shared agent core (agents/core/*). No API key required."""

from __future__ import annotations

import asyncio

from agents.core.context import BusinessContext, format_business_context
from agents.core.events import AgentEvent, AgentStep
from agents.core.prompts import DUCT_ARTIFACT_CLOSE, DUCT_ARTIFACT_OPEN, xml_block


# --- events -----------------------------------------------------------------

def test_event_values_and_aliases_match_frontend_contract():
    assert AgentEvent.PIPELINE_STARTED == "pipeline_started"
    assert AgentEvent.ARTIFACT_CHUNK == "artifact_chunk"
    assert AgentEvent.PLAN_GENERATED == "plan_generated"
    assert AgentStep.ENRICHING == "enriching"
    # Per-agent modules re-export the SAME shared enum objects.
    from agents.audit.events import AuditEvent
    from agents.content.events import ContentEvent
    assert AuditEvent is AgentEvent and ContentEvent is AgentEvent


# --- prompts ----------------------------------------------------------------

def test_xml_block_wraps_or_empties():
    assert xml_block("data", "  hello  ") == "<data>\nhello\n</data>"
    assert xml_block("data", "") == ""
    assert xml_block("data", "   ") == ""
    assert DUCT_ARTIFACT_OPEN == "<duct_artifact>" and DUCT_ARTIFACT_CLOSE == "</duct_artifact>"


# --- business context -------------------------------------------------------

def test_business_context_coerce_from_dict_model_and_none():
    assert BusinessContext.coerce(None) == BusinessContext()
    bc = BusinessContext.coerce({"business_name": "Acme", "target_roas": 3.0})
    assert bc.business_name == "Acme" and bc.target_roas == 3.0
    assert BusinessContext.coerce(bc) is bc
    # Legacy/unknown fields are tolerated (extra="ignore"), so one payload fits all agents.
    assert BusinessContext.coerce({"some_legacy_field": 1}).business_name == ""


def test_format_business_context_renders_only_populated_and_wraps():
    out = format_business_context(
        {"business_name": "Acme", "industry": "SaaS", "target_roas": 3.0, "competitors": ["x.com", "y.com"]}
    )
    assert out.startswith("<business_context>") and out.endswith("</business_context>")
    assert "Business: Acme" in out and "Industry: SaaS" in out
    assert "Target ROAS: 3.0" in out
    assert "Competitors: x.com, y.com" in out
    # Empty/zero fields are omitted; nothing populated → empty string.
    assert "Target CPA" not in out
    assert format_business_context(None) == ""
    assert format_business_context(BusinessContext()) == ""


def test_format_business_context_section_toggles():
    data = {"primary_organic_kpi": "organic_traffic", "target_cpa": 50.0}
    paid_only = format_business_context(data, include_organic=False)
    assert "Target CPA: 50.0" in paid_only and "Primary organic KPI" not in paid_only
    organic_only = format_business_context(data, include_paid=False)
    assert "Primary organic KPI: organic_traffic" in organic_only and "Target CPA" not in organic_only


# --- report stream parser ---------------------------------------------------

from agents.core.stream import DuctArtifactStreamParser  # noqa: E402


class _Rec:
    def __init__(self):
        self.text: list[str] = []
        self.chunks: list[str] = []
        self.closes: list[tuple[str, str]] = []
        self.opens = 0

    async def on_text(self, t):  # noqa: ANN001
        self.text.append(t)

    async def on_chunk(self, t):  # noqa: ANN001
        self.chunks.append(t)

    async def on_close(self, raw, turn):  # noqa: ANN001
        self.closes.append((raw, turn))

    async def on_open(self):
        self.opens += 1


def _run_parser(chunks: list[str]) -> _Rec:
    rec = _Rec()
    parser = DuctArtifactStreamParser(
        on_text=rec.on_text,
        on_artifact_chunk=rec.on_chunk,
        on_artifact_close=rec.on_close,
        on_open=rec.on_open,
        log_prefix="test",
    )

    async def go():
        for c in chunks:
            await parser.feed(c)
        await parser.flush()

    asyncio.run(go())
    return rec


def test_parser_plain_prose_no_report():
    rec = _run_parser(["hello ", "world"])
    assert "".join(rec.text) == "hello world"
    assert rec.closes == [] and rec.chunks == [] and rec.opens == 0


def test_parser_full_report_single_chunk():
    rec = _run_parser(["intro <duct_artifact>PAYLOAD</duct_artifact> outro"])
    assert rec.opens == 1
    assert "".join(rec.chunks) == "PAYLOAD"
    assert rec.closes == [("PAYLOAD", "intro")]
    assert "".join(rec.text) == "intro  outro"  # prose before + after the tag


def test_parser_split_open_tag_holdback():
    # The open tag is split across chunks — holdback must not miss it.
    rec = _run_parser(["before <duct_arti", "fact>PAY</duct_artifact>"])
    assert rec.opens == 1
    assert rec.closes == [("PAY", "before")]


def test_parser_split_close_tag():
    rec = _run_parser(["<duct_artifact>PAY</duct_", "artifact>after"])
    assert [c for c in rec.closes] == [("PAY", "")]
    assert "".join(rec.text) == "after"  # remainder after close streamed as prose


def test_parser_payload_streamed_in_pieces():
    rec = _run_parser(["<duct_artifact>", "A", "B", "C", "</duct_artifact>"])
    assert rec.chunks == ["A", "B", "C"]
    assert rec.closes == [("ABC", "")]


# --- legacy <duct_report> acceptance ----------------------------------------
# The tag was renamed report → artifact. The parser still accepts the old pair
# so conversations recorded before the rename replay, and a turn already in
# flight against a cached system prompt does not strand its payload.

def test_parser_accepts_legacy_report_tag():
    rec = _run_parser(["intro <duct_report>PAYLOAD</duct_report> outro"])
    assert rec.opens == 1
    assert rec.closes == [("PAYLOAD", "intro")]
    assert "".join(rec.text) == "intro  outro"


def test_parser_accepts_legacy_tag_split_across_chunks():
    rec = _run_parser(["before <duct_re", "port>PAY</duct_report>"])
    assert rec.opens == 1
    assert rec.closes == [("PAY", "before")]


def test_parser_does_not_cross_close_mismatched_tags():
    """A legacy open must not be terminated by the new close tag (or vice
    versa). Whichever convention opened decides which close ends the payload —
    otherwise a stream mentioning one tag could truncate the other."""
    rec = _run_parser(["<duct_report>PAY</duct_artifact>still inside"])
    assert rec.opens == 1
    assert rec.closes == []  # never closed — the wrong close tag was ignored

    rec = _run_parser(["<duct_artifact>PAY</duct_report>still inside"])
    assert rec.opens == 1
    assert rec.closes == []


# --- claude_sdk startup helpers ---------------------------------------------

from collections import deque  # noqa: E402

from agents.core import claude_sdk as _sdk  # noqa: E402


def test_is_rate_limited_matches_known_hints():
    assert _sdk.is_rate_limited("Error: usage limit reached for this org")
    assert _sdk.is_rate_limited("HTTP 429 Too Many Requests")
    assert not _sdk.is_rate_limited("ENOENT: command not found")
    assert not _sdk.is_rate_limited("")


def test_captured_stderr_prefers_buffer_then_skips_placeholder():
    buf: deque[str] = deque(["line one", "line two"])
    assert _sdk.captured_stderr(buf, Exception()) == "line one\nline two"

    class _Exc(Exception):
        stderr = _sdk.PLACEHOLDER_STDERR

    assert _sdk.captured_stderr(deque(), _Exc()) == ""  # placeholder treated as none

    class _Exc2(Exception):
        stderr = "real error text"

    assert _sdk.captured_stderr(deque(), _Exc2()) == "real error text"


def test_describe_startup_failure_phrasing():
    rl = _sdk.describe_startup_failure("usage limit reached", 1, agent_label="content engine")
    assert "content engine" in rl and "rate limit" in rl.lower()

    crash = _sdk.describe_startup_failure("boom", 1, agent_label="content engine")
    assert "exit code 1" in crash and "boom" in crash

    empty = _sdk.describe_startup_failure("", 1, agent_label="content engine")
    assert "without emitting stderr" in empty and "NODE_OPTIONS" in empty


# --- tool_schema (typed model -> @tool input_schema bridge) -----------------

import json  # noqa: E402

from agents.core.tool_schema import tool_schema  # noqa: E402


def test_tool_schema_inlines_enums_and_strips_pydantic_noise():
    """tool_schema() turns a typed Pydantic model into the clean flat JSON Schema
    the SDK passes verbatim: enums inlined, Optionals collapsed, noise stripped,
    required + ranges kept. This is also the PYDANTIC-DRIFT GUARD — the
    no-artifacts assertion fails loudly if a Pydantic upgrade changes the
    model_json_schema() shape in a way the cleaner doesn't handle."""
    from enum import StrEnum

    from pydantic import BaseModel, ConfigDict, Field

    class Color(StrEnum):
        RED = "red"
        BLUE = "blue"

    class Nested(BaseModel):
        label: str = Field(description="cell label")
        shade: Color = Field(Color.RED, description="cell color")

    class Inp(BaseModel):
        model_config = ConfigDict(extra="forbid")
        name: str = Field(description="the name")
        color: Color = Field(Color.RED, description="pick one")
        opt_color: Color | None = Field(None, description="optional enum")
        count: int = Field(1, ge=1, le=4, description="how many")
        note: str | None = Field(None, description="optional note")
        tags: list[str] = Field(default_factory=list, description="labels")
        cells: list[Nested] = Field(default_factory=list, description="nested list")

    s = tool_schema(Inp)
    blob = json.dumps(s)

    # No Pydantic bookkeeping/indirection may reach the model. If a Pydantic
    # version changes the schema shape (new wrapper key, different Optional
    # encoding), this catches the leak.
    for artifact in ("$ref", "$defs", "anyOf", "allOf", "title", "default"):
        assert artifact not in blob, f"{artifact} leaked into tool_schema output"

    assert s["type"] == "object"
    assert s["required"] == ["name"]                              # only the no-default field
    assert s["properties"]["color"]["enum"] == ["red", "blue"]   # enum inlined in place
    assert s["properties"]["opt_color"]["enum"] == ["red", "blue"]  # optional enum collapsed + inlined
    assert s["properties"]["color"]["description"] == "pick one"  # field desc wins over the enum def's
    assert s["properties"]["note"] == {"type": "string", "description": "optional note"}  # Optional -> T
    assert s["properties"]["count"]["minimum"] == 1 and s["properties"]["count"]["maximum"] == 4
    assert s["properties"]["tags"] == {"type": "array", "items": {"type": "string"}, "description": "labels"}
    # nested model inlined recursively (proves it for non-flat inputs other agents may use)
    cell = s["properties"]["cells"]["items"]
    assert cell["properties"]["shade"]["enum"] == ["red", "blue"]
    assert cell["required"] == ["label"]


# --- shutdown: close_all_sessions drains SSE streams -------------------------

def test_close_all_sessions_sentinels_sse_and_clears_registry():
    """On shutdown close_all_sessions must end every SSE stream: it pops each
    session and puts the None sentinel on its event_queue (what _sse_stream
    breaks on) AND chat_queue. This is what stops uvicorn's graceful shutdown
    from hanging on long-lived streams (a --reload or deploy would otherwise
    block until the chat idle-timeout)."""
    import asyncio as _asyncio

    from agents.core.session import (
        BaseAgentSession,
        close_all_sessions,
        get_session,
        register_session,
    )

    eq, cq = _asyncio.Queue(), _asyncio.Queue()
    register_session(BaseAgentSession(
        session_id="shutdown-drain-test", agent_type="content",
        event_queue=eq, chat_queue=cq,
    ))
    assert get_session("shutdown-drain-test") is not None

    close_all_sessions()

    assert get_session("shutdown-drain-test") is None   # popped from the registry
    assert eq.get_nowait() is None                      # SSE sentinel → _sse_stream exits
    assert cq.get_nowait() is None                      # chat-loop sentinel
