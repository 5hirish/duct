"""Linear and Notion as feeds (#565): read by code on the user's own trusted
connections, kept to the window, citable, and never fatal to the read.

Driven against a real in-process MCP server (``FakeMcpServer``), so the tool
lookup, the arguments sent and the parsing all run on what the server says.
"""

from __future__ import annotations

import json
from datetime import date

from agents.content.feed import Disclosure, FeedOptions, FeedSource, LeftOut, build_digest
from agents.content.feed_mcp import (
    LINEAR_ISSUE, NOTION_PAGE, linear_arguments, linear_items, notion_items, read_mcp_feeds,
)
from service.mcp.presets import preset
from service.mcp.store import ServerAccess, no_credentials
from tests.fakes import FakeMcpServer

WINDOW = (date(2026, 10, 29), date(2026, 11, 11))
ISSUES = [
    {"identifier": "ENG-412", "title": "Invoices from the job card", "status": "Done",
     "completedAt": "2026-11-04T10:00:00Z", "url": "https://linear.app/acme/issue/ENG-412"},
    {"identifier": "ENG-399", "title": "Still in review", "status": "In Review", "updatedAt": "2026-11-05T09:00:00Z"},
    {"identifier": "ENG-301", "title": "Done long ago", "status": "Done", "completedAt": "2026-09-01T09:00:00Z"},
    {"identifier": "ENG-420", "title": "Done, no completion date", "status": {"type": "completed"},
     "updatedAt": "2026-11-09T09:00:00Z"},
]
ROWS = [
    {"id": "p1", "Name": "Launch notes: invoices", "Published": {"start": "2026-11-06"},
     "Last edited": "2026-11-07T12:00:00Z", "url": "https://www.notion.so/p1"},
    {"id": "p2", "Name": "Draft, never published", "Created": "2026-08-01T00:00:00Z"},
    {"id": "p3", "Name": "Pricing page refresh", "Date": "2026-11-10"},
]


def test_completed_issues_inside_the_window_are_kept_and_cited():
    kept, left = linear_items({"issues": ISSUES}, WINDOW, disclosure=Disclosure.SHIPPED, already=set())
    assert [i.ref for i in kept] == ["ln:ENG-420", "ln:ENG-412"]
    assert {i.kind for i in kept} == {LINEAR_ISSUE}
    assert kept[1].url.endswith("ENG-412") and kept[1].at == "2026-11-04"
    assert not left


def test_releases_only_reads_nothing_from_a_private_tracker():
    kept, left = linear_items(ISSUES, WINDOW, disclosure=Disclosure.RELEASES, already=set())
    assert kept == [] and left[LeftOut.DISCLOSURE] == len(ISSUES)


def test_a_database_row_counts_by_its_most_telling_date():
    kept, left = notion_items({"results": ROWS}, WINDOW, already=set())
    assert [i.title for i in kept] == ["Pricing page refresh", "Launch notes: invoices"]
    assert kept[1].at == "2026-11-06"  # published, not the later edit
    assert all(i.ref.startswith("nt:") and i.kind == NOTION_PAGE for i in kept)
    again, left = notion_items(ROWS, WINDOW, already={kept[0].ref})
    assert len(again) == 1 and left[LeftOut.ALREADY_PLANNED] == 1


def test_only_the_arguments_the_tool_declares_are_sent():
    schema = {"properties": {"limit": {}, "updatedAt": {}, "team": {}}}
    assert linear_arguments(schema, WINDOW, today=date(2026, 11, 11)) == {"updatedAt": "-P14D", "limit": 100}
    assert linear_arguments({}, WINDOW, today=date(2026, 11, 11)) == {}


def _fake():
    server = FakeMcpServer()
    server.sent = []

    @server.mcp.tool()
    def list_issues(limit: int = 50, updatedAt: str = "") -> str:
        server.sent.append(("list_issues", {"limit": limit, "updatedAt": updatedAt}))
        return json.dumps({"issues": ISSUES})

    @server.mcp.tool(name="notion-fetch")
    def notion_fetch(id: str) -> str:
        server.sent.append(("notion-fetch", id))
        return "<database>\n<data-source url=\"collection://abc-123\">Launches</data-source>\n</database>"

    @server.mcp.tool(name="notion-query-data-sources")
    def notion_query(mode: str, data_source_url: str, limit: int = 50) -> str:
        server.sent.append(("notion-query-data-sources", data_source_url))
        return json.dumps({"results": ROWS, "has_more": False})

    return server


def _access(preset_id):
    p = preset(preset_id)
    return ServerAccess(row_id=None, key=preset_id, url=p.url, name=p.label, credentials=no_credentials())


async def test_both_feeds_are_read_on_trusted_connections_and_reach_the_digest(monkeypatch):
    server = _fake()
    async with server.running(monkeypatch):
        feed = await read_mcp_feeds(
            None, [FeedSource.LINEAR, FeedSource.NOTION], WINDOW, disclosure=Disclosure.SHIPPED, already=set(),
            notion_database="https://www.notion.so/acme/Launches-0123", servers=[_access("linear"), _access("notion")],
        )
    assert ("notion-query-data-sources", "collection://abc-123") in server.sent
    assert server.sent[0] == ("list_issues", {"limit": 100, "updatedAt": "-P14D"})
    assert {i.kind for i in feed.items} == {LINEAR_ISSUE, NOTION_PAGE} and feed.notes == []

    options = FeedOptions(sources=[FeedSource.LINEAR, FeedSource.NOTION])
    digest = build_digest(options, WINDOW, github_rows=None, duct=None, already=set(), extra=feed)
    assert digest.worth_a_plan  # two finished issues and two launch pages clear the gate
    assert all(ref in digest.refs() for ref in ("ln:ENG-412", "ln:ENG-420"))


async def test_a_missing_or_untrusted_source_leaves_a_note_not_a_failure(monkeypatch):
    stranger = ServerAccess(row_id=None, key="linear-copy", url="https://mcp.vendor.test/mcp", name="Linear copy",
                            credentials=no_credentials())
    server = _fake()
    async with server.running(monkeypatch):
        feed = await read_mcp_feeds(
            None, [FeedSource.LINEAR, FeedSource.NOTION], WINDOW, disclosure=Disclosure.SHIPPED, already=set(),
            servers=[stranger, _access("notion")],
        )
    assert feed.items == [] and server.sent == []
    assert any("Linear is not connected" in n for n in feed.notes)
    assert any("No Notion database" in n for n in feed.notes)
