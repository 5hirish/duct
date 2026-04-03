"""GenerateAgent — LangChain-based report generation agent.

Two-phase architecture (following nomadtools barrio pattern):
  Phase 1: Data fetch via tool use (optional — data can be pre-fetched)
  Phase 2: Synthesis via structured output

Provider-agnostic via init_chat_model(). Swap models by changing
GENERATE_PROVIDER / GENERATE_MODEL env vars.
"""

from __future__ import annotations

import logging
from time import perf_counter
from typing import Any, Callable, Dict, Optional

from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, SystemMessage

from agents.reporter.models import ModelName, Provider, get_api_key_kwargs
from agents.reporter.prompts import get_synthesis_user_prompt, get_system_prompt
from agents.reporter.schema import SynthesisSchema
from agents.reporter.tools import create_google_ads_tool

logger = logging.getLogger(__name__)


class GenerateAgent:
    """Report generation agent with tool use + structured output.

    Usage::

        agent = GenerateAgent(api_key="...", provider=Provider.OPENAI, model=ModelName.GPT_5_MINI)
        agent.setup_google_ads_tool(fetch_fn)
        result = await agent.synthesize(goal, context, brief_dict, raw_payload)
    """

    def __init__(
        self,
        api_key: str,
        provider: Provider = Provider.GOOGLE_GENAI,
        model: ModelName = ModelName.GEMINI_2_5_FLASH,
        temperature: float = 0.3,
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
        self.llm_with_tools = None
        self.llm_structured = self._setup_structured_output()

    def _setup_structured_output(self):
        """Configure structured output for the synthesis phase."""
        return self.llm.with_structured_output(
            SynthesisSchema,
            method="json_schema",
            strict=True,
        )

    def setup_google_ads_tool(
        self,
        fetch_fn: Callable[..., Dict[str, Any]],
    ) -> None:
        """Register the Google Ads fetch tool with pre-resolved credentials.

        ``fetch_fn`` is a closure that already has auth credentials baked in.
        Only customer_id, date_from, date_to are exposed to the LLM.
        """
        tool = create_google_ads_tool(fetch_fn)
        self.tools = [tool]
        self.llm_with_tools = self.llm.bind_tools(self.tools)

    async def synthesize(
        self,
        goal: str,
        context: str,
        brief_dict: Dict[str, Any],
        raw_payload: Dict[str, Any],
    ) -> SynthesisSchema:
        """Run the synthesis phase: structured output from brief + raw data.

        Returns a validated SynthesisSchema instance.
        """
        system_prompt = get_system_prompt(goal=goal, context=context)
        user_prompt = get_synthesis_user_prompt(brief_dict, raw_payload)

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
            "Synthesis completed in %.1fs with %s/%s",
            elapsed,
            self.provider.value,
            self.model.value,
        )
        return result

    def merge_synthesis(
        self,
        brief_dict: Dict[str, Any],
        synthesis: Optional[SynthesisSchema],
    ) -> Dict[str, Any]:
        """Merge synthesis results into the brief dict.

        If synthesis is None (LLM failed), returns the original brief unchanged.
        """
        if synthesis is None:
            return brief_dict

        out = synthesis.model_dump()
        brief_dict["narrative"] = out["narrative"]
        brief_dict["highlights"] = out["highlights"]
        brief_dict["risks"] = out["risks"]
        brief_dict["recommended_actions"] = out["recommended_actions"]
        return brief_dict
