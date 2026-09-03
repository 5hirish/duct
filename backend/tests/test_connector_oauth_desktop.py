"""Connector OAuth in the system browser — the desktop half of `routes/auth.py`.

Google refuses OAuth inside an embedded webview, so connecting a data source
from the desktop shell runs in the user's own browser and has to find its way
back into the app. That path has two properties nothing else in the suite
covers, and both fail silently if broken: the refresh token must never appear in
the deep-link URL, and a failure must land on a page the user can read rather
than as JSON in a browser tab outside the app.
"""

from __future__ import annotations

import pytest
from urllib.parse import parse_qs, urlparse
from fastapi import HTTPException

# Connectors register themselves on import; the routes resolve them by id.
import service.google.ads  # noqa: F401 — registers connector
import service.google.ga4  # noqa: F401
import service.google.gsc  # noqa: F401
import service.google.gtm  # noqa: F401
from routes import auth
from service import auth_exchange, oauthstate
from service.oauthstate import consume_state_for_flows


class _Cfg:
    """Only the fields the connector OAuth paths read."""

    def __init__(self, *, duct_local: bool = False) -> None:
        self.duct_local = duct_local
        self.frontend_origin = "https://app.getduct.ai"


class _Credentials:
    def __init__(self, refresh_token: str) -> None:
        self.refresh_token = refresh_token


GA4_READ = "https://www.googleapis.com/auth/analytics.readonly"


class _Session:
    """The oauth2 session, which is where the GRANTED scopes actually live.

    Not `flow.credentials.granted_scopes`: the installed google-auth-oauthlib
    does not populate that, so the token response is the only honest source.
    """

    def __init__(self, granted: tuple[str, ...]) -> None:
        self.token = {"scope": list(granted)}


class _Flow:
    """Stand-in for the google-auth Flow — the network is not what's under test."""

    def __init__(
        self,
        *,
        refresh_token: str = "rt-live",
        granted: tuple[str, ...] = ("https://www.googleapis.com/auth/analytics.readonly",),
    ) -> None:
        self.code_verifier = "verifier"
        self.credentials = _Credentials(refresh_token)
        self.oauth2session = _Session(granted)

    def authorization_url(self, **_):
        return "https://accounts.google.com/o/oauth2/auth?x=1", "state"

    def fetch_token(self, **_):
        return None


@pytest.fixture
def memory_state(monkeypatch):
    """Force the OAuth state store onto its in-memory path (no DB in this test)."""
    monkeypatch.setattr("service.oauthstate.get_engine", lambda: None)
    monkeypatch.setattr("service.oauthstate._memory_states", {}, raising=False)


@pytest.fixture(autouse=True)
def clean_exchange_store(monkeypatch):
    monkeypatch.setattr(auth_exchange, "_store", {})


def _stub_google(monkeypatch, flow: _Flow) -> None:
    monkeypatch.setattr(auth, "create_google_oauth_flow", lambda **_: flow)


# --- authorize ------------------------------------------------------------


def test_desktop_authorize_marks_the_flow_as_desktop(monkeypatch, memory_state):
    """`client=desktop` is the only thing that distinguishes the two paths, and
    it has to survive the round trip to Google in the state store."""
    monkeypatch.setattr(auth, "get_configs", lambda: _Cfg())
    _stub_google(monkeypatch, _Flow())

    response = auth.connector_oauth_authorize("ga4", client="desktop")

    assert response.status_code == 307
    assert response.headers["location"].startswith("https://accounts.google.com/")

    states = list(oauthstate._memory_states)
    assert len(states) == 1
    matched, _ = consume_state_for_flows(states[0], auth.GOOGLE_CONNECTOR_FLOWS, 300)
    assert matched == auth.CONNECTOR_FLOW_GA4 + auth.DESKTOP_FLOW_SUFFIX


def test_browser_authorize_is_unchanged(monkeypatch, memory_state):
    monkeypatch.setattr(auth, "get_configs", lambda: _Cfg())
    _stub_google(monkeypatch, _Flow())

    auth.connector_oauth_authorize("ga4")

    states = list(oauthstate._memory_states)
    matched, _ = consume_state_for_flows(states[0], auth.GOOGLE_CONNECTOR_FLOWS, 300)
    assert matched == auth.CONNECTOR_FLOW_GA4


# --- callback -------------------------------------------------------------


def test_desktop_callback_never_puts_the_refresh_token_in_the_url(monkeypatch, memory_state):
    """The whole point of the code exchange. A deep link is handled by whatever
    app claims the scheme, so a long-lived credential must not be in one."""
    monkeypatch.setattr(auth, "get_configs", lambda: _Cfg(duct_local=True))
    _stub_google(monkeypatch, _Flow(refresh_token="super-secret-refresh-token"))

    auth.connector_oauth_authorize("gsc", client="desktop")
    state = next(iter(oauthstate._memory_states))

    response = auth.google_oauth_callback_short_path(code="oauth-code", state=state)

    location = response.headers["location"]
    assert response.status_code == 307
    assert location.startswith("https://app.getduct.ai/desktop-auth?connector=gsc&auth_code=")
    assert "super-secret-refresh-token" not in location
    assert response.headers["cache-control"] == "no-store, max-age=0"

    code = location.split("auth_code=")[1]
    assert auth.exchange_connector_code(code=code) == {
        "connector_type": "gsc",
        "refresh_token": "super-secret-refresh-token",
        "granted_scopes": "https://www.googleapis.com/auth/analytics.readonly",
    }


def test_browser_callback_still_returns_the_token_in_the_fragment(monkeypatch, memory_state):
    """The web app's contract is untouched — the fragment never reaches a server."""
    monkeypatch.setattr(auth, "get_configs", lambda: _Cfg())
    _stub_google(monkeypatch, _Flow(refresh_token="rt-web"))

    auth.connector_oauth_authorize("ga4")
    state = next(iter(oauthstate._memory_states))

    response = auth.google_oauth_callback_short_path(code="oauth-code", state=state)

    location = response.headers["location"]
    assert location.startswith("https://app.getduct.ai/connections#ga4_refresh_token=rt-web")
    # The grant rides beside the token. Not a secret, and the browser needs it
    # to store what was actually consented to rather than what we asked for.
    fragment = parse_qs(urlparse(location).fragment)
    assert fragment["granted_scopes"] == [
        "https://www.googleapis.com/auth/analytics.readonly"
    ]


def test_a_partial_grant_is_recorded_rather_than_assumed(monkeypatch, memory_state):
    """GA4 asks for analytics.readonly AND analytics.edit. Someone who grants
    only the first must still connect — and what they withheld has to survive to
    the browser, or the card goes green over permissions we do not hold."""
    monkeypatch.setattr(auth, "get_configs", lambda: _Cfg())
    _stub_google(monkeypatch, _Flow(refresh_token="rt-partial", granted=(GA4_READ,)))

    auth.connector_oauth_authorize("ga4")
    state = next(iter(oauthstate._memory_states))

    response = auth.google_oauth_callback_short_path(code="oauth-code", state=state)

    fragment = parse_qs(urlparse(response.headers["location"]).fragment)
    assert fragment["granted_scopes"] == [GA4_READ]
    assert "analytics.edit" not in fragment["granted_scopes"][0]


def test_an_unreadable_grant_never_fails_the_connect(monkeypatch, memory_state):
    """A flow object that cannot report its scopes is a degraded answer, not a
    dead connect: the token is what the user came for."""
    monkeypatch.setattr(auth, "get_configs", lambda: _Cfg())
    flow = _Flow(refresh_token="rt-noscope")
    del flow.oauth2session
    _stub_google(monkeypatch, flow)

    auth.connector_oauth_authorize("ga4")
    state = next(iter(oauthstate._memory_states))

    response = auth.google_oauth_callback_short_path(code="oauth-code", state=state)

    location = response.headers["location"]
    assert "ga4_refresh_token=rt-noscope" in location
    # keep_blank_values: an empty grant is the whole point of this case, and
    # parse_qs drops blanks by default.
    fragment = parse_qs(urlparse(location).fragment, keep_blank_values=True)
    assert fragment["granted_scopes"] == [""]


def test_the_exchange_code_is_single_use(monkeypatch, memory_state):
    monkeypatch.setattr(auth, "get_configs", lambda: _Cfg(duct_local=True))
    _stub_google(monkeypatch, _Flow())

    auth.connector_oauth_authorize("gtm", client="desktop")
    state = next(iter(oauthstate._memory_states))
    response = auth.google_oauth_callback_short_path(code="oauth-code", state=state)
    code = response.headers["location"].split("auth_code=")[1]

    auth.exchange_connector_code(code=code)
    with pytest.raises(HTTPException) as excinfo:
        auth.exchange_connector_code(code=code)
    assert excinfo.value.status_code == 400


def test_a_connector_code_cannot_be_redeemed_as_a_session_token():
    """Namespacing, not decoration: `/auth/exchange` hands back whatever it finds
    as the caller's JWT. A connector refresh token must not be findable there."""
    code = auth_exchange.store_connector_code(connector_type="ga4", refresh_token="rt")

    assert auth_exchange.consume_exchange_code(code) is None
    # And a rejected cross-namespace read must not burn the code for its owner.
    assert auth_exchange.consume_connector_code(code) == {
        "connector_type": "ga4",
        "refresh_token": "rt",
        "granted_scopes": "",
    }


def test_a_signin_code_cannot_be_redeemed_as_connector_credentials():
    code = auth_exchange.store_exchange_code("a.jwt.value")

    assert auth_exchange.consume_connector_code(code) is None
    assert auth_exchange.consume_exchange_code(code) == "a.jwt.value"


# --- failures -------------------------------------------------------------


def test_desktop_failures_land_on_the_relay_page(monkeypatch, memory_state):
    """The system browser renders whatever the sidecar returns, so it can't be JSON."""
    monkeypatch.setattr(auth, "get_configs", lambda: _Cfg(duct_local=True))

    response = auth.google_oauth_callback_short_path(code="", state="")

    assert response.status_code == 307
    assert response.headers["location"] == (
        f"https://app.getduct.ai/desktop-auth?connector=&error={auth.CONNECT_ERROR_EXPIRED}"
    )


def test_web_failures_keep_their_json_contract(monkeypatch, memory_state):
    monkeypatch.setattr(auth, "get_configs", lambda: _Cfg(duct_local=False))

    with pytest.raises(HTTPException) as excinfo:
        auth.google_oauth_callback_short_path(code="", state="")

    assert excinfo.value.status_code == 400


def test_missing_consent_is_explained_rather_than_crashing(monkeypatch, memory_state):
    """Google returns no refresh token when the account has approved before —
    the single most likely real failure, and the one worth naming."""
    monkeypatch.setattr(auth, "get_configs", lambda: _Cfg(duct_local=True))
    _stub_google(monkeypatch, _Flow(refresh_token=""))

    auth.connector_oauth_authorize("google_ads", client="desktop")
    state = next(iter(oauthstate._memory_states))

    response = auth.google_oauth_callback_short_path(code="oauth-code", state=state)

    assert response.headers["location"].endswith(f"&error={auth.CONNECT_ERROR_CONSENT}")
    assert "connector=google_ads" in response.headers["location"]


def test_an_unexpected_crash_is_still_an_explainable_page(monkeypatch, memory_state):
    monkeypatch.setattr(auth, "get_configs", lambda: _Cfg(duct_local=True))
    monkeypatch.setattr(
        auth,
        "consume_state_for_flows",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    response = auth.google_oauth_callback_short_path(code="c", state="s")

    assert response.status_code == 307
    assert response.headers["location"].endswith(f"error={auth.CONNECT_ERROR_SERVER}")
