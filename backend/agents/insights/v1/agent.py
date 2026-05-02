"""GenerateInsightsAgent — LangGraph-backed insight generation agent.

Two-phase architecture:
  Phase 1: Goal-driven data fetch via LangGraph tool-calling loop (Phase 1 graph)
  Phase 2: Synthesis via structured output (Phase 2 graph)

Both phases are implemented as LangGraph StateGraphs (see graph.py), which gives:
  - Parallel tool execution via ToolNode (replaces sequential for-loop)
  - Per-node checkpointing via InMemorySaver (Phase 2 can retry without re-running Phase 1)
  - Multi-turn tool calling support (LLM loops back after seeing tool results)
  - Explicit arg injection node (replaces manual setdefault loop)

Provider-agnostic via init_chat_model(). Swap models with GENERATE_PROVIDER / GENERATE_MODEL.
Public API is identical to the previous LangChain implementation.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from time import perf_counter
from typing import Any

from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from agents.models import ModelName, Provider, get_api_key_kwargs
from agents.insights.goals import InsightGenerationGoal, goal_heading_text
from agents.insights.goals.organic_growth import OrganicGrowthGoal
from agents.insights.registry import get_tools_for_request as _registry_get_tools
from agents.insights.schema import SynthesisSchema
from agents.insights.tools import (
    _register_default_tools,
    get_tool_creator,
)
from agents.insights.v1.graph import InsightsGraphState, build_phase1_graph, build_phase2_graph

logger = logging.getLogger(__name__)


class GenerateInsightsAgent:
    """Insight generation agent with goal-driven tool use + structured output.

    Usage::

        agent = GenerateInsightsAgent(api_key="...", provider=Provider.OPENAI, model=ModelName.GPT_5_MINI)
        agent.setup_tools_for_goal(goal=InsightGenerationGoal.LOWER_CAC, fetch_fns={...})
        supplementary = await agent.fetch_supplementary_data(
            customer_id,
            date_from,
            date_to,
            goal=InsightGenerationGoal.LOWER_CAC,
            custom_goal="",
            context="",
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

        self.tools: list = []
        self.tools_by_name: dict[str, Any] = {}
        self.llm_with_tools = None
        self.llm_structured = self._setup_structured_output()

        # LangGraph Phase 1 graph — rebuilt whenever setup_tools_for_goal is called
        self._phase1_graph = None
        self._active_mode: str = "paid_ads"
        self._goal_allowlist: set[str] = set()

    def _setup_structured_output(self):
        """Configure structured output for the synthesis phase."""
        return self.llm.with_structured_output(
            SynthesisSchema,
            method="json_schema",
            strict=True,
        )

    def setup_tools_for_goal(
        self,
        goal: InsightGenerationGoal | OrganicGrowthGoal,
        fetch_fns: dict[str, Callable[..., dict[str, Any]]],
        mode: str = "paid_ads",
    ) -> list[str]:
        """Register supplementary tools based on the user's goal.

        ``fetch_fns`` maps tool name → pre-credentialed fetch function.
        Returns list of registered tool names.
        """
        if mode == "organic_growth":
            from agents.insights.goals.organic_growth import GOAL_TOOL_ALLOWLIST
            goal_allowlist = GOAL_TOOL_ALLOWLIST.get(goal, [])
        else:
            from agents.insights.goals.paid_ads import GOAL_TOOL_ALLOWLIST
            goal_allowlist = GOAL_TOOL_ALLOWLIST.get(goal, [])
        self._active_mode = mode
        self._goal_allowlist = set(goal_allowlist)

        _register_default_tools()
        available_tool_names = list(fetch_fns.keys())
        tool_specs = _registry_get_tools(
            goal=goal.value,
            available_tool_names=available_tool_names,
            allowlist=goal_allowlist,
            max_tools=8,
        )
        tool_names = [spec.name for spec in tool_specs]
        self.tools = []
        self.tools_by_name = {}

        for name in tool_names:
            creator = get_tool_creator(name)
            fn = fetch_fns.get(name)
            if creator and fn:
                tool = creator(fn)
                self.tools.append(tool)
                self.tools_by_name[tool.name] = tool

        if self.tools:
            self.llm_with_tools = self.llm.bind_tools(self.tools)

        # Invalidate cached Phase 1 graph — it must be rebuilt with the new tools
        self._phase1_graph = None

        registered = list(self.tools_by_name.keys())
        logger.info("Registered %d tools for goal '%s': %s", len(registered), goal.value, registered)
        return registered

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
        """Phase 1: LangGraph tool-calling loop to gather supplementary data.

        The LLM sees which tools are available and decides which to call based
        on the goal and context. ToolNode executes all requested tools in
        parallel. Returns {tool_name: result_dict} for every tool that ran.
        """
        if not self.llm_with_tools or not self.tools:
            return {}

        priority_names = self._goal_allowlist
        tool_lines = []
        for t in self.tools:
            tag = " [PRIORITY]" if t.name in priority_names else ""
            tool_lines.append(f"- {t.name}{tag}: {t.description}")
        tool_descriptions = "\n".join(tool_lines)

        _role_by_mode = {
            "organic_growth": "You are a senior organic growth analyst preparing supplementary data for an SEO insight brief.",
            "paid_ads": "You are a senior paid media analyst preparing supplementary data for a Google Ads brief.",
        }
        role_line = _role_by_mode.get(self._active_mode, "You are a data analyst preparing supplementary data for an insight brief.")
        sources_str = ", ".join(connected_sources) if connected_sources else "the connected data sources"

        system_msg = (
            f"{role_line} "
            f"Connected sources: {sources_str}. "
            "The user's goal and context are provided below. "
            "You have access to supplementary data tools. Call the tools "
            "that will provide the most actionable data for this goal. "
            "Only call tools that materially improve actionability for this goal. "
            "You do NOT need to call every available tool — only the ones relevant "
            "to the specific goal and context.\n\n"
            f"Available tools:\n{tool_descriptions}"
        )

        goal_line = goal_heading_text(goal, custom_goal=custom_goal)
        user_msg = (
            f"Goal: {goal_line}\n"
            f"Context: {context or 'None provided'}\n"
            f"Customer ID: {customer_id}\n"
            f"GA4 Property ID: {ga4_property_id or 'N/A'}\n"
            f"GSC Site URL: {gsc_site_url or 'N/A'}\n"
            f"Date range: {date_from} to {date_to}\n\n"
            "Call the tools you need to gather supplementary data for this insight."
        )

        messages = [SystemMessage(content=system_msg), HumanMessage(content=user_msg)]

        if self._phase1_graph is None:
            self._phase1_graph = build_phase1_graph(self.llm_with_tools, self.tools)

        initial_state: InsightsGraphState = {
            "goal": goal.value,
            "mode": self._active_mode,
            "customer_id": customer_id,
            "date_from": date_from,
            "date_to": date_to,
            "ga4_property_id": ga4_property_id or "",
            "gsc_site_url": gsc_site_url or "",
            "connected_sources": connected_sources or [],
            "custom_goal": custom_goal or "",
            "context": context or "",
            "messages": messages,
            "supplementary_data": {},
            "all_briefs": {},
            "business_context": None,
            "synthesis_result": None,
        }

        config = RunnableConfig(configurable={"thread_id": str(uuid.uuid4())})
        start = perf_counter()
        try:
            final = await self._phase1_graph.ainvoke(initial_state, config=config)
        except Exception:
            logger.exception("Phase 1 graph failed with %s/%s", self.provider.value, self.model.value)
            return {}

        supplementary: dict[str, Any] = final.get("supplementary_data", {})
        elapsed = perf_counter() - start
        logger.info(
            "Phase 1 completed in %.1fs — fetched %d supplementary datasets: %s",
            elapsed, len(supplementary), list(supplementary.keys()),
        )
        return supplementary

    async def synthesize(
        self,
        goal: InsightGenerationGoal | OrganicGrowthGoal,
        custom_goal: str,
        context: str,
        all_briefs: dict[str, Any],
        supplementary: dict[str, Any] | None = None,
        business_context: dict[str, Any] | None = None,
        mode: str = "paid_ads",
    ) -> SynthesisSchema:
        """Phase 2: Structured output from connector briefs + supplementary data.

        `all_briefs` maps connector_id → {"brief": {...}, "raw": {...}}.
        Returns a validated SynthesisSchema instance.
        """
        phase2_graph = build_phase2_graph(self.llm_structured)

        initial_state: InsightsGraphState = {
            "goal": goal.value,
            "mode": mode,
            "all_briefs": all_briefs,
            "supplementary_data": supplementary or {},
            "business_context": business_context,
            "custom_goal": custom_goal or "",
            "context": context or "",
            "messages": [],
            "customer_id": "",
            "date_from": "",
            "date_to": "",
            "ga4_property_id": "",
            "gsc_site_url": "",
            "connected_sources": [],
            "synthesis_result": None,
        }

        config = RunnableConfig(configurable={"thread_id": str(uuid.uuid4())})
        start = perf_counter()
        try:
            final = await phase2_graph.ainvoke(initial_state, config=config)
            result = final.get("synthesis_result")
        except Exception:
            logger.exception(
                "Phase 2 graph failed with %s/%s, returning None",
                self.provider.value,
                self.model.value,
            )
            return None

        elapsed = perf_counter() - start
        logger.info(
            "Phase 2 (synthesis) completed in %.1fs with %s/%s",
            elapsed,
            self.provider.value,
            self.model.value,
        )
        return result

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
