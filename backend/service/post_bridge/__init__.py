"""PostBridge client + Pydantic response models.

PostBridge proxies posts and analytics to TikTok, Instagram, YouTube,
LinkedIn, X, Facebook, and Threads. The duct backend never calls these
platforms directly — it talks only to PostBridge.

Credentials are stored as a ConnectorCredential row with
connector_type='post_bridge' (one per user; multiple accounts share the
same API key). Decryption goes through service.credentials.

This package is wired into agents/content/tools.py (writer tools for the
content agent) and routes/content.py (REST endpoints).
"""

from service.post_bridge.client import (
    PostBridgeAPIError,
    PostBridgeClient,
    client_for_user,
)
from service.post_bridge.schema import (
    PostBridgeAnalytics,
    PostBridgeCreatePostRequest,
    PostBridgeCreatePostResponse,
    PostBridgeDailySnapshot,
    PostBridgeError,
    PostBridgePost,
    PostBridgePostStatus,
    PostBridgePostType,
    PostBridgeSocialAccount,
    PostBridgeUploadUrl,
)

__all__ = [
    "PostBridgeAPIError",
    "PostBridgeAnalytics",
    "PostBridgeClient",
    "PostBridgeCreatePostRequest",
    "PostBridgeCreatePostResponse",
    "PostBridgeDailySnapshot",
    "PostBridgeError",
    "PostBridgePost",
    "PostBridgePostStatus",
    "PostBridgePostType",
    "PostBridgeSocialAccount",
    "PostBridgeUploadUrl",
    "client_for_user",
]
