"""Desktop sign-in: the two ways it used to fail silently.

The desktop shell runs the backend as a loopback sidecar on SQLite, a
combination nothing else exercises — the deployment is Postgres and every test
below used to be Postgres-shaped by accident. Both regressions guarded here were
invisible until a user clicked Sign in on a shipped build.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlmodel import Session, SQLModel

from models.auth import OAuthState
from routes import signin
from service.oauthstate import consume_state_for_flows, save_state
from tests.conftest import make_sqlite_engine
from utils.dates import utcnow


class _Cfg:
    """Only the fields the sign-in paths read."""

    def __init__(self, *, duct_local: bool, turnstile_secret_key: str = "") -> None:
        self.duct_local = duct_local
        self.frontend_origin = "http://localhost:3003"
        self.turnstile_secret_key = turnstile_secret_key


def test_oauth_state_round_trips_timezone_aware_on_sqlite(monkeypatch):
    """The bug that broke desktop sign-in for every user who tried it.

    SQLite has no timestamp type: SQLAlchemy drops the offset on write, so
    `expires_at` came back naive and `expires_at <= utcnow()` raised
    `TypeError`. That is not a `SQLAlchemyError`, so the store's fallback never
    caught it — it surfaced as a bare "Internal Server Error" in the user's
    browser, after they had already approved at Google.
    """
    engine = make_sqlite_engine()
    monkeypatch.setattr("service.oauthstate.get_engine", lambda: engine)

    save_state("state-1", "verifier-1", signin.SIGNIN_DESKTOP_FLOW, 300)
    matched_flow, verifier = consume_state_for_flows(
        "state-1", (signin.SIGNIN_FLOW, signin.SIGNIN_DESKTOP_FLOW), 300
    )

    assert matched_flow == signin.SIGNIN_DESKTOP_FLOW
    assert verifier == "verifier-1"


def test_expired_state_is_rejected_rather_than_crashing(monkeypatch):
    """The comparison has to still *work*, not merely stop raising."""
    engine = make_sqlite_engine()
    monkeypatch.setattr("service.oauthstate.get_engine", lambda: engine)

    past = utcnow() - timedelta(seconds=60)
    with Session(engine) as session:
        session.add(
            OAuthState(
                state="stale",
                flow=signin.SIGNIN_DESKTOP_FLOW,
                code_verifier="v",
                issued_at=past - timedelta(seconds=300),
                expires_at=past,
            )
        )
        session.commit()

    assert consume_state_for_flows("stale", (signin.SIGNIN_DESKTOP_FLOW,), 300) == (None, None)


def test_every_persisted_timestamp_is_timezone_aware():
    """Structural guard: a new model must not reach for raw `DateTime` again.

    One naive column is enough to reintroduce the crash above, in a table nobody
    thinks of as auth-related, on a platform CI does not run.
    """
    import models  # noqa: F401 — registers every table on SQLModel.metadata
    from models.columns import _UTCDateTime

    def is_timestamp(type_) -> bool:
        # `python_type` raises NotImplementedError on types that have no Python
        # equivalent (JSON, the UUID variant), so it cannot just be read.
        try:
            return type_.python_type is datetime
        except NotImplementedError:
            return False

    timestamps = [
        (f"{table.name}.{column.name}", column.type)
        for table in SQLModel.metadata.tables.values()
        for column in table.columns
        if is_timestamp(column.type)
    ]
    # Guard the guard: a filter that matches nothing would pass forever.
    assert len(timestamps) > 40, f"expected the schema's timestamp columns, found {timestamps}"

    naive = [name for name, type_ in timestamps if not isinstance(type_, _UTCDateTime)]
    assert not naive, f"declare these with utc_datetime(): {naive}"


def test_desktop_failures_land_on_the_relay_page(monkeypatch):
    """The system browser renders whatever the sidecar returns, so it can't be JSON."""
    monkeypatch.setattr(signin, "get_configs", lambda: _Cfg(duct_local=True))

    response = signin.signin_google_callback(code="", state="")

    assert response.status_code == 307
    assert (
        response.headers["location"]
        == f"http://localhost:3003/desktop-auth?error={signin.SIGNIN_ERROR_EXPIRED}"
    )
    assert response.headers["cache-control"] == "no-store, max-age=0"


def test_web_failures_keep_their_json_contract(monkeypatch):
    """The web app drives this with fetch and shows its own message. Unchanged."""
    monkeypatch.setattr(signin, "get_configs", lambda: _Cfg(duct_local=False))

    with pytest.raises(HTTPException) as excinfo:
        signin.signin_google_callback(code="", state="")

    assert excinfo.value.status_code == 400


def test_an_unexpected_crash_is_still_an_explainable_page(monkeypatch):
    """The catch-all: whatever breaks next, the user does not get a dead page."""
    monkeypatch.setattr(signin, "get_configs", lambda: _Cfg(duct_local=True))
    monkeypatch.setattr(
        signin,
        "consume_state_for_flows",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    response = signin.signin_google_callback(code="c", state="s")

    assert response.status_code == 307
    assert response.headers["location"].endswith(f"?error={signin.SIGNIN_ERROR_SERVER}")


# --- Turnstile and the desktop flow ---------------------------------------
#
# Turnstile is a widget on the hosted login page. The desktop shell opens the
# system browser straight at /authorize, so it has no widget and no token —
# which meant sign-in died with "Turnstile token required." the moment a
# sidecar was pointed at an env that configures Turnstile.


async def _authorize(client: str = "") -> object:
    request = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))
    return await signin.signin_google_authorize(request, turnstile_token="", client=client)


@pytest.mark.asyncio
async def test_loopback_sidecar_does_not_require_turnstile(monkeypatch):
    monkeypatch.setattr(
        signin, "get_configs", lambda: _Cfg(duct_local=True, turnstile_secret_key="secret")
    )
    # Past the Turnstile gate, the next step is building the Google flow; with no
    # client configured that fails as a *config* error, which is proof enough
    # that the challenge no longer blocks the request.
    monkeypatch.setattr(
        signin,
        "create_google_signin_flow",
        lambda **_: (_ for _ in ()).throw(ValueError("no client")),
    )

    response = await _authorize(client="desktop")

    assert response.headers["location"].endswith(f"?error={signin.SIGNIN_ERROR_CONFIG}")


@pytest.mark.asyncio
async def test_hosted_api_still_requires_turnstile(monkeypatch):
    monkeypatch.setattr(
        signin, "get_configs", lambda: _Cfg(duct_local=False, turnstile_secret_key="secret")
    )

    with pytest.raises(HTTPException) as excinfo:
        await _authorize()

    assert excinfo.value.status_code == 400


@pytest.mark.asyncio
async def test_client_desktop_cannot_be_used_to_skip_turnstile(monkeypatch):
    """`client` is caller-supplied. Keying the exemption on it would let anyone
    bypass the challenge on the hosted API by appending it to the URL."""
    monkeypatch.setattr(
        signin, "get_configs", lambda: _Cfg(duct_local=False, turnstile_secret_key="secret")
    )

    with pytest.raises(HTTPException) as excinfo:
        await _authorize(client="desktop")

    assert excinfo.value.status_code == 400
