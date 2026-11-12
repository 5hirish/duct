"""Zernio client and its ``Publisher`` adapter.

Zernio schedules and publishes to LinkedIn, X, TikTok, Instagram, YouTube,
Facebook, Threads, Pinterest, Bluesky and Google Business, and reports each
post's numbers, LinkedIn and X included. Duct talks only to Zernio, never to
the platforms directly, through ``service/zernio/publisher.py``.

Credentials: each user's own key (``ZERNIO_KEY``); ZERNIO_API_KEY is a local
and desktop fallback only (service/vendor_keys.py).
"""

from service.zernio.client import ZERNIO_KEY, ZernioAPIError, ZernioClient

__all__ = ["ZERNIO_KEY", "ZernioAPIError", "ZernioClient"]
