"""The operator profile: one row, one voice, read by every agent that writes.

What these cover is the two ways a profile is worth having at all: it reaches a
run nobody is watching (the scheduled brief has no browser to send preferences
from), and it says something the model can act on rather than restating Duct's
defaults as if the person had chosen them.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session

import routes.profile as profile_routes
import service.auth as auth_service
import service.profile as profile_service
from db.session import get_session as get_session_dep
from models.auth import User
from tests.conftest import make_sqlite_engine

from agents.core.voice import VOICE_GUIDANCE, user_context_block
from agents.preferences import UserPreferences
from service.profile import (
    DEFAULTS,
    NOTES_MAX_CHARS,
    Profile,
    WRITING_PRESETS,
    _clean_preset,
    _clean_text,
    resolve,
)


class TestPreset:
    def test_one_control_still_answers_the_two_older_fields(self):
        """The page asks once; the prompts that read style and depth are unchanged."""
        assert Profile(writing_preset="executive").communication_style == "executive"
        assert Profile(writing_preset="executive").report_depth == "summary"
        assert Profile(writing_preset="technical").report_depth == "detailed"

    def test_an_unknown_preset_reads_as_the_default_rather_than_breaking(self):
        """A preset from a newer client must not make this one raise."""
        assert Profile(writing_preset="oracular").communication_style == "practitioner"
        assert _clean_preset("ORACULAR") == "practitioner"

    def test_every_preset_maps_to_a_real_style_and_depth(self):
        """The pair lands in UserPreferences, whose Literals are the real contract."""
        fields = UserPreferences.model_fields
        styles = fields["communication_style"].annotation.__args__
        depths = fields["report_depth"].annotation.__args__
        for style, depth in WRITING_PRESETS.values():
            assert style in styles
            assert depth in depths


class TestNotesAreCapped:
    def test_the_free_text_cannot_grow_without_limit(self):
        """It rides in every prompt this account ever runs."""
        assert len(_clean_text("x" * 5000, limit=NOTES_MAX_CHARS)) == NOTES_MAX_CHARS


class TestResolve:
    def test_no_row_and_no_payload_is_the_shipped_default(self):
        assert resolve(None, None) == DEFAULTS

    def test_a_signed_out_run_keeps_the_voice_picked_in_the_browser(self):
        """No row to read, so the request payload is the only thing there is."""
        prefs = UserPreferences(
            role="Growth Manager", communication_style="executive", report_depth="summary"
        )
        got = resolve(None, prefs)
        assert got.writing_preset == "executive"
        assert got.role == "Growth Manager"

    def test_a_payload_pair_no_preset_matches_still_resolves_to_its_style(self):
        """Executive tone with full evidence is a legitimate older setting."""
        prefs = UserPreferences(communication_style="executive", report_depth="detailed")
        assert resolve(None, prefs).writing_preset == "executive"


class TestUserContextBlock:
    def test_an_untouched_profile_renders_nothing(self):
        """"They asked for practitioner" and "nobody said" are different instructions."""
        assert user_context_block(DEFAULTS) == ""

    def test_the_block_carries_name_voice_language_and_notes(self):
        block = user_context_block(
            Profile(
                display_name="Shirish",
                role="Product Manager",
                writing_preset="executive",
                communication_language="Spanish",
                notes="Give me the number first, then the why.",
            )
        )
        assert "<user_context>" in block
        assert "Shirish" in block
        assert "Product Manager" in block
        assert VOICE_GUIDANCE["executive"] in block
        assert "Spanish" in block
        assert "Give me the number first" in block

    def test_the_default_language_asks_for_nothing(self):
        """Empty means "match the language they wrote in", which a model does anyway."""
        block = user_context_block(Profile(display_name="Shirish"))
        assert "Write in" not in block

    def test_the_operators_own_words_come_last(self):
        """The notes outrank the preset, so a model reading in order meets them last."""
        block = user_context_block(
            Profile(writing_preset="executive", notes="Always show the full evidence.")
        )
        assert block.index(VOICE_GUIDANCE["executive"]) < block.index("Always show the full")


@pytest.mark.parametrize("preset", sorted(WRITING_PRESETS))
def test_every_preset_has_guidance_prose(preset):
    """A preset the page offers with no guidance behind it changes nothing."""
    assert VOICE_GUIDANCE[preset].strip()


# ---------------------------------------------------------------------------
# The round trip. The point of the table is that a run nobody is watching can
# read what somebody set, so these go through the route and the database.
# ---------------------------------------------------------------------------


@pytest.fixture
def engine(monkeypatch):
    """In-memory DB, wired into `service/profile`'s own `db_session()` calls.

    The service opens its session rather than taking one as a dependency, so
    the module attribute is the seam. A fresh Session per call is fine:
    StaticPool means they share the one in-memory connection, and each call
    closing its own session is exactly what the service does in production.
    """
    eng = make_sqlite_engine()

    def _fake_db():
        yield Session(eng)

    monkeypatch.setattr(profile_service, "db_session", _fake_db)
    return eng


@pytest.fixture
def db(engine):
    with Session(engine) as session:
        yield session


@pytest.fixture
def user(db):
    row = User(email="profile-owner@example.com", name="Owner")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def client(db, user=None):
    app = FastAPI()
    app.include_router(profile_routes.router, prefix="/api/user/profile")
    app.dependency_overrides[get_session_dep] = lambda: db
    if user is not None:
        app.dependency_overrides[auth_service.get_current_user] = lambda: user
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def api(db, user):
    return client(db, user)


class TestRoundTrip:
    def test_an_account_that_never_opened_the_page_reads_as_the_defaults(self, api):
        body = api.get("/api/user/profile").json()
        assert body["writing_preset"] == "practitioner"
        assert body["display_name"] == ""
        assert body["communication_language"] == ""

    def test_what_was_saved_on_one_device_is_what_the_next_run_reads(self, api):
        api.put("/api/user/profile", json={"display_name": "Shirish", "writing_preset": "executive"})
        body = api.get("/api/user/profile").json()
        assert body["display_name"] == "Shirish"
        assert body["writing_preset"] == "executive"
        # The pair older prompts read travels with it, derived not stored twice.
        assert body["communication_style"] == "executive"
        assert body["report_depth"] == "summary"

    def test_a_partial_write_leaves_the_other_controls_alone(self, api):
        """The page saves each control as it is touched."""
        api.put("/api/user/profile", json={"display_name": "Shirish", "notes": "Numbers first."})
        api.put("/api/user/profile", json={"writing_preset": "technical"})
        body = api.get("/api/user/profile").json()
        assert body["display_name"] == "Shirish"
        assert body["notes"] == "Numbers first."
        assert body["writing_preset"] == "technical"

    def test_notes_are_capped_at_the_write(self, api):
        api.put("/api/user/profile", json={"notes": "x" * 4000})
        assert len(api.get("/api/user/profile").json()["notes"]) == NOTES_MAX_CHARS

    def test_the_endpoint_is_the_user(self, db):
        """No path here takes a user id from the request."""
        assert client(db).get("/api/user/profile").status_code in (401, 403)
