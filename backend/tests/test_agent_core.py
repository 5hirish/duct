"""Unit tests for the shared agent core (agents/core/*). No API key required."""

from __future__ import annotations

import asyncio

from agents.core.artifacts import (
    ArtifactMetadata,
    BaseArtifact,
    EvidenceSource,
    Finding,
    Narrative,
    RecommendedAction,
)
from agents.core.business_context import BusinessContext, format_business_context
from agents.core.contracts import BaseAgentRequest, StreamingAgentRunner
from agents.core.events import AgentEvent, AgentStep, make_event
from agents.core.prompts import DUCT_REPORT_CLOSE, DUCT_REPORT_OPEN, xml_block


# --- events -----------------------------------------------------------------

def test_event_values_and_aliases_match_frontend_contract():
    assert AgentEvent.PIPELINE_STARTED == "pipeline_started"
    assert AgentEvent.REPORT_CHUNK == "report_chunk"
    assert AgentEvent.PLAN_GENERATED == "plan_generated"
    assert AgentStep.ENRICHING == "enriching"
    # Per-agent modules re-export the SAME shared enum objects.
    from agents.audit.events import AuditEvent
    from agents.content.events import ContentEvent
    assert AuditEvent is AgentEvent and ContentEvent is AgentEvent


def test_make_event_normalizes_event_and_keeps_payload():
    body = make_event(AgentEvent.STEP_STARTED, step_id="crawl_pages", label="Crawling")
    assert body == {"event": "step_started", "step_id": "crawl_pages", "label": "Crawling"}


# --- prompts ----------------------------------------------------------------

def test_xml_block_wraps_or_empties():
    assert xml_block("data", "  hello  ") == "<data>\nhello\n</data>"
    assert xml_block("data", "") == ""
    assert xml_block("data", "   ") == ""
    assert DUCT_REPORT_OPEN == "<duct_report>" and DUCT_REPORT_CLOSE == "</duct_report>"


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


# --- artifacts --------------------------------------------------------------

def test_base_artifact_composes_shared_components():
    art = BaseArtifact(
        metadata=ArtifactMetadata(agent_type="audit_seo", version="1", source_metadata={"theme": "organic_growth"}),
        headline="Spend efficiency declined",
        narrative=Narrative(verdict="declining", summary="ROAS fell", takeaway="cut waste"),
        findings=[
            Finding(
                id="title-too-short",
                title="Titles too short",
                severity="warn",
                evidence_sources=[EvidenceSource(source="crawl", url="https://x.com", value="13 chars")],
            )
        ],
        recommended_actions=[RecommendedAction(id="a1", title="Rewrite titles", priority="high")],
    )
    dumped = art.model_dump()
    assert dumped["metadata"]["source_metadata"]["theme"] == "organic_growth"
    assert dumped["findings"][0]["evidence_sources"][0]["value"] == "13 chars"
    # Round-trips.
    assert BaseArtifact.model_validate(dumped) == art


# --- contracts --------------------------------------------------------------

def test_base_agent_request_defaults_and_business_context():
    req = BaseAgentRequest()
    assert req.engine == "" and req.adaptive_thinking is False
    assert isinstance(req.business_context, BusinessContext)


def test_streaming_runner_protocol_is_runtime_checkable():
    class Dummy:
        async def run(self, session_id, request, emit):  # noqa: ANN001
            return None

    class NotARunner:
        pass

    assert isinstance(Dummy(), StreamingAgentRunner)
    assert not isinstance(NotARunner(), StreamingAgentRunner)


# --- report stream parser ---------------------------------------------------

from agents.core.report_stream import DuctReportStreamParser  # noqa: E402


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
    parser = DuctReportStreamParser(
        on_text=rec.on_text,
        on_report_chunk=rec.on_chunk,
        on_report_close=rec.on_close,
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
    rec = _run_parser(["intro <duct_report>PAYLOAD</duct_report> outro"])
    assert rec.opens == 1
    assert "".join(rec.chunks) == "PAYLOAD"
    assert rec.closes == [("PAYLOAD", "intro")]
    assert "".join(rec.text) == "intro  outro"  # prose before + after the tag


def test_parser_split_open_tag_holdback():
    # The open tag is split across chunks — holdback must not miss it.
    rec = _run_parser(["before <duct_re", "port>PAY</duct_report>"])
    assert rec.opens == 1
    assert rec.closes == [("PAY", "before")]


def test_parser_split_close_tag():
    rec = _run_parser(["<duct_report>PAY</duct_", "report>after"])
    assert [c for c in rec.closes] == [("PAY", "")]
    assert "".join(rec.text) == "after"  # remainder after close streamed as prose


def test_parser_payload_streamed_in_pieces():
    rec = _run_parser(["<duct_report>", "A", "B", "C", "</duct_report>"])
    assert rec.chunks == ["A", "B", "C"]
    assert rec.closes == [("ABC", "")]
