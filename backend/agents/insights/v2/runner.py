"""AdkInsightsRunner — ADK-based drop-in replacement for GenerateInsightsAgent.

Public interface mirrors GenerateInsightsAgent (v1) so routes/generate.py
can select either engine via a config flag without any other changes.

Key differences from v1:
- Both phases run inside a single ADK 2.x dynamic-workflow node (the
  replacement for 1.x's SequentialAgent): an orchestrator node dispatches
  the two LlmAgent phases via Context.run_node.
- setup_tools_for_goal() + run_pipeline() replace the separate
  fetch_supplementary_data() / synthesize() calls.
- fetch_supplementary_data() and synthesize() are kept as no-op stubs for
  interface parity; the route layer calls run_pipeline() instead.
- Structured output is obtained by parsing the LLM's raw JSON text with
  SynthesisSchema.model_validate_json() (provider-agnostic).

API key injection:
  ADK reads credentials from standard env vars:
    GOOGLE_API_KEY   — for Gemini models
    ANTHROPIC_API_KEY — for Claude models (via google.adk.models.anthropic_llm)
  The runner sets the correct env var at construction time if it is not
  already present, then restores the original value when the run completes.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from collections.abc import Callable
from time import perf_counter
from typing import Any

from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types as genai_types

from agents.insights.goals import InsightGenerationGoal
from agents.insights.goals.organic_growth import OrganicGrowthGoal
from agents.insights.prompts import get_synthesis_user_prompt, get_system_prompt
from agents.insights.registry import get_tools_for_request as _registry_get_tools
from agents.insights.schema import SynthesisSchema
from agents.insights.tools import _register_default_tools
from agents.engines import Engine, ENGINE_PROVIDER_ENV_VAR as _ENGINE_PROVIDER_ENV_VAR
from agents.models import ModelName, Provider

from .agents import SYNTHESIS_AGENT_NAME, build_pipeline_node
from .schema_compat import extract_json_dict, parse_synthesis_from_text
from .state_keys import (
    STATE_ALL_BRIEFS,
    STATE_CONNECTED_SRCS,
    STATE_CONTEXT,
    STATE_CUSTOM_GOAL,
    STATE_CUSTOMER_ID,
    STATE_DATE_FROM,
    STATE_DATE_TO,
    STATE_GA4_PROPERTY_ID,
    STATE_GOAL,
    STATE_GSC_SITE_URL,
    STATE_MODE,
    STATE_SUPPLEMENTARY,
    STATE_SYNTHESIS_TEXT,
)
from .tools import build_adk_tools_for_goal

logger = logging.getLogger(__name__)

_APP_NAME = "duct"
_USER_ID = "system"

_PROVIDER_ENV_VAR: dict[Provider, str] = _ENGINE_PROVIDER_ENV_VAR[Engine.V2]


def _resolve_adk_model_string(provider: Provider, model: ModelName) -> str:
    """ADK model string for a (provider, model). The id is owned by the
    ModelName enum in agents/models.py; Gemini and Anthropic are native to ADK,
    while OpenAI routes through LiteLLM and needs an ``openai/`` prefix
    (requires google-adk[extensions])."""
    if provider == Provider.OPENAI:
        return f"openai/{model.value}"
    return model.value


class AdkInsightsRunner:
    """ADK-powered insight pipeline (v2 engine).

    Drop-in replacement for GenerateInsightsAgent.  The route layer detects
    this class with isinstance() and calls run_pipeline() instead of the
    separate fetch_supplementary_data() / synthesize() pair.
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
        self.model_str = _resolve_adk_model_string(provider, model)
        self._api_key = api_key
        self._temperature = temperature

        self._goal_tool_names: list[str] = []
        self._fetch_fns: dict[str, Callable[..., dict[str, Any]]] = {}
        self._active_mode: str = "paid_ads"
        self._phase1_params: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Interface parity with GenerateInsightsAgent
    # ------------------------------------------------------------------

    def setup_tools_for_goal(
        self,
        goal: InsightGenerationGoal | OrganicGrowthGoal,
        fetch_fns: dict[str, Callable[..., dict[str, Any]]],
        mode: str = "paid_ads",
    ) -> list[str]:
        """Select tools for the goal and store fetch functions for run_pipeline."""
        if mode == "organic_growth":
            from agents.insights.goals.organic_growth import GOAL_TOOL_ALLOWLIST
        else:
            from agents.insights.goals.paid_ads import GOAL_TOOL_ALLOWLIST
        allowlist = GOAL_TOOL_ALLOWLIST.get(goal, [])
        self._active_mode = mode

        _register_default_tools()
        specs = _registry_get_tools(
            goal=goal.value,
            available_tool_names=list(fetch_fns.keys()),
            allowlist=allowlist,
            max_tools=8,
        )
        self._goal_tool_names = [s.name for s in specs]
        self._fetch_fns = fetch_fns

        logger.info(
            "v2: registered %d tools for goal '%s' (mode: %s): %s",
            len(self._goal_tool_names),
            goal.value,
            mode,
            self._goal_tool_names,
        )
        return self._goal_tool_names

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
        """No-op stub — v2 runs both phases together in run_pipeline()."""
        self._phase1_params = dict(
            customer_id=customer_id,
            date_from=date_from,
            date_to=date_to,
            goal=goal,
            ga4_property_id=ga4_property_id,
            gsc_site_url=gsc_site_url,
            custom_goal=custom_goal,
            context=context,
            connected_sources=connected_sources or [],
        )
        return {}

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
    ) -> SynthesisSchema | None:
        """No-op stub — v2 runs both phases together in run_pipeline()."""
        return None

    # ------------------------------------------------------------------
    # Core ADK pipeline
    # ------------------------------------------------------------------

    async def run_pipeline(
        self,
        goal: InsightGenerationGoal | OrganicGrowthGoal,
        custom_goal: str,
        context: str,
        all_briefs: dict[str, Any],
        business_context: dict[str, Any] | None = None,
        user_context: dict[str, Any] | None = None,
        mode: str = "paid_ads",
        customer_id: str = "",
        date_from: str = "",
        date_to: str = "",
        ga4_property_id: str = "",
        gsc_site_url: str = "",
        connected_sources: list[str] | None = None,
        emit_event: Callable[..., Any] | None = None,
    ) -> tuple[dict[str, Any], SynthesisSchema | None]:
        """Run the full two-phase ADK pipeline.

        Returns (supplementary, synthesis) matching the shape returned by
        the v1 fetch_supplementary_data + synthesize pair.
        """
        adk_tools = build_adk_tools_for_goal(self._goal_tool_names, self._fetch_fns)

        synthesis_system_prompt = get_system_prompt(
            goal=goal,
            mode=mode,
        )
        all_briefs_text = get_synthesis_user_prompt(
            all_briefs,
            mode=mode,
            business_context=business_context,
            user_context=user_context,
            goal=goal,
            custom_goal=custom_goal,
            context=context,
        )

        pipeline = build_pipeline_node(
            model_str=self.model_str,
            adk_tools=adk_tools,
            mode=mode,
            synthesis_system_prompt=synthesis_system_prompt,
        )

        session_service = InMemorySessionService()
        session_id = str(uuid.uuid4())
        runner = Runner(
            node=pipeline,
            app_name=_APP_NAME,
            session_service=session_service,
        )

        # Pre-populate session state — ADK injects these into {placeholder} slots
        initial_state: dict[str, Any] = {
            STATE_GOAL: goal.value,
            STATE_CUSTOM_GOAL: custom_goal or "",
            STATE_MODE: mode,
            STATE_CUSTOMER_ID: customer_id or "",
            STATE_DATE_FROM: date_from or "",
            STATE_DATE_TO: date_to or "",
            STATE_GA4_PROPERTY_ID: ga4_property_id or "",
            STATE_GSC_SITE_URL: gsc_site_url or "",
            STATE_CONTEXT: context or "",
            STATE_CONNECTED_SRCS: json.dumps(connected_sources or []),
            # Large text blobs for synthesis agent
            STATE_ALL_BRIEFS: all_briefs_text,
            # Placeholder — overwritten by DataFetchAgent's output_key
            STATE_SUPPLEMENTARY: "{}",
        }

        await session_service.create_session(
            app_name=_APP_NAME,
            user_id=_USER_ID,
            session_id=session_id,
            state=initial_state,
        )

        trigger = genai_types.Content(
            role="user",
            parts=[genai_types.Part(text="Run the insight pipeline.")],
        )

        env_var = _PROVIDER_ENV_VAR.get(self.provider, "GOOGLE_API_KEY")
        original_env_val = os.environ.get(env_var)
        if self._api_key and not os.environ.get(env_var):
            os.environ[env_var] = self._api_key

        # SSE streaming must be requested explicitly in ADK 2.x; without it no
        # partial events are emitted. We forward only the synthesis agent's
        # partials so "synthesis_chunk" carries synthesis text (not Phase 1's
        # tool-result JSON).
        run_config = RunConfig(streaming_mode=StreamingMode.SSE)

        start = perf_counter()
        try:
            async for event in runner.run_async(
                user_id=_USER_ID,
                session_id=session_id,
                new_message=trigger,
                run_config=run_config,
            ):
                if (
                    emit_event
                    and event.partial
                    and event.author == SYNTHESIS_AGENT_NAME
                    and event.content
                    and event.content.parts
                ):
                    for part in event.content.parts:
                        text = getattr(part, "text", None)
                        if text:
                            await emit_event({"event": "synthesis_chunk", "text": text})
        except Exception:
            logger.exception(
                "v2 ADK pipeline failed with %s/%s",
                self.provider.value,
                self.model_str,
            )
            return {}, None
        finally:
            # Restore original env value
            if original_env_val is None and env_var in os.environ:
                del os.environ[env_var]
            elif original_env_val is not None:
                os.environ[env_var] = original_env_val

        elapsed = perf_counter() - start
        logger.info("v2 ADK pipeline completed in %.1fs", elapsed)

        updated_session = await session_service.get_session(
            app_name=_APP_NAME,
            user_id=_USER_ID,
            session_id=session_id,
        )
        if updated_session is None:
            logger.error("v2: session not found after pipeline run")
            return {}, None

        state = updated_session.state

        # Parse supplementary data written by DataFetchAgent. The agent is asked
        # for fence-less JSON but models don't always comply, so extraction is
        # tolerant of markdown fences and surrounding prose.
        supplementary = extract_json_dict(state.get(STATE_SUPPLEMENTARY, "{}"))

        # Parse synthesis written by SynthesisAgent
        synthesis_raw = state.get(STATE_SYNTHESIS_TEXT, "")
        synthesis = None
        if synthesis_raw:
            synthesis = parse_synthesis_from_text(synthesis_raw)
            if synthesis is None:
                logger.error("v2: SynthesisSchema validation failed")

        return supplementary, synthesis

    # ------------------------------------------------------------------
    # Helper parity with GenerateInsightsAgent
    # ------------------------------------------------------------------

    def apply_classification_overrides(
        self,
        brief_dict: dict[str, Any],
        synthesis: SynthesisSchema | None,
    ) -> None:
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
        if synthesis is None:
            return None
        return synthesis.model_dump()
