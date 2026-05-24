"""Unit tests for service.post_bridge.

Uses respx to mock httpx — no network calls. Covers happy paths, error
handling (PostBridgeAPIError), and credential resolver behaviour without
a real DB.
"""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest

from agents.models import Platform
from service.post_bridge import (
    PostBridgeAPIError,
    PostBridgeClient,
    PostBridgeCreatePostRequest,
    PostBridgePostType,
)


def _resp_factory(method_name: str, body: dict | list, status: int = 200):
    """Build a mock httpx transport that responds to a single request."""

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=body)

    return httpx.MockTransport(_handler)


@pytest.mark.asyncio
async def test_list_social_accounts_parses_items():
    body = {
        "items": [
            {
                "id":                  "acc_1",
                "platform":            "tiktok",
                "username":            "maxauralab",
                "display_name":        "MaxAura Lab",
                "profile_picture_url": "https://cdn.example.com/pic.png",
            },
        ]
    }
    transport = _resp_factory("GET", body)
    async with httpx.AsyncClient(transport=transport) as ac:
        client = PostBridgeClient("sk-fake", client=ac)
        accounts = await client.list_social_accounts(platform="tiktok")
        assert len(accounts) == 1
        assert accounts[0].id == "acc_1"
        assert accounts[0].platform == Platform.TIKTOK
        assert accounts[0].username == "maxauralab"


@pytest.mark.asyncio
async def test_list_social_accounts_handles_bare_list():
    """Some PostBridge endpoints return a bare list, not {items: [...]}.
    The client should handle both shapes."""
    body = [
        {"id": "acc_1", "platform": "instagram", "username": "x"},
        {"id": "acc_2", "platform": "tiktok",    "username": "y"},
    ]
    transport = _resp_factory("GET", body)
    async with httpx.AsyncClient(transport=transport) as ac:
        client = PostBridgeClient("sk-fake", client=ac)
        accounts = await client.list_social_accounts()
        assert {a.id for a in accounts} == {"acc_1", "acc_2"}


@pytest.mark.asyncio
async def test_create_post_returns_typed_response():
    body = {
        "post_id":      "pb_post_123",
        "result_id":    "res_999",
        "status":       "scheduled",
        "scheduled_at": "2026-06-15T10:00:00+00:00",
    }
    transport = _resp_factory("POST", body)
    async with httpx.AsyncClient(transport=transport) as ac:
        client = PostBridgeClient("sk-fake", client=ac)
        req = PostBridgeCreatePostRequest(
            account_ids=["acc_1"],
            caption="hello",
            hashtags=["#x", "#y"],
            media_urls=["https://cdn.example.com/img.png"],
            scheduled_at=datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc),
            post_type=PostBridgePostType.SLIDESHOW,
        )
        resp = await client.create_post(req)
        assert resp.post_id == "pb_post_123"
        assert resp.status.value == "scheduled"


@pytest.mark.asyncio
async def test_get_analytics_backfills_post_id():
    body = {  # PostBridge omits post_id in the body for this endpoint
        "view_count":     1234,
        "like_count":     567,
        "comment_count":  12,
        "share_count":    3,
        "save_count":     45,
        "save_rate":      0.036,
        "last_synced_at": "2026-06-16T08:00:00+00:00",
    }
    transport = _resp_factory("GET", body)
    async with httpx.AsyncClient(transport=transport) as ac:
        client = PostBridgeClient("sk-fake", client=ac)
        analytics = await client.get_analytics("pb_post_123")
        assert analytics.post_id == "pb_post_123"  # backfilled from path
        assert analytics.view_count == 1234
        assert analytics.save_rate == pytest.approx(0.036)


@pytest.mark.asyncio
async def test_non_2xx_raises_post_bridge_api_error():
    body = {"code": "rate_limited", "message": "Too many requests"}
    transport = _resp_factory("GET", body, status=429)
    async with httpx.AsyncClient(transport=transport) as ac:
        client = PostBridgeClient("sk-fake", client=ac)
        with pytest.raises(PostBridgeAPIError) as ei:
            await client.list_social_accounts()
        assert ei.value.status_code == 429
        assert ei.value.error.code == "rate_limited"


@pytest.mark.asyncio
async def test_network_error_raises_api_error():
    def _broken(_req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")
    transport = httpx.MockTransport(_broken)
    async with httpx.AsyncClient(transport=transport) as ac:
        client = PostBridgeClient("sk-fake", client=ac)
        with pytest.raises(PostBridgeAPIError) as ei:
            await client.list_social_accounts()
        assert ei.value.status_code == 0
        assert ei.value.error.code == "network_error"


@pytest.mark.asyncio
async def test_authorization_header_attached():
    captured: dict = {}

    def _handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("Authorization")
        captured["user_agent"] = request.headers.get("User-Agent")
        return httpx.Response(200, json={"items": []})

    transport = httpx.MockTransport(_handler)
    async with httpx.AsyncClient(transport=transport) as ac:
        client = PostBridgeClient("sk-fake-key", client=ac)
        await client.list_social_accounts()
        assert captured["auth"] == "Bearer sk-fake-key"
        assert captured["user_agent"].startswith("DuctContentAgent/")


def test_client_for_user_missing_credential():
    """Without a ConnectorCredential row, helper raises ValueError so the
    route layer can return a clean 400/404."""
    from unittest.mock import MagicMock

    from service.post_bridge import client_for_user

    db = MagicMock()
    db.execute.return_value.scalars.return_value.first.return_value = None
    with pytest.raises(ValueError, match="PostBridge is not connected"):
        client_for_user(user_id=__import__("uuid").uuid4(), db=db)


def test_client_for_user_missing_api_key_in_credential():
    """A credential with no api_key field also raises a helpful error."""
    from unittest.mock import MagicMock, patch

    from models.connector import ConnectorCredential
    from service.post_bridge import client_for_user

    row = MagicMock(spec=ConnectorCredential)
    row.credentials_enc = "fake-token"
    db = MagicMock()
    db.execute.return_value.scalars.return_value.first.return_value = row
    with patch("service.post_bridge.client.decrypt_credentials", return_value={"other": "x"}):
        with pytest.raises(ValueError, match="missing 'api_key'"):
            client_for_user(user_id=__import__("uuid").uuid4(), db=db)
