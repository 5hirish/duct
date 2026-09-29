"""A bounded research loop that ends in a typed answer.

Both enrichment passes — the audit's competitor research and content's
trending research — are the same shape: a model with web tools and nothing
else, a handful of searches and fetches, then one structured answer. The loop
lives here once, because the shape of that last step now depends on the model,
and two copies of that decision are how one of them ends up forcing a tool
call on a model that refuses it.

Its own module rather than a function in ``agents/core/lc.py``: it builds a
bare ``create_agent`` graph, which ``tests/test_agent_assembly.py`` allows only
in a module named for a one-shot pass, and ``lc.py`` is not one.
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from agents.core.lc import prompt_caching_middleware, structured_output
from agents.models import accepts_forced_tool_choice


def _llm_model_id(llm: Any) -> str:
    return str(getattr(llm, "model", None) or getattr(llm, "model_name", None) or "")


async def research_answer(
    prompt: str,
    llm: Any,
    tools: list[Any],
    schema: type[BaseModel],
    *,
    recursion_limit: int,
) -> BaseModel | None:
    """One bounded tool loop that ends in a typed answer, or ``None``.

    The usual shape is ``ToolStrategy``: the answer is itself a tool, and
    ``create_agent`` forces ``tool_choice`` so the loop cannot end without
    calling it. A model that refuses a forced tool call
    (``agents/models.accepts_forced_tool_choice``) would fail that on its
    first request, so it runs the same loop free instead and one
    ``structured_output`` call reads the answer out of what it wrote last.

    Not native structured output inside the loop, though ``create_agent``
    offers it: on Anthropic that is ``output_config.format``, which the API
    refuses beside citations, and Anthropic's web search always cites.

    The extraction call carries no tools at all, so a page's injected
    instruction can at worst colour the answer — the same reach it had when
    the answer was a tool call inside the loop.
    """
    from langchain.agents import create_agent
    from langchain.agents.structured_output import ToolStrategy

    forced = accepts_forced_tool_choice(_llm_model_id(llm))
    agent = create_agent(
        model=llm,
        tools=list(tools),
        response_format=ToolStrategy(schema) if forced else None,
        # Every call re-sends the pages already fetched; cached on Anthropic.
        middleware=prompt_caching_middleware(),
    )
    result = await agent.ainvoke(
        {"messages": [{"role": "user", "content": prompt}]},
        {"recursion_limit": recursion_limit},
    )
    if not isinstance(result, dict):
        return None
    if forced:
        found = result.get("structured_response")
        return found if isinstance(found, schema) else None

    messages = result.get("messages") or []
    findings = messages[-1].text if messages else ""
    if not findings.strip():
        return None
    answer = await structured_output(llm, schema).ainvoke([
        HumanMessage(content=(
            f"{prompt}\n\n<findings>\n{findings}\n</findings>\n\n"
            "The research is done. Fill in the answer the task above asks for, "
            "from these findings only."
        )),
    ])
    return answer if isinstance(answer, schema) else None
