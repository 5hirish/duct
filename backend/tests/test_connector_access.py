"""Connector access + discovery — the layer that replaces the insights wizard.

The wizard's first four steps existed because the backend could not answer
"what is this project connected to?" or ask for what was missing. These pin the
answers:

  * an inventory that reports the full registry, including what is NOT connected
    — that absence is what becomes an offer to connect;
  * credentials that resolve server-side by the SAME ladder as writes, so an
    agent with no browser (a scheduled brief, a mid-run discovery) can read;
  * a choice, once made, that persists as a project binding so no later session
    asks again.

No network: the adapters are never reached, and the one test that would need a
provider asserts the failure path instead.
"""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet
from sqlmodel import Session

import service.credentials as credentials_service
from config import Configs
from models.auth import User
from models.connector import ConnectorCredential, ProjectConnector
from models.project import Project
from service import connector_access
from service.connector_access import (
    STATUS_AVAILABLE,
    STATUS_BOUND,
    STATUS_NOT_CONNECTED,
    attach_account,
    bind_project_account,
    get_data_source,
    list_data_sources,
    resolve_read_credentials,
)
from tests.conftest import make_sqlite_engine

FERNET_KEY = Fernet.generate_key().decode()


@pytest.fixture
def db():
    engine = make_sqlite_engine(drop_partial_indexes=True)
    with Session(engine) as session:
        yield session


@pytest.fixture
def cfg(monkeypatch):
    config = Configs(
        credentials_encryption_key=FERNET_KEY,
        google_ads_developer_token="env-dev-token",
        google_oauth_client_id="env-client-id",
        google_oauth_client_secret="env-client-secret",
    )
    monkeypatch.setattr(credentials_service, "get_configs", lambda: config)
    monkeypatch.setattr(connector_access, "get_configs", lambda: config, raising=False)
    import config as config_module

    monkeypatch.setattr(config_module, "get_configs", lambda: config)
    return config


@pytest.fixture
def user(db):
    row = User(email="access@example.com")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@pytest.fixture
def project(db, user):
    row = Project(name="Acme", user_id=user.id)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _store(db, user, connector_type, account_id, data, account_name=""):
    row = ConnectorCredential(
        user_id=user.id,
        connector_type=connector_type,
        account_id=account_id,
        account_name=account_name,
        credentials_enc=credentials_service.encrypt_credentials(data),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _source(db, user, project, connector_id):
    return get_data_source(db, connector_id, user_id=user.id, project_id=project.id)


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------

def test_inventory_reports_what_is_not_connected(db, user, project, cfg):
    """"Not connected" is the most useful answer here — it is what the agent
    turns into an offer. An inventory of only what exists could not do that."""
    sources = list_data_sources(db, user_id=user.id, project_id=project.id)

    ids = {s.connector_id for s in sources}
    assert {"google_ads", "ga4", "gsc"} <= ids
    assert all(s.status == STATUS_NOT_CONNECTED for s in sources)


def test_stored_but_unbound_is_available_not_bound(db, user, project, cfg):
    """Authorized is not the same as chosen — the distinction is what tells the
    agent to call SelectAccount rather than RequestConnection."""
    _store(db, user, "google_ads", "111", {"refresh_token": "t"}, account_name="Acme Ads")

    source = _source(db, user, project, "google_ads")

    assert source.status == STATUS_AVAILABLE
    assert source.account_id == "111"


def test_binding_wins_and_reports_the_account(db, user, project, cfg):
    row = _store(db, user, "ga4", "222", {"refresh_token": "t"}, account_name="Acme GA4")
    db.add(ProjectConnector(
        project_id=project.id, connector_type="ga4", connector_credential_id=row.id,
    ))
    db.commit()

    source = _source(db, user, project, "ga4")

    assert source.status == STATUS_BOUND
    assert (source.account_id, source.account_name) == ("222", "Acme GA4")


def test_ready_sources_sort_first(db, user, project, cfg):
    """The agent reads this list top-down; what it can use now belongs at the top."""
    row = _store(db, user, "gsc", "https://acme.com", {"refresh_token": "t"})
    db.add(ProjectConnector(
        project_id=project.id, connector_type="gsc", connector_credential_id=row.id,
    ))
    _store(db, user, "stripe", "acct_1", {"api_key": "rk_x"})
    db.commit()

    statuses = [s.status for s in list_data_sources(db, user_id=user.id, project_id=project.id)]

    assert statuses[0] == STATUS_BOUND
    assert statuses[1] == STATUS_AVAILABLE


def test_inventory_flags_manual_credential_connectors(db, user, project, cfg):
    """Stripe has no OAuth scope, so there is no link to offer — the agent has
    to phrase that ask differently, so it needs to know."""
    by_id = {s.connector_id: s for s in list_data_sources(db, user_id=user.id, project_id=project.id)}

    assert by_id["stripe"].auth_kind == "manual"
    assert by_id["google_ads"].auth_kind == "oauth"


def test_inventory_reports_catalog_coverage(db, user, project, cfg):
    """Whether the entity catalog covers a connector decides what the agent can
    actually analyse with it, so it travels with the source."""
    by_id = {s.connector_id: s for s in list_data_sources(db, user_id=user.id, project_id=project.id)}

    assert by_id["google_ads"].has_catalog is True
    assert by_id["stripe"].has_catalog is False


# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------

def test_reads_resolve_server_side_without_a_browser(db, user, project, cfg):
    """The whole reason this exists: an agent that discovers mid-run it needs
    Search Console has no browser to fetch a token from."""
    _store(db, user, "gsc", "", {"refresh_token": "stored-token"})

    creds = resolve_read_credentials(
        db, user_id=user.id, project_id=project.id, connector_type="gsc"
    )

    assert creds["refresh_token"] == "stored-token"
    assert creds["client_id"] == "env-client-id"  # env fills the app's own half


def test_read_credentials_follow_the_project_binding(db, user, project, cfg):
    """Reads and writes must not disagree about which account they mean."""
    _store(db, user, "google_ads", "", {"refresh_token": "user-default"})
    bound = _store(db, user, "google_ads", "999", {"refresh_token": "project-token"})
    db.add(ProjectConnector(
        project_id=project.id, connector_type="google_ads", connector_credential_id=bound.id,
    ))
    db.commit()

    creds = resolve_read_credentials(
        db, user_id=user.id, project_id=project.id, connector_type="google_ads"
    )

    assert creds["refresh_token"] == "project-token"


def test_manual_connector_credentials_come_back_unshaped(db, user, project, cfg):
    """Stripe's blob is not Google-shaped; forcing it into that shape would drop
    the api_key entirely."""
    _store(db, user, "stripe", "", {"api_key": "rk_live_x"})

    creds = resolve_read_credentials(
        db, user_id=user.id, project_id=project.id, connector_type="stripe"
    )

    assert creds == {"api_key": "rk_live_x"}


def test_missing_credentials_are_empty_not_an_error(db, user, project, cfg):
    assert resolve_read_credentials(
        db, user_id=user.id, project_id=project.id, connector_type="ga4"
    ) == {}


# ---------------------------------------------------------------------------
# Choosing an account
# ---------------------------------------------------------------------------

def test_choice_persists_so_the_next_session_does_not_ask(db, user, project, cfg):
    _store(db, user, "google_ads", "111", {"refresh_token": "t"}, account_name="Acme")

    bind_project_account(
        db, project_id=project.id, user_id=user.id,
        connector_type="google_ads", account_id="111",
    )

    assert _source(db, user, project, "google_ads").status == STATUS_BOUND


def test_cannot_bind_an_account_the_caller_does_not_own(db, user, project, cfg):
    """You may offer your own account to a project, never point it at someone
    else's row — the same rule routes/project_connectors.py enforces."""
    other = User(email="someone-else@example.com")
    db.add(other)
    db.commit()
    db.refresh(other)
    _store(db, other, "google_ads", "777", {"refresh_token": "theirs"})

    result = bind_project_account(
        db, project_id=project.id, user_id=user.id,
        connector_type="google_ads", account_id="777",
    )

    assert result is None
    assert _source(db, user, project, "google_ads").status == STATUS_NOT_CONNECTED


def test_picking_an_account_after_oauth_writes_the_row_the_ui_would(db, user, project, cfg):
    """After OAuth there is one account-agnostic row. Choosing a property must
    leave exactly the state the Connections page would have written, so the two
    paths cannot drift apart."""
    _store(db, user, "ga4", "", {"refresh_token": "oauth-token"})

    attach_account(
        db, project_id=project.id, user_id=user.id,
        connector_type="ga4", account_id="333", account_name="Acme Web",
    )

    source = _source(db, user, project, "ga4")
    assert (source.status, source.account_id, source.account_name) == (
        STATUS_BOUND, "333", "Acme Web",
    )
    # The secret was copied, not re-requested — the user does not sign in twice.
    assert resolve_read_credentials(
        db, user_id=user.id, project_id=project.id, connector_type="ga4"
    )["refresh_token"] == "oauth-token"


def test_attaching_an_account_with_nothing_authorized_is_refused(db, user, project, cfg):
    assert attach_account(
        db, project_id=project.id, user_id=user.id,
        connector_type="ga4", account_id="333",
    ) is None


# ---------------------------------------------------------------------------
# The tools — pause, skip, and the questions that must never be asked
# ---------------------------------------------------------------------------

import asyncio  # noqa: E402
import uuid  # noqa: E402

from agents.core.connector_tools import _request_connection, _select_account  # noqa: E402
from agents.core.events import AgentEvent  # noqa: E402
from agents.core.session import make_future_pause  # noqa: E402
from agents.insights.schema import create_insights_session  # noqa: E402


@pytest.fixture
def bridge(db, monkeypatch):
    """A live session plus an emit that records, with the tools' DB work pointed
    at the test's in-memory database."""
    class _Ctx:
        def __init__(self):
            self.session = create_insights_session(str(uuid.uuid4()))
            self.events: list[dict] = []

        async def emit(self, event: dict) -> None:
            self.events.append(dict(event))

        async def answer(self, payload: dict, timeout: float = 2.0) -> None:
            """Resolve whatever the session is parked on, once it parks."""
            deadline = asyncio.get_event_loop().time() + timeout
            while self.session.answer_future is None:
                if asyncio.get_event_loop().time() > deadline:
                    raise AssertionError("the tool never parked on a future")
                await asyncio.sleep(0.01)
            self.session.answer_future.set_result(payload)

    class _Scoped:
        def __init__(self, s):
            self._s = s

        def __enter__(self):
            return self._s

        def __exit__(self, *a):
            return False

    def _fake_session_gen():
        yield _Scoped(db).__enter__()

    monkeypatch.setattr("db.session.get_session", lambda: _fake_session_gen())
    return _Ctx()


def _kwargs(ctx, user, project):
    """The tool bodies on the in-process pause — the binder's default, spelled
    out so the test drives the same Future the messages route resolves."""
    return dict(
        user_id=user.id, project_id=project.id,
        pause=make_future_pause(
            ctx.session, ctx.session.session_id, ctx.emit, log_prefix="test"
        ),
    )


async def test_one_candidate_is_never_a_question(db, user, project, cfg, bridge):
    """Being asked to choose from a list of one is exactly how a wizard feels.
    A single stored account binds silently."""
    _store(db, user, "google_ads", "111", {"refresh_token": "t"}, account_name="Acme")

    result = await _select_account("google_ads", "", **_kwargs(bridge, user, project))

    assert result["status"] == "selected"
    assert result["account_id"] == "111"
    assert bridge.events == []  # the user was never interrupted


async def test_several_candidates_ask_and_then_persist(db, user, project, cfg, bridge):
    _store(db, user, "google_ads", "111", {"refresh_token": "t"}, account_name="Acme")
    _store(db, user, "google_ads", "222", {"refresh_token": "t"}, account_name="Acme EU")

    task = asyncio.create_task(
        _select_account("google_ads", "", **_kwargs(bridge, user, project))
    )
    await bridge.answer({"account_id": "222", "account_name": "Acme EU"})
    result = await task

    assert bridge.events[0]["event"] == AgentEvent.ACCOUNT_SELECTION_REQUIRED
    assert {c["account_id"] for c in bridge.events[0]["candidates"]} == {"111", "222"}
    assert result["status"] == "selected"
    # Persisted, so the next session does not ask again.
    assert _source(db, user, project, "google_ads").account_id == "222"


async def test_declining_an_account_tells_the_agent_to_carry_on(db, user, project, cfg, bridge):
    """A skip is an answer, not a failure — and the model is told not to re-ask."""
    _store(db, user, "google_ads", "111", {"refresh_token": "t"})
    _store(db, user, "google_ads", "222", {"refresh_token": "t"})

    task = asyncio.create_task(
        _select_account("google_ads", "", **_kwargs(bridge, user, project))
    )
    await bridge.answer({})
    result = await task

    assert result["status"] == "skipped"
    assert "Do not ask again" in result["message"]


async def test_already_bound_does_not_interrupt(db, user, project, cfg, bridge):
    row = _store(db, user, "ga4", "333", {"refresh_token": "t"}, account_name="Web")
    db.add(ProjectConnector(
        project_id=project.id, connector_type="ga4", connector_credential_id=row.id,
    ))
    db.commit()

    result = await _select_account("ga4", "", **_kwargs(bridge, user, project))

    assert result["status"] == "already_selected"
    assert bridge.events == []


async def test_connection_request_offers_a_link_and_a_reason(db, user, project, cfg, bridge):
    """The reason is what the user reads beside the button, so it must reach the
    event — and an OAuth connector must carry the path that starts the sign-in."""
    task = asyncio.create_task(
        _request_connection(
            "gsc", "to see which queries lost clicks", **_kwargs(bridge, user, project)
        )
    )
    await bridge.answer({"skipped": True})
    await task

    event = bridge.events[0]
    assert event["event"] == AgentEvent.CONNECTION_REQUIRED
    assert event["reason"] == "to see which queries lost clicks"
    assert event["authorize_path"] == "/auth/connectors/gsc/oauth/authorize"
    assert event["auth_kind"] == "oauth"


async def test_declining_a_connection_is_a_normal_outcome(db, user, project, cfg, bridge):
    task = asyncio.create_task(
        _request_connection("gsc", "because", **_kwargs(bridge, user, project))
    )
    await bridge.answer({"skipped": True})
    result = await task

    assert result["status"] == "skipped"
    assert "state in your output which source is missing" in result["message"]


async def test_a_claimed_connection_is_verified_not_believed(db, user, project, cfg, bridge):
    """The client reports that the OAuth tab closed; only the database knows
    whether a credential actually landed."""
    task = asyncio.create_task(
        _request_connection("gsc", "because", **_kwargs(bridge, user, project))
    )
    await bridge.answer({"connected": True})
    result = await task

    assert result["status"] == "not_connected"
    assert "may not have completed" in result["message"]


async def test_asking_to_connect_something_already_connected_answers_instead(
    db, user, project, cfg, bridge
):
    _store(db, user, "gsc", "https://acme.com", {"refresh_token": "t"})

    result = await _request_connection("gsc", "because", **_kwargs(bridge, user, project))

    assert result["status"] == "already_connected"
    assert bridge.events == []


async def test_manual_connectors_offer_no_link(db, user, project, cfg, bridge):
    """Stripe has no OAuth scope — offering a dead link would be worse than
    telling the agent to explain where to paste a key."""
    task = asyncio.create_task(
        _request_connection("stripe", "to reconcile revenue", **_kwargs(bridge, user, project))
    )
    await bridge.answer({"skipped": True})
    await task

    assert bridge.events[0]["auth_kind"] == "manual"
    assert bridge.events[0]["authorize_path"] == ""
