"""What the person watching a run gets to see the agent doing.

A run is mostly tool calls, and until now the app saw almost none of them.
Two families had bespoke plumbing — a data pull emitted a STEP event from the
insights runner, a sub-agent dispatch emitted one from ``deep_session`` — and
everything else (a web search, a page read, an image the content agent drew)
happened in silence. The transcript said "Working…" for ninety seconds and
then produced a brief citing a source nobody saw it open.

This is the one place that decides what surfaces. Every tool call already
passes through ``recorder_tool_hooks``; ``activity_hooks`` wraps that pair and
emits a TOOL_ACTIVITY event for the tools on the allowlist below, twice per
call — ``running`` when it starts, ``success``/``error`` when it returns.

Two rules hold the design together:

* **Allowlist, never denylist.** A tool is invisible until someone decides
  what its card says. A new internal tool (a memory read, a catalogue
  listing, a todo write) then costs nothing and leaks nothing; the failure
  mode of a denylist is the opposite one, and it is a privacy failure, not a
  cosmetic one.
* **Structured fields, never prose.** The event carries ``title``,
  ``subtitle``, ``source`` and a small ``meta`` dict. The app writes the
  sentence, in the reader's language — the old step labels were English
  built in Python (``f"{entity_id} · {date_from} → {date_to}"``) and could
  never be anything else.

The payload is deliberately small. It is the *notice* that a tool ran, not
its output: the full input and result are already recorded for the transcript
(``persistence.record_tool_use``), and a card that carried a page of fetched
JSON would put attacker-authored text in the UI and in every client's memory.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from agents.core.events import AgentEvent, StepStatus

logger = logging.getLogger(__name__)


class ActivityKind(StrEnum):
    """Which card the app draws. Contract with app/src/lib/agentEvents.js."""

    DATA = "data"              # a connector pull — logo, entity, window, rows
    WEB_SEARCH = "web_search"  # a query and the sources it came back with
    WEB_FETCH = "web_fetch"    # one page read, by host
    IMAGE = "image"            # an image the agent drew, shown inline
    SLIDE = "slide"            # a rendered slide
    SUBAGENT = "subagent"      # a dispatched sub-agent
    MEMORY = "memory"          # a search of, or a read from, project memory
    CONTEXT = "context"        # project context read: business, brand, library, the run's own blocks
    ARTIFACT = "artifact"      # an existing document opened or listed
    ACTION = "action"          # something saved, published or logged on the person's behalf


# Tool names. The core ones are PascalCase (the model reads them in its
# prompt); the content agent's are snake_case, which is its own convention.
FETCH_DATA_TOOL = "FetchData"
GENERATE_IMAGE_TOOL = "generate_image"
EDIT_IMAGE_TOOL = "edit_image"
RENDER_SLIDE_TOOL = "render_slide"
# Not a tool the model calls: the runner's own "I read the project context"
# notice, emitted where the run's CONTEXT row is recorded, so the person sees
# the enriched turn — business, profile, memory, connectors — was in play.
PROJECT_CONTEXT_TOOL = "ProjectContext"

# A card shows at most this many source chips; the rest become "+N".
MAX_SOURCE_CHIPS = 6
# Room for a query or a sub-agent brief on one line, not a paragraph.
TITLE_CHARS = 140


def _text(value: Any) -> str:
    return str(value or "").strip()


def _envelope(result: Any) -> dict[str, Any]:
    """The tool's return as a dict, or ``{}``.

    Tools here return a JSON string; a result that is already a dict (a test,
    a future tool) is taken as-is, and anything else — content blocks, a bare
    string, an over-cap preview — yields ``{}`` and the mapper falls back to
    the call's own arguments.
    """
    if isinstance(result, dict):
        return result
    if isinstance(result, str):
        try:
            parsed = json.loads(result)
        except (ValueError, TypeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _row_count(data: Any) -> int | None:
    """How many rows a fetch came back with, best effort.

    Every connector shapes its payload differently, so this recognises the two
    shapes that cover them and gives up quietly on the rest. A card with no
    count is fine; a card with a wrong count is not.
    """
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict):
        for key in ("rows", "items", "results"):
            value = data.get(key)
            if isinstance(value, list):
                return len(value)
    return None


def _host(url: str) -> str:
    try:
        return urlparse(url if "//" in url else f"https://{url}").hostname or ""
    except ValueError:
        return ""


def _ok(env: dict[str, Any], is_error: bool) -> bool:
    """A tool's verdict. Tools that return an envelope say so in ``status``;
    the rest are judged by the harness's own error flag."""
    if env and "status" in env:
        return env.get("status") in ("ok", "received", "success")
    return not is_error


def _list_len(env: dict[str, Any]) -> int | None:
    """How many things a listing came back with: the first list at the top
    level, or the envelope's own ``count``. None when it has neither."""
    if isinstance(env.get("count"), int):
        return env["count"]
    for value in env.values():
        if isinstance(value, list):
            return len(value)
    return None


# ---------------------------------------------------------------------------
# Mappers — one per tool, each returning the card's fields
# ---------------------------------------------------------------------------


def _data_start(args: dict[str, Any]) -> dict[str, Any]:
    entity = _text(args.get("entity_id"))
    return {
        "kind": ActivityKind.DATA,
        "title": entity,
        "source": entity.split("_", 1)[0],  # best guess until the result names it
        "meta": {"date_from": _text(args.get("date_from")), "date_to": _text(args.get("date_to"))},
    }


def _data_finish(args: dict[str, Any], result: Any, is_error: bool) -> dict[str, Any]:
    env = _envelope(result)
    ok = env.get("status") == "ok" if env else not is_error
    entity = _text(env.get("entity_id")) or _text(args.get("entity_id"))
    meta: dict[str, Any] = {
        "date_from": _text(env.get("date_from")) or _text(args.get("date_from")),
        "date_to": _text(env.get("date_to")) or _text(args.get("date_to")),
    }
    rows = _row_count(env.get("data"))
    if rows is not None:
        meta["rows"] = rows
    return {
        "kind": ActivityKind.DATA,
        "status": StepStatus.SUCCESS if ok else StepStatus.ERROR,
        "title": entity,
        # The connector id is the logo and the name the Connections page uses;
        # the entity prefix only ever approximated it.
        "source": _text(env.get("connector_id")) or entity.split("_", 1)[0],
        "meta": meta,
        # The provider's own sentence. The model paraphrases a failure; the
        # person deciding whether to reconnect needs what the API said.
        "error": "" if ok else _text(env.get("message")),
        # The status is a state, not a synonym for failure: a revoked grant is
        # fixed by reconnecting, an unknown entity by nothing the user can do.
        "reason": "" if ok else _text(env.get("status")),
    }


def _search_start(args: dict[str, Any]) -> dict[str, Any]:
    return {"kind": ActivityKind.WEB_SEARCH, "title": _text(args.get("query"))[:TITLE_CHARS]}


def _search_finish(args: dict[str, Any], result: Any, is_error: bool) -> dict[str, Any]:
    env = _envelope(result)
    ok = env.get("status") == "ok" if env else not is_error
    sources = env.get("sources") if isinstance(env.get("sources"), list) else []
    chips = [
        {"title": _text(s.get("title")) or _host(_text(s.get("url"))), "url": _text(s.get("url"))}
        for s in sources[:MAX_SOURCE_CHIPS]
        if isinstance(s, dict)
    ]
    return {
        "kind": ActivityKind.WEB_SEARCH,
        "status": StepStatus.SUCCESS if ok else StepStatus.ERROR,
        "title": _text(env.get("query")) or _text(args.get("query"))[:TITLE_CHARS],
        "meta": {"sources": chips, "source_count": len(sources), "grounded": bool(env.get("grounded"))},
        "error": "" if ok else _text(env.get("message")),
    }


def _fetch_page_start(args: dict[str, Any]) -> dict[str, Any]:
    url = _text(args.get("url"))
    return {"kind": ActivityKind.WEB_FETCH, "title": _host(url) or url, "meta": {"url": url}}


def _fetch_page_finish(args: dict[str, Any], result: Any, is_error: bool) -> dict[str, Any]:
    env = _envelope(result)
    ok = env.get("status") == "ok" if env else not is_error
    url = _text(env.get("url")) or _text(args.get("url"))
    return {
        "kind": ActivityKind.WEB_FETCH,
        "status": StepStatus.SUCCESS if ok else StepStatus.ERROR,
        "title": _host(url) or url,
        "meta": {"url": url, "truncated": bool(env.get("truncated"))},
        "error": "" if ok else _text(env.get("message")),
    }


def _image_start(args: dict[str, Any]) -> dict[str, Any]:
    return {"kind": ActivityKind.IMAGE, "title": _text(args.get("prompt"))[:TITLE_CHARS]}


def _image_finish(args: dict[str, Any], result: Any, is_error: bool) -> dict[str, Any]:
    env = _envelope(result)
    urls = env.get("asset_urls") if isinstance(env.get("asset_urls"), list) else []
    ok = bool(urls) and not is_error
    return {
        "kind": ActivityKind.IMAGE,
        "status": StepStatus.SUCCESS if ok else StepStatus.ERROR,
        "title": _text(args.get("prompt"))[:TITLE_CHARS],
        # The picture is the card. Duct-hosted paths only — these come from
        # our own media routes, never from the model. `attached_to` is the
        # slide it landed on, which is the difference between "it drew
        # something" and "it drew the thing on slide three".
        "meta": {
            "images": [_text(u) for u in urls if _text(u)],
            "model": _text(env.get("model")),
            "attached_to": _text(env.get("attached_to")),
        },
        "error": "" if ok else _text(env.get("message") or env.get("error")),
    }


def _slide_start(args: dict[str, Any]) -> dict[str, Any]:
    return {"kind": ActivityKind.SLIDE, "title": _text(args.get("slide_id"))}


def _slide_finish(args: dict[str, Any], result: Any, is_error: bool) -> dict[str, Any]:
    env = _envelope(result)
    url = _text(env.get("asset_url"))
    return {
        "kind": ActivityKind.SLIDE,
        "status": StepStatus.ERROR if is_error or not url else StepStatus.SUCCESS,
        "title": _text(env.get("slide_id")) or _text(args.get("slide_id")),
        "meta": {"images": [url] if url else [], "note": _text(env.get("note"))},
    }


def _subagent_start(args: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": ActivityKind.SUBAGENT,
        "title": _text(args.get("subagent_type")) or "agent",
        "meta": {"brief": _text(args.get("description"))[:TITLE_CHARS]},
    }


def _subagent_finish(args: dict[str, Any], result: Any, is_error: bool) -> dict[str, Any]:
    text = result if isinstance(result, str) else str(result)
    return {
        "kind": ActivityKind.SUBAGENT,
        "status": StepStatus.ERROR if is_error else StepStatus.SUCCESS,
        "title": _text(args.get("subagent_type")) or "agent",
        "meta": {"summary": text.strip()[:TITLE_CHARS]},
    }


def _pages_start(args: dict[str, Any]) -> dict[str, Any]:
    """The audit's FetchPages: several pages of the audited site in one call."""
    urls = [_text(u) for u in (args.get("urls") or []) if _text(u)]
    return {
        "kind": ActivityKind.WEB_FETCH,
        "title": _host(urls[0]) if urls else "",
        "meta": {"urls": urls, "count": len(urls)},
    }


def _pages_finish(args: dict[str, Any], result: Any, is_error: bool) -> dict[str, Any]:
    env = _envelope(result)
    urls = [_text(u) for u in (args.get("urls") or []) if _text(u)]
    pages = env.get("pages") if isinstance(env.get("pages"), list) else []
    errors = env.get("errors") if isinstance(env.get("errors"), list) else []
    ok = not is_error and (bool(pages) or not errors)
    return {
        "kind": ActivityKind.WEB_FETCH,
        "status": StepStatus.SUCCESS if ok else StepStatus.ERROR,
        "title": _host(urls[0]) if urls else "",
        "meta": {"urls": urls, "count": len(pages) if env else len(urls), "failed": len(errors)},
        "error": "" if ok else "; ".join(_text(e) for e in errors[:3]),
    }


def _memory_search_start(args: dict[str, Any]) -> dict[str, Any]:
    return {"kind": ActivityKind.MEMORY, "title": _text(args.get("query"))[:TITLE_CHARS]}


def _memory_search_finish(args: dict[str, Any], result: Any, is_error: bool) -> dict[str, Any]:
    env = _envelope(result)
    count = env.get("count") if isinstance(env.get("count"), int) else None
    return {
        "kind": ActivityKind.MEMORY,
        "status": StepStatus.SUCCESS if _ok(env, is_error) else StepStatus.ERROR,
        "title": _text(args.get("query"))[:TITLE_CHARS],
        "meta": {"count": count} if count is not None else {},
        "error": "" if _ok(env, is_error) else _text(env.get("message")),
    }


def _memory_get_start(args: dict[str, Any]) -> dict[str, Any]:
    return {"kind": ActivityKind.MEMORY, "title": _text(args.get("memory_id")), "meta": {"read": True}}


def _memory_get_finish(args: dict[str, Any], result: Any, is_error: bool) -> dict[str, Any]:
    env = _envelope(result)
    memory = env.get("memory") if isinstance(env.get("memory"), dict) else {}
    ok = bool(memory) and _ok(env, is_error)
    return {
        "kind": ActivityKind.MEMORY,
        "status": StepStatus.SUCCESS if ok else StepStatus.ERROR,
        "title": _text(memory.get("title")) or _text(args.get("memory_id")),
        "meta": {"read": True, "memory_id": _text(memory.get("memory_id") or memory.get("id"))},
        "error": "" if ok else _text(env.get("message")),
    }


def _read_start(args: dict[str, Any]) -> dict[str, Any]:
    """A read of something the project already holds — brand context, the
    topic bank, connected sources. The tool name says which; the app words it."""
    return {"kind": ActivityKind.CONTEXT, "title": _text(args.get("post_id") or args.get("slide_id") or args.get("query"))}


def _read_finish(args: dict[str, Any], result: Any, is_error: bool) -> dict[str, Any]:
    env = _envelope(result)
    ok = _ok(env, is_error)
    count = _list_len(env) if ok else None
    return {
        "kind": ActivityKind.CONTEXT,
        "status": StepStatus.SUCCESS if ok else StepStatus.ERROR,
        "title": _text(args.get("post_id") or args.get("slide_id") or args.get("query")),
        "meta": {"count": count} if count is not None else {},
        "error": "" if ok else _text(env.get("message")),
    }


def _artifact_get_start(args: dict[str, Any]) -> dict[str, Any]:
    return {"kind": ActivityKind.ARTIFACT, "title": _text(args.get("artifact_id"))}


def _artifact_get_finish(args: dict[str, Any], result: Any, is_error: bool) -> dict[str, Any]:
    env = _envelope(result)
    ok = bool(env.get("artifact_id")) and not is_error
    return {
        "kind": ActivityKind.ARTIFACT,
        "status": StepStatus.SUCCESS if ok else StepStatus.ERROR,
        "title": _text(env.get("title")) or _text(args.get("artifact_id")),
        "meta": {
            "artifact_id": _text(env.get("artifact_id") or args.get("artifact_id")),
            "kind": _text(env.get("kind")),
            "version": env.get("version") if isinstance(env.get("version"), int) else None,
        },
        # A miss comes back as a sentence, not an envelope; the row keeps it.
        "error": "" if ok else (_text(result) if isinstance(result, str) and not env else _text(env.get("message"))),
    }


def _artifact_list_start(args: dict[str, Any]) -> dict[str, Any]:
    return {"kind": ActivityKind.ARTIFACT, "title": "", "meta": {"listing": True}}


def _artifact_list_finish(args: dict[str, Any], result: Any, is_error: bool) -> dict[str, Any]:
    env = _envelope(result)
    rows = env.get("artifacts") if isinstance(env.get("artifacts"), list) else []
    return {
        "kind": ActivityKind.ARTIFACT,
        "status": StepStatus.ERROR if is_error else StepStatus.SUCCESS,
        "title": "",
        "meta": {"listing": True, "count": len(rows)},
    }


def _action_start(args: dict[str, Any]) -> dict[str, Any]:
    """Something done on the person's behalf: a draft saved, a post published,
    metrics logged. The tool name carries the verb; the app words it."""
    # By its words (a topic, a headline), never by a row id the person has
    # no way to read.
    return {"kind": ActivityKind.ACTION, "title": _text(args.get("title") or args.get("topic"))}


def _action_finish(args: dict[str, Any], result: Any, is_error: bool) -> dict[str, Any]:
    env = _envelope(result)
    ok = _ok(env, is_error)
    meta = {k: _text(env.get(k)) for k in ("post_id", "slide_id", "status", "scheduled_at") if env.get(k)}
    return {
        "kind": ActivityKind.ACTION,
        "status": StepStatus.SUCCESS if ok else StepStatus.ERROR,
        "title": _text(env.get("topic") or env.get("headline")) or _action_start(args)["title"],
        "meta": meta,
        "error": "" if ok else _text(env.get("message") or env.get("error")),
    }


def _context_fields(record: dict[str, Any], *_rest: Any) -> dict[str, Any]:
    """The run's own context notice, from the CONTEXT row's payload: which
    blocks were non-empty, so the person knows the turn was enriched with
    their business, profile, memory and sources — and which of those the
    run had nothing for."""
    blocks = record.get("blocks") if isinstance(record.get("blocks"), dict) else {}
    present = [name for name, value in blocks.items() if value not in (None, "", [], {}, False)]
    return {
        "kind": ActivityKind.CONTEXT,
        "status": StepStatus.SUCCESS,
        "title": "",
        "meta": {"blocks": present, "resume": bool(record.get("resume"))},
    }


# The allowlist. A tool not named here never reaches the UI — see the module
# docstring on why this is a list of what shows rather than what hides.
# `task` is deepagents' dispatch tool; the constant lives in deep_session and
# is repeated as a literal here to keep this module import-free of it.
#
# What is left out, and why each has somewhere else to show: RememberFact
# (MEMORY_WRITTEN draws the "Remembered" note, with undo), RequestConnection /
# SelectAccount / AskUserQuestion (the pause cards), CreateArtifact /
# UpdateArtifact / RewriteArtifact (the artifact card), write_todos (the todo
# strip), the execution proposal (the change-set card), and the audit's
# report builders — Start / Add / Finalize / SubmitAuditReport — whose
# progress is the audit's own step ladder. Everything else the model can call
# is here.
ACTIVITY_TOOLS: dict[str, tuple[Callable[..., dict], Callable[..., dict]]] = {
    FETCH_DATA_TOOL: (_data_start, _data_finish),
    "WebSearch": (_search_start, _search_finish),
    "WebFetch": (_fetch_page_start, _fetch_page_finish),
    "FetchPages": (_pages_start, _pages_finish),
    GENERATE_IMAGE_TOOL: (_image_start, _image_finish),
    EDIT_IMAGE_TOOL: (_image_start, _image_finish),
    RENDER_SLIDE_TOOL: (_slide_start, _slide_finish),
    "task": (_subagent_start, _subagent_finish),
    "SearchMemory": (_memory_search_start, _memory_search_finish),
    "GetMemory": (_memory_get_start, _memory_get_finish),
    "ListDataSources": (_read_start, _read_finish),
    "GetArtifact": (_artifact_get_start, _artifact_get_finish),
    "ListArtifacts": (_artifact_list_start, _artifact_list_finish),
    PROJECT_CONTEXT_TOOL: (_context_fields, _context_fields),
    # The content agent's reads of what the project holds …
    "fetch_brand_context": (_read_start, _read_finish),
    "fetch_topic_bank": (_read_start, _read_finish),
    "fetch_format_library": (_read_start, _read_finish),
    "fetch_avatar_library": (_read_start, _read_finish),
    "fetch_content_history": (_read_start, _read_finish),
    "fetch_content_assets": (_read_start, _read_finish),
    "fetch_discovered_references": (_read_start, _read_finish),
    "fetch_post": (_read_start, _read_finish),
    "fetch_slide_context": (_read_start, _read_finish),
    # … and what it does on the person's behalf.
    "submit_plan": (_action_start, _action_finish),
    "submit_post_draft": (_action_start, _action_finish),
    "edit_slide": (_action_start, _action_finish),
    "publish_post": (_action_start, _action_finish),
    "mark_posted": (_action_start, _action_finish),
    "log_metrics": (_action_start, _action_finish),
}


def activity_payload(
    tool: str, activity_id: str, fields: dict[str, Any], status: StepStatus
) -> dict[str, Any]:
    """One TOOL_ACTIVITY event, with the keys the app always expects present."""
    return {
        "event": AgentEvent.TOOL_ACTIVITY,
        # The tool_use_id: the start and the finish are the same card, and the
        # app updates in place rather than drawing the call twice.
        "activity_id": activity_id,
        "tool": tool,
        "kind": str(fields.get("kind") or ""),
        "status": str(fields.get("status") or status),
        "title": _text(fields.get("title")),
        "subtitle": _text(fields.get("subtitle")),
        "source": _text(fields.get("source")),
        "meta": fields.get("meta") or {},
        "error": _text(fields.get("error")),
        "reason": _text(fields.get("reason")),
    }


def activity_hooks(
    emit: Callable[[dict[str, Any]], Awaitable[None]] | None,
    on_tool_use: Callable[[str, Any, str], Awaitable[None]],
    on_tool_result: Callable[[str, Any, str, bool], Awaitable[None]],
) -> tuple[Callable[..., Awaitable[None]], Callable[..., Awaitable[None]]]:
    """Wrap a hook pair so allowlisted tools also emit TOOL_ACTIVITY.

    Wrapping rather than replacing: the hooks it takes keep doing their own
    job (the recorder writes its forensics, the sub-agent hooks move the
    ladder) and this adds the user-visible half. A mapper that raises is
    swallowed — a run must never fail because a card could not be drawn.
    """
    # The call's arguments, kept until its result arrives: a finish mapper
    # reads both, because what a tool was asked for is often clearer than what
    # it returned ("landing pages" beats an empty envelope).
    pending: dict[str, dict[str, Any]] = {}

    async def _emit(payload: dict[str, Any]) -> None:
        if emit is None:
            return
        try:
            await emit(payload)
        except Exception:  # noqa: BLE001 — the UI's notice, never the run
            logger.debug("activity: emit failed", exc_info=True)

    async def wrapped_use(name: str, tool_input: Any, tool_use_id: str) -> None:
        await on_tool_use(name, tool_input, tool_use_id)
        mapper = ACTIVITY_TOOLS.get(name)
        if mapper is None:
            return
        args = tool_input if isinstance(tool_input, dict) else {}
        pending[tool_use_id] = args
        try:
            fields = mapper[0](args)
        except Exception:  # noqa: BLE001
            logger.debug("activity: %s start mapper failed", name, exc_info=True)
            return
        await _emit(activity_payload(name, tool_use_id, fields, StepStatus.RUNNING))

    async def wrapped_result(name: str, result: Any, tool_use_id: str, is_error: bool) -> None:
        await on_tool_result(name, result, tool_use_id, is_error)
        mapper = ACTIVITY_TOOLS.get(name)
        args = pending.pop(tool_use_id, {})
        if mapper is None:
            return
        try:
            fields = mapper[1](args, result, is_error)
        except Exception:  # noqa: BLE001
            logger.debug("activity: %s finish mapper failed", name, exc_info=True)
            return
        await _emit(activity_payload(name, tool_use_id, fields, StepStatus.SUCCESS))

    return wrapped_use, wrapped_result


async def announce_context(recorder: Any, emit: Callable[[dict[str, Any]], Awaitable[None]] | None, record: dict[str, Any]) -> None:
    """Record the run's CONTEXT row and show the person it happened.

    The row (``EventKind.CONTEXT``) is what a session review replays against;
    the TOOL_ACTIVITY notice is the reader's side of the same fact — "Read
    project context · business, memory, 4 sources" — drawn live here and, on
    a reopened thread, from that stored row. One call so a runner cannot
    write the row and forget the notice, or the reverse. Best-effort both
    ways, like every recorder write.
    """
    if recorder is not None:
        try:
            await recorder.record_context(record)
        except Exception:  # noqa: BLE001
            logger.warning("activity: CONTEXT row failed", exc_info=True)
    # A resume is silent on the wire: the reopened transcript already holds
    # the notice from the run that composed the context, and a row on every
    # reopen would say the same thing once per visit.
    if emit is None or record.get("resume"):
        return
    try:
        await emit(activity_payload(
            PROJECT_CONTEXT_TOOL, f"context-{uuid4().hex[:12]}", _context_fields(record), StepStatus.SUCCESS
        ))
    except Exception:  # noqa: BLE001
        logger.debug("activity: context notice failed", exc_info=True)


__all__ = [
    "ACTIVITY_TOOLS",
    "PROJECT_CONTEXT_TOOL",
    "ActivityKind",
    "activity_hooks",
    "activity_payload",
    "announce_context",
]
