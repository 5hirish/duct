"""GenerateInsightsAgent — insight generation on the LangChain 1.x agent stack.

Two phases, same public interface as before so ``routes/generate.py`` is
unchanged:

  Phase 1 (data fetch): ``create_agent`` runs the tool-calling loop. The model
    picks *which* goal-relevant tools to call; it never supplies their
    arguments — connector identifiers and the date range are baked into each
    tool's closure at bind time (see ``_bind_tool``). That removes the whole
    class of hallucinated-identifier bugs the old graph patched around with a
    dedicated ``_patch_tool_args_node``.

  Phase 2 (synthesis): a single structured-output call. The previous version
    wrapped this one node in a ``StateGraph`` for "checkpointing and streaming
    parity"; nothing depended on either, so the graph is gone and token
    streaming comes from ``astream_events`` instead.

Replaces the hand-rolled two-graph implementation (``v1/graph.py``, deleted) as
part of consolidating on one harness —
see `the engine consolidation review (duct-cloud, private)` §9.

Provider-agnostic via ``init_chat_model``: any provider LangChain supports,
including OpenAI-compatible gateways such as OpenRouter. Swap with
GENERATE_PROVIDER / GENERATE_MODEL.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from time import perf_counter
from typing import Any

from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool
from pydantic import BaseModel

from agents.models import ModelName, Provider, get_api_key_kwargs
from agents.insights.goals import InsightGenerationGoal, goal_heading_text
from agents.insights.goals.organic_growth import OrganicGrowthGoal
from agents.insights.prompts import get_synthesis_user_prompt, get_system_prompt
from agents.insights.registry import get_tools_for_request as _registry_get_tools
from agents.insights.schema import SynthesisSchema
from agents.insights.tools import (
    CONNECTOR_BY_TOOL,
    TOOL_DESCRIPTIONS,
    _register_default_tools,
)

logger = logging.getLogger(__name__)

# Ceiling on the Phase 1 tool-calling loop. The model calls each tool at most
# once, so this only bounds pathological retry loops.
_MAX_PHASE1_ITERATIONS = 6

_ROLE_BY_MODE = {
    "organic_growth": (
        "You are a senior organic growth analyst preparing supplementary data "
        "for an SEO insight brief."
    ),
    "paid_ads": (
        "You are a senior paid media analyst preparing supplementary data for a "
        "Google Ads brief."
    ),
}


class _NoArgs(BaseModel):
    """Empty tool schema — every fetch argument is pre-bound, so the model
    chooses the tool and nothing else."""


class GenerateInsightsAgent:
    """Insight generation agent with goal-driven tool use + structured output.

    Usage::

        agent = GenerateInsightsAgent(api_key="...", provider=Provider.OPENAI, model=ModelName.GPT_5_MINI)
        agent.setup_tools_for_goal(goal=InsightGenerationGoal.LOWER_CAC, fetch_fns={...})
        supplementary = await agent.fetch_supplementary_data(
            customer_id, date_from, date_to, goal=InsightGenerationGoal.LOWER_CAC,
        )
        result = await agent.synthesize(
            goal=InsightGenerationGoal.LOWER_CAC,
            custom_goal="",
            context="",
            all_briefs=all_briefs,
            supplementary=supplementary,
        )
    """

    def __init__(
        self,
        api_key: str,
        provider: Provider = Provider.GOOGLE_GENAI,
        model: ModelName = ModelName.GEMINI_2_5_FLASH,
        temperature: float = 1.0,
    ) -> None:
        self.provider = provider
        self.model = model

        api_key_kwargs = get_api_key_kwargs(provider, api_key)
        self.llm = init_chat_model(
            model=model.value,
            model_provider=provider.value,
            temperature=temperature,
            **api_key_kwargs,
        )
        self.llm_structured = self._setup_structured_output()

        # Populated by setup_tools_for_goal; bound to identifiers per fetch call.
        self._fetch_fns: dict[str, Callable[..., dict[str, Any]]] = {}
        self._tool_names: list[str] = []
        self._active_mode: str = "paid_ads"
        self._goal_allowlist: set[str] = set()

    def _setup_structured_output(self):
        """Configure structured output for the synthesis phase."""
        return self.llm.with_structured_output(
            SynthesisSchema,
            method="json_schema",
            strict=True,
        )

    # -----------------------------------------------------------------------
    # Tool setup
    # -----------------------------------------------------------------------

    def setup_tools_for_goal(
        self,
        goal: InsightGenerationGoal | OrganicGrowthGoal,
        fetch_fns: dict[str, Callable[..., dict[str, Any]]],
        mode: str = "paid_ads",
    ) -> list[str]:
        """Select the supplementary tools relevant to the user's goal.

        ``fetch_fns`` maps tool name → pre-credentialed fetch function.
        Returns the list of selected tool names. The tools themselves are built
        per request in ``fetch_supplementary_data``, once the connector
        identifiers are known.
        """
        if mode == "organic_growth":
            from agents.insights.goals.organic_growth import GOAL_TOOL_ALLOWLIST
        else:
            from agents.insights.goals.paid_ads import GOAL_TOOL_ALLOWLIST
        goal_allowlist = GOAL_TOOL_ALLOWLIST.get(goal, [])

        self._active_mode = mode
        self._goal_allowlist = set(goal_allowlist)
        self._fetch_fns = fetch_fns

        _register_default_tools()
        tool_specs = _registry_get_tools(
            goal=goal.value,
            available_tool_names=list(fetch_fns.keys()),
            allowlist=goal_allowlist,
            max_tools=8,
        )
        self._tool_names = [spec.name for spec in tool_specs if spec.name in fetch_fns]

        logger.info(
            "Selected %d tools for goal '%s': %s",
            len(self._tool_names), goal.value, self._tool_names,
        )
        return list(self._tool_names)

    def _bind_tool(
        self,
        name: str,
        *,
        customer_id: str,
        date_from: str,
        date_to: str,
        ga4_property_id: str,
        gsc_site_url: str,
    ) -> StructuredTool | None:
        """Wrap a fetch function as a zero-argument tool.

        The connector identifiers come from the request, never from the model —
        so they are closed over here rather than exposed in the tool schema. The
        fetch functions are blocking HTTP clients, so they run in a worker
        thread to keep the event loop free.
        """
        fn = self._fetch_fns.get(name)
        if fn is None:
            return None
        connector = CONNECTOR_BY_TOOL.get(name, "google_ads")

        if connector == "ga4":
            kwargs = {"property_id": ga4_property_id, "date_from": date_from, "date_to": date_to}
        elif connector == "gsc":
            kwargs = {"site_url": gsc_site_url, "date_from": date_from, "date_to": date_to}
        else:
            kwargs = {"customer_id": customer_id, "date_from": date_from, "date_to": date_to}

        async def _run() -> str:
            try:
                result = await asyncio.to_thread(lambda: fn(**kwargs))
            except Exception:
                # One failing connector must not abort the whole brief.
                logger.exception("Phase 1 tool %s failed", name)
                return json.dumps({})
            return json.dumps(result, default=str)

        description = TOOL_DESCRIPTIONS.get(name, f"Fetch {name.replace('_', ' ')}.")
        if name in self._goal_allowlist:
            description = f"[PRIORITY] {description}"

        return StructuredTool.from_function(
            coroutine=_run,
            name=name,
            description=description,
            args_schema=_NoArgs,
        )

    # -----------------------------------------------------------------------
    # Phase 1 — supplementary data
    # -----------------------------------------------------------------------

    async def fetch_supplementary_data(
        self,
        customer_id: str,
        date_from: str,
        date_to: str,
        goal: InsightGenerationGoal | OrganicGrowthGoal,
        ga4_property_id: str = "",
        gsc_site_url: str = "",
        custom_goal: str = "",
        context: str = "",
        connected_sources: list[str] | None = None,
    ) -> dict[str, Any]:
        """Phase 1: agent tool-calling loop to gather supplementary data.

        The model decides which of the goal-relevant tools are worth calling.
        Returns {tool_name: result_dict} for every tool that ran.
        """
        tools = [
            tool
            for name in self._tool_names
            if (
                tool := self._bind_tool(
                    name,
                    customer_id=customer_id,
                    date_from=date_from,
                    date_to=date_to,
                    ga4_property_id=ga4_property_id,
                    gsc_site_url=gsc_site_url,
                )
            )
            is not None
        ]
        if not tools:
            return {}

        sources = ", ".join(connected_sources) if connected_sources else "the connected data sources"
        role = _ROLE_BY_MODE.get(
            self._active_mode,
            "You are a data analyst preparing supplementary data for an insight brief.",
        )
        system_prompt = (
            f"{role} Connected sources: {sources}. "
            "Call the tools that provide the most actionable data for the user's "
            "goal. Only call tools that materially improve actionability — you do "
            "NOT need to call every available tool. Tools marked [PRIORITY] are "
            "the most relevant for this goal. Each tool takes no arguments; the "
            "account identifiers and date range are already applied. "
            "When you have gathered enough data, stop and reply with a one-line summary."
        )
        user_prompt = (
            f"Goal: {goal_heading_text(goal, custom_goal=custom_goal)}\n"
            f"Context: {context or 'None provided'}\n"
            f"Date range: {date_from} to {date_to}\n\n"
            "Call the tools you need to gather supplementary data for this insight."
        )

        agent = create_agent(model=self.llm, tools=tools, system_prompt=system_prompt)

        start = perf_counter()
        try:
            final = await agent.ainvoke(
                {"messages": [HumanMessage(content=user_prompt)]},
                {"recursion_limit": _MAX_PHASE1_ITERATIONS * 2},
            )
        except Exception:
            logger.exception(
                "Phase 1 failed with %s/%s", self.provider.value, self.model.value
            )
            return {}

        supplementary = _collect_tool_results(final.get("messages", []))
        logger.info(
            "Phase 1 completed in %.1fs — fetched %d supplementary datasets: %s",
            perf_counter() - start, len(supplementary), list(supplementary),
        )
        return supplementary

    # -----------------------------------------------------------------------
    # Phase 2 — synthesis
    # -----------------------------------------------------------------------

    async def synthesize(
        self,
        goal: InsightGenerationGoal | OrganicGrowthGoal,
        custom_goal: str,
        context: str,
        all_briefs: dict[str, Any],
        supplementary: dict[str, Any] | None = None,
        business_context: dict[str, Any] | None = None,
        user_context: dict[str, Any] | None = None,
        mode: str = "paid_ads",
        emit_event: Callable | None = None,
        memory: str = "",
    ) -> SynthesisSchema | None:
        """Phase 2: structured output from connector briefs + supplementary data.

        ``all_briefs`` maps connector_id → {"brief": {...}, "raw": {...}}.
        Returns a validated SynthesisSchema, or None if synthesis failed.
        """
        messages = [
            SystemMessage(content=get_system_prompt(goal=goal.value, mode=mode)),
            HumanMessage(
                content=get_synthesis_user_prompt(
                    all_briefs,
                    supplementary=supplementary or {},
                    mode=mode,
                    business_context=business_context,
                    user_context=user_context,
                    goal=goal.value,
                    custom_goal=custom_goal or "",
                    context=context or "",
                    memory=memory,
                )
            ),
        ]

        start = perf_counter()
        try:
            if emit_event is not None:
                result = await self._synthesize_streaming(messages, emit_event)
            else:
                result = await self.llm_structured.ainvoke(messages)
        except Exception:
            logger.exception(
                "Phase 2 (synthesis) failed with %s/%s, returning None",
                self.provider.value,
                self.model.value,
            )
            return None

        logger.info(
            "Phase 2 (synthesis) completed in %.1fs with %s/%s",
            perf_counter() - start, self.provider.value, self.model.value,
        )
        return result

    async def _synthesize_streaming(
        self, messages: list, emit_event: Callable
    ) -> SynthesisSchema | None:
        """Structured synthesis that also emits token deltas as they arrive.

        ``with_structured_output`` yields only the parsed object, so the raw
        token stream is taken from the underlying chat-model events. If no
        parsed output is seen (provider differences in event shape), fall back
        to a plain call rather than losing the brief.
        """
        result: SynthesisSchema | None = None
        async for event in self.llm_structured.astream_events(messages):
            kind = event.get("event")
            if kind == "on_chat_model_stream":
                text = _chunk_text(event.get("data", {}).get("chunk"))
                if text:
                    await emit_event({"event": "synthesis_chunk", "text": text})
            elif kind in ("on_chain_end", "on_parser_end"):
                output = event.get("data", {}).get("output")
                if isinstance(output, SynthesisSchema):
                    result = output

        if result is None:
            logger.warning("Streaming synthesis produced no parsed output; retrying without streaming")
            result = await self.llm_structured.ainvoke(messages)
        return result

    # -----------------------------------------------------------------------
    # Result shaping (unchanged)
    # -----------------------------------------------------------------------

    def apply_classification_overrides(
        self,
        brief_dict: dict[str, Any],
        synthesis: SynthesisSchema | None,
    ) -> None:
        """Apply LLM classification overrides to campaign action fields in-place.

        Mutates ``brief_dict["campaigns"]`` so the connector brief reflects
        the LLM's judgment on action/action_reason.  Does nothing when
        synthesis is None or has no overrides.
        """
        if synthesis is None:
            return

        overrides = synthesis.model_dump().get("classification_overrides", [])
        if not overrides or "campaigns" not in brief_dict:
            return

        override_map = {o["campaign_name"]: o for o in overrides}
        for campaign in brief_dict["campaigns"]:
            name = campaign.get("campaign_name", "")
            if name in override_map:
                ovr = override_map[name]
                campaign["action"] = ovr["override_action"]
                campaign["action_reason"] = ovr["reasoning"]

    @staticmethod
    def extract_synthesis(synthesis: SynthesisSchema | None) -> dict[str, Any] | None:
        """Convert SynthesisSchema to a plain dict for the envelope.

        Returns None when synthesis failed or was skipped.
        """
        if synthesis is None:
            return None
        return synthesis.model_dump()

    def merge_synthesis(
        self,
        brief_dict: dict[str, Any],
        synthesis: SynthesisSchema | None,
    ) -> dict[str, Any]:
        """Merge synthesis results into the brief dict (flat format).

        Prefer ``apply_classification_overrides`` + ``extract_synthesis`` for
        the envelope format.
        """
        if synthesis is None:
            return brief_dict

        out = synthesis.model_dump()
        brief_dict["narrative"] = out["narrative"]
        brief_dict["highlights"] = out["highlights"]
        brief_dict["risks"] = out["risks"]
        brief_dict["recommended_actions"] = out["recommended_actions"]
        brief_dict["classification_overrides"] = out.get("classification_overrides", [])
        brief_dict["analysis_notes"] = out.get("analysis_notes", "")

        self.apply_classification_overrides(brief_dict, synthesis)
        return brief_dict


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _collect_tool_results(messages: list) -> dict[str, Any]:
    """Gather ToolMessage payloads into {tool_name: result}."""
    supplementary: dict[str, Any] = {}
    for msg in messages:
        if isinstance(msg, ToolMessage) and msg.name:
            try:
                supplementary[msg.name] = json.loads(msg.content)
            except (json.JSONDecodeError, TypeError):
                supplementary[msg.name] = {"raw": msg.content}
    return supplementary


def _chunk_text(chunk: Any) -> str:
    """Text out of a chat-model stream chunk, for both string and block content."""
    content = getattr(chunk, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            item.get("text", "")
            for item in content
            if isinstance(item, dict) and item.get("type") == "text"
        )
    return ""
