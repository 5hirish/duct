"""On-demand media download for TikTok posts.

Searches never download media (keeps them cheap + token-light). This module is
used only by the ``fetch_tiktok_media`` tool to pull bytes when the user wants
to analyze content visually.

Two source kinds appear in scraped posts:
  - TikTok CDN URLs (cover_url / original_cover_url / slideshow_image_links):
    public, signed, expire within hours — a plain GET works.
  - Apify key-value-store URLs (media_urls, populated by shouldDownloadVideos):
    token-gated — a plain GET 403s, so we retry with the API token appended, but
    ONLY when the host is genuinely Apify (never leak the token to another host).

All fetches go through the SSRF-guarded safe_get_bytes.
"""

from __future__ import annotations

from .url_safety import host_in, is_public_http_url, safe_get_bytes

# The ONLY hosts we'll append the Apify token to (exact match, never substring:
# "https://evil.com/?x=api.apify.com" must NOT leak the token).
_APIFY_HOSTS = {"api.apify.com", "storage.apify.com"}

_IMAGE_TIMEOUT_SECS = 20.0
_VIDEO_TIMEOUT_SECS = 60.0  # clips are a few MB — more headroom than images


def fetch_media_bytes(url: str, token: str = "", *, timeout: float = _IMAGE_TIMEOUT_SECS) -> bytes | None:
    """Fetch bytes from a TikTok CDN or Apify-hosted URL (SSRF-guarded). On a
    miss, retry once with the Apify token appended — but only for Apify hosts.
    Returns None if there's no URL or every attempt fails."""
    if not url or not is_public_http_url(url):
        return None
    data = safe_get_bytes(url, timeout=timeout)
    if not data and token and host_in(url, _APIFY_HOSTS):
        sep = "&" if "?" in url else "?"
        data = safe_get_bytes(f"{url}{sep}token={token}", timeout=timeout)
    return data or None


def first_video_bytes(media_urls: list[str], token: str = "") -> bytes | None:
    """Fetch the first downloadable .mp4 from a post's Apify-hosted ``media_urls``
    (populated only when the scrape requested shouldDownloadVideos)."""
    for url in media_urls or []:
        data = fetch_media_bytes(url, token, timeout=_VIDEO_TIMEOUT_SECS)
        if data:
            return data
    return None


def sniff_image_format(data: bytes) -> str:
    """Best-effort image format from magic bytes (for the MCP Image mime type).
    Defaults to jpeg — TikTok covers/slides are JPEG."""
    if data[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    return "jpeg"
