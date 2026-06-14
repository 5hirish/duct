"""LangGraph StateGraph implementation for V1 insight generation.

Two separate graphs:
  Phase 1 (build_phase1_graph): LLM tool-calling loop → supplementary data dict
  Phase 2 (build_phase2_graph): Structured output synthesis → SynthesisSchema

The graphs are used by GenerateInsightsAgent (agent.py) which preserves the
existing public API.
"""

from __future__ import annotations

import json
import logging
import operator
from functools import partial
from typing import Annotated, Any, TypedDict

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from agents.insights.prompts import get_synthesis_user_prompt, get_system_prompt
from langgraph.graph.message import add_messages

logger = logging.getLogger(__name__)


class InsightsGraphState(TypedDict):
    # Phase 1 context — set once before the graph runs, read-only inside nodes
    goal: str
    mode: str
    customer_id: str
    date_from: str
    date_to: str
    ga4_property_id: str
    gsc_site_url: str
    connected_sources: list[str]
    custom_goal: str
    context: str

    # Phase 1 message accumulator — add_messages appends and deduplicates by ID
    messages: Annotated[list[BaseMessage], add_messages]

    # Phase 2 inputs/outputs
    supplementary_data: Annotated[dict[str, Any], operator.or_]  # dict-merge reducer
    all_briefs: dict[str, Any]
    business_context: dict[str, Any] | None
    synthesis_result: Any | None


# ---------------------------------------------------------------------------
# Node functions
# ---------------------------------------------------------------------------

async def _call_llm_node(state: InsightsGraphState, *, llm_with_tools) -> dict:
    """Invoke the tool-bound LLM; appends AIMessage to messages."""
    try:
        response = await llm_with_tools.ainvoke(state["messages"])
        return {"messages": [response]}
    except Exception:
        logger.exception("call_llm node failed")
        # Return an AIMessage with no tool_calls so the graph routes to extract_supplementary
        from langchain_core.messages import AIMessage
        return {"messages": [AIMessage(content="", tool_calls=[])]}


def _patch_tool_args_node(state: InsightsGraphState) -> dict:
    """Inject connector identifiers into LLM-generated tool_call args.

    The LLM should not be generating customer_id / property_id / site_url
    from thin air — they come from the request. This node patches them in
    before ToolNode executes, replacing the manual setdefault loop in v1.
    """
    last_msg = state["messages"][-1]
    if not hasattr(last_msg, "tool_calls") or not last_msg.tool_calls:
        return {}

    patched_calls = []
    for tc in last_msg.tool_calls:
        args = dict(tc["args"])
        tool_name = tc["name"]
        if "ga4" in tool_name:
            args.setdefault("property_id", state["ga4_property_id"])
        elif "gsc" in tool_name:
            args.setdefault("site_url", state["gsc_site_url"])
        else:
            args.setdefault("customer_id", state["customer_id"])
        args.setdefault("date_from", state["date_from"])
        args.setdefault("date_to", state["date_to"])
        patched_calls.append({**tc, "args": args})

    # model_copy preserves the message ID so add_messages replaces the original in-place
    new_msg = last_msg.model_copy(update={"tool_calls": patched_calls})
    return {"messages": [new_msg]}


def _extract_supplementary_node(state: InsightsGraphState) -> dict:
    """Collect ToolMessage results from messages into a supplementary_data dict."""
    supplementary: dict[str, Any] = {}
    for msg in state["messages"]:
        if isinstance(msg, ToolMessage) and msg.name:
            try:
                supplementary[msg.name] = json.loads(msg.content)
            except (json.JSONDecodeError, TypeError):
                supplementary[msg.name] = {"raw": msg.content}
    return {"supplementary_data": supplementary}


async def _synthesize_node(state: InsightsGraphState, *, llm_structured) -> dict:
    """Produce structured SynthesisSchema output from briefs + supplementary data."""
    system_prompt = get_system_prompt(
        goal=state["goal"],
        mode=state.get("mode", "paid_ads"),
    )
    user_prompt = get_synthesis_user_prompt(
        state["all_briefs"],
        supplementary=state.get("supplementary_data") or {},
        mode=state.get("mode", "paid_ads"),
        business_context=state.get("business_context"),
        goal=state["goal"],
        custom_goal=state.get("custom_goal", ""),
        context=state.get("context", ""),
    )
    messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
    try:
        result = await llm_structured.ainvoke(messages)
        return {"synthesis_result": result}
    except Exception:
        logger.exception("synthesize node failed")
        return {"synthesis_result": None}


# ---------------------------------------------------------------------------
# Graph factories
# ---------------------------------------------------------------------------

def build_phase1_graph(llm_with_tools, tools: list):
    """Build the Phase 1 StateGraph: LLM tool-calling loop → supplementary data.

    Topology:
      START → call_llm ──[tool_calls]──► patch_tool_args → tools → call_llm
                       └──[no calls]──► extract_supplementary → END
    """
    tool_node = ToolNode(tools, handle_tool_errors=True)

    graph = StateGraph(InsightsGraphState)
    graph.add_node("call_llm", partial(_call_llm_node, llm_with_tools=llm_with_tools))
    graph.add_node("patch_tool_args", _patch_tool_args_node)
    graph.add_node("tools", tool_node)
    graph.add_node("extract_supplementary", _extract_supplementary_node)

    graph.add_edge(START, "call_llm")
    graph.add_conditional_edges(
        "call_llm",
        tools_condition,
        path_map={"tools": "patch_tool_args", "__end__": "extract_supplementary"},
    )
    graph.add_edge("patch_tool_args", "tools")
    graph.add_edge("tools", "call_llm")  # loop — supports multi-turn tool calling
    graph.add_edge("extract_supplementary", END)

    return graph.compile(checkpointer=MemorySaver())


def build_phase2_graph(llm_structured):
    """Build the Phase 2 StateGraph: single synthesize node → SynthesisSchema.

    Wrapping in a StateGraph gives checkpointing and streaming parity with Phase 1.
    """
    graph = StateGraph(InsightsGraphState)
    graph.add_node("synthesize", partial(_synthesize_node, llm_structured=llm_structured))
    graph.add_edge(START, "synthesize")
    graph.add_edge("synthesize", END)

    return graph.compile(checkpointer=MemorySaver())
