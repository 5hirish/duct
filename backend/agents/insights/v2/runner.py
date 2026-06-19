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

import asyncio
import contextlib
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

# Serializes the (rare) env-var fallback path so concurrent runs injecting
# *different* keys via os.environ can't read each other's key mid-call. The
# common paths — a per-model BYO key (carried on a LiteLlm model) and the shared
# server key (same value across runs) — never take this lock.
_ENV_LOCK = asyncio.Lock()

# LiteLLM provider-route prefix per provider (used to carry a per-model api_key).
_LITELLM_PREFIX: dict[Provider, str] = {
    Provider.OPENAI: "openai",
    Provider.ANTHROPIC: "anthropic",
    Provider.GOOGLE_GENAI: "gemini",
}


def _resolve_adk_model_string(provider: Provider, model: ModelName) -> str:
    """ADK model string for a (provider, model). The id is owned by the
    ModelName enum in agents/models.py; Gemini and Anthropic are native to ADK,
    while OpenAI routes through LiteLLM and needs an ``openai/`` prefix
    (requires google-adk[extensions])."""
    if provider == Provider.OPENAI:
        return f"openai/{model.value}"
    return model.value


def _build_adk_model(provider: Provider, model: ModelName, api_key: str, *, prefer_per_model: bool):
    """Return ``(adk_model, per_model_key)`` for a (provider, model).

    When ``prefer_per_model`` (a per-request bring-your-own key) and a key is
    present, wrap the model in a ``LiteLlm`` instance carrying that key so it
    travels *with the model* — no process-global ``os.environ`` mutation, so
    concurrent requests with different BYO keys can't race on a shared env var.

    Otherwise (the shared server key, or the LiteLlm extra not installed) return
    the plain model string, which ADK resolves against the provider env var —
    unchanged from the original behaviour. ``per_model_key`` is True only when the
    key is carried on the returned model object.
    """
    model_str = _resolve_adk_model_string(provider, model)
    if not (prefer_per_model and api_key):
        return model_str, False
    # The lite_llm module imports even without the extra, but constructing LiteLlm
    # raises ImportError when the `litellm` package (google-adk[extensions]) is
    # absent — so guard the construction, not just the import, and fall back to
    # serialized env-var injection (still race-safe) when it's unavailable.
    try:
        from google.adk.models.lite_llm import LiteLlm

        litellm_id = f"{_LITELLM_PREFIX.get(provider, 'gemini')}/{model.value}"
        return LiteLlm(model=litellm_id, api_key=api_key), True
    except Exception:
        logger.warning(
            "v2: LiteLlm (google-adk[extensions]) unavailable; falling back to "
            "serialized env-var key injection for provider=%s", provider.value,
        )
        return model_str, False


@contextlib.asynccontextmanager
async def _maybe_env(env_var: str, value: str | None, *, serialize: bool):
    """Temporarily set ``os.environ[env_var]=value``, restoring it after.

    No-op when ``value`` is None (per-model key carried on the model, or no key).
    When ``serialize`` is True, hold ``_ENV_LOCK`` for the duration so a
    concurrent run injecting a *different* value can't observe this one mid-call
    — used only on the BYO env-var fallback path.
    """
    if value is None:
        yield
        return
    async with contextlib.AsyncExitStack() as stack:
        if serialize:
            await stack.enter_async_context(_ENV_LOCK)
        original = os.environ.get(env_var)
        os.environ[env_var] = value
        try:
            yield
        finally:
            if original is None:
                os.environ.pop(env_var, None)
            else:
                os.environ[env_var] = original


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
        byo_key: bool = False,
    ) -> None:
        self.provider = provider
        self.model = model
        self.model_str = _resolve_adk_model_string(provider, model)
        self._api_key = api_key
        # A per-request bring-your-own key is carried per-model (LiteLlm) so it
        # never touches the process-global env; the shared server key keeps the
        # original env-var path (same value across runs → no race).
        self._byo_key = byo_key
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

        # A BYO key is carried per-model (LiteLlm api_key); the server key keeps
        # the env-var path. per_model_key=True means nothing is injected globally.
        adk_model, per_model_key = _build_adk_model(
            self.provider, self.model, self._api_key, prefer_per_model=self._byo_key
        )

        pipeline = build_pipeline_node(
            model_str=adk_model,
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

        # Inject the key via the provider env var ONLY when it isn't already
        # carried on the model (i.e. the server-key path, or a LiteLlm fallback).
        # A BYO env injection is serialized so concurrent different-key runs can't
        # race; the server key is the same value across runs, so it isn't locked.
        env_var = _PROVIDER_ENV_VAR.get(self.provider, "GOOGLE_API_KEY")
        inject_value = self._api_key if (self._api_key and not per_model_key) else None

        # SSE streaming must be requested explicitly in ADK 2.x; without it no
        # partial events are emitted. We forward only the synthesis agent's
        # partials so "synthesis_chunk" carries synthesis text (not Phase 1's
        # tool-result JSON).
        run_config = RunConfig(streaming_mode=StreamingMode.SSE)

        start = perf_counter()
        try:
            async with _maybe_env(env_var, inject_value, serialize=self._byo_key):
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
