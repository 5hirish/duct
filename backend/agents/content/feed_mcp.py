"""Linear and Notion as feeds for a plan from shipped work (#565).

Read by code before the model starts, the same as GitHub: what reaches the
prompt is filtered, capped and citable (``ln:`` and ``nt:`` refs), and a
quiet window still costs no model call. The agent never browses these
servers for a feed; it is handed what was found.

Both are the user's own MCP connections, and only the presets Duct trusts
(``trust_read_only``): a server added by address is never read here, because
whatever Duct sends it, it sends to a stranger.

Neither vendor publishes a stable tool contract, so nothing here assumes one:

* **Linear** documents its endpoints but not its tool names. The collector
  looks for a tool from ``LINEAR_ISSUE_TOOLS`` on each read, sends only the
  arguments that tool's own schema declares, and decides "completed in the
  window" in code from whatever dates and status the rows carry. A server
  without such a tool says so in a note, and the read goes on without it.
* **Notion** reads one database the person picked. ``notion-fetch`` turns
  its link into the data source, ``notion-query-data-sources`` (rows mode)
  returns its rows, and a row counts when one of its dates falls in the
  window. Rows mode spends the workspace's query allowance below Business
  with Notion AI, so one call per read, at most ``NOTION_ROW_LIMIT`` rows.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from typing import Any
from uuid import UUID

from agents.content.feed import Disclosure, FeedItem, FeedSource, LeftOut

logger = logging.getLogger(__name__)

LINEAR = "linear"
NOTION = "notion"
LINEAR_ISSUE = "linear_issue"
NOTION_PAGE = "notion_page"

# The names Linear's hosted server has used for its issue listing. Checked in
# order against what the server offers on each read.
LINEAR_ISSUE_TOOLS = ("list_issues", "linear_list_issues", "search_issues")
NOTION_FETCH = "notion-fetch"
NOTION_QUERY = "notion-query-data-sources"
# The OpenAI-style clients strip the prefix; accept either spelling.
NOTION_ALIASES = {NOTION_FETCH: ("notion-fetch", "fetch"), NOTION_QUERY: ("notion-query-data-sources", "query-data-sources")}

ISSUE_LIMIT = 100
NOTION_ROW_LIMIT = 100
MAX_PER_SOURCE = 15

_DONE = frozenset({"done", "completed", "complete", "shipped", "released", "closed"})
_DATE_KEYS = re.compile(r"(complet|publish|releas|ship|launch|date|updat|edit|creat)", re.IGNORECASE)
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}")
_DATA_SOURCE = re.compile(r"collection://[A-Za-z0-9-]+")
_IDENTIFIER = re.compile(r"^[A-Z][A-Z0-9]*-\d+$")


@dataclass
class McpFeed:
    """What the Linear and Notion reads came to."""

    items: list[FeedItem] = field(default_factory=list)
    left_out: Counter = field(default_factory=Counter)
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Parsing: tolerant of shape, strict about the window
# ---------------------------------------------------------------------------


def _payload(text: str, structured: Any) -> Any:
    """The tool's answer as data: its structured content when that holds the
    rows, else its text parsed as JSON. A tool that returns a JSON string
    comes back from the SDK wrapped as ``{"result": "<json>"}``."""
    if isinstance(structured, dict) and isinstance(structured.get("result"), str) and len(structured) == 1:
        text, structured = structured["result"], None
    if structured not in (None, {}, []) and _records(structured):
        return structured
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return structured


def _records(value: Any) -> list[dict]:
    """The list of row objects inside a tool result, wherever it sits: the
    list itself, or the first list of objects under a key such as ``issues``,
    ``nodes`` or ``results``."""
    if isinstance(value, list):
        return [v for v in value if isinstance(v, dict)]
    if isinstance(value, dict):
        for key in ("issues", "nodes", "results", "items", "rows", "data", "pages"):
            found = value.get(key)
            if isinstance(found, list):
                return [v for v in found if isinstance(v, dict)]
            if isinstance(found, dict):
                nested = _records(found)
                if nested:
                    return nested
    return []


def _day(value: Any) -> date | None:
    if isinstance(value, dict):  # Notion's {"start": …} date property
        value = value.get("start") or value.get("date")
    text = str(value or "")
    if not _ISO_DATE.match(text):
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _in(day: date | None, window: tuple[date, date]) -> bool:
    return day is not None and window[0] <= day <= window[1]


def _status(issue: dict) -> str:
    raw = issue.get("status") or issue.get("state") or ""
    if isinstance(raw, dict):
        raw = raw.get("type") or raw.get("name") or ""
    return str(raw).strip().lower()


def linear_items(raw: Any, window: tuple[date, date], *, disclosure: Disclosure,
                 already: set[str]) -> tuple[list[FeedItem], Counter]:
    """Completed Linear issues inside the window, newest first. Linear is a
    private tracker, so a "releases only" disclosure reads none of it."""
    left: Counter = Counter()
    rows = _records(raw)
    if disclosure == Disclosure.RELEASES:
        left[LeftOut.DISCLOSURE] += len(rows)
        return [], left
    kept: list[FeedItem] = []
    for issue in rows:
        identifier = str(issue.get("identifier") or "").strip()
        title = str(issue.get("title") or "").strip()
        if not title or not _IDENTIFIER.match(identifier):
            continue
        completed = _day(issue.get("completedAt") or issue.get("completed_at"))
        done = completed is not None or _status(issue) in _DONE
        when = completed or _day(issue.get("updatedAt") or issue.get("updated_at"))
        if not done or not _in(when, window):
            continue
        ref = f"ln:{identifier}"
        if ref in already:
            left[LeftOut.ALREADY_PLANNED] += 1
            continue
        kept.append(FeedItem(ref=ref, kind=LINEAR_ISSUE, title=title, url=str(issue.get("url") or ""),
                             at=when.isoformat(), state="completed"))
    kept.sort(key=lambda i: i.at, reverse=True)
    if len(kept) > MAX_PER_SOURCE:
        left[LeftOut.OVER_CAP] += len(kept) - MAX_PER_SOURCE
        kept = kept[:MAX_PER_SOURCE]
    return kept, left


def _row_title(row: dict) -> str:
    for key in ("title", "Title", "Name", "name"):
        if isinstance(row.get(key), str) and row[key].strip():
            return row[key].strip()
    return next((v.strip() for v in row.values() if isinstance(v, str) and v.strip()
                 and not v.startswith(("http", "collection://"))), "")


def _row_day(row: dict) -> date | None:
    """The row's most telling date: one under a published / released / done
    key before an edited or created one, newest within the same rank."""
    ranked: list[tuple[int, date]] = []
    for key, value in row.items():
        found = _day(value)
        match = _DATE_KEYS.search(str(key))
        if found is None or match is None:
            continue
        word = match.group(1).lower()
        rank = 0 if word in ("publish", "releas", "ship", "launch", "complet", "date") else 1
        ranked.append((rank, found))
    if not ranked:
        return None
    best = min(r for r, _ in ranked)
    return max(d for r, d in ranked if r == best)


def notion_items(raw: Any, window: tuple[date, date], *, already: set[str]) -> tuple[list[FeedItem], Counter]:
    """Rows of the picked database dated inside the window, newest first."""
    left: Counter = Counter()
    kept: list[FeedItem] = []
    for row in _records(raw):
        title = _row_title(row)
        when = _row_day(row)
        if not title or not _in(when, window):
            continue
        url = str(row.get("url") or row.get("URL") or "")
        anchor = str(row.get("id") or url or title)
        ref = f"nt:{hashlib.sha256(anchor.encode()).hexdigest()[:10]}"
        if ref in already:
            left[LeftOut.ALREADY_PLANNED] += 1
            continue
        kept.append(FeedItem(ref=ref, kind=NOTION_PAGE, title=title, url=url, at=when.isoformat()))
    kept.sort(key=lambda i: i.at, reverse=True)
    if len(kept) > MAX_PER_SOURCE:
        left[LeftOut.OVER_CAP] += len(kept) - MAX_PER_SOURCE
        kept = kept[:MAX_PER_SOURCE]
    return kept, left


# ---------------------------------------------------------------------------
# The reads
# ---------------------------------------------------------------------------


def linear_arguments(schema: dict, window: tuple[date, date], *, today: date) -> dict:
    """Only what the tool's own schema declares: an unknown argument is an
    error on a strict server, and a missing filter is made up for in code."""
    props = (schema or {}).get("properties") or {}
    days = max(1, (today - window[0]).days + 1)
    args: dict[str, Any] = {}
    for key in ("updatedAt", "updated_at", "updatedSince"):
        if key in props:
            args[key] = f"-P{days}D"
            break
    if "limit" in props:
        args["limit"] = ISSUE_LIMIT
    if "first" in props:
        args["first"] = ISSUE_LIMIT
    if "orderBy" in props:
        args["orderBy"] = "updatedAt"
    if "includeArchived" in props:
        args["includeArchived"] = False
    return args


def _id_argument(schema: dict) -> str:
    """The name ``notion-fetch`` takes its link under: its schema says."""
    props = (schema or {}).get("properties") or {}
    for key in ("id", "url", "uri"):
        if key in props:
            return key
    required = (schema or {}).get("required") or []
    return required[0] if required else "id"


def _servers_sync(user_id: UUID) -> list:
    from db.session import get_session as db_session
    from service.mcp.store import servers_for_user

    with next(db_session()) as db:
        return servers_for_user(db, user_id)


def _sink(access):
    """Where a refreshed token is kept, as the agent's own calls keep it."""
    async def save(credentials: dict) -> None:
        if access.row_id is None:
            return

        def _store() -> None:
            from db.session import get_session as db_session
            from service.mcp.store import store_credentials

            with next(db_session()) as db:
                store_credentials(db, access.row_id, credentials)

        await asyncio.to_thread(_store)

    return save


def _tool(tools: list, names: tuple[str, ...]):
    by_name = {t.name: t for t in tools}
    return next((by_name[n] for n in names if n in by_name), None)


async def read_mcp_feeds(
    user_id: UUID,
    sources: list[FeedSource],
    window: tuple[date, date],
    *,
    disclosure: Disclosure,
    already: set[str],
    notion_database: str = "",
    today: date | None = None,
    servers: list | None = None,
) -> McpFeed:
    """Read the asked-for Linear and Notion feeds on the user's own trusted
    connections. Never raises: a source that cannot be read leaves a note."""
    from service.mcp import client as mcp_client
    from service.mcp.presets import preset_for_url

    out = McpFeed()
    today = today or window[1]
    wanted = [s for s in sources if s in (FeedSource.LINEAR, FeedSource.NOTION)]
    if not wanted:
        return out
    if servers is None:
        try:
            servers = await asyncio.to_thread(_servers_sync, user_id)
        except Exception:  # noqa: BLE001
            logger.warning("feed: could not read connected servers", exc_info=True)
            servers = []
    by_preset = {}
    for access in servers:
        found = preset_for_url(access.url)
        if found and found.trust_read_only and access.vetted:
            by_preset.setdefault(found.id, access)

    async def linear() -> None:
        access = by_preset.get(LINEAR)
        if access is None:
            out.notes.append("Linear is not connected, so nothing was read from it.")
            return
        tools = await mcp_client.list_tools(access, _sink(access))
        tool = _tool(tools, LINEAR_ISSUE_TOOLS)
        if tool is None:
            out.notes.append("Linear offers no issue listing Duct recognises ("
                             + ", ".join(LINEAR_ISSUE_TOOLS) + "), so nothing was read from it.")
            return
        result = await mcp_client.call_tool(access, tool.name, linear_arguments(tool.input_schema, window, today=today), _sink(access))
        if result.is_error:
            out.notes.append("Linear refused the issue listing, so nothing was read from it.")
            return
        kept, left = linear_items(_payload(result.text, result.structured), window,
                                  disclosure=disclosure, already=already)
        out.items += kept
        out.left_out.update(left)

    async def notion() -> None:
        access = by_preset.get(NOTION)
        if access is None:
            out.notes.append("Notion is not connected, so nothing was read from it.")
            return
        if not notion_database.strip():
            out.notes.append("No Notion database was picked, so nothing was read from Notion.")
            return
        tools = await mcp_client.list_tools(access, _sink(access))
        fetch = _tool(tools, NOTION_ALIASES[NOTION_FETCH])
        query = _tool(tools, NOTION_ALIASES[NOTION_QUERY])
        if fetch is None or query is None:
            out.notes.append("Notion does not offer the database tools Duct needs, so nothing was read from it.")
            return
        source = notion_database.strip()
        if not source.startswith("collection://"):
            fetched = await mcp_client.call_tool(
                access, fetch.name, {_id_argument(fetch.input_schema): source}, _sink(access),
            )
            found = _DATA_SOURCE.search(fetched.text or "")
            if fetched.is_error or found is None:
                out.notes.append("Notion could not open the picked database, so nothing was read from it.")
                return
            source = found.group(0)
        result = await mcp_client.call_tool(
            access, query.name, {"mode": "rows", "data_source_url": source, "limit": NOTION_ROW_LIMIT}, _sink(access),
        )
        if result.is_error:
            out.notes.append("Notion refused the database read, so nothing was read from it.")
            return
        kept, left = notion_items(_payload(result.text, result.structured), window, already=already)
        out.items += kept
        out.left_out.update(left)

    jobs = {FeedSource.LINEAR: linear, FeedSource.NOTION: notion}
    for source in wanted:
        try:
            await jobs[source]()
        except Exception as exc:  # noqa: BLE001 — one source failing never ends the read
            logger.warning("feed: %s read failed", source, exc_info=True)
            out.notes.append(f"{source.value.title()} could not be read ({type(exc).__name__}).")
    return out
