"""ClaudeAgentSdkRunner — Claude Agent SDK-based insight pipeline (v3 engine).

Public interface mirrors GenerateInsightsAgent (v1)
so routes/generate.py can select any engine via a single config flag.

Architecture — two-phase pipeline:

  Phase 1 (data fetch): The v1 fetch functions are pre-credentialed Python
    callables. Rather than spawning a subprocess MCP server just to call them,
    we run them in-process via asyncio.gather(), exactly as the v1 agent does
    when it calls all goal-relevant tools. This gives us the same tool-call
    results without IPC overhead.

  Phase 2 (synthesis): We use claude_agent_sdk.query() with a dedicated
    "synthesizer" AgentDefinition. The synthesizer subagent has no tools —
    its only job is to read briefs + supplementary data from its prompt and
    output valid SynthesisSchema JSON. We parse ResultMessage.result with
    SynthesisSchema.model_validate_json().

Claude Agent SDK features demonstrated vs v1:
  - AgentDefinition (subagent with custom system prompt + restricted tools)
  - permission_mode="dontAsk"  (no interactive prompts in backend context)
  - Disk-backed session (automatically persisted as JSONL; no manual state svc)
  - Model override per subagent
  - Structured output via ResultMessage.result → Pydantic validation

API key:
  claude_agent_sdk reads ANTHROPIC_API_KEY from the environment. If the
  caller provides an api_key and the env var is unset we temporarily set it
  during the run.

Provider support:
  The Claude Agent SDK only supports Anthropic models natively. If a non-
  Anthropic provider is configured we log a warning and fall back to
  claude-sonnet-5.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from time import perf_counter
from typing import Any

from agents.insights.goals import InsightGenerationGoal
from agents.insights.goals.organic_growth import OrganicGrowthGoal
from agents.insights.prompts import get_synthesis_user_prompt, get_system_prompt
from agents.insights.registry import get_tools_for_request as _registry_get_tools
from agents.insights.schema import SynthesisSchema
from agents.engines import Engine, get_env_var_for_engine_provider
from agents.insights.tools import CONNECTOR_BY_TOOL, _register_default_tools
from agents.insights.schema_compat import parse_synthesis_from_text
from agents.models import AgentPermissionMode, AgentTool, ModelName, Provider

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model mapping
# ---------------------------------------------------------------------------

# Claude Agent SDK runs Anthropic models only; anything else falls back to Sonnet.
# Model strings come from the ModelName enum in agents/models.py — never hardcoded here.
_ANTHROPIC_MODELS = (
    ModelName.CLAUDE_OPUS,
    ModelName.CLAUDE_OPUS_1M,   # [1m] is a CLI model string — v3 only, never v1
    ModelName.CLAUDE_SONNET,
    ModelName.CLAUDE_HAIKU,
)


def _resolve_model_string(provider: Provider, model: ModelName) -> str:
    if provider != Provider.ANTHROPIC or model not in _ANTHROPIC_MODELS:
        logger.warning(
            "v3: Claude Agent SDK only supports Anthropic models natively; "
            "ignoring provider=%s, model=%s and falling back to %s",
            provider.value,
            model.value,
            ModelName.CLAUDE_SONNET.value,
        )
        return ModelName.CLAUDE_SONNET.value
    return model.value


# ---------------------------------------------------------------------------
# Data fetch helpers (Phase 1 — in-process)
# ---------------------------------------------------------------------------

def _build_fetch_call(
    name: str,
    fn: Callable[..., Any],
    connector: str,
    customer_id: str,
    date_from: str,
    date_to: str,
    ga4_property_id: str,
    gsc_site_url: str,
) -> dict[str, Any]:
    """Call one fetch function synchronously and return {name: result}."""
    try:
        if connector == "ga4":
            result = fn(property_id=ga4_property_id, date_from=date_from, date_to=date_to)
        elif connector == "gsc":
            result = fn(site_url=gsc_site_url, date_from=date_from, date_to=date_to)
        else:
            result = fn(customer_id=customer_id, date_from=date_from, date_to=date_to)
        return {name: result}
    except Exception:
        logger.exception("v3: tool %s failed", name)
        return {name: {}}


async def _fetch_all(
    tool_names: list[str],
    fetch_fns: dict[str, Callable[..., Any]],
    customer_id: str,
    date_from: str,
    date_to: str,
    ga4_property_id: str,
    gsc_site_url: str,
) -> dict[str, Any]:
    """Run all goal-relevant fetch functions concurrently in a thread pool."""
    loop = asyncio.get_event_loop()
    tasks = []
    for name in tool_names:
        fn = fetch_fns.get(name)
        if not fn:
            continue
        connector = CONNECTOR_BY_TOOL.get(name, "google_ads")
        tasks.append(
            loop.run_in_executor(
                None,
                lambda _name=name, _fn=fn, _conn=connector: _build_fetch_call(
                    _name, _fn, _conn,
                    customer_id, date_from, date_to,
                    ga4_property_id, gsc_site_url,
                ),
            )
        )
    results = await asyncio.gather(*tasks, return_exceptions=True)
    supplementary: dict[str, Any] = {}
    for r in results:
        if isinstance(r, Exception):
            logger.error("v3: fetch task raised %s", r)
        else:
            supplementary.update(r)
    return supplementary


# ---------------------------------------------------------------------------
# Synthesis (Phase 2 — Claude Agent SDK)
# ---------------------------------------------------------------------------

_SYNTHESIS_ORCHESTRATOR_PROMPT = """\
You are an insight orchestration agent. Your only task is to delegate synthesis
to the 'synthesizer' subagent and return its result verbatim.

Steps:
1. Invoke the 'synthesizer' subagent with the full connector data and
   supplementary data provided below as the prompt.
2. Return the synthesizer's raw JSON output — do NOT add any wrapper or
   commentary around it.

The synthesizer will produce a JSON object conforming to SynthesisSchema.
Your final output must be that exact JSON string, nothing else.
"""

_SYNTHESIZER_SYSTEM_PROMPT_SUFFIX = """

<output_format>
Output ONLY a valid JSON object matching SynthesisSchema.
No markdown fences, no preamble, no trailing text.
</output_format>
"""


async def _run_synthesis(
    *,
    model_str: str,
    synthesis_system_prompt: str,
    synthesis_user_prompt: str,
    api_key: str,
    provider: Provider,
    emit_event: Callable | None = None,
) -> SynthesisSchema | None:
    """Run synthesis phase via Claude Agent SDK with a synthesizer subagent."""
    from claude_agent_sdk import AgentDefinition, ClaudeAgentOptions, query
    from claude_agent_sdk import ResultMessage, StreamEvent

    env_var = get_env_var_for_engine_provider(Engine.V3, provider) or "ANTHROPIC_API_KEY"
    # Inject the resolved provider key into the per-call SDK env (merged over
    # os.environ for the subprocess only) instead of mutating the process-global
    # os.environ. This makes a per-request bring-your-own key always win and keeps
    # concurrent requests from racing on a shared var. When api_key is empty (e.g.
    # local subscription-OAuth) we leave it unset so the SDK can fall back to
    # CLAUDE_CODE_OAUTH_TOKEN / ~/.claude.
    sdk_env = {
        "ENABLE_PROMPT_CACHING_1H": "1",
        # Clear inherited Claude Code IDE session vars that confuse child instances
        "CLAUDE_CODE_SESSION_ID": "",
        "CLAUDE_EFFORT": "",
        "CLAUDE_CODE_ENABLE_SDK_FILE_CHECKPOINTING": "false",
    }
    if api_key:
        sdk_env[env_var] = api_key

    try:
        options = ClaudeAgentOptions(
            model=model_str,
            permission_mode=AgentPermissionMode.DONT_ASK,
            allowed_tools=[AgentTool.AGENT],
            max_turns=5,
            system_prompt=_SYNTHESIS_ORCHESTRATOR_PROMPT,
            include_partial_messages=True,
            env=sdk_env,
            agents={
                "synthesizer": AgentDefinition(
                    description=(
                        "Expert marketing analyst. Produces structured SynthesisSchema JSON "
                        "from connector briefs and supplementary data. Use for the synthesis phase."
                    ),
                    prompt=synthesis_system_prompt + _SYNTHESIZER_SYSTEM_PROMPT_SUFFIX,
                    tools=[],
                    model=model_str,
                ),
            },
        )

        full_prompt = (
            "Use the 'synthesizer' subagent to synthesize insights from the "
            "following data and return the JSON output:\n\n"
            + synthesis_user_prompt
        )

        synthesis_text: str | None = None
        _tok_cache_read = 0
        _tok_cache_write = 0
        async for message in query(prompt=full_prompt, options=options):
            if isinstance(message, StreamEvent):
                ev = message.event
                ev_type = ev.get("type")
                if ev_type == "message_start":
                    usage = ev.get("message", {}).get("usage", {})
                    _tok_cache_read += usage.get("cache_read_input_tokens", 0)
                    _tok_cache_write += usage.get("cache_creation_input_tokens", 0)
                if emit_event and ev_type == "content_block_delta":
                    delta = ev.get("delta", {})
                    if delta.get("type") == "text_delta":
                        chunk = delta.get("text", "")
                        if chunk:
                            await emit_event({"event": "synthesis_chunk", "text": chunk})
            elif isinstance(message, ResultMessage) and message.result:
                synthesis_text = message.result
                break

        logger.info("v3: synthesis cache_read=%d cache_write=%d", _tok_cache_read, _tok_cache_write)

        if not synthesis_text:
            logger.error("v3: synthesis produced no result")
            return None

        return parse_synthesis_from_text(synthesis_text)

    except Exception:
        logger.exception("v3: synthesis phase failed")
        return None


# ---------------------------------------------------------------------------
# Runner class
# ---------------------------------------------------------------------------

class ClaudeAgentSdkRunner:
    """Claude Agent SDK-powered insight pipeline (v3 engine).

    Drop-in replacement for GenerateInsightsAgent (v1).
    The route layer detects this class with isinstance() and calls run_pipeline()
    instead of the separate fetch_supplementary_data() / synthesize() pair.
    """

    def __init__(
        self,
        api_key: str,
        provider: Provider = Provider.ANTHROPIC,
        model: ModelName = ModelName.CLAUDE_SONNET,
        temperature: float = 1.0,
    ) -> None:
        self.provider = provider
        self.model = model
        self.model_str = _resolve_model_string(provider, model)
        self._api_key = api_key
        self._temperature = temperature

        self._goal_tool_names: list[str] = []
        self._fetch_fns: dict[str, Callable[..., Any]] = {}
        self._active_mode: str = "paid_ads"

    # ------------------------------------------------------------------
    # Interface parity with GenerateInsightsAgent
    # ------------------------------------------------------------------

    def setup_tools_for_goal(
        self,
        goal: InsightGenerationGoal | OrganicGrowthGoal,
        fetch_fns: dict[str, Callable[..., Any]],
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
            "v3: registered %d tools for goal '%s' (mode: %s): %s",
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
        """No-op stub — v3 runs both phases together in run_pipeline()."""
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
        """No-op stub — v3 runs both phases together in run_pipeline()."""
        return None

    # ------------------------------------------------------------------
    # Core pipeline
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
        emit_event: Callable | None = None,
        memory: str = "",
    ) -> tuple[dict[str, Any], SynthesisSchema | None]:
        """Run the full two-phase pipeline.

        Phase 1: fetch supplementary data in-process (concurrent, thread pool)
        Phase 2: synthesize via Claude Agent SDK with a synthesizer subagent

        Returns (supplementary, synthesis) matching the shape returned by
        the v1 fetch_supplementary_data + synthesize pair.
        """
        start = perf_counter()

        # Phase 1 — in-process data fetch
        logger.info("v3: starting Phase 1 — data fetch (%d tools)", len(self._goal_tool_names))
        supplementary = await _fetch_all(
            tool_names=self._goal_tool_names,
            fetch_fns=self._fetch_fns,
            customer_id=customer_id,
            date_from=date_from,
            date_to=date_to,
            ga4_property_id=ga4_property_id,
            gsc_site_url=gsc_site_url,
        )
        logger.info("v3: Phase 1 done — %d datasets fetched", len(supplementary))

        # Build synthesis prompts
        synthesis_system_prompt = get_system_prompt(
            goal=goal,
            mode=mode,
        )
        synthesis_user_prompt = get_synthesis_user_prompt(
            all_briefs,
            supplementary=supplementary,
            mode=mode,
            business_context=business_context,
            user_context=user_context,
            goal=goal,
            custom_goal=custom_goal,
            context=context,
            memory=memory,
        )

        # Phase 2 — Claude Agent SDK synthesis
        logger.info("v3: starting Phase 2 — synthesis via Claude Agent SDK")
        synthesis = await _run_synthesis(
            model_str=self.model_str,
            synthesis_system_prompt=synthesis_system_prompt,
            synthesis_user_prompt=synthesis_user_prompt,
            api_key=self._api_key,
            provider=self.provider,
            emit_event=emit_event,
        )

        elapsed = perf_counter() - start
        logger.info(
            "v3: pipeline completed in %.1fs (synthesis %s)",
            elapsed,
            "ok" if synthesis else "failed",
        )
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
