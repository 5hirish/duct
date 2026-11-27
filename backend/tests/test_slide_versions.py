"""A slide can go back to an earlier version, from the chat or the slide.

Until 2026-11-27 every change to a slide overwrote the last: a better picture
the person preferred was gone, and asking for it back meant a regeneration
that never gives the same picture. Every writer now keeps the state it
replaced (agents/content/slide_versions.py).
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlmodel import Session

from agents.content.schema import make_session
from agents.content.slide_versions import MAX_VERSIONS, record_changes, restore
from models.content import ContentPost
from tests.conftest import make_sqlite_engine


def _slide(n: int, **fields) -> dict:
    return {"slide_id": f"slide-0{n}", "kind": "photo", "headline": f"Headline {n}",
            "image_prompt": f"p{n}", **fields}


def _row(slides):
    return SimpleNamespace(slides=slides, slide_versions={})


def test_only_a_slide_that_changed_keeps_its_old_state():
    before = [_slide(1, image_url="/a.png"), _slide(2)]
    row = _row([_slide(1, image_url="/b.png"), {**_slide(2)}])

    assert record_changes(row, before, by="agent") == ["slide-01"]
    (kept,) = row.slide_versions["slide-01"]
    assert kept["slide"]["image_url"] == "/a.png" and kept["by"] == "agent"
    assert "slide-02" not in row.slide_versions


def test_a_restore_is_undone_by_the_same_restore():
    row = _row([_slide(1, image_url="/a.png")])
    for url in ("/b.png", "/c.png"):
        before = list(row.slides)
        row.slides = [_slide(1, image_url=url)]
        record_changes(row, before, by="agent")

    assert restore(row, "slide-01", 1)
    assert row.slides[0]["image_url"] == "/b.png"
    assert restore(row, "slide-01", 1)
    assert row.slides[0]["image_url"] == "/c.png"
    assert restore(row, "slide-01", 2)            # the first picture, two steps back
    assert row.slides[0]["image_url"] == "/a.png"
    assert not restore(row, "slide-01", 3)


def test_nothing_to_go_back_to_changes_nothing():
    row = _row([_slide(1)])
    assert not restore(row, "slide-01", 1)
    assert not restore(row, "slide-09", 1)
    assert row.slides == [_slide(1)]


def test_history_is_capped_per_slide():
    row = _row([_slide(1, image_url="/0.png")])
    for i in range(1, MAX_VERSIONS + 4):
        before = list(row.slides)
        row.slides = [_slide(1, image_url=f"/{i}.png")]
        record_changes(row, before, by="agent")
    kept = row.slide_versions["slide-01"]
    assert len(kept) == MAX_VERSIONS
    assert kept[-1]["slide"]["image_url"] == f"/{MAX_VERSIONS + 2}.png"


# ---------------------------------------------------------------------------
# Through the agent's tools, as "undo that" in the chat reaches it
# ---------------------------------------------------------------------------

@pytest.fixture
def engine(monkeypatch):
    engine = make_sqlite_engine()
    monkeypatch.setattr("agents.content.tools.get_engine", lambda: engine)
    return engine


def _tools(session, emit):
    from agents.content.tools import build_content_tools_lc

    return {t.name: t for t in build_content_tools_lc(session.project_id, emit, session)}


def test_the_agent_edits_a_slide_and_puts_it_back(engine, emitted):
    row = ContentPost(project_id=uuid4(), post_dir_slug="bob", slides=[_slide(1), _slide(2)], status="draft")
    with Session(engine) as db:
        db.add(row)
        db.commit()
        db.refresh(row)
    session = make_session("s", row.project_id, "draft_post")
    session.post_id = row.id
    tools = _tools(session, emitted)

    asyncio.run(tools["edit_slide"].ainvoke({"slide_id": "slide-02", "patch": {"headline": "Worse"}}))
    result = json.loads(asyncio.run(tools["restore_slide"].ainvoke({"slide_id": "slide-02"})))

    assert result["slide_id"] == "slide-02" and result["versions"] == 1
    with Session(engine) as db:
        stored = db.get(ContentPost, row.id)
        assert stored.slides[1]["headline"] == "Headline 2"
        assert stored.slide_versions["slide-02"][-1]["slide"]["headline"] == "Worse"
        assert "Headline 2" in stored.slides_html
    shown = emitted.events[-1]["payload"]
    assert shown["slides"][1]["headline"] == "Headline 2" and "slide-02" in shown["slide_versions"]

    refused = json.loads(asyncio.run(tools["restore_slide"].ainvoke({"slide_id": "slide-01"})))
    assert refused["status"] == "error"
