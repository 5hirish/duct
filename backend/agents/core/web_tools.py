"""Web reach for the LangChain (V1) agents: one fetch tool, one search spec.

The Claude Agent SDK shipped ``WebSearch`` and ``WebFetch`` as CLI built-ins,
so the content agent had the open web for free. V1 has no CLI, so the two
capabilities are supplied here — differently, because they *are* different:

* **Fetching a page** is Duct's own work. ``fetch_page_text`` is a plain domain
  function over the crawl fetcher (SSRF-guarded, size-capped, boilerplate
  stripped with trafilatura), and ``build_web_fetch_tool_lc`` is its binder.
  It works on every provider.
* **Searching the web** is a provider capability, not something to rebuild
  from a scraped results page. ``provider_web_search_tool`` returns the
  provider's *server-side* search tool spec — the dict shape LangChain passes
  straight through ``bind_tools`` — or ``None`` where Duct has not verified
  one. Anthropic's ``web_search_20250305`` is the one mounted today; Gemini's
  ``google_search`` grounding and OpenAI's ``web_search`` exist but neither
  has been exercised against a live tool-calling loop here, and a wrong spec
  is a 400 on every turn, so they stay off until they have been.

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

from agents.models import Provider
from service.crawl.fetcher import SSRFError, fetch, make_client, validate_public_url

logger = logging.getLogger(__name__)

WEB_FETCH_TOOL = "WebFetch"

# Enough of a page for research (an article, a trend digest) without letting
# one fetch fill a meaningful slice of the context window.
WEB_FETCH_MAX_CHARS = 8_000

# Anthropic's server-side search: the model searches inside its own turn and
# the results come back as content blocks, never through the tool node. The
# cap bounds spend per turn; a research pass rarely needs more.
ANTHROPIC_WEB_SEARCH_MAX_USES = 8

PROVIDER_WEB_SEARCH_TOOL: dict[Provider, dict[str, Any]] = {
    Provider.ANTHROPIC: {
        "type": "web_search_20250305",
        "name": "web_search",
        "max_uses": ANTHROPIC_WEB_SEARCH_MAX_USES,
    },
}


def provider_web_search_tool(provider: Provider | None) -> dict[str, Any] | None:
    """The provider's built-in web search tool spec, or None when unverified."""
    if provider is None:
        return None
    spec = PROVIDER_WEB_SEARCH_TOOL.get(provider)
    return dict(spec) if spec else None


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


__all__ = [
    "PROVIDER_WEB_SEARCH_TOOL",
    "WEB_FETCH_TOOL",
    "build_web_fetch_tool_lc",
    "fetch_page_text",
    "provider_web_search_tool",
]
