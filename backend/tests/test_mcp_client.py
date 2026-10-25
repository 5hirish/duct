"""The MCP client against a real server, in process (``FakeMcpServer``).

What these hold: a server's own ``readOnlyHint`` is the only thing that makes
a tool read-only; a refused token becomes ``reauth_required`` (dug out of the
SDK's exception groups); and a refused token with a refresh token behind it
is refreshed once, persisted, and retried before anyone is told to reconnect.
"""

from __future__ import annotations

import time

import pytest
from mcp.types import ToolAnnotations

from service.mcp import client as mcp_client
from service.mcp import oauth
from service.mcp.store import (
    ACCESS_TOKEN,
    NEEDS_REAUTH,
    ServerAccess,
    key_credentials,
    no_credentials,
    oauth_credentials,
)
from tests.fakes import FakeMcpServer

URL = "https://mcp.vendor.test/mcp"


def _server(token: str | None = None) -> FakeMcpServer:
    server = FakeMcpServer(token=token)

    @server.mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def keyword_volume(keyword: str) -> dict:
        """Monthly search volume for one keyword. Costs one credit."""
        return {"keyword": keyword, "volume": 1300}

    @server.mcp.tool()
    def create_page(title: str) -> str:
        """Create a page in the workspace."""
        return f"created {title}"

    @server.mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True))
    def delete_page(page_id: str) -> str:
        """Delete a page."""
        return "deleted"

    return server


def _access(credentials: dict) -> ServerAccess:
    return ServerAccess(row_id=None, key="vendor", url=URL, name="Vendor", credentials=credentials)


def _oauth(access_token: str, *, refresh_token: str = "rt", expires_at: float | None = None) -> dict:
    return oauth_credentials(
        tokens=oauth.Tokens(access_token=access_token, refresh_token=refresh_token, expires_at=expires_at),
        registration=oauth.ClientRegistration(client_id="duct-client"),
        token_endpoint="https://auth.vendor.test/token",
        resource=URL,
        issuer="https://auth.vendor.test",
    )


async def test_tools_list_with_only_the_servers_own_word_for_read_only(monkeypatch):
    async with _server().running(monkeypatch):
        tools = {t.name: t for t in await mcp_client.list_tools(_access(no_credentials()))}

    assert set(tools) == {"keyword_volume", "create_page", "delete_page"}
    assert tools["keyword_volume"].read_only is True
    # Unannotated is not harmless: it asks first.
    assert tools["create_page"].read_only is False
    assert tools["delete_page"].read_only is False
    assert tools["keyword_volume"].input_schema["required"] == ["keyword"]


async def test_a_call_returns_the_servers_text(monkeypatch):
    async with _server().running(monkeypatch):
        result = await mcp_client.call_tool(_access(no_credentials()), "keyword_volume", {"keyword": "seo"})

    assert result.is_error is False
    assert '"volume": 1300' in result.text


async def test_an_api_key_rides_as_a_bearer(monkeypatch):
    server = _server(token="pasted-key")
    async with server.running(monkeypatch):
        assert await mcp_client.probe(_access(key_credentials("pasted-key"))) == 3

    assert set(server.authorizations) == {"Bearer pasted-key"}


async def test_a_refused_key_is_reauth_required_not_a_crash(monkeypatch):
    async with _server(token="the-real-key").running(monkeypatch):
        with pytest.raises(mcp_client.McpCallError) as caught:
            await mcp_client.list_tools(_access(key_credentials("a-wrong-key")))

    assert caught.value.code == mcp_client.CODE_REAUTH


async def test_a_refused_token_is_refreshed_once_persisted_and_retried(monkeypatch):
    refreshed: list[str] = []

    async def fake_refresh(**kwargs):
        refreshed.append(kwargs["refresh_token"])
        return oauth.Tokens(access_token="fresh", expires_at=time.time() + 3600)

    monkeypatch.setattr(mcp_client.oauth, "refresh", fake_refresh)
    saved: list[dict] = []

    async def sink(credentials: dict) -> None:
        saved.append(credentials)

    access = _access(_oauth("revoked-early"))
    async with _server(token="fresh").running(monkeypatch):
        tools = await mcp_client.list_tools(access, sink)

    assert len(tools) == 3
    assert refreshed == ["rt"]
    assert saved[-1][ACCESS_TOKEN] == "fresh"


async def test_an_expiring_token_is_refreshed_before_the_call(monkeypatch):
    async def fake_refresh(**kwargs):
        return oauth.Tokens(access_token="fresh", refresh_token=kwargs["refresh_token"])

    monkeypatch.setattr(mcp_client.oauth, "refresh", fake_refresh)
    server = _server(token="fresh")
    async with server.running(monkeypatch):
        await mcp_client.list_tools(_access(_oauth("stale", expires_at=time.time() + 5)))

    assert server.authorizations and set(server.authorizations) == {"Bearer fresh"}


async def test_a_refused_refresh_flags_the_server_for_reconnecting(monkeypatch):
    async def refused(**kwargs):
        raise oauth.OAuthFailed("invalid_grant")

    monkeypatch.setattr(mcp_client.oauth, "refresh", refused)
    saved: list[dict] = []

    async def sink(credentials: dict) -> None:
        saved.append(credentials)

    async with _server(token="never").running(monkeypatch):
        with pytest.raises(mcp_client.McpCallError) as caught:
            await mcp_client.list_tools(_access(_oauth("dead")), sink)

    assert caught.value.code == mcp_client.CODE_REAUTH
    assert saved and saved[-1][NEEDS_REAUTH] is True


async def test_a_server_flagged_for_reconnecting_is_not_called_at_all(monkeypatch):
    server = _server()
    async with server.running(monkeypatch):
        with pytest.raises(mcp_client.McpCallError) as caught:
            await mcp_client.list_tools(_access({**_oauth("x"), NEEDS_REAUTH: True}))

    assert caught.value.code == mcp_client.CODE_REAUTH
    assert server.authorizations == []
