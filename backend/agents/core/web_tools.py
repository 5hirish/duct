"""Web reach for the LangChain (V1) agents: one fetch tool, one search tool.

The Claude Agent SDK shipped ``WebSearch`` and ``WebFetch`` as CLI built-ins,
so the content agent had the open web for free. V1 has no CLI, so both are
supplied here.

**Fetching** is Duct's own work on every provider: ``fetch_page_text`` over
the crawl fetcher (SSRF-guarded, size-capped, boilerplate stripped with
trafilatura), bound by ``build_web_fetch_tool_lc``.

**Searching** follows the rule image generation already set — a capability
the running model may not have is a Duct tool, not a provider feature every
model must support:

* Where the provider's *server-side* search survives a real tool-calling
  loop, mount that: it costs no extra round trip and the model searches
  inside its own turn. Anthropic is the case that qualifies, and
  ``provider_web_search_tool`` returns its spec — versioned per model,
  because the tool ``type`` is not a provider constant.
* Everywhere else, mount ``build_web_search_tool_lc`` — Duct's own
  ``WebSearch``, an ordinary function tool backed by an isolated grounded
  Gemini call (service/google/gemini/search.py). It behaves the same on
  Gemini, OpenAI and OpenRouter, and it needs nothing of the running model
  beyond the ability to call a tool.

That second bullet replaces an earlier design that tried to bind each
provider's built-in search. It does not survive contact with the providers:
Gemini rejects ``google_search`` alongside function declarations outright on
2.5, and on 3.x accepts it only with a ``tool_config`` flag that
langchain-google-genai silently drops whenever ``tool_choice`` is set — which
``create_agent`` always sets under a ``ToolStrategy``. The measured matrix is
in ``tests/test_web_search.py``.

A tool that reads the open web reads attacker-authored text by construction.
Both tools return plain strings and hold no session, key or write path, so
an injected instruction has nothing to reach — the same posture the SDK
enrichment sub-agents took with ``tools=[WebSearch, WebFetch]`` and nothing
else.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any

from agents.models import ModelName, Provider
from service.crawl.fetcher import SSRFError, fetch, make_client, validate_public_url

logger = logging.getLogger(__name__)

WEB_FETCH_TOOL = "WebFetch"
WEB_SEARCH_TOOL = "WebSearch"

# Enough of a page for research (an article, a trend digest) without letting
# one fetch fill a meaningful slice of the context window.
WEB_FETCH_MAX_CHARS = 8_000

# Anthropic's server-side search: the model searches inside its own turn and
# the results come back as content blocks, never through the tool node. The
# cap bounds spend per turn; a research pass rarely needs more.
ANTHROPIC_WEB_SEARCH_MAX_USES = 8

# The tool `type` is versioned per model, not per provider. The 2026-02-09
# variant adds dynamic filtering and is documented for Opus 5 and Sonnet 5;
# every other model — Haiku, and Fable until it is on that list — takes the
# 2025-03-05 basic variant, which is still served everywhere. Naming a
# variant a model does not accept is a 400 on every turn, so the default
# here is the one that works everywhere rather than the newest.
ANTHROPIC_WEB_SEARCH_DYNAMIC = "web_search_20260209"
ANTHROPIC_WEB_SEARCH_BASIC = "web_search_20250305"
ANTHROPIC_DYNAMIC_SEARCH_MODELS: frozenset[str] = frozenset({
    ModelName.CLAUDE_OPUS.value,
    ModelName.CLAUDE_SONNET.value,
})


def provider_web_search_tool(
    provider: Provider | None, model: ModelName | str | None = None
) -> dict[str, Any] | None:
    """The provider's built-in search spec, or None to use Duct's own tool.

    None is the answer for every provider but Anthropic, and it is not a gap:
    ``build_web_search_tool_lc`` covers those. OpenAI's ``{"type":
    "web_search"}`` is a verified spec that would also work here — binding it
    flips langchain-openai to the Responses API automatically — but it has
    never been exercised against a live loop in this codebase, and one tool
    that behaves identically everywhere is worth more than a second one that
    behaves differently. Mount it here if that trade ever changes.
    """
    if provider is not Provider.ANTHROPIC:
        return None
    model_id = str(getattr(model, "value", model) or "")
    kind = (
        ANTHROPIC_WEB_SEARCH_DYNAMIC
        if model_id in ANTHROPIC_DYNAMIC_SEARCH_MODELS
        else ANTHROPIC_WEB_SEARCH_BASIC
    )
    return {"type": kind, "name": "web_search", "max_uses": ANTHROPIC_WEB_SEARCH_MAX_USES}


def _readable_text(html: str) -> str:
    """Main-content text of an HTML page, boilerplate stripped.

    trafilatura first (the same extractor the audit crawl uses); a bare tag
    strip when it finds nothing, so a thin page still yields *something*
    rather than an empty tool result the model reads as "page is blank".
    """
    try:
        import trafilatura

        extracted = trafilatura.extract(
            html, include_comments=False, include_tables=True, favor_precision=False
        )
        if extracted and extracted.strip():
            return extracted.strip()
    except Exception as exc:  # noqa: BLE001 - extraction is best-effort
        logger.debug("web_fetch: trafilatura failed: %s", exc)
    stripped = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    stripped = re.sub(r"<[^>]+>", " ", stripped)
    return re.sub(r"\s+", " ", stripped).strip()


async def fetch_page_text(url: str, *, max_chars: int = WEB_FETCH_MAX_CHARS) -> dict[str, Any]:
    """Fetch one public URL and return its readable text, as a result payload.

    Errors are returned, not raised: a tool that raises ends the agent loop,
    while a payload lets the model read why and move on. Private and reserved
    addresses are refused before any request is made.
    """
    url = (url or "").strip()
    if not url:
        return {"status": "error", "message": "url is required."}
    try:
        validate_public_url(url)
    except SSRFError as exc:
        return {"status": "error", "message": f"{url}: {exc}"}

    async with make_client() as client:
        result = await fetch(client, url)
    if result.status == 0 or not result.text:
        return {"status": "error", "message": f"{url}: could not be fetched."}
    if result.status >= 400:
        return {"status": "error", "message": f"{url}: HTTP {result.status}."}

    text = _readable_text(result.text)
    truncated = len(text) > max_chars
    return {
        "status": "ok",
        "url": url,
        "http_status": result.status,
        "text": text[:max_chars],
        "truncated": truncated,
    }


def build_web_fetch_tool_lc(
    *,
    on_fetch_start: Callable[[str], Awaitable[None]] | None = None,
    on_fetch: Callable[[str, bool], Awaitable[None]] | None = None,
) -> Any:
    """``WebFetch`` as a LangChain tool.

    The hooks let a runner show each fetch as a step in the UI; they default
    to nothing so a subagent can mount the same tool without a session.
    """
    from langchain_core.tools import StructuredTool
    from pydantic import BaseModel, Field

    class WebFetchArgs(BaseModel):
        url: str = Field(description="A public http(s) URL to read.")

    async def web_fetch(url: str) -> str:
        if on_fetch_start is not None:
            await on_fetch_start(url)
        payload = await fetch_page_text(url)
        if on_fetch is not None:
            await on_fetch(url, payload.get("status") == "ok")
        return json.dumps(payload)

    return StructuredTool.from_function(
        coroutine=web_fetch,
        name=WEB_FETCH_TOOL,
        description=(
            "Read one public web page and return its main text (boilerplate "
            f"stripped, up to {WEB_FETCH_MAX_CHARS} characters). Use it to verify a "
            "claim, read a trend digest, or study a reference you already have the "
            "URL for. It cannot search — pass a full URL."
        ),
        args_schema=WebFetchArgs,
    )


def build_web_search_tool_lc(
    gemini_api_key: str,
    *,
    on_search_start: Callable[[str], Awaitable[None]] | None = None,
    on_search: Callable[[str, bool], Awaitable[None]] | None = None,
) -> Any:
    """``WebSearch`` as a LangChain tool, for providers with no usable built-in.

    The hooks mirror ``build_web_fetch_tool_lc``'s so a runner can render each
    search as a step. Returns ``None`` without a key rather than mounting a
    tool that can only apologise — an agent told it has search and then handed
    an error every time burns turns rediscovering that.
    """
    if not gemini_api_key:
        return None

    from langchain_core.tools import StructuredTool
    from pydantic import BaseModel, Field

    from service.google.gemini.search import search_web

    class WebSearchArgs(BaseModel):
        query: str = Field(description="What to search the web for, in plain language.")

    async def web_search(query: str) -> str:
        if on_search_start is not None:
            await on_search_start(query)
        payload = await search_web(gemini_api_key, query)
        if on_search is not None:
            await on_search(query, payload.get("status") == "ok")
        return json.dumps(payload)

    return StructuredTool.from_function(
        coroutine=web_search,
        name=WEB_SEARCH_TOOL,
        description=(
            "Search the web and get back a short grounded answer with its "
            "sources. Use it to find what is current — a trend, a launch, a "
            "competitor's move — when you do not already have a URL. Follow up "
            f"with {WEB_FETCH_TOOL} on a source to read it in full."
        ),
        args_schema=WebSearchArgs,
    )


def web_search_available(
    provider: Provider | None, model: ModelName | str | None, gemini_api_key: str
) -> bool:
    """Whether this run can search at all — either search, either way.

    A caller that has nothing useful to do without search (the enrichment
    research pass) asks this instead of building the tools and inspecting
    them.
    """
    return provider_web_search_tool(provider, model) is not None or bool(gemini_api_key)


def build_web_tools_lc(
    provider: Provider | None,
    model: ModelName | str | None,
    gemini_api_key: str,
    *,
    fetch_hooks: tuple[Any, Any] = (None, None),
    search_hooks: tuple[Any, Any] = (None, None),
) -> list[Any]:
    """Every web tool this run should carry: fetch, plus whichever search fits.

    One call so a runner and its sub-agents cannot drift into mounting
    different sets — the bug this replaces was a sub-agent binding a built-in
    the parent had already ruled out.
    """
    on_fetch_start, on_fetch = fetch_hooks
    tools: list[Any] = [
        build_web_fetch_tool_lc(on_fetch_start=on_fetch_start, on_fetch=on_fetch)
    ]
    native = provider_web_search_tool(provider, model)
    if native is not None:
        # A dict tool binds to the model, never to the tool node; create_agent
        # splits them on exactly that type check.
        tools.append(native)
        return tools
    on_search_start, on_search = search_hooks
    search = build_web_search_tool_lc(
        gemini_api_key, on_search_start=on_search_start, on_search=on_search
    )
    if search is not None:
        tools.append(search)
    return tools


__all__ = [
    "ANTHROPIC_WEB_SEARCH_BASIC",
    "ANTHROPIC_WEB_SEARCH_DYNAMIC",
    "WEB_FETCH_TOOL",
    "WEB_SEARCH_TOOL",
    "build_web_fetch_tool_lc",
    "build_web_search_tool_lc",
    "build_web_tools_lc",
    "web_search_available",
    "fetch_page_text",
    "provider_web_search_tool",
]
