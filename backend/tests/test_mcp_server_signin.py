"""Browser sign-in to Duct's MCP server: Duct as the OAuth authorization server.

What these pin, in the order a reviewer would worry about them:

  * nothing reaches an address the client did not register, and a client id
    nobody signed, or one edited after signing, gets nowhere;
  * a code is the person's consent, spent once, by the client that asked,
    with the verifier it committed to;
  * what the exchange mints is an MCP token: it works on /mcp, nowhere else,
    renews once per refresh token, and stops when the person disconnects it;
  * the documents a client reads to find all this say what the spec says, so
    Claude Code, Codex, Cursor and OpenCode can sign in at all.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import secrets
import uuid
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import jwt
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlmodel import Session

from config import Configs
from db.session import get_session
from models.auth import McpToken, User
from routes import mcp_oauth, mcp_server, mcp_tokens
from service import mcp_tokens as token_service
from service.auth import get_current_user
from service.mcp_server import oauth
from service.mcp_tokens import MAX_CONNECTED_AGENTS, REFRESH_PREFIX, TOKEN_PREFIX
from service.user_store import guest_email
from tests.conftest import make_sqlite_engine

API = "https://api.duct.test"
APP = "https://app.duct.test"
SECRET = "a-test-secret-that-is-long-enough-for-the-check"
CALLBACK = "http://127.0.0.1:33418/callback"


def _pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def _query(url: str) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}


class _Env:
    def __init__(self, session: Session, client: TestClient, config: Configs):
        self.session, self.client, self.config = session, client, config
        self.signed_in: User | None = None

    def user(self, email: str) -> User:
        user = User(email=email, full_name=email.split("@")[0])
        self.session.add(user)
        self.session.commit()
        self.session.refresh(user)
        return user

    def register(self, name: str = "Claude Code", uris: list[str] | None = None) -> str:
        res = self.client.post("/oauth/register", json={
            "client_name": name, "redirect_uris": uris or [CALLBACK],
            "grant_types": ["authorization_code", "refresh_token"], "token_endpoint_auth_method": "none",
        })
        assert res.status_code == 201, res.text
        return res.json()["client_id"]

    def authorize(self, client_id: str, challenge: str, *, redirect_uri: str = CALLBACK, **extra):
        params = {
            "response_type": "code", "client_id": client_id, "redirect_uri": redirect_uri,
            "code_challenge": challenge, "code_challenge_method": "S256", "state": "st-1",
            "resource": f"{API}/mcp", **extra,
        }
        return self.client.get("/oauth/authorize", params=params, follow_redirects=False)

    def consent(self, client_id: str, challenge: str, **extra) -> str:
        """The request code the app's consent page is opened with."""
        res = self.authorize(client_id, challenge, **extra)
        assert res.status_code == 302, res.text
        location = res.headers["location"]
        assert location.startswith(f"{APP}/authorize?"), location
        return _query(location)["request"]

    def allow(self, request_code: str) -> dict[str, str]:
        res = self.client.post(f"/api/oauth/requests/{request_code}/approve")
        assert res.status_code == 200, res.text
        return _query(res.json()["redirect_to"])

    def exchange(self, client_id: str, code: str, verifier: str, redirect_uri: str = CALLBACK):
        return self.client.post("/oauth/token", data={
            "grant_type": "authorization_code", "code": code, "client_id": client_id,
            "redirect_uri": redirect_uri, "code_verifier": verifier, "resource": f"{API}/mcp",
        })

    def refresh(self, client_id: str, refresh_token: str):
        return self.client.post("/oauth/token", data={
            "grant_type": "refresh_token", "refresh_token": refresh_token, "client_id": client_id,
        })

    def sign_in(self, user: User, name: str = "Claude Code") -> tuple[str, dict]:
        """The whole flow, as a client and a person run it. Returns the client
        id and the token response."""
        self.signed_in = user
        client_id = self.register(name)
        verifier, challenge = _pkce()
        answer = self.allow(self.consent(client_id, challenge))
        res = self.exchange(client_id, answer["code"], verifier)
        assert res.status_code == 200, res.text
        return client_id, res.json()

    def ping(self, token: str):
        return self.client.post(
            "/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"}, headers={"Authorization": f"Bearer {token}"}
        )


@pytest.fixture
def config(monkeypatch):
    config = Configs(api_public_url=API, frontend_origin=APP, jwt_secret=SECRET)
    monkeypatch.setattr(oauth, "get_configs", lambda: config)
    return config


@pytest.fixture
def env(config):
    engine = make_sqlite_engine(drop_partial_indexes=True)
    session = Session(engine)
    app = FastAPI()
    app.include_router(mcp_server.router)
    app.include_router(mcp_oauth.router)
    app.include_router(mcp_oauth.consent_router, prefix="/api/oauth/requests")
    app.include_router(mcp_tokens.router, prefix="/api/user/mcp-tokens")
    state = _Env(session, TestClient(app, raise_server_exceptions=False), config)

    def _session():
        yield session

    def _user():
        if state.signed_in is None:
            raise HTTPException(status_code=401, detail="Not authenticated")
        return state.signed_in

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_current_user] = _user
    yield state
    session.close()
    engine.dispose()


# -- discovery --------------------------------------------------------------------

def test_an_unsigned_call_points_the_agent_at_where_to_sign_in(env):
    res = env.client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"})
    assert res.status_code == 401
    challenge = res.headers["WWW-Authenticate"]
    assert f'resource_metadata="{API}/.well-known/oauth-protected-resource/mcp"' in challenge
    assert "error=" not in challenge, "a first call sent nothing that could be invalid"
    assert 'error="invalid_token"' in env.ping(TOKEN_PREFIX + "made-up").headers["WWW-Authenticate"]


def test_the_metadata_names_this_server_and_what_it_supports(env):
    for path in ("/.well-known/oauth-protected-resource/mcp", "/.well-known/oauth-protected-resource"):
        resource = env.client.get(path).json()
        assert resource["resource"] == f"{API}/mcp"
        assert resource["authorization_servers"] == [API]

    server = env.client.get("/.well-known/oauth-authorization-server").json()
    # RFC 8414 §3.3: the issuer is exactly where the document was fetched from.
    assert server["issuer"] == API
    assert server["authorization_endpoint"] == f"{API}/oauth/authorize"
    assert server["token_endpoint"] == f"{API}/oauth/token"
    assert server["registration_endpoint"] == f"{API}/oauth/register"
    assert server["code_challenge_methods_supported"] == ["S256"]
    assert server["token_endpoint_auth_methods_supported"] == ["none"]


def test_a_desktop_sidecar_offers_no_sign_in(env, monkeypatch):
    # Only the fields the module reads: a real local-mode Configs creates the
    # desktop data directory as it validates.
    sidecar = SimpleNamespace(api_public_url="http://127.0.0.1:51234", frontend_origin="tauri://localhost",
                              jwt_secret=SECRET, duct_local=True)
    monkeypatch.setattr(oauth, "get_configs", lambda: sidecar)
    assert env.client.get("/.well-known/oauth-authorization-server").status_code == 404
    assert env.client.post("/oauth/register", json={"redirect_uris": [CALLBACK]}).status_code == 404
    # Never a redirect: the sidecar's app is tauri://, which a system browser cannot open.
    assert env.client.get("/oauth/authorize", follow_redirects=False).status_code == 404
    challenge = env.client.post("/mcp", json={}).headers["WWW-Authenticate"]
    assert "resource_metadata" not in challenge, "a pasted token is the sidecar's only way in"


# -- registration -------------------------------------------------------------------

@pytest.mark.parametrize("uri", [
    "http://localhost:6274/oauth/callback",
    "http://[::1]:7777/cb",
    "https://claude.ai/api/mcp/auth_callback",
    "cursor://anysphere.cursor-retrieval/oauth/user-duct/callback",
])
def test_registration_takes_the_addresses_real_agents_use(env, uri):
    assert env.register(uris=[uri])


@pytest.mark.parametrize("body, code", [
    ({"redirect_uris": ["http://evil.example/cb"]}, "invalid_redirect_uri"),
    ({"redirect_uris": ["javascript:alert(1)"]}, "invalid_redirect_uri"),
    ({"redirect_uris": ["https://ok.example/cb#frag"]}, "invalid_redirect_uri"),
    # The consent page names the host: a lookalike or a name before an "@"
    # would put "claude.ai" on screen in front of someone else's server.
    ({"redirect_uris": ["https://\u0441laude.ai/api/mcp/auth_callback"]}, "invalid_redirect_uri"),
    ({"redirect_uris": ["https://claude.ai@evil.example/cb"]}, "invalid_redirect_uri"),
    # Loopback to Python, evil.example to a browser, which reads "\\" as "/".
    ({"redirect_uris": ["http://evil.example\\@127.0.0.1/cb"]}, "invalid_redirect_uri"),
    ({"redirect_uris": []}, "invalid_redirect_uri"),
    ({"redirect_uris": [CALLBACK], "token_endpoint_auth_method": "client_secret_basic"}, "invalid_client_metadata"),
    ({"redirect_uris": [CALLBACK], "grant_types": ["client_credentials"]}, "invalid_client_metadata"),
])
def test_registration_refuses_what_could_leak_a_code(env, body, code):
    res = env.client.post("/oauth/register", json=body)
    assert res.status_code == 400
    assert res.json()["error"] == code


def test_a_client_id_is_never_a_session(env):
    client_id = env.register()
    settings = Configs(jwt_secret=SECRET)
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=client_id)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(get_current_user(creds, settings, env.session))
    assert exc.value.status_code == 401


# -- authorize ------------------------------------------------------------------------

def test_an_unknown_or_edited_client_never_redirects_to_the_address_it_named(env):
    _, challenge = _pkce()
    claims = jwt.decode(env.register(), options={"verify_signature": False})
    forged = jwt.encode({**claims, "redirect_uris": ["https://evil.example/cb"]}, SECRET, "HS256")
    for client_id, uri in (("made-up", CALLBACK), (forged, "https://evil.example/cb")):
        res = env.authorize(client_id, challenge, redirect_uri=uri)
        assert res.status_code == 302
        assert res.headers["location"] == f"{APP}/authorize?error=invalid_request"

    unregistered = env.authorize(env.register(), challenge, redirect_uri="https://evil.example/cb")
    assert unregistered.headers["location"] == f"{APP}/authorize?error=invalid_request"


def test_a_loopback_listener_may_come_back_on_another_port(env):
    _, challenge = _pkce()
    client_id = env.register()
    assert env.consent(client_id, challenge, redirect_uri="http://127.0.0.1:50999/callback")
    for elsewhere in (
        "http://127.0.0.1:50999/elsewhere",
        "http://evil.example\\@127.0.0.1:50999/callback",
        "http://user@127.0.0.1:50999/callback",
    ):
        res = env.authorize(client_id, challenge, redirect_uri=elsewhere)
        assert res.headers["location"] == f"{APP}/authorize?error=invalid_request", elsewhere


def test_an_error_goes_straight_back_only_to_this_computer(env):
    """Anyone can register, so an immediate redirect to a registered https
    address would make Duct's domain a redirector for whoever registered it."""
    _, challenge = _pkce()
    uri = "https://agent.example/cb"
    res = env.authorize(env.register(uris=[uri]), challenge, redirect_uri=uri, response_type="token")
    assert res.headers["location"] == f"{APP}/authorize?error=invalid_request"


@pytest.mark.parametrize("extra, error", [
    ({"code_challenge_method": "plain"}, "invalid_request"),
    ({"response_type": "token"}, "unsupported_response_type"),
    ({"resource": "https://elsewhere.example/mcp"}, "invalid_target"),
])
def test_a_bad_request_from_a_known_client_goes_back_to_it_with_an_error(env, extra, error):
    _, challenge = _pkce()
    res = env.authorize(env.register(), challenge, **extra)
    back = _query(res.headers["location"])
    assert res.headers["location"].startswith(CALLBACK)
    assert (back["error"], back["state"], back["iss"]) == (error, "st-1", API)


def test_the_consent_page_learns_who_is_asking_and_where_it_returns(env):
    _, challenge = _pkce()
    request_code = env.consent(env.register("Claude Code"), challenge)
    for _ in range(2):  # a reload reads it again
        described = env.client.get(f"/api/oauth/requests/{request_code}").json()
    assert described == {"client_name": "Claude Code", "destination": "device", "destination_name": "127.0.0.1"}
    assert env.client.get("/api/oauth/requests/made-up").status_code == 404


def test_a_web_destination_shows_its_port(env):
    _, challenge = _pkce()
    uri = "https://agent.example:8443/cb"
    request_code = env.consent(env.register(uris=[uri]), challenge, redirect_uri=uri)
    described = env.client.get(f"/api/oauth/requests/{request_code}").json()
    assert (described["destination"], described["destination_name"]) == ("web", "agent.example:8443")


def test_declining_sends_the_agent_access_denied_and_spends_the_request(env):
    _, challenge = _pkce()
    request_code = env.consent(env.register(), challenge)
    res = env.client.post(f"/api/oauth/requests/{request_code}/deny")
    back = _query(res.json()["redirect_to"])
    assert (back["error"], back["state"]) == ("access_denied", "st-1")
    assert env.client.get(f"/api/oauth/requests/{request_code}").status_code == 404


def test_allowing_needs_a_signed_in_person_and_not_a_guest(env):
    _, challenge = _pkce()
    request_code = env.consent(env.register(), challenge)
    assert env.client.post(f"/api/oauth/requests/{request_code}/approve").status_code == 401
    env.signed_in = env.user(guest_email(uuid.uuid4().hex))
    assert env.client.post(f"/api/oauth/requests/{request_code}/approve").status_code == 403
    env.signed_in = env.user("ana@acme.example")
    answer = env.allow(request_code)
    assert (answer["state"], answer["iss"]) == ("st-1", API)
    assert env.client.post(f"/api/oauth/requests/{request_code}/approve").status_code == 404, "spent"


# -- the exchange ---------------------------------------------------------------------

def test_signing_in_mints_an_mcp_token_that_works_on_mcp(env):
    _, tokens = env.sign_in(env.user("ana@acme.example"))
    assert tokens["token_type"] == "Bearer" and tokens["expires_in"] == 3600
    assert tokens["access_token"].startswith(TOKEN_PREFIX)
    assert tokens["refresh_token"].startswith(REFRESH_PREFIX)
    assert env.ping(tokens["access_token"]).status_code == 200
    stored = env.session.execute(select(McpToken)).scalar_one()
    assert tokens["access_token"] not in str(stored.__dict__) and tokens["refresh_token"] not in str(stored.__dict__)


def test_a_code_is_spent_once_and_only_by_the_client_that_committed_to_it(env):
    env.signed_in = env.user("ana@acme.example")
    client_id, other = env.register(), env.register("Something Else")
    verifier, challenge = _pkce()

    code = env.allow(env.consent(client_id, challenge))["code"]
    assert env.exchange(client_id, code, _pkce()[0]).json()["error"] == "invalid_grant"
    assert env.exchange(client_id, code, verifier).json()["error"] == "invalid_grant", "a failed try spends it"

    code = env.allow(env.consent(client_id, challenge))["code"]
    assert env.exchange(other, code, verifier).json()["error"] == "invalid_grant"

    code = env.allow(env.consent(client_id, challenge))["code"]
    assert env.exchange(client_id, code, verifier, redirect_uri="http://127.0.0.1:1/x").json()["error"] == "invalid_grant"

    code = env.allow(env.consent(client_id, challenge))["code"]
    assert env.exchange(client_id, code, verifier).status_code == 200
    assert env.exchange(client_id, code, verifier).json()["error"] == "invalid_grant"


def test_a_refresh_token_renews_once_and_only_for_its_client(env):
    client_id, first = env.sign_in(env.user("ana@acme.example"))
    assert env.refresh(env.register(), first["refresh_token"]).json()["error"] == "invalid_grant"

    renewed = env.refresh(client_id, first["refresh_token"])
    assert renewed.status_code == 200, renewed.text
    second = renewed.json()
    assert env.ping(second["access_token"]).status_code == 200
    assert env.ping(first["access_token"]).status_code == 401, "the old access token went with the rotation"
    assert env.refresh(client_id, first["refresh_token"]).json()["error"] == "invalid_grant"


def test_the_person_sees_a_connected_agent_and_disconnecting_it_ends_it(env):
    ana = env.user("ana@acme.example")
    client_id, tokens = env.sign_in(ana, "Codex")
    listed = env.client.get("/api/user/mcp-tokens").json()
    assert [(t["kind"], t["name"], t["hint"]) for t in listed] == [("agent", "Codex", "")]

    assert env.client.delete(f"/api/user/mcp-tokens/{listed[0]['id']}").status_code == 204
    assert env.ping(tokens["access_token"]).status_code == 401
    assert env.refresh(client_id, tokens["refresh_token"]).json()["error"] == "invalid_grant"
    assert env.client.get("/api/user/mcp-tokens").json() == []


def test_connecting_past_the_cap_disconnects_the_least_recently_used(env):
    ana = env.user("ana@acme.example")
    for i in range(MAX_CONNECTED_AGENTS):
        token_service.connect_agent(ana, client_id=f"c{i}", client_name=f"agent {i}", session=env.session)
    env.signed_in = ana
    env.sign_in(ana, "newest")
    names = {t["name"] for t in env.client.get("/api/user/mcp-tokens").json()}
    assert len(names) == MAX_CONNECTED_AGENTS
    assert "newest" in names and "agent 0" not in names
    # Pasted tokens are counted apart, so connecting never costs one.
    assert env.client.post("/api/user/mcp-tokens", json={"name": "CI"}).status_code == 201
