"""GenerateInsightsAgent — LangChain-based insight generation agent.

Two-phase architecture (following nomadtools barrio pattern):
  Phase 1: Goal-driven data fetch via tool calling (supplementary queries)
  Phase 2: Synthesis via structured output (all collected data)

Provider-agnostic via init_chat_model(). Swap models by changing
GENERATE_PROVIDER / GENERATE_MODEL env vars.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from time import perf_counter
from typing import Any

from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from agents.models import ModelName, Provider, get_api_key_kwargs
from agents.reporter.goals import InsightGenerationGoal, goal_heading_text
from agents.reporter.prompts import get_synthesis_user_prompt, get_system_prompt
from agents.reporter.schema import SynthesisSchema
from agents.reporter.tools import (
    GOAL_TOOL_PRIORITIES,
    create_ad_group_performance_tool,
    create_campaign_performance_tool,
    create_device_performance_tool,
    create_ga4_conversion_paths_tool,
    create_ga4_landing_pages_tool,
    create_geo_performance_tool,
    create_gsc_page_performance_tool,
    create_gsc_query_performance_tool,
    create_search_terms_tool,
    get_tool_names_for_goal,
)

logger = logging.getLogger(__name__)

# Map tool name → creator function
_TOOL_CREATORS = {
    "fetch_campaign_performance": create_campaign_performance_tool,
    "fetch_search_terms": create_search_terms_tool,
    "fetch_device_performance": create_device_performance_tool,
    "fetch_geo_performance": create_geo_performance_tool,
    "fetch_ad_group_performance": create_ad_group_performance_tool,
    "fetch_ga4_landing_pages": create_ga4_landing_pages_tool,
    "fetch_ga4_conversion_paths": create_ga4_conversion_paths_tool,
    "fetch_gsc_query_performance": create_gsc_query_performance_tool,
    "fetch_gsc_page_performance": create_gsc_page_performance_tool,
}


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
            brief_dict=brief_dict,
            raw_payload=raw_payload,
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

    def _setup_structured_output(self):
        """Configure structured output for the synthesis phase."""
        return self.llm.with_structured_output(
            SynthesisSchema,
            method="json_schema",
            strict=True,
        )

    def setup_tools_for_goal(
        self,
        goal: InsightGenerationGoal,
        fetch_fns: dict[str, Callable[..., dict[str, Any]]],
    ) -> list[str]:
        """Register supplementary tools based on the user's goal.

        ``fetch_fns`` maps tool name → pre-credentialed fetch function.
        Returns list of registered tool names.
        """
        tool_names = get_tool_names_for_goal(goal)
        self.tools = []
        self.tools_by_name = {}

        for name in tool_names:
            creator = _TOOL_CREATORS.get(name)
            fn = fetch_fns.get(name)
            if creator and fn:
                tool = creator(fn)
                self.tools.append(tool)
                self.tools_by_name[tool.name] = tool

        if self.tools:
            self.llm_with_tools = self.llm.bind_tools(self.tools)

        registered = list(self.tools_by_name.keys())
        logger.info("Registered %d tools for goal '%s': %s", len(registered), goal.value, registered)
        return registered

    async def fetch_supplementary_data(
        self,
        customer_id: str,
        date_from: str,
        date_to: str,
        goal: InsightGenerationGoal,
        ga4_property_id: str = "",
        gsc_site_url: str = "",
        custom_goal: str = "",
        context: str = "",
    ) -> dict[str, Any]:
        """Phase 1: Let the LLM decide which supplementary data to fetch.

        The LLM sees which tools are available and decides which to call
        based on the goal and context. Returns a dict of
        {tool_name: result_dict} for all tools that were called.
        """
        if not self.llm_with_tools or not self.tools:
            return {}

        priority_names = set(GOAL_TOOL_PRIORITIES.get(goal, []))
        tool_lines = []
        for t in self.tools:
            tag = " [PRIORITY]" if t.name in priority_names else ""
            tool_lines.append(f"- {t.name}{tag}: {t.description}")
        tool_descriptions = "\n".join(tool_lines)

        system_msg = (
            "You are a Google Ads analyst preparing data for a report. "
            "The user's goal and context are provided below. "
            "You have access to supplementary data tools. Call the tools "
            "that will provide the most actionable data for this goal. "
            "Tools marked [PRIORITY] are most likely useful for this goal, "
            "but call any tool you believe will provide actionable data. "
            "You do NOT need to call every tool — only the ones relevant "
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

        messages = [
            SystemMessage(content=system_msg),
            HumanMessage(content=user_msg),
        ]

        supplementary: dict[str, Any] = {}
        start = perf_counter()

        try:
            # First LLM call — get tool call decisions
            response: AIMessage = await self.llm_with_tools.ainvoke(messages)

            if not response.tool_calls:
                logger.info("Agent chose not to call any supplementary tools")
                return {}

            # Execute each tool call
            messages.append(response)
            for tool_call in response.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]

                # Inject connector identifiers and dates if the LLM did not provide them.
                if "ga4" in tool_name:
                    tool_args.setdefault("property_id", ga4_property_id)
                elif "gsc" in tool_name:
                    tool_args.setdefault("site_url", gsc_site_url)
                else:
                    tool_args.setdefault("customer_id", customer_id)
                tool_args.setdefault("date_from", date_from)
                tool_args.setdefault("date_to", date_to)

                tool = self.tools_by_name.get(tool_name)
                if not tool:
                    logger.warning("Unknown tool call: %s", tool_name)
                    continue

                logger.info("Calling tool: %s", tool_name)
                try:
                    result = tool.invoke(tool_args)
                    supplementary[tool_name] = result
                    messages.append(
                        ToolMessage(content=json.dumps(result, default=str)[:50_000], tool_call_id=tool_call["id"])
                    )
                except Exception:
                    logger.exception("Tool %s failed", tool_name)
                    messages.append(
                        ToolMessage(content='{"error": "Tool execution failed"}', tool_call_id=tool_call["id"])
                    )

        except Exception:
            logger.exception("Phase 1 (tool calling) failed with %s/%s", self.provider.value, self.model.value)
            return {}

        elapsed = perf_counter() - start
        logger.info(
            "Phase 1 completed in %.1fs — fetched %d supplementary datasets: %s",
            elapsed, len(supplementary), list(supplementary.keys()),
        )
        return supplementary

    async def synthesize(
        self,
        goal: InsightGenerationGoal,
        custom_goal: str,
        context: str,
        brief_dict: dict[str, Any],
        raw_payload: dict[str, Any],
        supplementary: dict[str, Any] | None = None,
        business_context: dict[str, Any] | None = None,
    ) -> SynthesisSchema:
        """Phase 2: Structured output from brief + raw data + supplementary.

        Returns a validated SynthesisSchema instance.
        """
        system_prompt = get_system_prompt(
            goal=goal,
            custom_goal=custom_goal,
            context=context,
            business_context=business_context,
        )
        user_prompt = get_synthesis_user_prompt(brief_dict, raw_payload, supplementary=supplementary)

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]

        start = perf_counter()
        try:
            result = await self.llm_structured.ainvoke(messages)
        except Exception:
            logger.exception(
                "Synthesis failed with %s/%s, returning None",
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

    # ── legacy convenience (kept for backwards compat) ──────────────────
    def merge_synthesis(
        self,
        brief_dict: dict[str, Any],
        synthesis: SynthesisSchema | None,
    ) -> dict[str, Any]:
        """Merge synthesis results into the brief dict (legacy flat format).

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


# Backward compatibility alias for older imports.
GenerateAgent = GenerateInsightsAgent
