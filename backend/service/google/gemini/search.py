"""Grounded web search over google-genai — Duct's own search capability.

The same shape as image generation next door, and for the same reason: a
capability the running model may not have, supplied as a Duct tool backed by
a Gemini call, rather than as a provider built-in the model must support.

That distinction is what makes this file exist. Gemini *does* ship a
server-side ``google_search`` tool, but it cannot be bound alongside function
declarations, which every Duct agent has:

  gemini-2.5-flash   400 — "Built-in tools ({google_search}) and Function
                     Calling cannot be combined in the same request."
  gemini-3.x         400 — unless tool_config.include_server_side_tool_
                     invocations is set, which langchain-google-genai drops
                     whenever tool_choice is also set (chat_models.py,
                     _process_tool_config), so the structured-output paths
                     cannot use it at all.

Searching *alone* — no function declarations in the request — is accepted on
every Gemini generation. So that is what this does: one isolated grounded
call per search, returning the synthesis and its citations. The agent calling
it keeps all its own tools, on any provider.

Returns the answer rather than a list of blue links because the caller is a
model with a context window to protect: a synthesis with sources costs a
fraction of the pages it read, and ``WebFetch`` is right there when the agent
wants the full text of one of them.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from agents.models import ModelName

logger = logging.getLogger(__name__)

# Cheap, 1M context, and grounded — search is volume work, and the synthesis
# is only as good as the pages it cites either way.
SEARCH_MODEL = ModelName.GEMINI_3_5_FLASH_LITE

# A search that has not answered in this long is worth less than the turn it
# is holding up. The caller degrades rather than waits.
SEARCH_TIMEOUT_SECONDS = 45.0

# Enough sources to judge a claim, few enough to stay a citation list rather
# than a second document.
MAX_SOURCES = 8


def _sources(grounding: Any) -> list[dict[str, str]]:
    """Citation chunks → ``{title, url}``, deduped, best-effort.

    The uris are ``vertexaisearch.cloud.google.com`` redirects rather than the
    publisher's own URL, and the title is usually the bare domain. Both are
    still enough for the model to attribute a claim and to hand the link to
    ``WebFetch``, which follows the redirect.
    """
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for chunk in (getattr(grounding, "grounding_chunks", None) or []):
        web = getattr(chunk, "web", None)
        url = (getattr(web, "uri", "") or "").strip() if web else ""
        if not url or url in seen:
            continue
        seen.add(url)
        out.append({"title": (getattr(web, "title", "") or "").strip(), "url": url})
        if len(out) >= MAX_SOURCES:
            break
    return out


async def search_web(
    api_key: str,
    query: str,
    *,
    model: ModelName | str = SEARCH_MODEL,
    timeout: float = SEARCH_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Search the web for ``query`` and return a grounded answer with sources.

    Errors are returned, not raised: this is called from a tool, and a tool
    that raises ends the agent loop while a payload lets the model read what
    went wrong and carry on.
    """
    query = (query or "").strip()
    if not query:
        return {"status": "error", "message": "query is required."}
    if not api_key:
        return {
            "status": "error",
            "message": "Web search is unavailable: no Gemini key is connected.",
        }

    try:
        from google import genai  # late import — heavy module
        from google.genai import types

        client = genai.Client(api_key=api_key)
        response = await asyncio.wait_for(
            client.aio.models.generate_content(
                model=str(getattr(model, "value", model)),
                contents=query,
                # The only tool in the request. Adding any function declaration
                # here is what the module docstring is about.
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())],
                ),
            ),
            timeout=timeout,
        )
        answer = (response.text or "").strip()
        candidates = response.candidates or []
        grounding = getattr(candidates[0], "grounding_metadata", None) if candidates else None
        sources = _sources(grounding)
        queries_run = list(getattr(grounding, "web_search_queries", None) or [])
    except asyncio.TimeoutError:
        logger.warning("web_search: timed out after %.0fs", timeout)
        return {"status": "error", "message": f"Search timed out after {timeout:.0f}s."}
    except Exception as exc:  # noqa: BLE001 - a failed search must not end the run
        logger.warning("web_search failed: %s", exc)
        return {"status": "error", "message": f"Search failed: {exc}"}

    if not answer and not sources:
        return {"status": "error", "message": f"No results for {query!r}."}
    return {
        "status": "ok",
        "query": query,
        "answer": answer,
        "queries_run": queries_run,
        "sources": sources,
        # False when the model answered from its own weights instead of the
        # index — worth knowing before quoting it as "current".
        "grounded": bool(sources),
    }


__all__ = ["MAX_SOURCES", "SEARCH_MODEL", "search_web"]
