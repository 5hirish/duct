"""Audit tools on the LangChain stack — parity with the Claude-SDK originals.

These check what the *model* and the *runner* observe: the tool names, the
incremental report state machine, the status strings, the callbacks, and the
rule that a bad call returns an error payload instead of raising. They were
written against the Claude-Agent-SDK originals, which is why the names are what
they are; the originals are gone and these are now the definition.

No network: the report tools are pure, and FetchPages is exercised only for its
host-scoping guard, which rejects before any fetch.
"""

from __future__ import annotations

import json

import pytest

from agents.audit.v1.tools import build_audit_tools


@pytest.fixture
def crawl_result():
    from agents.audit.schema import CrawlPlan, CrawlResult

    return CrawlResult(plan=CrawlPlan(root_url="https://getduct.ai"))


def _header(**over) -> dict:
    """Minimal valid AuditReportStart payload."""
    return {
        "overall_score": 72, "score_band": "good",
        "pages_crawled": 12, "total_sitemap_urls": 40, **over,
    }


def _category(cid: str, **over) -> dict:
    """Minimal valid AuditCategory payload."""
    return {
        "id": cid, "label": cid.title(), "score": 8,
        "tooltip": f"{cid} health", "findings": [], **over,
    }


async def _call(tools, name: str, **kwargs) -> dict:
    """Invoke a tool by name and decode its JSON result."""
    tool = next(t for t in tools if t.name == name)
    return json.loads(await tool.ainvoke(kwargs))


# ---------------------------------------------------------------------------
# Surface parity
# ---------------------------------------------------------------------------

def test_freehand_mode_exposes_only_fetch_pages(crawl_result):
    tools = build_audit_tools(crawl_result, report_mode="freehand")
    assert [t.name for t in tools] == ["FetchPages"]


def test_template_mode_exposes_the_report_builders(crawl_result):
    tools = build_audit_tools(crawl_result, report_mode="template")
    assert [t.name for t in tools] == [
        "FetchPages",
        "StartAuditReport",
        "AddAuditCategory",
        "FinalizeAuditReport",
        "SubmitAuditReport",
    ]


def test_report_tools_reuse_the_existing_pydantic_schemas(crawl_result):
    """Schemas were hand-converted to JSON Schema before; now they are the schema."""
    from agents.audit.schema import AuditCategory, AuditReportStart

    tools = {t.name: t for t in build_audit_tools(crawl_result, report_mode="template")}
    assert tools["StartAuditReport"].args_schema is AuditReportStart
    assert tools["AddAuditCategory"].args_schema is AuditCategory


# ---------------------------------------------------------------------------
# Incremental report state machine
# ---------------------------------------------------------------------------

async def test_finalize_before_any_category_is_a_recoverable_error(crawl_result):
    """Must return an error payload, not raise — a raise would end the run."""
    tools = build_audit_tools(crawl_result, report_mode="template")

    result = await _call(tools, "FinalizeAuditReport", top_priorities=[], wins=[], roadmap=[])

    assert result["status"] == "error"
    assert "AddAuditCategory" in result["message"]


async def test_start_add_finalize_accumulates_and_submits(crawl_result):
    submitted: list[dict] = []

    async def on_submit(payload: dict) -> dict:
        submitted.append(payload)
        return {"status": "published", "version": 1}

    tools = build_audit_tools(
        crawl_result, report_mode="template", on_submit_report=on_submit
    )

    await _call(tools, "StartAuditReport", **_header(headline="Solid"))
    first = await _call(tools, "AddAuditCategory", **_category("meta"))
    second = await _call(tools, "AddAuditCategory", **_category("perf"))
    final = await _call(tools, "FinalizeAuditReport", top_priorities=[], wins=[], roadmap=[])

    assert first["status"] == "category_added"
    assert first["categories_so_far"] == 1
    assert second["categories_so_far"] == 2
    assert final == {"status": "published", "version": 1}

    # The finalized payload merges the header, the categories and backend-owned fields.
    assert len(submitted) == 1
    payload = submitted[0]
    assert payload["overall_score"] == 72
    assert [c["id"] for c in payload["categories"]] == ["meta", "perf"]
    assert payload["url"] == "https://getduct.ai"
    assert payload["generated_at"], "backend fills generated_at"


async def test_start_resets_a_previous_draft(crawl_result):
    tools = build_audit_tools(crawl_result, report_mode="template")

    await _call(tools, "StartAuditReport", **_header(overall_score=50, score_band="critical"))
    await _call(tools, "AddAuditCategory", **_category("meta"))
    await _call(tools, "StartAuditReport", **_header(overall_score=80))
    again = await _call(tools, "AddAuditCategory", **_category("perf"))

    assert again["categories_so_far"] == 1, "a restart must clear accumulated categories"


async def test_submit_failure_is_reported_not_raised(crawl_result):
    async def on_submit(_payload: dict) -> dict:
        raise RuntimeError("schema validation failed")

    tools = build_audit_tools(
        crawl_result, report_mode="template", on_submit_report=on_submit
    )
    await _call(tools, "StartAuditReport", **_header(overall_score=1, score_band="critical"))
    await _call(tools, "AddAuditCategory", **_category("meta"))

    result = await _call(tools, "FinalizeAuditReport", top_priorities=[], wins=[], roadmap=[])

    assert result["status"] == "error"
    assert "schema validation failed" in result["message"]


# ---------------------------------------------------------------------------
# Live progress callback
# ---------------------------------------------------------------------------

async def test_category_callback_receives_running_count(crawl_result):
    seen: list[tuple[int, str]] = []

    async def on_added(count: int, category: dict) -> None:
        seen.append((count, category.get("id", "")))

    tools = build_audit_tools(
        crawl_result, report_mode="template", on_category_added=on_added
    )
    await _call(tools, "StartAuditReport", **_header(overall_score=1, score_band="critical"))
    await _call(tools, "AddAuditCategory", **_category("meta"))
    await _call(tools, "AddAuditCategory", **_category("perf"))

    assert seen == [(1, "meta"), (2, "perf")]


async def test_broken_progress_callback_does_not_fail_the_tool(crawl_result):
    """Streaming is best-effort — a dead SSE consumer must not break the audit."""

    async def on_added(_count: int, _category: dict) -> None:
        raise RuntimeError("SSE consumer gone")

    tools = build_audit_tools(
        crawl_result, report_mode="template", on_category_added=on_added
    )
    await _call(tools, "StartAuditReport", **_header(overall_score=1, score_band="critical"))

    result = await _call(tools, "AddAuditCategory", **_category("meta"))

    assert result["status"] == "category_added"


# ---------------------------------------------------------------------------
# FetchPages scoping (SSRF / off-site guard)
# ---------------------------------------------------------------------------

async def test_fetch_pages_rejects_off_site_urls(crawl_result):
    """Rejected before any network call — the guard is host comparison."""
    tools = build_audit_tools(crawl_result, report_mode="freehand")

    result = await _call(tools, "FetchPages", urls=["https://evil.example/steal"])

    assert result["pages"] == []
    assert any("not from audited site" in e for e in result["errors"])


# ---------------------------------------------------------------------------
# The roadmap contract
# ---------------------------------------------------------------------------

async def test_a_roadmap_phase_without_tasks_is_rejected_before_the_report_is_assembled(crawl_result):
    """Two live runs finalised the three phase headers the prompt names with
    nothing under them. The schema is the tool contract, so the empty phase is
    a validation error the agent loop hands back to the model, not a report."""
    from pydantic import ValidationError

    tools = build_audit_tools(crawl_result, report_mode="template")
    await _call(tools, "StartAuditReport", **_header())
    await _call(tools, "AddAuditCategory", **_category("on_page_seo"))
    empty_phase = {"label": "0–30 days", "theme": "Unblock", "tasks": []}

    with pytest.raises(ValidationError, match="tasks"):
        await _call(tools, "FinalizeAuditReport", top_priorities=[], wins=[], roadmap=[empty_phase])
