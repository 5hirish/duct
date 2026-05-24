"""PostBridge client + typed Pydantic models.

PostBridge proxies posts and analytics to TikTok, Instagram, YouTube,
LinkedIn, Twitter, Facebook, Threads, Bluesky, Pinterest, and Google
Business Profile. duct talks only to PostBridge — never to the
platforms directly.

Posting flow (from PostBridge docs):
  1. GET  /v1/social-accounts                — list connected accounts
  2. POST /v1/media/create-upload-url        — get a signed upload URL
  3. PUT  <signed URL>                       — upload the bytes
  4. POST /v1/posts {caption, social_accounts:[id], media:[media_id]}
                                              — create + schedule the post

Analytics flow:
  1. POST /v1/analytics/sync?platform=…      — refresh PostBridge's cache
  2. GET  /v1/post-results?post_id=…         — find the post_result_id(s)
  3. GET  /v1/analytics?post_result_id=…     — lifetime metrics
  4. GET  /v1/analytics/{id}/daily           — daily snapshots + deltas

Credentials: ConnectorCredential row with connector_type='post_bridge'
takes precedence; falls back to .env POSTBRIDGE_API_KEY for MVP.
"""

from service.post_bridge.client import (
    PostBridgeAPIError,
    PostBridgeClient,
    client_for_user,
)
from service.post_bridge.schema import (
    CreateUploadUrlRequest,
    PostBridgeAnalytics,
    PostBridgeAnalyticsDaily,
    PostBridgeCreatePostRequest,
    PostBridgeDailyDelta,
    PostBridgeDailySnapshot,
    PostBridgeError,
    PostBridgeMedia,
    PostBridgeMimeType,
    PostBridgePlatform,
    PostBridgePost,
    PostBridgePostResult,
    PostBridgePostStatus,
    PostBridgeSocialAccount,
    PostBridgeUploadUrl,
)

__all__ = [
    "CreateUploadUrlRequest",
    "PostBridgeAPIError",
    "PostBridgeAnalytics",
    "PostBridgeAnalyticsDaily",
    "PostBridgeClient",
    "PostBridgeCreatePostRequest",
    "PostBridgeDailyDelta",
    "PostBridgeDailySnapshot",
    "PostBridgeError",
    "PostBridgeMedia",
    "PostBridgeMimeType",
    "PostBridgePlatform",
    "PostBridgePost",
    "PostBridgePostResult",
    "PostBridgePostStatus",
    "PostBridgeSocialAccount",
    "PostBridgeUploadUrl",
    "client_for_user",
]
