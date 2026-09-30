"""GitHub App — the one-click connection, end to end over ``FakeWire``.

What this file holds is the security property the App path rests on
(service/github/app.py, step 4): Duct's private key will mint a token for any
installation id it is handed, so an installation id must only ever come from
GitHub, for the user who started the connect. Three tests are that property
from three sides — a claim by the wrong account, a credential written by a
request, and an account listing asked for by a request — and the rest is the
flow those tests assume works: OAuth with PKCE, the install detour, the
desktop relay, the one-hour token narrowed to one repository.
"""

from __future__ import annotations

import base64
import hashlib
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlmodel import Session

import routes.auth as auth_routes
import routes.connectors as connectors_routes
import routes.user_connectors as uc_routes
import service.auth as auth_service
import service.credentials as credentials_service
from config import Configs
from db.session import get_session as get_session_dep
from models.auth import User
from models.connector import ConnectorCredential
from service.auth_exchange import store_github_grant
from service.github import app as gh_app
from service.github.fetch import fetch_github
from tests.conftest import make_sqlite_engine
from tests.fakes import FakeWire

API = "https://api.duct.test"
APP_ORIGIN = "https://app.duct.test"
CLIENT_ID = "Iv23liDUCTTEST"
SLUG = "duct-test"
CALLBACK = f"{API}/auth/connectors/github/oauth/callback"


@pytest.fixture(scope="module")
def private_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def cfg(monkeypatch, private_key):
    pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    config = Configs(
        api_public_url=API,
        frontend_origin=APP_ORIGIN,
        credentials_encryption_key=Fernet.generate_key().decode(),
        github_app_slug=SLUG,
        github_app_client_id=CLIENT_ID,
        github_app_client_secret="client-secret",
        # One line with literal escapes, the way a dotenv file holds it.
        github_app_private_key=pem.replace("\n", "\\n"),
    )
    for module in (gh_app, auth_routes, credentials_service):
        monkeypatch.setattr(module, "get_configs", lambda: config)
    # The OAuth state store on its in-memory path: no database behind it here.
    monkeypatch.setattr("service.oauthstate.get_engine", lambda: None)
    monkeypatch.setattr("service.oauthstate._memory_states", {}, raising=False)
    gh_app.clear_token_cache()
    yield config
    gh_app.clear_token_cache()


@pytest.fixture
def wire(monkeypatch):
    import service.rest as rest

    monkeypatch.setattr(rest.time, "sleep", lambda *_: None)
    return FakeWire().install(monkeypatch)


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
        app.include_router(auth_routes.router)
        app.include_router(uc_routes.router, prefix="/api/user/connectors")
        app.include_router(connectors_routes.router, prefix="/api/connectors")
        app.dependency_overrides[get_session_dep] = lambda: db
        app.dependency_overrides[auth_service.get_current_user] = lambda: self.user
        self.user = None
        self.http = TestClient(app, follow_redirects=False)

    def as_(self, user):
        self.user = user
        return self.http


def _query(location: str) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(urlparse(location).query).items()}


def _in_an_hour() -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _github_grants(wire, repos_by_installation: dict[int, list[dict]]) -> FakeWire:
    wire.on("POST", "/login/oauth/access_token", {"access_token": "ghu_user", "token_type": "bearer"})
    for installation_id, repos in repos_by_installation.items():
        wire.on("GET", f"/user/installations/{installation_id}/repositories", {
            "total_count": len(repos), "repositories": repos,
        })
    wire.on("GET", "/user/installations", {
        "total_count": len(repos_by_installation),
        "installations": [{"id": i} for i in repos_by_installation],
    })
    return wire


def _connect(browser, user, *, client: str = "") -> str:
    """Start a connect as ``user``; returns the state GitHub would carry back."""
    link = browser.as_(user).post("/api/user/connectors/github/connect").json()["link"]
    extra = f"&client={client}" if client else ""
    started = browser.as_(user).get(f"/auth/connectors/github/oauth/authorize?link={link}{extra}")
    assert started.status_code == 307
    return _query(started.headers["location"])["state"]


def _rows(db) -> dict[str, dict]:
    rows = db.execute(select(ConnectorCredential)).scalars().all()
    return {r.account_id: credentials_service.decrypt_credentials(r.credentials_enc) for r in rows}


REPO_NEW = {"full_name": "acme/app", "description": "The app", "private": True, "pushed_at": "2026-09-27T10:00:00Z"}
REPO_OLD = {"full_name": "acme/site", "description": "", "private": False, "pushed_at": "2026-08-01T10:00:00Z"}


# ---------------------------------------------------------------------------
# The App's own identity, and the tokens it mints
# ---------------------------------------------------------------------------

def test_the_app_signs_as_its_client_id_for_under_ten_minutes(cfg, private_key):
    now = time.time()
    claims = jwt.decode(gh_app.app_jwt(now), private_key.public_key(), algorithms=["RS256"])
    assert claims["iss"] == CLIENT_ID
    assert claims["iat"] <= now - 59  # backdated against clock drift
    assert claims["exp"] - now <= 600  # GitHub refuses anything longer


def test_a_key_pasted_across_dotenv_lines_turns_the_app_off_and_says_why(tmp_path, monkeypatch, caplog):
    # What python-dotenv leaves of a multi-line paste: the header, alone.
    env = tmp_path / ".env"
    env.write_text(
        f"GITHUB_APP_SLUG={SLUG}\nGITHUB_APP_CLIENT_ID={CLIENT_ID}\nGITHUB_APP_CLIENT_SECRET=s\n"
        "GITHUB_APP_PRIVATE_KEY=-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA\n-----END RSA PRIVATE KEY-----\n"
    )
    config = Configs(_env_file=[env])
    monkeypatch.setattr(gh_app, "get_configs", lambda: config)
    assert config.github_app_private_key == ""
    assert not gh_app.is_configured()
    assert "GITHUB_APP_PRIVATE_KEY is cut short" in caplog.text


def test_a_token_reads_one_repository_read_only_and_is_reused_until_near_expiry(cfg, wire, private_key):
    answers = iter([
        {"token": "ghs_short", "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=60)).isoformat()},
        {"token": "ghs_long", "expires_at": _in_an_hour()},
    ])
    wire.on("POST", "/app/installations/42/access_tokens", lambda _call: next(answers), status=201)

    assert gh_app.installation_token("42", "app") == "ghs_short"
    # A minute left is inside the refresh margin: mint again rather than start
    # a pull on a token about to die. An hour left is reused.
    assert gh_app.installation_token("42", "app") == "ghs_long"
    assert gh_app.installation_token("42", "app") == "ghs_long"

    mints = wire.sent("POST", "/access_tokens")
    assert len(mints) == 2
    assert mints[0].json == {"repositories": ["app"], "permissions": gh_app.APP_PERMISSIONS}
    assert set(gh_app.APP_PERMISSIONS.values()) == {"read"}
    bearer = mints[0].headers["Authorization"].removeprefix("Bearer ")
    assert jwt.decode(bearer, private_key.public_key(), algorithms=["RS256"])["iss"] == CLIENT_ID


@pytest.mark.parametrize(("status", "says"), [
    (401, "settings"),
    (403, "suspended"),
    (404, "no longer installed"),
    (422, "no longer has access"),
])
def test_a_refused_mint_says_what_fixes_it(cfg, wire, status, says):
    wire.on("POST", "/access_tokens", {"message": "nope"}, status=status)
    with pytest.raises(ValueError, match=says):
        gh_app.installation_token("42", "app")


def test_granted_repositories_are_what_the_user_can_see_newest_push_first(cfg, wire, monkeypatch):
    _github_grants(wire, {42: [REPO_OLD], 7: [REPO_NEW]})
    repos, omitted = gh_app.granted_repositories("ghu_user")
    assert [(r.installation_id, r.full_name) for r in repos] == [("7", "acme/app"), ("42", "acme/site")]
    assert omitted == 0
    # Read with the user's token, from the /user/ endpoints: the intersection
    # of where the App is installed and what this person can open.
    assert {c.headers["Authorization"] for c in wire.calls} == {"Bearer ghu_user"}

    monkeypatch.setattr(gh_app, "MAX_GRANTED_REPOS", 1)
    repos, omitted = gh_app.granted_repositories("ghu_user")
    assert [r.full_name for r in repos] == ["acme/app"] and omitted == 1


def test_a_spent_code_is_a_refusal_not_a_token(cfg, wire):
    # GitHub answers a bad code with 200 and an error field, not a 4xx.
    wire.on("POST", "/login/oauth/access_token", {
        "error": "bad_verification_code",
        "error_description": "The code passed is incorrect or expired.",
    })
    with pytest.raises(ValueError, match="incorrect or expired"):
        gh_app.exchange_code("c0de", "verifier")
    sent = wire.sent("POST", "/login/oauth/access_token")[0].data
    assert sent["code_verifier"] == "verifier" and sent["redirect_uri"] == CALLBACK


# ---------------------------------------------------------------------------
# The connect
# ---------------------------------------------------------------------------

def test_a_connect_writes_one_row_per_granted_repository_for_the_user_who_started_it(cfg, wire, db, alice):
    browser = _Browser(db)
    link = browser.as_(alice).post("/api/user/connectors/github/connect").json()["link"]
    started = browser.as_(alice).get(f"/auth/connectors/github/oauth/authorize?link={link}")
    assert started.headers["location"].startswith("https://github.com/login/oauth/authorize?")
    asked = _query(started.headers["location"])
    assert (asked["client_id"], asked["redirect_uri"], asked["code_challenge_method"]) == (
        CLIENT_ID, CALLBACK, "S256",
    )

    _github_grants(wire, {42: [REPO_OLD, REPO_NEW]})
    home = browser.http.get(f"/auth/connectors/github/oauth/callback?code=c0de&state={asked['state']}")
    assert home.headers["location"].startswith(f"{APP_ORIGIN}/connections?connector=github&auth_code=")

    # PKCE: the verifier sent with the code is the one the challenge was made from.
    verifier = wire.sent("POST", "/login/oauth/access_token")[0].data["code_verifier"]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    assert challenge == asked["code_challenge"]

    code = _query(home.headers["location"])["auth_code"]
    claimed = browser.as_(alice).post("/api/user/connectors/github/claim", json={"code": code})
    assert claimed.status_code == 200
    assert sorted(c["account_id"] for c in claimed.json()["connectors"]) == ["acme/app", "acme/site"]
    assert _rows(db) == {
        "acme/app": {"installation_id": "42", "repo": "acme/app"},
        "acme/site": {"installation_id": "42", "repo": "acme/site"},
    }
    # Single use.
    again = browser.as_(alice).post("/api/user/connectors/github/claim", json={"code": code})
    assert again.status_code == 404


def test_a_grant_is_never_claimed_into_another_account(cfg, wire, db, alice, mallory):
    """The forged link: Mallory mints a connect link for her own account and
    gets Alice to open it. Alice approves on GitHub — Duct is already
    authorized, so GitHub may not even ask — and her repositories come back.
    They must not land in Mallory's account, and Alice's session cannot
    adopt a grant her own link did not start."""
    browser = _Browser(db)
    state = _connect(browser, mallory)
    _github_grants(wire, {42: [REPO_NEW]})
    home = browser.http.get(f"/auth/connectors/github/oauth/callback?code=c0de&state={state}")
    code = _query(home.headers["location"])["auth_code"]

    refused = browser.as_(alice).post("/api/user/connectors/github/claim", json={"code": code})
    assert refused.status_code == 404
    # Spent by the wrong claim, so a second try by anyone finds nothing either.
    assert browser.as_(mallory).post("/api/user/connectors/github/claim", json={"code": code}).status_code == 404
    assert _rows(db) == {}


def test_a_request_can_never_write_or_list_an_installation(cfg, wire, db, alice):
    """Duct's key mints for any installation id it is handed. If a request
    could store one, or list with one, it could read someone else's code."""
    browser = _Browser(db).as_(alice)
    forged = {"installation_id": "42", "repo": "victim/secret"}

    saved = browser.post("/api/user/connectors", json={"connector_type": "github", "credentials": forged})
    assert saved.status_code == 422 and "installation_id" in saved.json()["detail"]
    listed = browser.post("/api/connectors/github/accounts", json={"credentials": forged})
    assert listed.status_code == 422
    assert _rows(db) == {}
    assert wire.calls == []  # nothing was minted, nothing was asked of GitHub


def test_no_installation_yet_detours_through_the_install_screen_once(cfg, wire, db, alice):
    browser = _Browser(db)
    state = _connect(browser, alice)
    _github_grants(wire, {})
    to_install = browser.http.get(f"/auth/connectors/github/oauth/callback?code=c1&state={state}")
    location = to_install.headers["location"]
    assert location.startswith(f"https://github.com/apps/{SLUG}/installations/select_target?")

    # Back from GitHub. The installation_id it appends is spoofable and ignored:
    # the connect resumes at OAuth, and GitHub says what was installed.
    resumed = browser.http.get(
        "/auth/connectors/github/setup?installation_id=999&setup_action=install"
        f"&state={_query(location)['state']}"
    )
    assert resumed.headers["location"].startswith("https://github.com/login/oauth/authorize?")

    # The install granted nothing this user can read. The connect ends, with an
    # empty grant, rather than sending them back to the install screen forever.
    ended = browser.http.get(
        f"/auth/connectors/github/oauth/callback?code=c2&state={_query(resumed.headers['location'])['state']}"
    )
    assert ended.headers["location"].startswith(f"{APP_ORIGIN}/connections?connector=github&auth_code=")
    code = _query(ended.headers["location"])["auth_code"]
    assert browser.as_(alice).post("/api/user/connectors/github/claim", json={"code": code}).json() == {
        "connectors": [], "omitted": 0,
    }
    assert not any("/999" in c.url for c in wire.calls)


def test_a_setup_return_without_state_hands_back_to_the_signed_in_page(cfg, db):
    back = _Browser(db).http.get("/auth/connectors/github/setup?installation_id=1&setup_action=update")
    assert back.status_code == 307
    assert back.headers["location"] == f"{APP_ORIGIN}/connections?connector=github&installed=1"


def test_a_desktop_connect_comes_home_through_the_relay(cfg, wire, db, alice):
    browser = _Browser(db)
    state = _connect(browser, alice, client="desktop")
    _github_grants(wire, {42: [REPO_NEW]})
    home = browser.http.get(f"/auth/connectors/github/oauth/callback?code=c0de&state={state}")
    assert home.headers["location"].startswith(f"{APP_ORIGIN}/desktop-auth?connector=github&auth_code=")


def test_without_the_app_or_a_link_nothing_starts(cfg, db, alice, monkeypatch):
    browser = _Browser(db)
    assert browser.http.get("/auth/connectors/github/oauth/authorize").status_code == 400
    assert browser.http.get("/auth/connectors/github/oauth/authorize?link=forged").status_code == 400

    unconfigured = Configs(api_public_url=API, frontend_origin=APP_ORIGIN)
    for module in (gh_app, auth_routes):
        monkeypatch.setattr(module, "get_configs", lambda: unconfigured)
    assert browser.as_(alice).get("/api/user/connectors/github/app").json() == {
        "available": False, "manage_url": "",
    }
    assert browser.as_(alice).post("/api/user/connectors/github/connect").status_code == 501
    assert browser.http.get("/auth/connectors/github/oauth/authorize?link=x").status_code == 501


def test_a_reconnect_drops_app_rows_github_no_longer_grants_and_keeps_pasted_tokens(cfg, db, alice):
    browser = _Browser(db).as_(alice)
    for account_id, blob in (
        ("acme/gone", {"installation_id": "42", "repo": "acme/gone"}),
        ("acme/mine", {"token": "github_pat_x", "repo": "acme/mine"}),
        ("acme/app", {"token": "github_pat_y", "repo": "acme/app"}),
    ):
        db.add(ConnectorCredential(
            user_id=alice.id, connector_type="github", account_id=account_id,
            account_name=account_id, credentials_enc=credentials_service.encrypt_credentials(blob),
        ))
    db.commit()

    code = store_github_grant(user_id=str(alice.id), grant={
        "repos": [{"installation_id": "42", "full_name": "acme/app"}], "omitted": 0,
    })
    assert browser.post("/api/user/connectors/github/claim", json={"code": code}).status_code == 200
    assert _rows(db) == {
        # The App now covers acme/app, so its row replaces the pasted token's.
        "acme/app": {"installation_id": "42", "repo": "acme/app"},
        # A token row for a repository the App does not cover is the user's own.
        "acme/mine": {"token": "github_pat_x", "repo": "acme/mine"},
    }


# ---------------------------------------------------------------------------
# Reading with a grant
# ---------------------------------------------------------------------------

def test_an_app_row_pulls_with_one_token_minted_for_its_repository(cfg, wire):
    wire.on("POST", "/app/installations/42/access_tokens", {"token": "ghs_repo", "expires_at": _in_an_hour()}, status=201)
    for path in ("commits", "pulls", "issues", "releases"):
        wire.on("GET", f"/repos/acme/app/{path}", [])

    payload = fetch_github({"installation_id": "42", "repo": "acme/app"}, "2026-09-01", "2026-09-28")

    assert payload["errors"] == {}
    assert len(wire.sent("POST", "/access_tokens")) == 1  # once per pull, not per section
    assert wire.sent("POST", "/access_tokens")[0].json["repositories"] == ["app"]
    reads = [c for c in wire.calls if c.method == "GET"]
    assert reads and {c.headers["Authorization"] for c in reads} == {"Bearer ghs_repo"}


def test_an_app_row_lists_itself_without_asking_github(cfg, wire):
    from service.connectors import ConnectorAuthContext, registry

    _meta, adapter = registry()["github"]
    rows = adapter.list_accounts(
        ConnectorAuthContext("github", extras={"installation_id": "42", "repo": "acme/app"})
    )
    assert rows == [{"account_id": "acme/app", "account_name": "acme/app"}]
    assert wire.calls == []
