"""Insights v1 engine on the LangChain 1.x agent stack.

The engine had no tests before the port (see
`docs/engineering/agent-engine-consolidation-review.md` §2). These cover the
behaviour `routes/generate.py` depends on, driven by a fake chat model so they
need no API key and no network.

The load-bearing property is argument binding: connector identifiers come from
the request and are closed over per tool, so a model cannot invent a customer
id. The old implementation patched hallucinated args in a graph node instead.
"""

from __future__ import annotations

import json

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage

from agents.insights.goals import InsightGenerationGoal
from agents.insights.v1.agent import GenerateInsightsAgent, _chunk_text, _collect_tool_results
from agents.models import ModelName, Provider


class ToolCallingFake(FakeMessagesListChatModel):
    """Fake chat model that accepts `bind_tools`, so it can drive an agent loop."""

    def bind_tools(self, tools, **kwargs):  # noqa: ARG002 - fake ignores the schema
        return self


@pytest.fixture
def calls():
    """Records the kwargs each fetch function was invoked with."""
    return {}


@pytest.fixture
def fetch_fns(calls):
    def _make(name: str, payload: dict):
        def _fn(**kwargs):
            calls[name] = kwargs
            return payload

        return _fn

    return {
        "fetch_campaign_performance": _make(
            "fetch_campaign_performance", {"campaigns": [{"name": "Brand"}]}
        ),
        "fetch_search_terms": _make("fetch_search_terms", {"terms": ["duct seo"]}),
    }


def _agent(responses: list[AIMessage]) -> GenerateInsightsAgent:
    agent = GenerateInsightsAgent.__new__(GenerateInsightsAgent)
    agent.provider = Provider.GOOGLE_GENAI
    agent.model = ModelName.GEMINI_2_5_FLASH
    agent.llm = ToolCallingFake(responses=responses)
    agent.llm_structured = None
    agent._fetch_fns = {}
    agent._tool_names = []
    agent._active_mode = "paid_ads"
    agent._goal_allowlist = set()
    return agent


# ---------------------------------------------------------------------------
# Tool selection
# ---------------------------------------------------------------------------

def test_setup_selects_goal_relevant_tools(fetch_fns):
    agent = _agent([AIMessage(content="ok")])

    names = agent.setup_tools_for_goal(
        goal=InsightGenerationGoal.LOWER_CAC, fetch_fns=fetch_fns
    )

    assert names, "expected at least one goal-relevant tool"
    # Never offer a tool we have no fetch function for.
    assert set(names) <= set(fetch_fns)


def test_setup_ignores_tools_without_fetch_fns(fetch_fns):
    agent = _agent([AIMessage(content="ok")])
    agent.setup_tools_for_goal(
        goal=InsightGenerationGoal.LOWER_CAC,
        fetch_fns={"fetch_search_terms": fetch_fns["fetch_search_terms"]},
    )
    assert agent._tool_names == ["fetch_search_terms"]


def test_setup_excludes_tools_outside_the_goal_allowlist(fetch_fns):
    """LOWER_CAC does not want campaign performance — the allowlist decides."""
    agent = _agent([AIMessage(content="ok")])
    names = agent.setup_tools_for_goal(
        goal=InsightGenerationGoal.LOWER_CAC,
        fetch_fns={"fetch_campaign_performance": fetch_fns["fetch_campaign_performance"]},
    )
    assert names == []


# ---------------------------------------------------------------------------
# Argument binding — the reason the patch node is gone
# ---------------------------------------------------------------------------

def test_bound_tool_takes_no_arguments(fetch_fns):
    """The model picks the tool; it cannot supply (or invent) the identifiers."""
    agent = _agent([AIMessage(content="ok")])
    agent.setup_tools_for_goal(goal=InsightGenerationGoal.LOWER_CAC, fetch_fns=fetch_fns)

    tool = agent._bind_tool(
        "fetch_search_terms",
        customer_id="123",
        date_from="2026-01-01",
        date_to="2026-01-31",
        ga4_property_id="",
        gsc_site_url="",
    )

    assert tool is not None
    assert tool.args == {}, "identifiers must not be exposed to the model"


def test_bind_tool_routes_identifiers_by_connector(fetch_fns):
    agent = _agent([AIMessage(content="ok")])
    agent._fetch_fns = fetch_fns
    ids = dict(
        customer_id="cust-1",
        date_from="2026-01-01",
        date_to="2026-01-31",
        ga4_property_id="ga4-9",
        gsc_site_url="https://getduct.ai",
    )
    # google_ads connector → customer_id, not property_id/site_url
    assert agent._bind_tool("fetch_campaign_performance", **ids) is not None


def test_bind_tool_returns_none_without_fetch_fn():
    agent = _agent([AIMessage(content="ok")])
    assert (
        agent._bind_tool(
            "fetch_campaign_performance",
            customer_id="1", date_from="a", date_to="b",
            ga4_property_id="", gsc_site_url="",
        )
        is None
    )


# ---------------------------------------------------------------------------
# Phase 1
# ---------------------------------------------------------------------------

async def test_phase1_runs_selected_tools_with_request_identifiers(fetch_fns, calls):
    agent = _agent(
        [
            AIMessage(
                content="",
                tool_calls=[{"name": "fetch_search_terms", "args": {}, "id": "c1"}],
            ),
            AIMessage(content="Gathered search terms."),
        ]
    )
    agent.setup_tools_for_goal(goal=InsightGenerationGoal.LOWER_CAC, fetch_fns=fetch_fns)

    supplementary = await agent.fetch_supplementary_data(
        customer_id="9876543210",
        date_from="2026-01-01",
        date_to="2026-01-31",
        goal=InsightGenerationGoal.LOWER_CAC,
    )

    assert supplementary == {"fetch_search_terms": {"terms": ["duct seo"]}}
    assert calls["fetch_search_terms"] == {
        "customer_id": "9876543210",
        "date_from": "2026-01-01",
        "date_to": "2026-01-31",
    }


async def test_phase1_returns_empty_without_tools():
    agent = _agent([AIMessage(content="nothing to do")])
    result = await agent.fetch_supplementary_data(
        customer_id="1", date_from="a", date_to="b", goal=InsightGenerationGoal.LOWER_CAC
    )
    assert result == {}


async def test_phase1_survives_a_failing_connector(fetch_fns):
    """One broken connector must not abort the brief."""

    def _boom(**_kwargs):
        raise RuntimeError("Google Ads 503")

    agent = _agent(
        [
            AIMessage(
                content="",
                tool_calls=[{"name": "fetch_search_terms", "args": {}, "id": "c1"}],
            ),
            AIMessage(content="done"),
        ]
    )
    agent.setup_tools_for_goal(
        goal=InsightGenerationGoal.LOWER_CAC,
        fetch_fns={"fetch_search_terms": _boom},
    )

    supplementary = await agent.fetch_supplementary_data(
        customer_id="1", date_from="2026-01-01", date_to="2026-01-31",
        goal=InsightGenerationGoal.LOWER_CAC,
    )

    assert supplementary == {"fetch_search_terms": {}}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def test_collect_tool_results_falls_back_to_raw():
    from langchain_core.messages import ToolMessage

    messages = [
        ToolMessage(content=json.dumps({"a": 1}), name="good", tool_call_id="1"),
        ToolMessage(content="not json", name="bad", tool_call_id="2"),
    ]
    assert _collect_tool_results(messages) == {"good": {"a": 1}, "bad": {"raw": "not json"}}


def test_chunk_text_handles_string_and_block_content():
    assert _chunk_text(AIMessage(content="hello")) == "hello"
    assert (
        _chunk_text(
            AIMessage(content=[{"type": "text", "text": "a"}, {"type": "thinking", "text": "x"}])
        )
        == "a"
    )
    assert _chunk_text(None) == ""
