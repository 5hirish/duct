"""Which channels a project posts on, and what each is told (agents/content/
channel_config.py, platform_guides.py, the /content/channels routes).

The crawl's list stands in until the person chooses; a chosen list wins and
rewrites the legacy list so older readers agree; a channel can be on with no
scheduler account behind it; the guide and the person's own words about a
channel ride into the opening turn together.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session

import routes.content as content_routes
import service.auth as auth_service
from agents.content.channel_config import ChannelConfig, ChannelProfile, active_platforms, load_channel_config, save_channel_config
from agents.content.channels import OFFERED, Platform, resolve
from agents.content.platform_guides import GUIDES, render_channel_guides
from agents.content.prompts import _brand_stanza
from agents.content.schema import ContentBrandContext
from db.session import get_session as get_session_dep
from models.auth import User
from models.membership import ProjectMember
from models.project import Project
from service.membership import ROLE_OWNER
from tests.conftest import make_sqlite_engine
from tests.fakes import ZernioQueue, connect_scheduler


def test_the_crawls_channels_stand_in_until_the_person_chooses():
    config = load_channel_config({"active_channels": ["tiktok", "x", "pinterest"]})
    assert config.chosen is False
    # X is spelled the way posts spell it; Pinterest is not offered, so it is not planned for.
    assert config.enabled() == ["tiktok", "twitter"]


def test_a_chosen_list_wins_and_rewrites_the_legacy_one():
    blob = {"active_channels": ["tiktok"], "brand_voice": "warm"}
    config = ChannelConfig(
        primary_publisher="zernio",
        channels={
            "blog": ChannelProfile(enabled=True, notes="Hugo site, publish by hand", target_media=["article"]),
            "instagram": ChannelProfile(enabled=True, username="@glowupdaily"),
            "tiktok": ChannelProfile(enabled=False),
        },
        chosen=True,
    )
    saved = save_channel_config(blob, config)
    assert saved["brand_voice"] == "warm"                    # everything else kept
    assert saved["active_channels"] == ["instagram", "blog"]  # offered order, legacy readers agree
    again = load_channel_config(saved)
    assert again.chosen and again.enabled() == ["instagram", "blog"]
    assert again.channels["instagram"].username == "glowupdaily"  # the @ is not part of a handle
    assert active_platforms(saved) == ["instagram", "blog"]


def test_every_offered_channel_has_rules_and_a_guide():
    for cid in OFFERED:
        assert cid in GUIDES, cid
        assert resolve(cid).label
    # An article is written as text whatever playbook stands in for it.
    assert resolve(Platform.BLOG).text_first and resolve(Platform.BLOG).rules.long_form
    assert resolve(Platform.WORDPRESS).text_first


def test_the_guides_ride_into_the_brand_stanza_with_the_persons_words():
    brand = ContentBrandContext(
        project_id="00000000-0000-0000-0000-000000000001",
        project_name="Kestrel",
        active_channels=["instagram", "blog"],
        channel_profiles={"blog": {"enabled": True, "notes": "Hugo site, publish by hand", "target_media": ["article"]}},
    )
    stanza = _brand_stanza(brand)
    assert "<channel_guides" in stanza
    assert "Instagram (instagram)" in stanza and "Blog (blog)" in stanza
    assert "Hugo site, publish by hand" in stanza and "post only: article" in stanza
    # A draft for one channel gets that channel's guide and no other.
    one = _brand_stanza(brand, ["instagram"])
    assert "Instagram (instagram)" in one and "Blog (blog)" not in one
    assert render_channel_guides(["pinterest"]) == ""


# --- the routes -----------------------------------------------------------------

@pytest.fixture
def db():
    with Session(make_sqlite_engine()) as session:
        yield session


def _user(db, email) -> User:
    row = User(email=email)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _project(db, owner) -> Project:
    row = Project(user_id=owner.id, name="Kestrel", slug="kestrel", brand_channels={"active_channels": ["tiktok"]})
    db.add(row)
    db.commit()
    db.refresh(row)
    db.add(ProjectMember(project_id=row.id, user_id=owner.id, role=ROLE_OWNER))
    db.commit()
    return row


def _api(db, user) -> TestClient:
    app = FastAPI()
    app.include_router(content_routes.router, prefix="/api")
    app.dependency_overrides[get_session_dep] = lambda: db
    app.dependency_overrides[auth_service.get_current_user] = lambda: user
    return TestClient(app, raise_server_exceptions=False)


def test_the_tab_reads_every_offered_channel_and_saves_a_choice(db, monkeypatch):
    owner = _user(db, "owner@example.com")
    project = _project(db, owner)
    connect_scheduler(monkeypatch, db, owner.id, ZernioQueue().publisher, publisher_id="zernio")
    api = _api(db, owner)

    before = api.get(f"/api/content/channels?project_id={project.id}").json()
    assert before["chosen"] is False and before["primary_publisher"] == ""
    assert [c["id"] for c in before["channels"]] == list(OFFERED)
    by_id = {c["id"]: c for c in before["channels"]}
    assert by_id["tiktok"]["enabled"] is True            # the crawl found it
    assert by_id["blog"]["enabled"] is False and by_id["blog"]["long_form"] is True
    assert by_id["instagram"]["guide"]["limits"]         # the agent's rules, shown to the person

    res = api.put("/api/content/channels", json={
        "project_id": str(project.id),
        "primary_publisher": "zernio",
        "channels": {
            "tiktok": {"enabled": True, "username": "real_glowupdaily", "target_media": ["video", "slideshow"]},
            "blog": {"enabled": True, "notes": "publish by hand", "target_media": ["article"]},
        },
    })
    assert res.status_code == 200, res.text
    after = res.json()
    assert after["chosen"] is True and after["primary_publisher"] == "zernio"
    on = [c["id"] for c in after["channels"] if c["enabled"]]
    assert on == ["tiktok", "blog"]
    db.refresh(project)
    assert active_platforms(project.brand_channels) == ["tiktok", "blog"]


def test_the_primary_scheduler_has_to_be_connected_and_the_channel_offered(db):
    owner = _user(db, "owner2@example.com")
    project = _project(db, owner)
    api = _api(db, owner)
    body = {"project_id": str(project.id), "primary_publisher": "zernio", "channels": {}}
    assert api.put("/api/content/channels", json=body).status_code == 422
    body = {"project_id": str(project.id), "channels": {"pinterest": {"enabled": True}}}
    assert api.put("/api/content/channels", json=body).status_code == 422
    body = {"project_id": str(project.id), "channels": {"blog": {"enabled": True, "target_media": ["hologram"]}}}
    assert api.put("/api/content/channels", json=body).status_code == 422


def test_a_stranger_is_told_the_project_does_not_exist(db):
    owner = _user(db, "owner3@example.com")
    stranger = _user(db, "stranger@example.com")
    project = _project(db, owner)
    api = _api(db, stranger)
    assert api.get(f"/api/content/channels?project_id={project.id}").status_code == 404
    body = {"project_id": str(project.id), "channels": {"blog": {"enabled": True}}}
    assert api.put("/api/content/channels", json=body).status_code == 404


# --- which schedulers analytics reads --------------------------------------------

def test_analytics_asks_the_schedulers_the_project_uses():
    from routes.content import LinkedAccountOut, _analytics_schedulers
    from service.publishers.registry import spec_for

    zernio, bridge = spec_for("zernio"), spec_for("post_bridge")
    both = [bridge, zernio]
    link = LinkedAccountOut(account_id="acc_li", publisher="zernio", platform="linkedin", username="k")
    # Linked accounts decide; a stale key at the other scheduler is never asked.
    assert _analytics_schedulers(both, [link], "") == [zernio]
    # Nothing linked: the primary one, then everything.
    assert _analytics_schedulers(both, [], "zernio") == [zernio]
    assert _analytics_schedulers(both, [], "") == both
    # A primary that is no longer connected falls back to all, not to nothing.
    assert _analytics_schedulers([bridge], [], "zernio") == [bridge]


def test_a_linked_account_switches_its_channel_on_and_lends_its_handle():
    # Before anyone chose: the crawl found TikTok, Zernio holds a LinkedIn
    # account. LinkedIn is on and its handle is the account's.
    config = load_channel_config({"active_channels": ["tiktok"]}, [("linkedin", "@kestrel")])
    assert config.enabled() == ["tiktok", "linkedin"]
    assert config.channels["linkedin"].username == "kestrel"
    # Once chosen, a linked account does not switch a channel the person
    # turned off back on, but still lends its handle to an empty field.
    saved = save_channel_config({}, ChannelConfig(channels={"linkedin": ChannelProfile(enabled=False)}, chosen=True))
    again = load_channel_config(saved, [("linkedin", "kestrel")])
    assert again.enabled() == [] and again.channels["linkedin"].username == "kestrel"
