"""The pillars Content Studio plans from (``agents/content/pillars.py``).

The audit's crawl and an outside agent's draft write the project profile's
pillar names; the Brand tab writes the Studio's own list. Every reader goes
through ``pillars_of``, so a project set up from Claude Code plans with the
pillars its profile shows.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session

import routes.content as content_routes
import service.auth as auth_service
from agents.content.pillars import pillars_of
from db.session import get_session as get_session_dep
from models.auth import User
from models.membership import ProjectMember
from models.project import Project
from service.membership import ROLE_OWNER
from service.project_draft import PROVENANCE_DOCUMENT, PROVENANCE_USER
from tests.conftest import make_sqlite_engine


def _project(**kwargs) -> Project:
    return Project(name="Acme", **kwargs)


def test_the_profiles_names_stand_in_while_the_studio_has_none():
    project = _project(
        content_pillars={"items": [{"id": "", "name": " ", "description": ""}]},
        brand_channels={"content_pillars": ["Build in public", "build-in-public", "", "Pricing teardowns"]},
    )
    assert pillars_of(project) == [
        {"id": "build_in_public", "name": "Build in public", "description": ""},
        {"id": "pricing_teardowns", "name": "Pricing teardowns", "description": ""},
    ]


def test_the_studios_own_pillars_win_once_it_names_one():
    own = [{"id": "launches", "name": "Launches", "description": "What shipped this week."}]
    project = _project(content_pillars={"items": own}, brand_channels={"content_pillars": ["Ignored"]})
    assert pillars_of(project) == own


def test_no_pillars_anywhere_is_an_empty_list():
    assert pillars_of(_project()) == []


@pytest.fixture
def db():
    with Session(make_sqlite_engine()) as session:
        yield session


@pytest.fixture
def api_and_project(db):
    owner = User(email="writer@example.com")
    db.add(owner)
    db.commit()
    project = Project(
        user_id=owner.id, name="Duct", slug="duct",
        brand_channels={"content_pillars": ["Build in public"]},
        content_brand={"tone": "drafted", "do_say": "drafted"},
        provenance={"tone": PROVENANCE_DOCUMENT, "do_say": PROVENANCE_DOCUMENT},
    )
    db.add(project)
    db.commit()
    db.add(ProjectMember(project_id=project.id, user_id=owner.id, role=ROLE_OWNER))
    db.commit()
    app = FastAPI()
    app.include_router(content_routes.router, prefix="/api")
    app.dependency_overrides[get_session_dep] = lambda: db
    app.dependency_overrides[auth_service.get_current_user] = lambda: owner
    return TestClient(app, raise_server_exceptions=False), project


def test_the_brand_tab_shows_the_profiles_pillars_and_a_save_claims_what_changed(db, api_and_project):
    api, project = api_and_project
    url = f"/api/content/brand?project_id={project.id}"

    shown = api.get(url).json()
    assert [p["name"] for p in shown["content_pillars"]["items"]] == ["Build in public"]

    saved = api.put(url, json={
        "content_brand": {"tone": "what I typed", "do_say": "drafted"},
        "content_pillars": shown["content_pillars"],
    })
    assert saved.status_code == 200, saved.text
    db.refresh(project)
    assert project.provenance == {"tone": PROVENANCE_USER, "do_say": PROVENANCE_DOCUMENT}
    assert project.content_pillars["items"][0]["id"] == "build_in_public"
