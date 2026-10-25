"""Where a project's fields came from, kept on the server, and what may overwrite what.

Two writers, two rule sets (``service/project_draft.py``): a draft is a machine
and lands only where the three rules allow; a save is the person and wins
where they changed something, but cannot use an older copy of a draft to undo
a newer one. The route tests at the bottom hold the case the server-side
labels exist for: a draft written on the server survives the next save from
a device that never saw it.

Offline, on SQLite.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session

from db.session import get_session
from models.auth import User
from models.project import Project
from routes import user_projects
from service.auth import get_current_user
from service.membership import ensure_owner_membership
from service.project_draft import (
    FIELDS,
    PROVENANCE_CRAWL,
    PROVENANCE_DOCUMENT,
    PROVENANCE_INFERRED,
    PROVENANCE_USER,
    RANK,
    UNTITLED_PROJECT,
    merge_draft,
    reconcile_save,
    snapshot,
)
from tests.conftest import make_sqlite_engine


def _draft(**fields: tuple[object, str]) -> dict:
    return {name: {"value": value, "provenance": source} for name, (value, source) in fields.items()}


def _project(**kwargs) -> Project:
    return Project(name=kwargs.pop("name", UNTITLED_PROJECT), **kwargs)


# ---------------------------------------------------------------------------
# A draft: the three rules
# ---------------------------------------------------------------------------

def test_a_draft_lands_each_field_where_it_lives_and_labels_it():
    project = _project()
    landed = merge_draft(project, _draft(
        name=("Acme", PROVENANCE_CRAWL),
        website_url=("https://acme.example", PROVENANCE_CRAWL),
        personas=([{"name": "Working parent"}], PROVENANCE_INFERRED),
        brand_voice=("Friendly", PROVENANCE_INFERRED),
        favicon=("https://acme.example/favicon.ico", PROVENANCE_CRAWL),
        pitch=("", PROVENANCE_CRAWL),
    ))
    assert project.name == "Acme", "the placeholder name is not content"
    assert project.url == "https://acme.example"
    assert project.audience["personas"] == [{"name": "Working parent"}]
    assert project.brand_channels == {"brand_voice": "Friendly"}
    assert project.provenance == {
        "name": PROVENANCE_CRAWL, "website_url": PROVENANCE_CRAWL,
        "personas": PROVENANCE_INFERRED, "brand_voice": PROVENANCE_INFERRED,
    }, "the favicon stays on the device, and an empty value is not written"
    assert sorted(landed) == sorted(project.provenance)


def test_a_draft_never_overwrites_the_person():
    typed = _project(pitch="What I typed", provenance={"pitch": PROVENANCE_USER})
    legacy = _project(pitch="Typed before drafts existed")
    for project in (typed, legacy):
        merge_draft(project, _draft(pitch=("A homepage line", PROVENANCE_CRAWL)))
    assert typed.pitch == "What I typed"
    assert legacy.pitch == "Typed before drafts existed", "a filled field with no label is the person's"
    assert "pitch" not in legacy.provenance


def test_the_site_beats_the_files_and_both_beat_a_guess():
    project = _project()
    merge_draft(project, _draft(pitch=("From the site", PROVENANCE_CRAWL), industry=("SaaS & Software", PROVENANCE_INFERRED)))
    merge_draft(project, _draft(pitch=("From the deck", PROVENANCE_DOCUMENT), industry=("Fintech", PROVENANCE_DOCUMENT)))
    assert project.pitch == "From the site"
    assert project.industry == "Fintech"
    merge_draft(project, _draft(pitch=("The full crawl's line", PROVENANCE_CRAWL)))
    assert project.pitch == "The full crawl's line", "an equal source refreshes its own value"


def test_the_settings_pages_empty_persona_row_is_not_a_persona():
    project = _project(audience={"personas": [{"name": "", "description": "", "priority": "primary"}]})
    merge_draft(project, _draft(personas=([{"name": "Working parent"}], PROVENANCE_INFERRED)))
    assert project.audience["personas"] == [{"name": "Working parent"}]


def test_a_draft_cannot_claim_to_be_the_person():
    with pytest.raises(ValueError):
        merge_draft(_project(), _draft(pitch=("Mine now", PROVENANCE_USER)))


# ---------------------------------------------------------------------------
# A save: the person wins, an older copy of a draft does not
# ---------------------------------------------------------------------------

def _save(project: Project, labels: dict | None, **changes) -> None:
    """Write ``changes`` the way the PUT does, then settle it."""
    before, before_labels = snapshot(project), dict(project.provenance or {})
    for column, value in changes.items():
        setattr(project, column, value)
    reconcile_save(project, before, before_labels, labels)


def _drafted() -> Project:
    project = _project()
    merge_draft(project, _draft(pitch=("The newer crawl", PROVENANCE_CRAWL), industry=("Fintech", PROVENANCE_DOCUMENT)))
    return project


def test_an_older_copy_of_a_draft_cannot_undo_the_newer_one():
    project = _drafted()
    _save(project, {"pitch": PROVENANCE_CRAWL, "industry": PROVENANCE_DOCUMENT}, pitch="The older crawl", industry="")
    assert project.pitch == "The newer crawl"
    assert project.industry == "Fintech", "carrying a field along never blanks it"
    assert project.provenance == {"pitch": PROVENANCE_CRAWL, "industry": PROVENANCE_DOCUMENT}


def test_what_the_person_changed_wins_and_becomes_theirs():
    project = _drafted()
    _save(project, {"pitch": PROVENANCE_USER, "industry": PROVENANCE_USER}, pitch="My own words", industry="")
    assert (project.pitch, project.industry) == ("My own words", "")
    assert project.provenance == {"pitch": PROVENANCE_USER, "industry": PROVENANCE_USER}
    # A value that never came from a draft is one the person typed.
    _save(project, {}, company_name="Acme Foods")
    assert project.provenance["company_name"] == PROVENANCE_USER


def test_a_carried_draft_may_fill_a_blank_or_beat_a_lower_source():
    project = _drafted()
    _save(project, {"industry": PROVENANCE_CRAWL, "business_model": PROVENANCE_INFERRED},
          industry="Retail", business_model="Subscription")
    assert project.industry == "Retail"
    assert project.business_model == "Subscription"
    assert project.provenance["industry"] == PROVENANCE_CRAWL
    assert project.provenance["business_model"] == PROVENANCE_INFERRED


def test_confirming_a_chip_and_labels_drafted_before_the_server_kept_them():
    project = _project(pitch="From the site", industry="Fintech", provenance={"pitch": PROVENANCE_CRAWL})
    _save(project, {"pitch": PROVENANCE_USER, "industry": PROVENANCE_INFERRED})
    assert project.provenance == {"pitch": PROVENANCE_USER, "industry": PROVENANCE_INFERRED}


def test_a_client_that_sends_no_labels_saves_as_every_save_did():
    project = _drafted()
    _save(project, None, pitch="Whatever this tab had", industry="")
    assert (project.pitch, project.industry) == ("Whatever this tab had", "")
    assert project.provenance == {}, "what it changed is the person's, which is no label"


# ---------------------------------------------------------------------------
# The routes
# ---------------------------------------------------------------------------

class _Api:
    def __init__(self, session: Session, client: TestClient):
        self.session, self.client = session, client
        self.user: User | None = None


@pytest.fixture
def api():
    engine = make_sqlite_engine(drop_partial_indexes=True)
    session = Session(engine)
    app = FastAPI()
    app.include_router(user_projects.router, prefix="/api/user/projects")
    state = _Api(session, TestClient(app, raise_server_exceptions=False))

    def _session():
        yield session

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_current_user] = lambda: state.user
    yield state
    session.close()
    engine.dispose()


def _user(session: Session, email: str) -> User:
    user = User(email=email, full_name=email.split("@")[0])
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _body(**overrides) -> dict:
    return {"name": "Acme", "company_name": "", "pitch": "", "industry": "", "business_model": "",
            "website_url": "", "targets": {}, "audience": {}, "competition": {}, "brand_channels": {}, **overrides}


def test_a_draft_for_a_new_id_creates_the_project_and_keeps_the_labels(api):
    import uuid

    api.user = _user(api.session, "ana@acme.example")
    project_id = uuid.uuid4()
    res = api.client.post(f"/api/user/projects/{project_id}/draft", json={"fields": _draft(
        name=("Acme", PROVENANCE_CRAWL), pitch=("Dinners, planned.", PROVENANCE_CRAWL),
    )})
    assert res.status_code == 200, res.text
    out = res.json()
    assert (out["name"], out["pitch"], out["role"]) == ("Acme", "Dinners, planned.", "owner")
    assert out["provenance"] == {"name": PROVENANCE_CRAWL, "pitch": PROVENANCE_CRAWL}
    assert api.session.get(Project, project_id).slug == "acme"
    listed = api.client.get("/api/user/projects").json()
    assert listed[0]["provenance"] == out["provenance"], "a second device reads the same labels"


def test_a_server_draft_survives_a_save_from_a_device_that_never_saw_it(api):
    """The case the server-side labels exist for."""
    import uuid

    api.user = _user(api.session, "ana@acme.example")
    project_id = uuid.uuid4()
    api.client.put(f"/api/user/projects/{project_id}", json=_body(
        pitch="The first crawl", provenance={"pitch": PROVENANCE_CRAWL},
    ))
    api.client.post(f"/api/user/projects/{project_id}/draft", json={"fields": _draft(
        pitch=("The newer crawl", PROVENANCE_CRAWL), industry=("Fintech", PROVENANCE_DOCUMENT),
    )})
    # The laptop still holds the first crawl, and the person changed only the targets.
    res = api.client.put(f"/api/user/projects/{project_id}", json=_body(
        pitch="The first crawl", targets={"target_cpa": "45"}, provenance={"pitch": PROVENANCE_CRAWL},
    ))
    out = res.json()
    assert out["pitch"] == "The newer crawl"
    assert out["industry"] == "Fintech"
    assert out["targets"] == {"target_cpa": "45"}
    assert out["provenance"] == {
        "name": PROVENANCE_USER, "pitch": PROVENANCE_CRAWL, "industry": PROVENANCE_DOCUMENT,
    }, "the name came with no draft label, so the person gave it"


def test_a_label_the_server_does_not_know_never_fails_a_save(api):
    import uuid

    api.user = _user(api.session, "ana@acme.example")
    res = api.client.put(f"/api/user/projects/{uuid.uuid4()}", json=_body(
        pitch="Typed", provenance={"pitch": None, "favicon": PROVENANCE_CRAWL, "industry": {"odd": 1}},
    ))
    assert res.status_code == 200, res.text
    assert res.json()["provenance"] == {"name": PROVENANCE_USER, "pitch": PROVENANCE_USER}


def test_a_draft_reaches_only_a_project_the_caller_belongs_to(api):
    owner = _user(api.session, "ana@acme.example")
    project = Project(user_id=owner.id, name="Acme", slug="acme")
    api.session.add(project)
    api.session.flush()
    ensure_owner_membership(project, api.session)
    api.session.commit()

    api.user = _user(api.session, "mallory@elsewhere.example")
    res = api.client.post(f"/api/user/projects/{project.id}/draft", json={"fields": _draft(pitch=("Mine", PROVENANCE_CRAWL))})
    assert res.status_code == 404, "a non-member cannot tell the project exists"
    api.session.refresh(project)
    assert project.pitch == ""


@pytest.mark.parametrize("field", [
    {"pitch": {"value": "Mine now", "provenance": PROVENANCE_USER}},
    {"pitch": {"value": "Mine now", "provenance": "rumour"}},
    {"personas": {"value": "not a list", "provenance": PROVENANCE_INFERRED}},
])
def test_a_draft_that_claims_too_much_is_refused(api, field):
    import uuid

    api.user = _user(api.session, "ana@acme.example")
    res = api.client.post(f"/api/user/projects/{uuid.uuid4()}/draft", json={"fields": field})
    assert res.status_code == 422


# ---------------------------------------------------------------------------
# The browser runs the same rules for an instant answer
# ---------------------------------------------------------------------------

def test_the_app_ranks_and_names_the_fields_the_way_the_server_does():
    source = (Path(__file__).resolve().parents[2] / "app/src/lib/projectDraft.js").read_text()
    constants = dict(re.findall(r'export const (PROVENANCE_[A-Z]+) = "([a-z]+)";', source))
    ranks = dict(re.findall(r"\[(PROVENANCE_[A-Z]+)\]: (\d)", source))
    assert {constants[name]: int(rank) for name, rank in ranks.items()} == RANK
    paths = source.split("const FIELD_PATHS = Object.freeze({")[1].split("});")[0]
    assert set(re.findall(r"^\s+([a-z_]+):", paths, re.M)) == set(FIELDS) | {"favicon"}
