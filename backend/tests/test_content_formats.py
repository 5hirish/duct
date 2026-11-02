"""A project's formats bind (``agents/content/formats.py``).

The library was decoration: the plan was told there were no formats, a post
could not be started in one, and the renderer loads every style, so the
styles a format linked changed nothing. These pin the three places it binds
now: the plan reads the library, a draft started in a format is filed under
it, and a photo caption outside the format's styles is refused.
"""

from __future__ import annotations

import asyncio
import json
from uuid import uuid4

import pytest
from sqlmodel import Session

import agents.content.tools as content_tools
from agents.content.formats import FormatSummary, format_summaries, style_problems
from agents.content.prompts import build_plan_user_prompt, build_post_user_prompt
from agents.content.schema import ContentBrandContext, Slide
from agents.content.v1.runner import make_session
from models.auth import User
from models.content import ContentFormat, ContentPost
from models.project import Project
from tests.conftest import make_sqlite_engine

UGC = FormatSummary(slug="ugc", name="UGC raw", slide_count=7, styles=("hook", "cap-stroke", "body-neutral"))


def _slide(n: int, style: str, kind: str = "photo", headline: str = "words") -> Slide:
    return Slide(slide_id=f"slide-{n:02d}", kind=kind, caption_style=style, headline=headline)


def test_a_photo_caption_outside_the_formats_styles_is_named():
    problems = style_problems(UGC, [_slide(1, "hook"), _slide(2, "cap-raw"), _slide(3, "cap-stroke")])
    assert len(problems) == 1
    assert "slide-02 uses cap-raw" in problems[0] and "hook, cap-stroke" in problems[0]


def test_only_a_styled_photo_caption_is_held_to_the_format():
    text_card = _slide(1, "cap-raw", kind="text")
    no_words = _slide(2, "cap-raw", headline="")
    assert style_problems(UGC, [text_card, no_words]) == []


def test_a_format_that_links_no_caption_style_leaves_captions_free():
    body_only = FormatSummary(slug="cards", name="Cards", slide_count=None, styles=("body-neutral",))
    assert style_problems(body_only, [_slide(1, "cap-raw")]) == []


@pytest.fixture
def engine():
    return make_sqlite_engine()


@pytest.fixture
def project(engine):
    with Session(engine) as db:
        owner = User(email="maker@example.com")
        db.add(owner)
        db.commit()
        row = Project(user_id=owner.id, name="Duct", slug="duct")
        db.add(row)
        db.commit()
        db.add(ContentFormat(project_id=row.id, slug="ugc", name="UGC raw",
                             data={"default_slide_count": 7, "linked_styles": ["hook", "cap-stroke", "nope"]}))
        db.commit()
        db.refresh(row)
        return row


def test_the_plan_reads_the_library_it_used_to_be_told_was_empty(engine, project):
    with Session(engine) as db:
        formats = [f.as_dict() for f in format_summaries(db, project.id)]
    assert formats == [{"slug": "ugc", "name": "UGC raw", "slide_count": 7, "styles": ["hook", "cap-stroke"]}]
    brand = ContentBrandContext(project_id=project.id, project_name="Duct")
    assert "no formats" not in build_plan_user_prompt(brand, history=[], formats=formats, avatars=[])
    assert "fetch_format_library" in build_post_user_prompt(brand, None, format_slug="ugc", fmt=UGC)


def _submit(engine, project, monkeypatch, slides: list[dict]) -> dict:
    monkeypatch.setattr(content_tools, "_open_db", lambda: Session(engine))
    session = make_session(f"fmt-{uuid4()}", project.id, "draft_post")
    session.channel = "tiktok"
    session.format_slug = "ugc"

    async def _emit(_event):
        return None

    tools = {t.name: t for t in content_tools.build_content_tools_lc(project.id, _emit, session)}
    draft = {"type": "post", "project_id": str(project.id), "post_dir_slug": f"2026-11-01-{uuid4().hex[:4]}",
             "pillar": "build", "topic": "formats", "caption": "A caption.", "slides": slides}
    return json.loads(asyncio.run(tools["submit_post_draft"].ainvoke({"post": draft})))


def test_a_draft_started_in_a_format_is_filed_under_it(engine, project, monkeypatch):
    result = _submit(engine, project, monkeypatch, [
        {"slide_id": "slide-01", "caption_style": "hook", "headline": "Stop guessing"},
        {"slide_id": "slide-02", "caption_style": "cap-stroke", "headline": "Here is why"},
    ])
    assert result.get("status") != "error", result
    with Session(engine) as db:
        post = db.query(ContentPost).one()
        fmt = db.query(ContentFormat).one()
    assert post.format_id == fmt.id


def test_a_caption_style_the_format_does_not_link_is_refused(engine, project, monkeypatch):
    result = _submit(engine, project, monkeypatch, [
        {"slide_id": "slide-01", "caption_style": "cap-whisper", "headline": "Stop guessing"},
    ])
    assert result["status"] == "error" and "slide-01 uses cap-whisper" in result["message"]
    with Session(engine) as db:
        assert db.query(ContentPost).count() == 0
