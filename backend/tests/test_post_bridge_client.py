"""Unit tests for service.post_bridge — matches PostBridge v1 OpenAPI contract.

Uses httpx.MockTransport — no network calls. Covers:
  - GET /v1/social-accounts (numeric IDs, paginated {data, meta} envelope)
  - POST /v1/media/create-upload-url
  - PUT signed upload URL
  - POST /v1/posts (caption + social_accounts numeric + media id list)
  - GET /v1/post-results (post → post_result chain)
  - GET /v1/analytics + /v1/analytics/{id}/daily ({snapshots, deltas})
  - 4xx/5xx + transport errors raise PostBridgeAPIError
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
)


def _transport(responder):
    return httpx.MockTransport(responder)


# ---------------------------------------------------------------------------
# Social accounts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_social_accounts_parses_numeric_ids():
    body = {
        "data": [
            {"id": 101, "platform": "tiktok",    "username": "maxauralab"},
            {"id": 202, "platform": "instagram", "username": "maxauralab"},
        ],
        "meta": {"total": 2, "offset": 0, "limit": 50, "next": None},
    }
    async with httpx.AsyncClient(transport=_transport(lambda r: httpx.Response(200, json=body))) as ac:
        client = PostBridgeClient("sk-fake", client=ac)
        accounts = await client.list_social_accounts(platform=["tiktok", "instagram"])
        assert len(accounts) == 2
        assert accounts[0].id == 101
        assert isinstance(accounts[0].id, int)
        assert accounts[0].platform.value == "tiktok"
        # The duct Platform enum mirrors PostBridge naming
        assert Platform.TIKTOK.value == accounts[0].platform.value


# ---------------------------------------------------------------------------
# Media upload
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_upload_url_sends_required_fields():
    captured: dict = {}

    def _handler(req: httpx.Request) -> httpx.Response:
        captured["body"] = req.read()
        return httpx.Response(200, json={
            "media_id":   "m_123",
            "upload_url": "https://signed.example/upload",
            "name":       "photo.png",
        })

    async with httpx.AsyncClient(transport=_transport(_handler)) as ac:
        client = PostBridgeClient("sk-fake", client=ac)
        u = await client.create_upload_url(name="photo.png", mime_type="image/png", size_bytes=1024)
        assert u.media_id == "m_123"
        assert "image/png" in captured["body"].decode()
        assert b"1024" in captured["body"]


@pytest.mark.asyncio
async def test_upload_media_puts_bytes_without_auth_header():
    captured: dict = {}

    def _handler(req: httpx.Request) -> httpx.Response:
        captured["method"] = req.method
        captured["auth"]   = req.headers.get("Authorization")
        captured["ct"]     = req.headers.get("Content-Type")
        return httpx.Response(200)

    async with httpx.AsyncClient(transport=_transport(_handler)) as ac:
        client = PostBridgeClient("sk-fake", client=ac)
        await client.upload_media(b"PNGBYTES", "https://signed.example/upload", "image/png")
        assert captured["method"] == "PUT"
        assert captured["auth"] is None     # signed URL — no bearer token
        assert captured["ct"]   == "image/png"


# ---------------------------------------------------------------------------
# Posts — create / get / list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_post_uses_correct_field_names():
    captured: dict = {}

    def _handler(req: httpx.Request) -> httpx.Response:
        import json as _json
        captured["body"] = _json.loads(req.read())
        return httpx.Response(200, json={
            "id":       "pb_post_123",
            "caption":  "hello",
            "status":   "scheduled",
            "social_accounts": [101],
            "media":     None,
            "is_draft":  False,
            "scheduled_at": "2026-06-15T10:00:00+00:00",
        })

    async with httpx.AsyncClient(transport=_transport(_handler)) as ac:
        client = PostBridgeClient("sk-fake", client=ac)
        req = PostBridgeCreatePostRequest(
            caption="hello #x #y",
            social_accounts=[101],
            media=["m_123"],
            scheduled_at=datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc),
            platform_configurations={"tiktok": {"draft": False}},
        )
        resp = await client.create_post(req)
        # Wire shape matches PostBridge v1
        assert captured["body"]["social_accounts"] == [101]
        assert captured["body"]["media"]           == ["m_123"]
        assert "hashtags" not in captured["body"]
        assert resp.id == "pb_post_123"
        assert resp.status.value == "scheduled"


@pytest.mark.asyncio
async def test_get_post_returns_post_dto():
    async with httpx.AsyncClient(transport=_transport(lambda r: httpx.Response(200, json={
        "id": "pb_post_123",
        "caption": "x",
        "status": "posted",
        "social_accounts": [101],
        "is_draft": False,
    }))) as ac:
        client = PostBridgeClient("sk-fake", client=ac)
        post = await client.get_post("pb_post_123")
        assert post.id == "pb_post_123"
        assert post.status.value == "posted"


# ---------------------------------------------------------------------------
# Post results + analytics chain
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_post_results_unwraps_data_envelope():
    body = {
        "data": [{
            "id":                "res_1",
            "post_id":           "pb_post_123",
            "success":           True,
            "social_account_id": 101,
            "error":             None,
            "platform_data":     {"id": "tt_111", "url": "https://tiktok.com/v/111"},
        }],
        "meta": {"total": 1, "offset": 0, "limit": 50, "next": None},
    }
    async with httpx.AsyncClient(transport=_transport(lambda r: httpx.Response(200, json=body))) as ac:
        client = PostBridgeClient("sk-fake", client=ac)
        results = await client.list_post_results(post_id="pb_post_123")
        assert len(results) == 1
        assert results[0].id == "res_1"
        assert results[0].success is True
        assert results[0].platform_data.url.startswith("https://tiktok.com/")


@pytest.mark.asyncio
async def test_analytics_daily_parses_snapshots_and_deltas():
    body = {
        "snapshots": [
            {"date": "2026-06-15", "view_count": 100, "like_count": 5, "comment_count": 0, "share_count": 1},
            {"date": "2026-06-16", "view_count": 250, "like_count": 12, "comment_count": 2, "share_count": 3},
        ],
        "deltas": [
            {"date": "2026-06-16", "views": 150, "likes": 7, "comments": 2, "shares": 2},
        ],
    }
    async with httpx.AsyncClient(transport=_transport(lambda r: httpx.Response(200, json=body))) as ac:
        client = PostBridgeClient("sk-fake", client=ac)
        daily = await client.get_analytics_daily("ana_1")
        assert len(daily.snapshots) == 2
        assert daily.snapshots[1].view_count == 250
        assert len(daily.deltas) == 1
        assert daily.deltas[0].views == 150


@pytest.mark.asyncio
async def test_sync_analytics_swallows_rate_limit():
    """Sync should not raise on 429 — caller is expected to fall through to cached data."""
    body = {"code": "rate_limited", "message": "Wait between syncs"}
    async with httpx.AsyncClient(transport=_transport(lambda r: httpx.Response(429, json=body))) as ac:
        client = PostBridgeClient("sk-fake", client=ac)
        await client.sync_analytics(platform="tiktok")  # no raise


# ---------------------------------------------------------------------------
# Error surfaces
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_non_2xx_other_than_429_raises_post_bridge_api_error():
    body = {"code": "invalid", "message": "Caption too long"}
    async with httpx.AsyncClient(transport=_transport(lambda r: httpx.Response(400, json=body))) as ac:
        client = PostBridgeClient("sk-fake", client=ac)
        with pytest.raises(PostBridgeAPIError) as ei:
            await client.list_social_accounts()
        assert ei.value.status_code == 400
        assert ei.value.error.code == "invalid"


@pytest.mark.asyncio
async def test_network_error_raises_api_error():
    def _broken(_req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")
    async with httpx.AsyncClient(transport=_transport(_broken)) as ac:
        client = PostBridgeClient("sk-fake", client=ac)
        with pytest.raises(PostBridgeAPIError) as ei:
            await client.list_social_accounts()
        assert ei.value.status_code == 0
        assert ei.value.error.code == "network_error"


@pytest.mark.asyncio
async def test_authorization_header_attached():
    captured: dict = {}

    def _handler(req: httpx.Request) -> httpx.Response:
        captured["auth"]       = req.headers.get("Authorization")
        captured["user_agent"] = req.headers.get("User-Agent")
        return httpx.Response(200, json={"data": [], "meta": {"total": 0, "offset": 0, "limit": 50, "next": None}})

    async with httpx.AsyncClient(transport=_transport(_handler)) as ac:
        client = PostBridgeClient("sk-fake-key", client=ac)
        await client.list_social_accounts()
        assert captured["auth"] == "Bearer sk-fake-key"
        assert captured["user_agent"].startswith("DuctContentAgent/")


# ---------------------------------------------------------------------------
# Credential resolver
# ---------------------------------------------------------------------------


def test_client_for_user_uses_env_fallback_when_no_credential():
    """MVP behaviour: no ConnectorCredential row → use POSTBRIDGE_API_KEY from .env."""
    from unittest.mock import MagicMock, patch

    db = MagicMock()
    db.execute.return_value.scalars.return_value.first.return_value = None
    fake_cfg = MagicMock()
    fake_cfg.postbridge_api_key = "env-fallback-key"
    with patch("service.post_bridge.client.get_configs", return_value=fake_cfg):
        from service.post_bridge import client_for_user
        client = client_for_user(__import__("uuid").uuid4(), db)
        assert client._api_key == "env-fallback-key"


def test_client_for_user_raises_when_no_credential_or_env():
    from unittest.mock import MagicMock, patch

    from service.post_bridge import client_for_user

    db = MagicMock()
    db.execute.return_value.scalars.return_value.first.return_value = None
    fake_cfg = MagicMock()
    fake_cfg.postbridge_api_key = ""
    with patch("service.post_bridge.client.get_configs", return_value=fake_cfg):
        with pytest.raises(ValueError, match="PostBridge isn't connected"):
            client_for_user(__import__("uuid").uuid4(), db)
