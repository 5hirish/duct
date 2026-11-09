"""The content format library: built-ins on disk, a project's own rows, and
the filters the agent reads them through (agents/content/formats.py).

Three things are held here. The built-in directory stays valid (every file
parses, its header follows the Agent Skills shape, its filters name real
media kinds and channels), the merge rule holds (a project's row with a
built-in's slug replaces it, and only for that project), and the API refuses
a filter nothing would ever match.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session

from agents.content import formats as fl
from agents.content.channels import Platform
from agents.content.platform_guides import MEDIA_KINDS
from db.session import get_session as get_session_dep
from models.auth import User
from models.content import ContentFormat
from models.membership import ProjectMember
from models.project import Project
import routes.content as content_routes
import service.auth as auth_service
from service.membership import ROLE_OWNER
from tests.conftest import make_sqlite_engine

# The four that ship. Together they cover slideshow, video and text, so a
# plan on any channel finds a recipe for what it is making.
EXPECTED_BUILTINS = {"ugc-carousel", "educational-carousel", "short-video-script", "text-insight-post"}


# ---------------------------------------------------------------------------
# Frontmatter
# ---------------------------------------------------------------------------


def test_frontmatter_grammar_covers_inline_and_block_lists():
    meta, body = fl.parse_frontmatter(
        "---\n"
        "name: demo\n"
        'title: "A title: with a colon"\n'
        "media: [slideshow, video]\n"
        "channels:\n"
        "  - tiktok\n"
        "  - linkedin\n"
        "---\n"
        "# Body\n"
    )
    assert meta == {
        "name": "demo",
        "title": "A title: with a colon",
        "media": ["slideshow", "video"],
        "channels": ["tiktok", "linkedin"],
    }
    assert body == "# Body\n"


def test_a_file_without_a_header_is_body_only():
    meta, body = fl.parse_frontmatter("# Just a spec\n")
    assert meta == {}
    assert body == "# Just a spec\n"


def test_render_round_trips_parse():
    meta = {"name": "demo", "title": "Demo: one", "media": ["text"], "channels": []}
    parsed, _ = fl.parse_frontmatter(fl.render_frontmatter(meta) + "body\n")
    assert parsed == meta


# ---------------------------------------------------------------------------
# The built-in directory
# ---------------------------------------------------------------------------


def test_every_builtin_loads_and_the_expected_set_ships():
    builtins = {f["slug"]: f for f in fl.builtin_formats()}
    assert EXPECTED_BUILTINS <= set(builtins)
    for slug, f in builtins.items():
        assert fl.SLUG_RE.match(slug), slug
        assert f["name"] and f["name"] != slug, f"{slug} needs a human title"
        assert 1 <= len(f["description"]) <= fl.MAX_DESCRIPTION
        assert set(f["media"]) <= set(MEDIA_KINDS)
        assert set(f["channels"]) <= {str(p) for p in Platform}
        assert f["spec_markdown"].lstrip().startswith("#"), f"{slug} spec should open with its title"
        assert f["source"] == fl.SOURCE_BUILTIN
        assert f["id"] is None


def test_builtins_cover_every_media_kind_a_plan_can_ask_for():
    covered = {kind for f in fl.builtin_formats() for kind in f["media"]}
    assert {"slideshow", "video", "text"} <= covered


def test_a_broken_header_names_the_file(tmp_path):
    bad = tmp_path / "bad-one.md"
    bad.write_text("---\nname: other\ntitle: X\ndescription: y\nmedia: [hologram]\n---\nbody\n")
    with pytest.raises(ValueError) as exc:
        fl.load_builtin(bad)
    msg = str(exc.value)
    assert "bad-one.md" in msg
    assert "name must equal the file name" in msg
    assert "hologram" in msg


# ---------------------------------------------------------------------------
# Applicability
# ---------------------------------------------------------------------------


def test_empty_filters_match_everything_on_both_sides():
    everywhere = {"media": [], "channels": []}
    narrow = {"media": ["video"], "channels": ["tiktok"]}
    assert fl.applies(everywhere, media="text", channel="bluesky")
    assert fl.applies(narrow)
    assert fl.applies(narrow, media="video", channel="tiktok")
    assert not fl.applies(narrow, media="slideshow")
    assert not fl.applies(narrow, channel="linkedin")


def test_select_narrows_by_media_then_channel():
    lib = fl.library([])
    videos = fl.select(lib, media="video")
    assert {f["slug"] for f in videos} == {"short-video-script"}
    linkedin_text = fl.select(lib, media="text", channel="linkedin")
    assert {f["slug"] for f in linkedin_text} == {"text-insight-post"}
    assert fl.select(lib, media="slideshow", channel="linkedin")[0]["slug"] == "educational-carousel"


def test_validate_data_normalises_and_refuses_unknown_filters():
    out = fl.validate_data({
        "description": "  x  ",
        "media": ["VIDEO", "slideshow"],
        "channels": "tiktok",
        "spec_markdown": "# s",
        "default_slide_count": 7,       # legacy, dropped
        "linked_styles": ["hook"],      # legacy, dropped
    })
    assert out == {
        "description": "x",
        "media": ["video", "slideshow"],
        "channels": ["tiktok"],
        "spec_markdown": "# s",
    }
    with pytest.raises(ValueError, match="hologram"):
        fl.validate_data({"media": ["hologram"]})
    with pytest.raises(ValueError, match="myspace"):
        fl.validate_data({"channels": ["myspace"]})


# ---------------------------------------------------------------------------
# The merged library, through the API
# ---------------------------------------------------------------------------


@pytest.fixture
def db():
    with Session(make_sqlite_engine()) as session:
        yield session


@pytest.fixture
def owner(db):
    row = User(email="formats-owner@example.com")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@pytest.fixture
def project(db, owner):
    row = Project(user_id=owner.id, name="Owner's brand")
    db.add(row)
    db.commit()
    db.refresh(row)
    db.add(ProjectMember(project_id=row.id, user_id=owner.id, role=ROLE_OWNER))
    db.commit()
    return row


def client(db, user):
    app = FastAPI()
    app.include_router(content_routes.router, prefix="/api")
    app.dependency_overrides[get_session_dep] = lambda: db
    app.dependency_overrides[auth_service.get_current_user] = lambda: user
    return TestClient(app, raise_server_exceptions=False)


def test_a_new_project_sees_the_builtins_read_only(db, owner, project):
    res = client(db, owner).get(f"/api/content/formats?project_id={project.id}")
    assert res.status_code == 200
    rows = res.json()
    by_slug = {r["slug"]: r for r in rows}
    assert EXPECTED_BUILTINS <= set(by_slug)
    ugc = by_slug["ugc-carousel"]
    assert ugc["source"] == "builtin"
    assert ugc["id"] is None
    assert ugc["media"] == ["slideshow"]
    assert "tiktok" in ugc["channels"]
    assert ugc["data"]["spec_markdown"].startswith("# UGC Carousel")


def test_customising_a_builtin_replaces_it_for_that_project_only(db, owner, project):
    c = client(db, owner)
    res = c.post("/api/content/formats", json={
        "project_id": str(project.id),
        "slug": "ugc-carousel",
        "name": "Our UGC carousel",
        "data": {"description": "ours", "media": ["slideshow"], "channels": ["tiktok"], "spec_markdown": "# Ours"},
    })
    assert res.status_code == 201, res.text
    assert res.json()["source"] == "custom"
    assert res.json()["overrides_builtin"] is True

    rows = c.get(f"/api/content/formats?project_id={project.id}").json()
    mine = [r for r in rows if r["slug"] == "ugc-carousel"]
    assert len(mine) == 1 and mine[0]["name"] == "Our UGC carousel"
    # The built-ins still ship beside it.
    assert {r["slug"] for r in rows} >= EXPECTED_BUILTINS

    # Another project is untouched.
    other = Project(user_id=owner.id, name="Second brand", slug="second-brand")
    db.add(other)
    db.commit()
    db.refresh(other)
    db.add(ProjectMember(project_id=other.id, user_id=owner.id, role=ROLE_OWNER))
    db.commit()
    theirs = [r for r in c.get(f"/api/content/formats?project_id={other.id}").json() if r["slug"] == "ugc-carousel"]
    assert theirs[0]["source"] == "builtin"

    # Deleting the row is "reset": the built-in is back.
    row_id = mine[0]["id"]
    assert c.delete(f"/api/content/formats/{row_id}").status_code == 200
    back = [r for r in c.get(f"/api/content/formats?project_id={project.id}").json() if r["slug"] == "ugc-carousel"]
    assert back[0]["source"] == "builtin"


def test_the_api_refuses_a_filter_nothing_would_match(db, owner, project):
    res = client(db, owner).post("/api/content/formats", json={
        "project_id": str(project.id),
        "slug": "my-format",
        "name": "Mine",
        "data": {"media": ["hologram"]},
    })
    assert res.status_code == 422
    assert "hologram" in res.text


def test_the_api_refuses_a_slug_that_is_not_a_slug(db, owner, project):
    res = client(db, owner).post("/api/content/formats", json={
        "project_id": str(project.id), "slug": "Format D", "name": "x", "data": {},
    })
    assert res.status_code == 422


def test_an_old_row_still_reads_with_empty_filters(db, project):
    row = ContentFormat(
        project_id=project.id, slug="legacy", name="Legacy",
        data={"default_slide_count": 7, "linked_styles": ["hook"], "spec_markdown": "# L"},
    )
    rec = fl.custom_record(row)
    assert rec["media"] == [] and rec["channels"] == []
    assert rec["spec_markdown"] == "# L"
    assert rec["overrides_builtin"] is False
