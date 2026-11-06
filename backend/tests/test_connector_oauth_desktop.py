"""Connecting a Google source — `routes/auth.py` and the claim that ends it.

The connect used to hand the refresh token to the client: in a URL fragment
for a browser, behind a one-time code for the desktop shell. The page kept it
in that tab's session storage and synced it to the account if it could, so a
connection could live in one tab and nowhere else (issue #456). Now the token
goes from Google to the database and nowhere in between. What this file holds:

* no refresh token in any redirect, response body or listing;
* a connect needs a link naming the signed-in user, and the grant it produces
  is claimed by that user's session alone (the forged-link case);
* the browser and the desktop shell come home the same way, the desktop one in
  the deep-link shape released shells already route;
* a failure in the system browser lands on a page the user can read.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlmodel import Session

# Connectors register themselves on import; the routes resolve them by id.
import service.google.ads  # noqa: F401 — registers connector
import service.google.ga4  # noqa: F401
import service.google.gsc  # noqa: F401
import service.google.gtm  # noqa: F401
import routes.user_connectors as uc_routes
import service.auth as auth_service
import service.credentials as credentials_service
from db.session import get_session as get_session_dep
from models.auth import User
from models.connector import ConnectorCredential
from routes import auth
from service import auth_exchange, oauthstate
from service.credentials import decrypt_credentials, encrypt_credentials
from service.oauthstate import consume_state_full
from tests.conftest import make_sqlite_engine

APP_ORIGIN = "https://app.getduct.ai"
GA4_READ = "https://www.googleapis.com/auth/analytics.readonly"
SECRET = "super-secret-refresh-token"


class _Cfg:
    """Only the fields these paths read."""

    def __init__(self, *, duct_local: bool = False) -> None:
        self.duct_local = duct_local
        self.frontend_origin = APP_ORIGIN
        self.credentials_encryption_key = _KEY


_KEY = Fernet.generate_key().decode()


class _Credentials:
    def __init__(self, refresh_token: str) -> None:
        self.refresh_token = refresh_token


class _Session:
    """The oauth2 session, which is where the GRANTED scopes actually live.

    Not `flow.credentials.granted_scopes`: the installed google-auth-oauthlib
    does not populate that, so the token response is the only honest source.
    """

    def __init__(self, granted: tuple[str, ...]) -> None:
        self.token = {"scope": list(granted)}


class _Flow:
    """Stand-in for the google-auth Flow — the network is not what's under test."""

    def __init__(self, *, refresh_token: str = SECRET, granted: tuple[str, ...] = (GA4_READ,)) -> None:
        self.code_verifier = "verifier"
        self.credentials = _Credentials(refresh_token)
        self.oauth2session = _Session(granted)

    def authorization_url(self, **_):
        return "https://accounts.google.com/o/oauth2/auth?x=1", "state"

    def fetch_token(self, **_):
        return None


@pytest.fixture(autouse=True)
def stores(monkeypatch):
    """OAuth state on its in-memory path, and an empty code store per test."""
    monkeypatch.setattr("service.oauthstate.get_engine", lambda: None)
    monkeypatch.setattr("service.oauthstate._memory_states", {}, raising=False)
    monkeypatch.setattr(auth_exchange, "_store", {})


@pytest.fixture
def cfg(monkeypatch):
    def use(*, duct_local: bool = False) -> None:
        config = _Cfg(duct_local=duct_local)
        for module in (auth, credentials_service):
            monkeypatch.setattr(module, "get_configs", lambda: config)

    use()
    return use


@pytest.fixture
def google(monkeypatch):
    """Answer every Google flow with ``flow``; returns a setter."""
    def use(flow: _Flow) -> None:
        monkeypatch.setattr(auth, "create_google_oauth_flow", lambda **_: flow)

    use(_Flow())
    return use


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


class _Browser:
    """One app, with a switchable signed-in user; redirects are inspected, never followed."""

    def __init__(self, db):
        app = FastAPI()
        app.include_router(auth.router)
        app.include_router(uc_routes.router, prefix="/api/user/connectors")
        app.dependency_overrides[get_session_dep] = lambda: db
        app.dependency_overrides[auth_service.get_current_user] = lambda: self.user
        self.user = None
        self.http = TestClient(app, follow_redirects=False)

    def as_(self, user):
        self.user = user
        return self.http


def _query(location: str) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(urlparse(location).query).items()}


def _link(browser, user, connector="ga4") -> str:
    res = browser.as_(user).post("/api/user/connectors/connect-link", json={"connector_type": connector})
    assert res.status_code == 200, res.text
    return res.json()["link"]


def _start(browser, user, connector="ga4", *, desktop=False) -> str:
    """Mint a link as ``user`` and open the authorize route with it; returns the state."""
    link = _link(browser, user, connector)
    extra = "&client=desktop" if desktop else ""
    started = browser.http.get(f"/auth/connectors/{connector}/oauth/authorize?link={link}{extra}")
    assert started.status_code == 307
    assert urlparse(started.headers["location"]).hostname == "accounts.google.com"
    return next(iter(oauthstate._memory_states))


def _rows(db, user, connector="ga4"):
    return db.execute(
        select(ConnectorCredential).where(
            ConnectorCredential.user_id == user.id,
            ConnectorCredential.connector_type == connector,
        )
    ).scalars().all()


# --- authorize ------------------------------------------------------------


def test_a_connect_without_a_link_never_reaches_google(cfg, google, db):
    """No link, nobody to hand the grant to: stop before the consent screen."""
    browser = _Browser(db)
    assert browser.http.get("/auth/connectors/ga4/oauth/authorize").status_code == 400
    assert browser.http.get("/auth/connectors/ga4/oauth/authorize?link=forged").status_code == 400

    cfg(duct_local=True)
    relayed = browser.http.get("/auth/connectors/gsc/oauth/authorize?client=desktop")
    assert relayed.headers["location"] == (
        f"{APP_ORIGIN}/desktop-auth?connector=gsc&error={auth.CONNECT_ERROR_EXPIRED}"
    )
    assert not oauthstate._memory_states


def test_the_state_remembers_whose_connect_it_is_and_which_client(cfg, google, db, alice):
    browser = _Browser(db)
    state = _start(browser, alice, "ga4", desktop=True)

    consumed = consume_state_full(state, auth.GOOGLE_CONNECTOR_FLOWS, 300)
    assert consumed.flow == auth.CONNECTOR_FLOW_GA4 + auth.DESKTOP_FLOW_SUFFIX
    assert consumed.link_user_id == str(alice.id)


def test_a_link_is_spent_by_the_first_connect(cfg, google, db, alice):
    browser = _Browser(db)
    link = _link(browser, alice)
    assert browser.http.get(f"/auth/connectors/ga4/oauth/authorize?link={link}").status_code == 307
    assert browser.http.get(f"/auth/connectors/ga4/oauth/authorize?link={link}").status_code == 400


def test_only_a_sign_in_connector_mints_a_link(cfg, db, alice):
    browser = _Browser(db).as_(alice)
    refused = browser.post("/api/user/connectors/connect-link", json={"connector_type": "stripe"})
    assert refused.status_code == 422
    assert browser.post("/api/user/connectors/connect-link", json={"connector_type": "google-ads"}).status_code == 200


# --- callback and claim ---------------------------------------------------


@pytest.mark.parametrize("desktop", [False, True])
def test_the_token_goes_to_the_account_and_never_to_the_client(cfg, google, db, alice, desktop):
    """The whole point. Browser and desktop come home the same way, the desktop
    one through the relay page in the shape shell 0.7.2 routes, and neither
    carries the token: the signed-in page claims the grant and gets the row."""
    browser = _Browser(db)
    state = _start(browser, alice, "gsc", desktop=desktop)
    if desktop:
        cfg(duct_local=True)

    home = browser.http.get(f"/auth/google/callback?code=oauth-code&state={state}")

    location = home.headers["location"]
    page = "desktop-auth" if desktop else "connections"
    assert location.startswith(f"{APP_ORIGIN}/{page}?connector=gsc&auth_code=")
    assert SECRET not in location and "#" not in location
    assert home.headers["cache-control"] == "no-store, max-age=0"

    claimed = browser.as_(alice).post(
        "/api/user/connectors/claim", json={"code": _query(location)["auth_code"]}
    )
    assert claimed.status_code == 200
    assert SECRET not in claimed.text
    assert claimed.json()["connector_type"] == "gsc"

    (row,) = _rows(db, alice, "gsc")
    assert decrypt_credentials(row.credentials_enc) == {"refresh_token": SECRET}
    assert row.account_id == ""
    # And the page's listing, which every tab and device reads, shows it
    # without the secret.
    listing = browser.as_(alice).get("/api/user/connectors")
    assert [r["connector_type"] for r in listing.json()] == ["gsc"]
    assert SECRET not in listing.text


def test_the_per_connector_callback_stores_the_same_way(cfg, google, db, alice):
    browser = _Browser(db)
    state = _start(browser, alice, "gtm")
    home = browser.http.get(f"/auth/connectors/gtm/oauth/callback?code=c&state={state}")
    code = _query(home.headers["location"])["auth_code"]
    assert browser.as_(alice).post("/api/user/connectors/claim", json={"code": code}).status_code == 200
    assert len(_rows(db, alice, "gtm")) == 1


def test_a_forged_link_never_lands_a_victims_consent_on_the_senders_account(
    cfg, google, db, alice, mallory
):
    """Mallory mints a link for her own account and gets Alice to open it.
    Alice consents at Google; the grant comes home to Alice's browser, whose
    session is not Mallory's. Stored on the callback, Alice's Analytics would
    now be readable from Mallory's account."""
    browser = _Browser(db)
    state = _start(browser, mallory, "ga4")
    home = browser.http.get(f"/auth/google/callback?code=c&state={state}")
    code = _query(home.headers["location"])["auth_code"]

    assert browser.as_(alice).post("/api/user/connectors/claim", json={"code": code}).status_code == 404
    # Spent by the refusal: Mallory cannot claim it afterwards either.
    assert browser.as_(mallory).post("/api/user/connectors/claim", json={"code": code}).status_code == 404
    assert _rows(db, alice) == [] and _rows(db, mallory) == []


def test_a_grant_is_claimed_once(cfg, google, db, alice):
    browser = _Browser(db)
    state = _start(browser, alice)
    code = _query(browser.http.get(f"/auth/google/callback?code=c&state={state}").headers["location"])["auth_code"]
    assert browser.as_(alice).post("/api/user/connectors/claim", json={"code": code}).status_code == 200
    assert browser.as_(alice).post("/api/user/connectors/claim", json={"code": code}).status_code == 404


def test_a_state_with_nobody_behind_it_expires(cfg, google, db):
    """A connect begun before links existed has no user to hand its grant to."""
    oauthstate.save_state("old-state", "verifier", auth.CONNECTOR_FLOW_GA4, 300)
    with pytest.raises(HTTPException) as excinfo:
        auth.google_oauth_callback_short_path(code="c", state="old-state")
    assert excinfo.value.status_code == 400


def test_a_partial_grant_is_recorded_rather_than_assumed(cfg, google, db, alice):
    """GA4 asks for analytics.readonly AND analytics.edit. Someone who grants
    only the first must still connect — and what they withheld is recorded, or
    the card goes green over permissions we do not hold."""
    google(_Flow(granted=(GA4_READ,)))
    browser = _Browser(db)
    state = _start(browser, alice)
    code = _query(browser.http.get(f"/auth/google/callback?code=c&state={state}").headers["location"])["auth_code"]

    claimed = browser.as_(alice).post("/api/user/connectors/claim", json={"code": code}).json()

    assert claimed["granted_scopes"] == [GA4_READ]
    assert claimed["scope_status"] == "partial"
    assert any("analytics.edit" in s for s in claimed["missing_scopes"])


def test_an_unreadable_grant_never_fails_the_connect(cfg, google, db, alice):
    """A flow object that cannot report its scopes is a degraded answer, not a
    dead connect: the token is what the user came for."""
    flow = _Flow()
    del flow.oauth2session
    google(flow)
    browser = _Browser(db)
    state = _start(browser, alice)
    code = _query(browser.http.get(f"/auth/google/callback?code=c&state={state}").headers["location"])["auth_code"]

    claimed = browser.as_(alice).post("/api/user/connectors/claim", json={"code": code}).json()

    assert claimed["granted_scopes"] == []
    assert len(_rows(db, alice)) == 1


def test_a_reconnect_keeps_the_manager_account(cfg, google, db, alice):
    """The token is not the whole blob. A reconnect replacing it whole would drop
    the MCC id, and every read through that manager would quietly stop."""
    db.add(ConnectorCredential(
        user_id=alice.id, connector_type="google_ads", account_id="", account_name="",
        credentials_enc=encrypt_credentials({"refresh_token": "old", "login_customer_id": "1234567890"}),
    ))
    db.commit()
    browser = _Browser(db)
    state = _start(browser, alice, "google_ads")
    code = _query(browser.http.get(f"/auth/google/callback?code=c&state={state}").headers["location"])["auth_code"]

    claimed = browser.as_(alice).post("/api/user/connectors/claim", json={"code": code}).json()

    (row,) = _rows(db, alice, "google_ads")
    assert decrypt_credentials(row.credentials_enc) == {
        "refresh_token": SECRET, "login_customer_id": "1234567890",
    }
    assert claimed["settings"] == {"login_customer_id": "1234567890"}


def test_a_grant_code_cannot_be_redeemed_as_a_session_token():
    """Namespacing, not decoration: `/auth/exchange` hands back whatever it finds
    as the caller's JWT. A connector grant must not be findable there."""
    code = auth_exchange.store_connector_grant(user_id="u", connector_type="ga4", refresh_token="rt")

    assert auth_exchange.consume_exchange_code(code) is None
    # And a rejected cross-namespace read must not burn the code for its owner.
    assert auth_exchange.consume_connector_grant(code)["refresh_token"] == "rt"


def test_a_signin_code_cannot_be_claimed_as_a_connector_grant():
    code = auth_exchange.store_exchange_code("a.jwt.value")

    assert auth_exchange.consume_connector_grant(code) is None
    assert auth_exchange.consume_exchange_code(code) == "a.jwt.value"


# --- what a request may write ---------------------------------------------


def test_a_request_can_never_write_a_google_refresh_token(cfg, db, alice):
    """Only the connect flow writes one, so a token from anywhere else — a
    stale tab, another account's — cannot be planted on this one."""
    browser = _Browser(db).as_(alice)
    saved = browser.post("/api/user/connectors", json={
        "connector_type": "ga4", "credentials": {"refresh_token": "planted"},
    })
    assert saved.status_code == 422
    assert _rows(db, alice) == []


def test_the_manager_account_changes_without_touching_the_token(cfg, db, alice, mallory):
    row = ConnectorCredential(
        user_id=alice.id, connector_type="google_ads", account_id="", account_name="",
        credentials_enc=encrypt_credentials({"refresh_token": "kept"}),
    )
    db.add(row)
    db.commit()
    browser = _Browser(db)
    path = f"/api/user/connectors/{row.id}"

    saved = browser.as_(alice).patch(path, json={"settings": {"login_customer_id": "1234567890"}})
    assert saved.status_code == 200
    assert saved.json()["settings"] == {"login_customer_id": "1234567890"}
    assert "kept" not in saved.text
    assert decrypt_credentials(row.credentials_enc) == {
        "refresh_token": "kept", "login_customer_id": "1234567890",
    }

    # Clearing falls back to the server default rather than storing "".
    browser.as_(alice).patch(path, json={"settings": {"login_customer_id": ""}})
    assert decrypt_credentials(row.credentials_enc) == {"refresh_token": "kept"}

    assert browser.as_(alice).patch(path, json={"settings": {"refresh_token": "x"}}).status_code == 422
    assert browser.as_(mallory).patch(path, json={"settings": {"login_customer_id": "1"}}).status_code == 404
    assert decrypt_credentials(row.credentials_enc) == {"refresh_token": "kept"}


# --- failures -------------------------------------------------------------


def test_desktop_failures_land_on_the_relay_page(cfg):
    """The system browser renders whatever the sidecar returns, so it can't be JSON."""
    cfg(duct_local=True)

    response = auth.google_oauth_callback_short_path(code="", state="")

    assert response.status_code == 307
    assert response.headers["location"] == (
        f"{APP_ORIGIN}/desktop-auth?connector=&error={auth.CONNECT_ERROR_EXPIRED}"
    )


def test_web_failures_keep_their_json_contract(cfg):
    with pytest.raises(HTTPException) as excinfo:
        auth.google_oauth_callback_short_path(code="", state="")

    assert excinfo.value.status_code == 400


def test_missing_consent_is_explained_rather_than_crashing(cfg, google, db, alice):
    """Google returns no refresh token when the account has approved before —
    the single most likely real failure, and the one worth naming."""
    google(_Flow(refresh_token=""))
    browser = _Browser(db)
    state = _start(browser, alice, "google_ads", desktop=True)
    cfg(duct_local=True)

    response = browser.http.get(f"/auth/google/callback?code=c&state={state}")

    assert response.headers["location"].endswith(f"&error={auth.CONNECT_ERROR_CONSENT}")
    assert "connector=google_ads" in response.headers["location"]


def test_an_unexpected_crash_is_still_an_explainable_page(cfg, monkeypatch):
    cfg(duct_local=True)
    monkeypatch.setattr(
        auth,
        "consume_state_full",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    response = auth.google_oauth_callback_short_path(code="c", state="s")

    assert response.status_code == 307
    assert response.headers["location"].endswith(f"error={auth.CONNECT_ERROR_SERVER}")
