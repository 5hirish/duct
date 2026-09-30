"""Whose PostBridge and Apify account a request spends.

Both used to fall back to the instance's env key for every user, and nothing
let a user save a key of their own. On a hosted instance those keys are the
operator's: anyone who signed up and made a project could list the social
accounts connected to the PostBridge one and publish to them, and every
Discover search ran on the Apify one. The fallback now follows
``allow_server_provider_keys()`` like every other key this server holds
(service/vendor_keys.py), and each user saves their own.

Also pinned: a vendor's 401 is about the vendor key, and the app signs the user
out of Duct on a 401, so one must never be relayed as one.
"""

from __future__ import annotations

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlmodel import Session

import config
import routes.content as content_routes
import service.auth as auth_service
import service.credentials as credentials_service
import service.vendor_keys as vendor_keys
from config import Configs
from db.session import get_session as get_session_dep
from models.auth import User
from models.connector import ConnectorCredential
from models.membership import ROLE_COLLABORATOR, ROLE_OWNER, ProjectMember
from models.project import Project
from service.apify import APIFY_KEY, ApifyAPIError, ApifyClient
from service.post_bridge import (
    POSTBRIDGE_KEY,
    PostBridgeAPIError,
    PostBridgeClient,
    PostBridgeError,
    PostBridgeSocialAccount,
    client_for_user,
)
from service.vendor_keys import VendorNotConnected
from tests.conftest import make_sqlite_engine

OPERATOR_KEY = "operator-owned-key"
GOOD_KEY = "users-own-key"
VENDORS = {"post-bridge": POSTBRIDGE_KEY, "apify": APIFY_KEY}


@pytest.fixture
def db():
    # A collaborator beside the owner needs the owner-only index as Postgres has it.
    with Session(make_sqlite_engine(drop_partial_indexes=True)) as session:
        yield session


def _settings(monkeypatch, *, app_env: str) -> None:
    cfg = Configs(
        app_env=app_env,
        postbridge_api_key=OPERATOR_KEY,
        apify_api_key=OPERATOR_KEY,
        credentials_encryption_key=Fernet.generate_key().decode(),
    )
    for module in (config, vendor_keys, credentials_service):
        monkeypatch.setattr(module, "get_configs", lambda: cfg)


@pytest.fixture
def hosted(monkeypatch):
    _settings(monkeypatch, app_env="production")


@pytest.fixture
def local(monkeypatch):
    _settings(monkeypatch, app_env="local")


@pytest.fixture
def vendors(monkeypatch):
    """Both vendors know one key; anything else is refused the way each refuses."""
    async def list_social_accounts(self, **_kw):
        if self._api_key != GOOD_KEY:
            raise PostBridgeAPIError(PostBridgeError(message="Unauthorized"), status_code=401, url="/v1/social-accounts")
        return [PostBridgeSocialAccount(id=7, platform="twitter", username="duct")]

    async def apify_request(self, method, path, **_kw):
        if self._api_key != GOOD_KEY:
            raise ApifyAPIError(401, path, "User was not found or authentication token is not valid")
        return httpx.Response(201, json={"data": {"id": "run1", "status": "READY", "defaultDatasetId": "ds1"}})

    monkeypatch.setattr(PostBridgeClient, "list_social_accounts", list_social_accounts)
    monkeypatch.setattr(ApifyClient, "_request", apify_request)


def _user(db, email):
    row = User(email=email)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _project(db, owner, *collaborators):
    row = Project(user_id=owner.id, name="Brand")
    db.add(row)
    db.commit()
    db.refresh(row)
    db.add(ProjectMember(project_id=row.id, user_id=owner.id, role=ROLE_OWNER))
    for c in collaborators:
        db.add(ProjectMember(project_id=row.id, user_id=c.id, role=ROLE_COLLABORATOR))
    db.commit()
    return row


def _client(db, user):
    app = FastAPI()
    app.include_router(content_routes.router, prefix="/api")
    app.dependency_overrides[get_session_dep] = lambda: db
    app.dependency_overrides[auth_service.get_current_user] = lambda: user
    return TestClient(app, raise_server_exceptions=False)


def _discover(api, project):
    return api.post("/api/content/discover/start", json={
        "project_id": str(project.id),
        "actor_id": "clockworks/tiktok-scraper",
        "input_payload": {"hashtags": ["faceshape"], "resultsPerPage": 30},
    })


def test_a_hosted_signup_cannot_spend_the_operators_keys(db, hosted, vendors):
    stranger = _user(db, "stranger@example.com")
    project = _project(db, stranger)
    api = _client(db, stranger)

    with pytest.raises(VendorNotConnected):
        client_for_user(stranger.id, db)
    for vendor in VENDORS:
        assert api.get(f"/api/content/vendor-keys/{vendor}?project_id={project.id}").json()["connected"] is False
    listed = api.get(f"/api/content/social-accounts?project_id={project.id}")
    assert listed.status_code == 400 and "Content → Accounts" in listed.json()["detail"]
    searched = _discover(api, project)
    assert searched.status_code == 400 and "Content → Discover" in searched.json()["detail"]


def test_local_dev_still_runs_on_the_env_keys(db, local):
    me = _user(db, "me@example.com")
    project = _project(db, me)
    api = _client(db, me)

    assert client_for_user(me.id, db)._api_key == OPERATOR_KEY
    for vendor in VENDORS:
        status = api.get(f"/api/content/vendor-keys/{vendor}?project_id={project.id}").json()
        assert status == {"connected": True, "own_key": False, "is_owner": True}


@pytest.mark.parametrize("vendor", sorted(VENDORS))
def test_a_key_is_kept_only_once_the_vendor_accepts_it(db, hosted, vendors, vendor):
    me = _user(db, "me@example.com")
    project = _project(db, me)
    api = _client(db, me)
    url = f"/api/content/vendor-keys/{vendor}"

    refused = api.put(url, json={"api_key": "not-a-real-key"})
    assert refused.status_code == 422
    assert "didn't accept" in refused.json()["detail"]  # a sentence, never a validation list
    assert api.put(url, json={"api_key": "   "}).json()["detail"].startswith("Paste")
    assert db.execute(select(ConnectorCredential)).first() is None

    assert api.put(url, json={"api_key": GOOD_KEY}).status_code == 200
    row = db.execute(select(ConnectorCredential)).scalars().one()
    assert GOOD_KEY not in row.credentials_enc  # stored encrypted
    assert VENDORS[vendor].resolve(me.id, db) == GOOD_KEY
    status = api.get(f"{url}?project_id={project.id}").json()
    assert status == {"connected": True, "own_key": True, "is_owner": True}

    assert api.delete(url).status_code == 204
    assert api.get(f"{url}?project_id={project.id}").json()["connected"] is False


def test_a_saved_apify_key_runs_the_search(db, hosted, vendors):
    me = _user(db, "me@example.com")
    project = _project(db, me)
    api = _client(db, me)
    assert api.put("/api/content/vendor-keys/apify", json={"api_key": GOOD_KEY}).status_code == 200

    assert _discover(api, project).status_code == 200


def test_a_project_spends_its_owners_key_not_a_collaborators(db, hosted, vendors):
    owner = _user(db, "owner@example.com")
    helper = _user(db, "helper@example.com")
    project = _project(db, owner, helper)
    api = _client(db, helper)

    for vendor in VENDORS:
        assert api.put(f"/api/content/vendor-keys/{vendor}", json={"api_key": GOOD_KEY}).status_code == 200
        status = api.get(f"/api/content/vendor-keys/{vendor}?project_id={project.id}").json()
        assert status == {"connected": False, "own_key": False, "is_owner": False}
    assert api.get(f"/api/content/social-accounts?project_id={project.id}").status_code == 400
    assert _discover(api, project).status_code == 400


def test_a_key_the_vendor_stops_accepting_never_signs_the_user_out(db, hosted, vendors):
    me = _user(db, "me@example.com")
    project = _project(db, me)
    for key in VENDORS.values():
        key.save(me.id, "revoked-since", db)
    db.commit()
    api = _client(db, me)

    listed = api.get(f"/api/content/social-accounts?project_id={project.id}")
    assert listed.status_code == 502 and "Content → Accounts" in listed.json()["detail"]
    searched = _discover(api, project)
    assert searched.status_code == 502 and "Content → Discover" in searched.json()["detail"]


def test_an_unknown_vendor_is_not_a_route(db, hosted):
    me = _user(db, "me@example.com")
    project = _project(db, me)
    assert _client(db, me).get(f"/api/content/vendor-keys/stripe?project_id={project.id}").status_code == 404
