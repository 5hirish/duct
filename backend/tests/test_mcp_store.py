"""Credential blobs and the shared-client registration substitution.

For a pre-registered preset the secret lives in settings, not on the
connection: the registration handed to the token endpoint is built from the
stored blob but has that one field filled in from config. Rotating the setting
then fixes every install at once, rather than orphaning each one.
"""
from __future__ import annotations

import pytest

from config import Configs
from service.mcp.oauth import ClientRegistration, Tokens
from service.mcp.store import (
    AUTH_METHOD,
    CLIENT_ID,
    CLIENT_SECRET,
    oauth_credentials,
    registration_for,
)

HUBSPOT = "https://mcp.hubspot.com"
DCR = "https://mcp.vendor.test/mcp"


@pytest.fixture
def cfg(monkeypatch):
    """Config with the shared client configured. ``mcp_store`` reads it at
    token time, so the substitution only fires when this is patched."""
    config = Configs(
        hubspot_mcp_client_id="hubspot-client",
        hubspot_mcp_client_secret="hubspot-secret",
    )
    monkeypatch.setattr("service.mcp.store.get_configs", lambda: config)
    return config


def _reg(*, client_id: str = "client", client_secret: str = "per-reg", auth_method: str = "none") -> ClientRegistration:
    return ClientRegistration(client_id=client_id, client_secret=client_secret, auth_method=auth_method)


def _tokens() -> Tokens:
    return Tokens(access_token="at", refresh_token="rt", expires_at=None, scope="read")


def test_registration_for_leaves_a_dcr_registration_alone():
    reg = _reg(client_id="dcr", client_secret="per-reg", auth_method="none")
    assert registration_for(DCR, reg) == reg


def test_registration_for_fills_the_shared_secret_for_a_pre_registered_preset(cfg):
    reg = _reg(client_id="hubspot-client", client_secret="", auth_method="client_secret_post")
    result = registration_for(HUBSPOT, reg)

    assert result.client_secret == "hubspot-secret"
    # The rest is copied through unchanged
    assert result.client_id == "hubspot-client"
    assert result.auth_method == "client_secret_post"


def test_a_dcr_connection_keeps_its_secret_in_the_blob():
    reg = _reg(client_secret="per-reg")
    creds = oauth_credentials(
        tokens=_tokens(),
        registration=reg,
        token_endpoint="https://auth.vendor.test/token",
        resource=DCR,
        issuer="https://auth.vendor.test",
    )
    assert creds[CLIENT_SECRET] == "per-reg"


def test_a_shared_client_connection_stores_no_secret(cfg):
    reg = _reg(client_id="hubspot-client", client_secret="hubspot-secret", auth_method="client_secret_post")
    creds = oauth_credentials(
        tokens=_tokens(),
        registration=reg,
        token_endpoint="https://api.hubapi.com/oauth/v3/token",
        resource=HUBSPOT,
        issuer="https://api.hubapi.com",
        store_client_secret=False,
    )
    # The secret is not on the connection: it lives in settings.
    assert creds[CLIENT_SECRET] == ""
    assert creds[CLIENT_ID] == "hubspot-client"
    assert creds[AUTH_METHOD] == "client_secret_post"