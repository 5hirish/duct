"""Contract tests for service.post_bridge against the v1 OpenAPI shape.

Why mocked + not pure live: PostBridge calls cost money and require an
account per platform — these tests defend the wire-shape contract that
broke our publish flow the FIRST time we shipped (account_ids vs
social_accounts, string vs numeric IDs, hashtags inside caption vs
separate field). Each test below mirrors a real OpenAPI requirement
that a contract drift would silently break.

Live read-only smoke (one cheap call against a real account) lives in
tests/test_content_e2e.py behind POSTBRIDGE_API_KEY.
"""

from __future__ import annotations

import json as _json
from datetime import datetime, timezone

import httpx
import pytest

from service.post_bridge import (
    PostBridgeAPIError,
    PostBridgeClient,
    PostBridgeCreatePostRequest,
)


def _transport(responder):
    return httpx.MockTransport(responder)


# ---------------------------------------------------------------------------
# Wire-shape correctness — these are the contract bugs we already hit once
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_social_account_ids_are_numeric_and_data_envelope_unwrapped():
    """SocialAccountDto.id is NUMERIC (was the source of the publish bug).
    Envelope is {data, meta} — must unwrap."""
    body = {
        "data": [
            {"id": 101, "platform": "tiktok",    "username": "maxauralab"},
            {"id": 202, "platform": "instagram", "username": "maxauralab"},
        ],
        "meta": {"total": 2, "offset": 0, "limit": 50, "next": None},
    }
    async with httpx.AsyncClient(transport=_transport(lambda r: httpx.Response(200, json=body))) as ac:
        client = PostBridgeClient("sk-fake", client=ac)
        accounts = await client.list_social_accounts()
        assert [a.id for a in accounts] == [101, 202]
        assert all(isinstance(a.id, int) for a in accounts)


@pytest.mark.asyncio
async def test_create_post_uses_v1_field_names():
    """CreatePostDto requires: caption, social_accounts (numeric list),
    media (media_id list). NO hashtags field — hashtags go in caption.
    NO account_ids alias. This test is the regression guard against
    contract drift."""
    captured: dict = {}

    def _handler(req: httpx.Request) -> httpx.Response:
        captured["body"] = _json.loads(req.read())
        return httpx.Response(200, json={
            "id":              "pb_post_123",
            "caption":         "x",
            "status":          "scheduled",
            "social_accounts": [101],
            "is_draft":        False,
            "scheduled_at":    "2026-06-15T10:00:00+00:00",
        })

    async with httpx.AsyncClient(transport=_transport(_handler)) as ac:
        client = PostBridgeClient("sk-fake", client=ac)
        req = PostBridgeCreatePostRequest(
            caption="hello world #tag1 #tag2",
            social_accounts=[101],
            media=["m_abc"],
            scheduled_at=datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc),
        )
        resp = await client.create_post(req)

    assert captured["body"]["social_accounts"] == [101]
    assert captured["body"]["media"] == ["m_abc"]
    assert "hashtags"   not in captured["body"]
    assert "account_ids" not in captured["body"]
    assert resp.id == "pb_post_123"
    assert resp.status.value == "scheduled"


@pytest.mark.asyncio
async def test_upload_flow_create_url_then_put_bytes_no_auth_on_put():
    """The signed upload URL must be PUT without an Authorization header
    (the URL itself carries the signature). If we leak our Bearer token
    onto S3/GCS the upload either fails or — worse — quietly succeeds."""
    create_calls = []
    put_calls = []

    def _handler(req: httpx.Request) -> httpx.Response:
        if req.method == "POST":
            create_calls.append(_json.loads(req.read()))
            return httpx.Response(200, json={
                "media_id":   "m_xyz",
                "upload_url": "https://signed.example.com/upload?sig=abc",
                "name":       "slide-01.png",
            })
        if req.method == "PUT":
            put_calls.append({
                "auth": req.headers.get("Authorization"),
                "ct":   req.headers.get("Content-Type"),
                "len":  len(req.read()),
            })
            return httpx.Response(200)
        raise AssertionError(req.method)

    async with httpx.AsyncClient(transport=_transport(_handler)) as ac:
        client = PostBridgeClient("sk-fake", client=ac)
        upload = await client.create_upload_url(name="slide-01.png", mime_type="image/png", size_bytes=8)
        await client.upload_media(b"PNG-data", upload.upload_url, "image/png")

    assert create_calls[0] == {"name": "slide-01.png", "mime_type": "image/png", "size_bytes": 8}
    assert upload.media_id == "m_xyz"
    assert put_calls[0]["auth"] is None
    assert put_calls[0]["ct"]   == "image/png"
    assert put_calls[0]["len"]  == len(b"PNG-data")


@pytest.mark.asyncio
async def test_analytics_chain_post_to_post_result_to_analytics():
    """The analytics chain is the only path to metrics; if any link
    breaks the dashboard shows zeros forever. This test walks the
    full chain: list_post_results → list_analytics → get_analytics_daily."""
    calls: list[str] = []

    def _handler(req: httpx.Request) -> httpx.Response:
        calls.append(req.url.path)
        if req.url.path == "/v1/post-results":
            return httpx.Response(200, json={
                "data": [{
                    "id":                "res_1",
                    "post_id":           "pb_post_123",
                    "success":           True,
                    "social_account_id": 101,
                    "error":             None,
                    "platform_data":     {"id": "tt_111", "url": "https://tiktok.com/v/111"},
                }],
                "meta": {"total": 1, "offset": 0, "limit": 50, "next": None},
            })
        if req.url.path == "/v1/analytics":
            return httpx.Response(200, json={
                "data": [{
                    "id":             "ana_1",
                    "post_result_id": "res_1",
                    "platform":       "tiktok",
                    "view_count":     1234,
                    "like_count":     56,
                    "last_synced_at": "2026-06-15T08:00:00+00:00",
                }],
                "meta": {"total": 1, "offset": 0, "limit": 50, "next": None},
            })
        if req.url.path == "/v1/analytics/ana_1/daily":
            return httpx.Response(200, json={
                "snapshots": [
                    {"date": "2026-06-15", "view_count": 100, "like_count": 5, "comment_count": 0, "share_count": 1},
                    {"date": "2026-06-16", "view_count": 250, "like_count": 12, "comment_count": 2, "share_count": 3},
                ],
                "deltas": [
                    {"date": "2026-06-16", "views": 150, "likes": 7, "comments": 2, "shares": 2},
                ],
            })
        raise AssertionError(req.url.path)

    async with httpx.AsyncClient(transport=_transport(_handler)) as ac:
        client = PostBridgeClient("sk-fake", client=ac)
        results   = await client.list_post_results(post_id="pb_post_123")
        analytics = await client.list_analytics(post_result_id=[results[0].id])
        daily     = await client.get_analytics_daily(analytics[0].id)

    assert calls == [
        "/v1/post-results",
        "/v1/analytics",
        "/v1/analytics/ana_1/daily",
    ]
    assert analytics[0].view_count == 1234
    assert len(daily.snapshots) == 2 and daily.snapshots[1].view_count == 250
    assert len(daily.deltas)    == 1 and daily.deltas[0].views == 150


# ---------------------------------------------------------------------------
# Error surfaces — used by friendly-error mapping in the route layer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_analytics_swallows_429_not_other_errors():
    """sync_analytics is best-effort; caller falls through to cached
    data on rate-limit. Other 4xx/5xx must still raise so the user sees
    a real failure."""
    seq = iter([429, 500])

    def _handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(next(seq), json={"code": "x", "message": "y"})

    async with httpx.AsyncClient(transport=_transport(_handler)) as ac:
        client = PostBridgeClient("sk-fake", client=ac)
        await client.sync_analytics(platform="tiktok")  # 429 → no raise
        with pytest.raises(PostBridgeAPIError) as ei:
            await client.sync_analytics(platform="tiktok")
        assert ei.value.status_code == 500


@pytest.mark.asyncio
async def test_network_error_wraps_in_post_bridge_api_error_with_status_zero():
    """Route layer's friendly-error mapping looks at status_code==0 to
    say 'Couldn't reach the service'. If this contract breaks the user
    sees a raw httpx ConnectError instead."""
    def _broken(_req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")
    async with httpx.AsyncClient(transport=_transport(_broken)) as ac:
        client = PostBridgeClient("sk-fake", client=ac)
        with pytest.raises(PostBridgeAPIError) as ei:
            await client.list_social_accounts()
        assert ei.value.status_code == 0
        assert ei.value.error.code == "network_error"


@pytest.mark.asyncio
async def test_bearer_token_attached_to_api_calls_only():
    """Authorization header must be present on /v1/ API calls (Bearer
    token). Test also documents the User-Agent for support diagnosis."""
    captured: dict = {}

    def _handler(req: httpx.Request) -> httpx.Response:
        captured["auth"] = req.headers.get("Authorization")
        captured["ua"]   = req.headers.get("User-Agent")
        return httpx.Response(200, json={"data": [], "meta": {"total": 0, "offset": 0, "limit": 50, "next": None}})

    async with httpx.AsyncClient(transport=_transport(_handler)) as ac:
        client = PostBridgeClient("sk-actual-key", client=ac)
        await client.list_social_accounts()
        assert captured["auth"] == "Bearer sk-actual-key"
        assert captured["ua"].startswith("DuctContentAgent/")


# ---------------------------------------------------------------------------
# Credential resolver — MVP .env fallback behaviour
# ---------------------------------------------------------------------------


def test_client_for_user_falls_back_to_env_then_raises_when_missing():
    """MVP: no ConnectorCredential row → use POSTBRIDGE_API_KEY env. If
    that's also empty, raise with an actionable message the route layer
    can pass through to the user."""
    from unittest.mock import MagicMock, patch
    from service.post_bridge import client_for_user

    db = MagicMock()
    db.execute.return_value.scalars.return_value.first.return_value = None

    fake_cfg = MagicMock()
    fake_cfg.postbridge_api_key = "env-fallback-key"
    with patch("service.post_bridge.client.get_configs", return_value=fake_cfg):
        client = client_for_user(__import__("uuid").uuid4(), db)
        assert client._api_key == "env-fallback-key"

    fake_cfg.postbridge_api_key = ""
    with patch("service.post_bridge.client.get_configs", return_value=fake_cfg):
        with pytest.raises(ValueError, match="PostBridge isn't connected"):
            client_for_user(__import__("uuid").uuid4(), db)
