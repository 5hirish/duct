"""The onboarding sign-in bundle: one consent, signed in with a source.

Three properties, each of which fails silently if broken:

* the bundle is asked for **by name on one flow** — a plain sign-in is
  byte-for-byte what it was, and an unknown name is ignored rather than
  honoured;
* what is stored is what Google **granted**, never what was requested —
  untick both boxes and the sign-in still completes with nothing stored;
* the bundle is **read scopes only**. A write scope arriving here would ride
  every onboarding consent screen with no justification on it.

SQLite in memory, Google stubbed. No network.
"""

from __future__ import annotations

from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest
from cryptography.fernet import Fernet
from sqlmodel import Session, select

import service.credentials as credentials_service
import service.signin_sources as signin_sources
import service.user_store as user_store
from models.auth import User
from models.connector import ConnectorCredential
from routes import signin
from service import auth_exchange, oauthstate
from service.connector_scopes import READ, SCOPE_CATALOG
from service.credentials import decrypt_credentials
from service.google.constants import GA4_READ_SCOPE, GSC_READ_SCOPE
from service.oauthstate import consume_state_full
from tests.conftest import make_sqlite_engine

FERNET_KEY = Fernet.generate_key().decode()
IDENTITY = (
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
)


class _Cfg:
    def __init__(self, *, duct_local: bool = False) -> None:
        self.duct_local = duct_local
        self.frontend_origin = "https://app.getduct.ai"
        self.turnstile_secret_key = ""
        self.jwt_secret = "x" * 40
        self.google_oauth_client_id = "client-id"
        self.credentials_encryption_key = FERNET_KEY


class _Flow:
    """Stand-in for google-auth's Flow: records what it was asked and answers
    with a fixed grant. ``granted`` is what the token response says, which is
    the only honest source — ``credentials.granted_scopes`` is never set."""

    built_with: list[dict] = []

    def __init__(self, *, granted: tuple[str, ...], refresh_token: str | None = "rt-bundle") -> None:
        self.code_verifier = "verifier"
        self.credentials = SimpleNamespace(
            id_token={"sub": "sub-1", "email": "ada@example.com", "name": "Ada", "picture": ""},
            refresh_token=refresh_token,
        )
        self.oauth2session = SimpleNamespace(token={"scope": list(granted)})
        self.authorize_kwargs: dict = {}

    def authorization_url(self, **kwargs):
        self.authorize_kwargs = kwargs
        return "https://accounts.google.com/o/oauth2/auth?x=1", "state"

    def fetch_token(self, **_):
        return None


@pytest.fixture
def engine(monkeypatch):
    engine = make_sqlite_engine(drop_partial_indexes=True)
    monkeypatch.setattr(user_store, "get_engine", lambda: engine)
    monkeypatch.setattr(signin_sources, "get_engine", lambda: engine)
    monkeypatch.setattr("service.oauthstate.get_engine", lambda: None)
    monkeypatch.setattr("service.oauthstate._memory_states", {}, raising=False)
    monkeypatch.setattr(auth_exchange, "_store", {})
    cfg = _Cfg()
    monkeypatch.setattr(signin, "get_configs", lambda: cfg)
    monkeypatch.setattr(credentials_service, "get_configs", lambda: cfg)
    return engine


def _stub_google(monkeypatch, flow: _Flow) -> _Flow:
    calls: list[dict] = []

    def build(**kwargs):
        calls.append(kwargs)
        return flow

    monkeypatch.setattr(signin, "create_google_signin_flow", build)
    flow.built_with = calls
    return flow


async def _authorize(**query) -> object:
    request = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))
    # Called directly, so FastAPI's `Query` defaults are not applied.
    params = {"client": "", "link": "", "sources": "", **query}
    return await signin.signin_google_authorize(request, turnstile_token="", **params)


def _state() -> str:
    return next(iter(oauthstate._memory_states))


def _rows(engine) -> dict[str, ConnectorCredential]:
    with Session(engine) as db:
        return {r.connector_type: r for r in db.execute(select(ConnectorCredential)).scalars()}


# --- asking ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_bundle_adds_the_read_scopes_and_an_offline_grant(monkeypatch, engine):
    flow = _stub_google(monkeypatch, _Flow(granted=IDENTITY))

    await _authorize(sources="onboarding")

    assert flow.built_with[0]["scopes"] == [*IDENTITY, GSC_READ_SCOPE, GA4_READ_SCOPE]
    # No refresh token without these — and consent is forced because an
    # account that approved Duct before would otherwise get none.
    assert flow.authorize_kwargs["access_type"] == "offline"
    assert "consent" in flow.authorize_kwargs["prompt"]
    consumed = consume_state_full(_state(), signin.SIGNIN_FLOWS, 300)
    assert consumed.flow == signin.SIGNIN_SOURCES_FLOW


@pytest.mark.asyncio
async def test_a_plain_signin_is_unchanged(monkeypatch, engine):
    """The default path must not know the bundle exists."""
    flow = _stub_google(monkeypatch, _Flow(granted=IDENTITY))

    await _authorize()

    assert flow.built_with[0]["scopes"] is None
    assert flow.authorize_kwargs["access_type"] == "online"
    assert flow.authorize_kwargs["prompt"] == "select_account"
    assert consume_state_full(_state(), signin.SIGNIN_FLOWS, 300).flow == signin.SIGNIN_FLOW


@pytest.mark.asyncio
async def test_an_unknown_bundle_name_is_identity_only(monkeypatch, engine):
    """`sources` is caller-supplied. The only thing it can name is the one
    bundle; anything else must not become a way to request scopes."""
    flow = _stub_google(monkeypatch, _Flow(granted=IDENTITY))

    await _authorize(sources="gsc,ga4,adwords")

    assert flow.built_with[0]["scopes"] is None
    assert consume_state_full(_state(), signin.SIGNIN_FLOWS, 300).flow == signin.SIGNIN_FLOW


@pytest.mark.asyncio
async def test_the_desktop_bundle_still_comes_home_through_the_relay(monkeypatch, engine):
    _stub_google(monkeypatch, _Flow(granted=(*IDENTITY, GSC_READ_SCOPE, GA4_READ_SCOPE)))

    await _authorize(sources="onboarding", client="desktop")
    response = signin.signin_google_callback(code="c", state=_state())

    assert response.headers["location"].startswith("https://app.getduct.ai/desktop-auth?auth_code=")
    assert set(_rows(engine)) == {"gsc", "ga4"}


# --- storing what was granted ----------------------------------------------


@pytest.mark.asyncio
async def test_the_callback_stores_one_row_per_granted_source(monkeypatch, engine):
    _stub_google(monkeypatch, _Flow(granted=(*IDENTITY, GSC_READ_SCOPE, GA4_READ_SCOPE)))

    await _authorize(sources="onboarding")
    response = signin.signin_google_callback(code="c", state=_state())

    assert response.status_code == 307
    assert response.headers["location"].startswith("https://app.getduct.ai/?auth_code=")
    # The token itself never rides the URL.
    assert "rt-bundle" not in response.headers["location"]

    rows = _rows(engine)
    assert set(rows) == {"gsc", "ga4"}
    with Session(engine) as db:
        user = db.execute(select(User).where(User.email == "ada@example.com")).scalars().one()
    for connector_id, scope in (("gsc", GSC_READ_SCOPE), ("ga4", GA4_READ_SCOPE)):
        row = rows[connector_id]
        assert row.user_id == user.id
        # Each row records its own grant, exactly as the per-connector flow would.
        assert row.granted_scopes == scope
        assert decrypt_credentials(row.credentials_enc) == {"refresh_token": "rt-bundle"}


@pytest.mark.asyncio
async def test_a_partial_grant_stores_only_what_was_ticked(monkeypatch, engine):
    _stub_google(monkeypatch, _Flow(granted=(*IDENTITY, GSC_READ_SCOPE)))

    await _authorize(sources="onboarding")
    signin.signin_google_callback(code="c", state=_state())

    assert set(_rows(engine)) == {"gsc"}


@pytest.mark.asyncio
async def test_declining_every_box_is_still_a_complete_signin(monkeypatch, engine):
    """The bundle is an offer, not a condition."""
    _stub_google(monkeypatch, _Flow(granted=IDENTITY))

    await _authorize(sources="onboarding")
    response = signin.signin_google_callback(code="c", state=_state())

    assert response.headers["location"].startswith("https://app.getduct.ai/?auth_code=")
    code = parse_qs(urlparse(response.headers["location"]).query)["auth_code"][0]
    assert signin.exchange_auth_code(code=code)["token"]
    assert _rows(engine) == {}


@pytest.mark.asyncio
async def test_no_refresh_token_means_nothing_stored_and_no_error(monkeypatch, engine):
    """A scope without a refresh token is unusable by a scheduled run, and
    storing it would show a green card over a credential that dies in an hour."""
    _stub_google(monkeypatch, _Flow(granted=(*IDENTITY, GSC_READ_SCOPE), refresh_token=None))

    await _authorize(sources="onboarding")
    response = signin.signin_google_callback(code="c", state=_state())

    assert response.status_code == 307
    assert _rows(engine) == {}


@pytest.mark.asyncio
async def test_a_storage_failure_never_fails_the_signin(monkeypatch, engine):
    """By the time this runs the user has approved at Google; an error page
    here would strand them after the one step that cannot be retried."""
    _stub_google(monkeypatch, _Flow(granted=(*IDENTITY, GSC_READ_SCOPE)))
    monkeypatch.setattr(
        signin_sources, "upsert_credential", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db"))
    )

    await _authorize(sources="onboarding")
    response = signin.signin_google_callback(code="c", state=_state())

    assert response.headers["location"].startswith("https://app.getduct.ai/?auth_code=")


# --- the bundle's shape ------------------------------------------------------


def test_the_bundle_is_read_scopes_only():
    """Structural guard. A write scope in the bundle would ride every
    onboarding consent screen with no justification beside it."""
    for connector_id, scope in signin_sources.BUNDLE_SOURCES.items():
        info = SCOPE_CATALOG[scope]
        assert info.access == READ, f"{connector_id}: {scope} is a write scope"


def test_granted_sources_reads_the_grant_not_the_request():
    assert signin_sources.granted_sources(f"{GA4_READ_SCOPE} openid") == ["ga4"]
    assert signin_sources.granted_sources("") == []
    assert signin_sources.granted_sources(None) == []
