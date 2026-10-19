"""Connecting an MCP server, through the routes, end to end.

The property everything else rests on is the GitHub App's (``test_github_app``):
the callback is a URL anyone can be sent to, so what it produced is stored
only by the signed-in user who started the connect. The rest is the flow that
property assumes: discovery's three outcomes, the key path, the desktop way
home, and rows that are the owner's alone.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlmodel import Session

import routes.mcp_servers as mcp_routes
import service.auth as auth_service
import service.credentials as credentials_service
from config import Configs
from db.session import get_session as get_session_dep
from models.auth import User
from models.connector import ConnectorCredential
from service.mcp import oauth
from service.mcp.client import CODE_REAUTH, CODE_UNREACHABLE, McpCallError
from service.mcp.store import ACCESS_TOKEN, API_KEY, AUTH, MCP_CONNECTOR_TYPE
from tests.conftest import make_sqlite_engine

API = "https://api.duct.test"
APP = "https://app.duct.test"
SERVER = "https://mcp.vendor.test/mcp"

PLAN = oauth.AuthPlan(
    kind=oauth.AUTH_OAUTH,
    resource=SERVER,
    scope="read",
    issuer="https://auth.vendor.test",
    authorization_endpoint="https://auth.vendor.test/authorize",
    token_endpoint="https://auth.vendor.test/token",
    registration_endpoint="https://auth.vendor.test/register",
)


@pytest.fixture
def cfg(monkeypatch):
    config = Configs(
        api_public_url=API,
        frontend_origin=APP,
        credentials_encryption_key=Fernet.generate_key().decode(),
    )
    for module in (mcp_routes, oauth, credentials_service):
        monkeypatch.setattr(module, "get_configs", lambda: config)
    return config


@pytest.fixture
def db():
    with Session(make_sqlite_engine(drop_partial_indexes=True)) as session:
        yield session


def _user(db, email):
    user = User(email=email)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def alice(db):
    return _user(db, "alice@example.com")


@pytest.fixture
def mallory(db):
    return _user(db, "mallory@example.com")


@pytest.fixture
def vendor(monkeypatch):
    """The vendor's side, stubbed at the service seam: what discovery found,
    what the code exchanged for, and which credentials a probe accepted."""
    state = {"plan": PLAN, "probed": [], "refuse": False, "down": False}

    async def discover(url):
        if isinstance(state["plan"], Exception):
            raise state["plan"]
        return state["plan"]

    async def register(plan):
        return oauth.ClientRegistration(client_id="dcr-client")

    async def exchange_code(**kwargs):
        state["exchanged"] = kwargs
        return oauth.Tokens(access_token="at", refresh_token="rt", expires_at=None, scope="read")

    async def probe(access):
        state["probed"].append(access.credentials)
        if state["refuse"]:
            raise McpCallError(CODE_REAUTH, "refused")
        if state["down"]:
            raise McpCallError(CODE_UNREACHABLE, "did not answer")
        return 4

    monkeypatch.setattr(mcp_routes.oauth, "discover", discover)
    monkeypatch.setattr(mcp_routes.oauth, "register", register)
    monkeypatch.setattr(mcp_routes.oauth, "exchange_code", exchange_code)
    monkeypatch.setattr(mcp_routes.mcp_client, "probe", probe)
    return state


class _Browser:
    def __init__(self, db):
        app = FastAPI()
        app.include_router(mcp_routes.oauth_router)
        app.include_router(mcp_routes.router, prefix="/api/user/mcp")
        app.dependency_overrides[get_session_dep] = lambda: db
        app.dependency_overrides[auth_service.get_current_user] = lambda: self.user
        self.user = None
        self.http = TestClient(app, follow_redirects=False)

    def as_(self, user):
        self.user = user
        return self.http


@pytest.fixture
def browser(db, cfg):
    return _Browser(db)


def _query(location: str) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(urlparse(location).query).items()}


def _rows(db) -> list[ConnectorCredential]:
    return list(db.execute(select(ConnectorCredential)).scalars())


def _signed_in(browser, user, *, client: str = "") -> str:
    """Start a sign-in as ``user`` and come back from the vendor; returns the grant code."""
    started = browser.as_(user).post("/api/user/mcp/servers", json={"preset": "openseo", "client": client}).json()
    assert started["status"] == "authorize"
    state = _query(started["authorize_url"])["state"]
    back = browser.http.get(f"/auth/mcp/callback?code=the-code&state={state}")
    assert back.status_code == 307
    return back.headers["location"]


def test_a_sign_in_lands_in_the_account_that_started_it(browser, db, alice, vendor):
    location = _signed_in(browser, alice)
    assert location.startswith(f"{APP}/connections?")
    code = _query(location)["auth_code"]

    claimed = browser.as_(alice).post("/api/user/mcp/claim", json={"code": code})

    assert claimed.status_code == 200
    server = claimed.json()["server"]
    assert server["name"] == "OpenSEO" and server["auth"] == "oauth" and server["key"] == "openseo"
    (row,) = _rows(db)
    stored = credentials_service.decrypt_credentials(row.credentials_enc)
    assert row.user_id == alice.id and row.connector_type == MCP_CONNECTOR_TYPE
    assert stored[ACCESS_TOKEN] == "at" and stored["refresh_token"] == "rt"
    # The exchange went with the verifier and the resource the flow started with.
    assert vendor["exchanged"]["resource"] == SERVER and vendor["exchanged"]["verifier"]
    assert vendor["probed"][-1][ACCESS_TOKEN] == "at"


def test_someone_elses_sign_in_cannot_be_claimed_and_is_spent(browser, db, alice, mallory, vendor):
    code = _query(_signed_in(browser, alice))["auth_code"]

    assert browser.as_(mallory).post("/api/user/mcp/claim", json={"code": code}).status_code == 404
    # Spent by the wrong account's attempt: the right one cannot use it now either.
    assert browser.as_(alice).post("/api/user/mcp/claim", json={"code": code}).status_code == 404
    assert _rows(db) == []


def test_a_sign_in_is_kept_when_the_server_blips_on_the_first_listing(browser, db, alice, vendor):
    code = _query(_signed_in(browser, alice))["auth_code"]
    vendor["down"] = True

    claimed = browser.as_(alice).post("/api/user/mcp/claim", json={"code": code})

    assert claimed.status_code == 200
    (row,) = _rows(db)
    assert row.last_validated_at is None


def test_a_token_refused_straight_after_sign_in_is_not_kept(browser, db, alice, vendor):
    code = _query(_signed_in(browser, alice))["auth_code"]
    vendor["refuse"] = True

    assert browser.as_(alice).post("/api/user/mcp/claim", json={"code": code}).status_code == 422
    assert _rows(db) == []


def test_a_desktop_sign_in_goes_home_through_the_relay_page(browser, alice, vendor):
    location = _signed_in(browser, alice, client="desktop")
    assert location.startswith(f"{APP}/desktop-auth?")
    assert _query(location)["connector"] == "mcp"


@pytest.mark.parametrize("query, reason", [
    ("code=c&state=never-issued", "expired"),
    ("error=access_denied&state={state}", "consent"),
    ("code=c&state={state}&iss=https://evil.test", "exchange"),
])
def test_a_failed_return_names_the_failure_and_stores_nothing(browser, db, alice, vendor, query, reason):
    started = browser.as_(alice).post("/api/user/mcp/servers", json={"preset": "openseo"}).json()
    state = _query(started["authorize_url"])["state"]

    back = browser.http.get("/auth/mcp/callback?" + query.format(state=state))

    assert back.status_code == 307
    assert _query(back.headers["location"]) == {"connector": "mcp", "error": reason}
    assert _rows(db) == []


def test_a_state_is_single_use(browser, alice, vendor):
    started = browser.as_(alice).post("/api/user/mcp/servers", json={"preset": "openseo"}).json()
    state = _query(started["authorize_url"])["state"]
    browser.http.get(f"/auth/mcp/callback?code=c&state={state}")

    again = browser.http.get(f"/auth/mcp/callback?code=c&state={state}")
    assert _query(again.headers["location"])["error"] == "expired"


def test_a_pasted_key_is_proved_before_it_is_stored(browser, db, alice, vendor):
    saved = browser.as_(alice).post("/api/user/mcp/servers", json={"url": SERVER, "api_key": " k-1 "})

    assert saved.json()["status"] == "connected"
    assert saved.json()["server"]["auth"] == "key"
    (row,) = _rows(db)
    assert credentials_service.decrypt_credentials(row.credentials_enc) == {AUTH: "key", API_KEY: "k-1"}
    assert row.last_validated_at is not None


def test_a_refused_key_is_not_stored(browser, db, alice, vendor):
    vendor["refuse"] = True
    refused = browser.as_(alice).post("/api/user/mcp/servers", json={"url": SERVER, "api_key": "wrong"})
    assert refused.status_code == 422
    assert _rows(db) == []


def test_a_server_with_no_sign_in_duct_can_start_asks_for_a_key(browser, db, alice, vendor):
    vendor["plan"] = oauth.OAuthUnavailable("no registration")
    answer = browser.as_(alice).post("/api/user/mcp/servers", json={"preset": "posthog"})
    assert answer.json()["status"] == "needs_key"
    assert _rows(db) == []


def test_an_open_server_that_wants_credentials_for_its_tools_asks_for_a_key(browser, db, alice, vendor):
    vendor["plan"] = oauth.AuthPlan(kind=oauth.AUTH_NONE)
    vendor["refuse"] = True
    answer = browser.as_(alice).post("/api/user/mcp/servers", json={"url": SERVER})
    assert answer.json()["status"] == "needs_key"
    assert _rows(db) == []


def test_an_open_server_connects_without_a_sign_in(browser, db, alice, vendor):
    vendor["plan"] = oauth.AuthPlan(kind=oauth.AUTH_NONE)
    answer = browser.as_(alice).post("/api/user/mcp/servers", json={"url": SERVER, "name": "Docs"})
    assert answer.json()["status"] == "connected"
    assert answer.json()["server"]["auth"] == "none"
    assert answer.json()["server"]["name"] == "Docs"


@pytest.mark.parametrize("url", ["http://mcp.vendor.test/mcp", "https://localhost/mcp", "https://10.0.0.4/mcp"])
def test_an_unsafe_address_is_refused_before_anything_is_called(browser, alice, vendor, url):
    vendor["plan"] = AssertionError("discovery must not run")
    assert browser.as_(alice).post("/api/user/mcp/servers", json={"url": url}).status_code == 422


def test_servers_are_the_owners_alone(browser, db, alice, mallory, vendor):
    browser.as_(alice).post("/api/user/mcp/servers", json={"url": SERVER, "api_key": "k"})
    server_id = browser.as_(alice).get("/api/user/mcp/servers").json()["servers"][0]["id"]

    assert browser.as_(mallory).get("/api/user/mcp/servers").json() == {"servers": []}
    assert browser.as_(mallory).delete(f"/api/user/mcp/servers/{server_id}").status_code == 404
    assert len(_rows(db)) == 1
    assert browser.as_(alice).delete(f"/api/user/mcp/servers/{server_id}").status_code == 204
    assert _rows(db) == []


def test_no_secret_reaches_the_listing(browser, alice, vendor):
    browser.as_(alice).post("/api/user/mcp/servers", json={"url": SERVER, "api_key": "k-secret"})
    assert "k-secret" not in browser.as_(alice).get("/api/user/mcp/servers").text


def test_the_client_metadata_document_is_public_and_names_itself(browser):
    document = browser.http.get(oauth.CLIENT_METADATA_PATH)
    assert document.status_code == 200
    assert document.json()["client_id"] == f"{API}{oauth.CLIENT_METADATA_PATH}"
    assert document.json()["redirect_uris"] == [f"{API}{oauth.CALLBACK_PATH}"]
