"""Web search: which one a run gets, and why it is not the provider's.

The offline half pins the routing contract. The `live` half is the evidence
behind it — the reason Duct ships its own `WebSearch` on every provider but
Anthropic is a measured property of the Gemini API, not a preference, and a
claim like that rots unless something re-checks it.

Run the evidence with:

    GEMINI_API_KEY=… poetry run pytest tests/test_web_search.py -m live -s
"""

from __future__ import annotations

import asyncio
import json
import os

import pytest

from agents.core.web_tools import (
    ANTHROPIC_WEB_SEARCH_BASIC,
    ANTHROPIC_WEB_SEARCH_DYNAMIC,
    WEB_FETCH_TOOL,
    WEB_SEARCH_TOOL,
    build_web_search_tool_lc,
    build_web_tools_lc,
    provider_web_search_tool,
    web_search_available,
)
from agents.models import ModelName, Provider

GEMINI_KEY = "g-test-key"


# ---------------------------------------------------------------------------
# Routing: who gets the built-in, who gets Duct's tool, who gets nothing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "model,expected",
    [
        (ModelName.CLAUDE_OPUS, ANTHROPIC_WEB_SEARCH_DYNAMIC),
        (ModelName.CLAUDE_SONNET, ANTHROPIC_WEB_SEARCH_DYNAMIC),
        # Not on Anthropic's dynamic-filtering list, so it keeps the basic
        # variant. Naming a type a model does not serve is a 400 every turn.
        (ModelName.CLAUDE_HAIKU, ANTHROPIC_WEB_SEARCH_BASIC),
        (ModelName.CLAUDE_FABLE, ANTHROPIC_WEB_SEARCH_BASIC),
    ],
)
def test_the_anthropic_search_type_is_versioned_per_model(model, expected):
    spec = provider_web_search_tool(Provider.ANTHROPIC, model)
    assert spec["type"] == expected
    assert spec["name"] == "web_search"


@pytest.mark.parametrize(
    "provider", [Provider.GOOGLE_GENAI, Provider.OPENAI, Provider.OPENROUTER, None]
)
def test_no_other_provider_binds_a_built_in(provider):
    """Not a gap — Duct's own WebSearch covers these. See the live tests below
    for why Gemini's own tool cannot be bound alongside function calling."""
    assert provider_web_search_tool(provider, ModelName.GEMINI_3_8_FLASH) is None


def test_anthropic_can_search_without_a_gemini_key_and_others_cannot():
    assert web_search_available(Provider.ANTHROPIC, ModelName.CLAUDE_SONNET, "") is True
    assert web_search_available(Provider.GOOGLE_GENAI, ModelName.GEMINI_3_8_FLASH, "") is False
    assert web_search_available(Provider.GOOGLE_GENAI, ModelName.GEMINI_3_8_FLASH, GEMINI_KEY) is True


def _names(tools):
    return [t["type"] if isinstance(t, dict) else t.name for t in tools]


def test_anthropic_gets_fetch_plus_the_built_in():
    tools = build_web_tools_lc(Provider.ANTHROPIC, ModelName.CLAUDE_SONNET, GEMINI_KEY)
    assert _names(tools) == [WEB_FETCH_TOOL, ANTHROPIC_WEB_SEARCH_DYNAMIC]


@pytest.mark.parametrize(
    "provider,model",
    [
        (Provider.GOOGLE_GENAI, ModelName.GEMINI_3_8_FLASH),
        (Provider.GOOGLE_GENAI, ModelName.GEMINI_2_5_FLASH),
        (Provider.OPENAI, ModelName.GPT_5_6_TERRA),
        (Provider.OPENROUTER, ModelName.OR_KIMI_K3),
    ],
)
def test_every_other_provider_gets_ducts_own_search(provider, model):
    """The point of the design: one tool, same name, same behaviour, on a
    model that knows nothing about it beyond how to call a tool."""
    tools = build_web_tools_lc(provider, model, GEMINI_KEY)
    assert _names(tools) == [WEB_FETCH_TOOL, WEB_SEARCH_TOOL]


def test_without_a_gemini_key_a_non_anthropic_run_gets_fetch_only():
    """Better than a tool that can only apologise: an agent told it has search
    and handed an error every time burns turns rediscovering that."""
    tools = build_web_tools_lc(Provider.OPENAI, ModelName.GPT_5_6_TERRA, "")
    assert _names(tools) == [WEB_FETCH_TOOL]
    assert build_web_search_tool_lc("") is None


def test_the_search_tool_reports_a_provider_failure_instead_of_raising(monkeypatch):
    """A tool that raises ends the agent loop; a payload lets the model read
    what happened and carry on. Everything the provider touches — the call and
    the parse of what it returned — is inside that guarantee."""
    from google import genai

    def _boom(*_a, **_k):
        raise RuntimeError("provider exploded")

    monkeypatch.setattr(genai, "Client", _boom)
    payload = json.loads(asyncio.run(_invoke(build_web_search_tool_lc(GEMINI_KEY), "anything")))
    assert payload["status"] == "error"
    assert "provider exploded" in payload["message"]


async def _invoke(tool, query: str) -> str:
    return await tool.coroutine(query=query)


def test_an_empty_query_is_refused_before_any_call():
    from service.google.gemini.search import search_web

    payload = asyncio.run(search_web(GEMINI_KEY, "   "))
    assert payload["status"] == "error" and "required" in payload["message"]


def test_a_missing_key_is_reported_in_words_the_user_can_act_on():
    from service.google.gemini.search import search_web

    payload = asyncio.run(search_web("", "trending audio"))
    assert payload["status"] == "error" and "Gemini key" in payload["message"]


# ---------------------------------------------------------------------------
# The evidence. These cost pennies and need a real key.
# ---------------------------------------------------------------------------

_needs_key = pytest.mark.skipif(
    not os.environ.get("GEMINI_API_KEY"),
    reason="GEMINI_API_KEY not set — live web search skipped",
)


@_needs_key
@pytest.mark.live
def test_live_ducts_search_returns_a_grounded_answer_with_sources():
    from service.google.gemini.search import search_web

    payload = asyncio.run(search_web(
        os.environ["GEMINI_API_KEY"], "What is trending on TikTok this week?"
    ))
    assert payload["status"] == "ok", payload
    assert payload["answer"], "no synthesis came back"
    assert payload["sources"], "no citations — the search did not ground"
    assert all(s["url"] for s in payload["sources"])


@_needs_key
@pytest.mark.live
@pytest.mark.parametrize(
    "model", [ModelName.GEMINI_2_5_FLASH.value, ModelName.GEMINI_3_8_FLASH.value]
)
def test_live_gemini_refuses_its_own_search_beside_a_function_tool(model):
    """The measurement this whole design rests on.

    Binding ``{"google_search": {}}`` next to one ordinary function tool is a
    400 on every current Gemini generation:

      2.5   "Built-in tools ({google_search}) and Function Calling cannot be
            combined in the same request."
      3.x   "Please enable tool_config.include_server_side_tool_invocations to
            use Built-in tools with Function calling."

    3.x can be rescued with that flag — but only when nothing sets
    ``tool_choice``, because langchain-google-genai's ``_process_tool_config``
    rebuilds the config from the tool_choice branch and drops the flag, and
    ``create_agent`` always sets tool_choice under a ``ToolStrategy``. Duct's
    own WebSearch has neither constraint.

    If this test ever starts passing, Gemini has lifted the restriction and
    binding the built-in becomes worth reconsidering.
    """
    from langchain_core.tools import StructuredTool
    from langchain_google_genai import ChatGoogleGenerativeAI
    from pydantic import BaseModel, Field

    class Args(BaseModel):
        slug: str = Field(description="A slug.")

    async def note(slug: str) -> str:
        return slug

    tool = StructuredTool.from_function(
        coroutine=note, name="note", description="Note a slug.", args_schema=Args
    )
    llm = ChatGoogleGenerativeAI(model=model, google_api_key=os.environ["GEMINI_API_KEY"])
    bound = llm.bind_tools([{"google_search": {}}, tool])

    with pytest.raises(Exception) as caught:
        asyncio.run(bound.ainvoke("Search for one trending video format."))
    assert "INVALID_ARGUMENT" in str(caught.value)


@_needs_key
@pytest.mark.live
def test_live_gemini_search_alone_is_accepted():
    """The other half of the measurement, and why Duct's tool works: search
    with *no* function declarations in the request is fine everywhere. That is
    exactly the request service/google/gemini/search.py makes."""
    from langchain_google_genai import ChatGoogleGenerativeAI

    llm = ChatGoogleGenerativeAI(
        model=ModelName.GEMINI_2_5_FLASH.value, google_api_key=os.environ["GEMINI_API_KEY"]
    )
    reply = asyncio.run(llm.bind_tools([{"google_search": {}}]).ainvoke(
        "What is one trending short-form video format this week?"
    ))
    assert (reply.text or "").strip()
