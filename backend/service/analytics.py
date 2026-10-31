"""Product analytics and error tracking: the one module that names the vendor.

The app's `lib/analytics/` and the desktop shell's `telemetry/reporter.rs` draw
the same line for the same reason: the deployment we run measures, and anyone
running Duct for themselves gets nothing unless they set ``POSTHOG_API_KEY``.
Routes call :func:`capture_event`; nothing outside this file imports PostHog.

Off on a loopback deployment unless ``POSTHOG_ENABLE_LOCALHOST`` is set: a
developer's `.env.local` that happens to hold the production key would
otherwise file every local click and stack trace beside real users', and the
desktop sidecar binds 127.0.0.1 — "a user's laptop is not a deployment"
(`local_server.py`).
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from config import get_configs

logger = logging.getLogger(__name__)

# Written by the Railway build (scripts/posthog_release.py), which says why the
# release is resolved there rather than in a deploy workflow.
_RELEASE_ID_FILE = Path(__file__).resolve().parents[1] / ".posthog-release-id"

# One person-property write per user per process per day. The identity rides
# every request through the context below for free; the `$set` that keeps the
# email and name current is a billed event, and sending it on every
# authenticated request multiplied the event volume by the request rate.
_IDENTIFY_TTL_S = 24 * 60 * 60
_IDENTIFY_CACHE_MAX = 10_000
_identified: dict[str, float] = {}

_client: Any = None
_client_built = False


def _is_loopback(url: str) -> bool:
    return urlparse(url).hostname in {"localhost", "127.0.0.1", "::1"}


def _release_properties() -> dict:
    """``$release_id`` from the build, so an error says which deploy raised it.

    The SDK reads ``POSTHOG_RELEASE_ID`` itself, and a super property would
    override it, so the build's file counts only when the variable is unset.
    """
    if os.environ.get("POSTHOG_RELEASE_ID", "").strip():
        return {}
    try:
        release_id = _RELEASE_ID_FILE.read_text().strip()
    except OSError:
        return {}
    return {"$release_id": release_id} if release_id else {}


def client():
    """The process-wide PostHog client, or None when analytics is off."""
    global _client, _client_built
    if _client_built:
        return _client
    _client_built = True
    cfg = get_configs()
    if not cfg.posthog_api_key:
        return None
    if _is_loopback(cfg.api_public_url) and not cfg.posthog_enable_localhost:
        logger.info("PostHog off: loopback deployment (set POSTHOG_ENABLE_LOCALHOST to send).")
        return None

    from posthog import Posthog

    _client = Posthog(
        cfg.posthog_api_key,
        host=cfg.posthog_host,
        enable_exception_autocapture=True,
        # LLM prompts and completions carry the customer's connected-tool data
        # (their GA4 numbers, ad spend, search terms). Model, tokens, latency
        # and cost are what we need; the content is theirs, not ours to keep.
        privacy_mode=True,
        super_properties={"environment": cfg.app_env, "service": "backend", **_release_properties()},
    )
    return _client


class _LoggedExceptionHandler(logging.Handler):
    """Report `logger.exception(...)` the way an uncaught error is reported.

    Most failures here are caught, logged with a traceback and survived — a
    connector pull, a checkpoint write, a background sweep — and the old error
    tracker turned those log records into reports. PostHog's middleware only
    sees what escapes a route, so without this every handled failure would
    vanish from error tracking. Uvicorn's own "Exception in ASGI application"
    line is skipped: the middleware already reported that exception, and the
    SDK drops a second capture of the same object anyway.
    """

    _SKIP = ("posthog", "uvicorn", "backoff")

    def emit(self, record: logging.LogRecord) -> None:
        if not record.exc_info or record.name.startswith(self._SKIP):
            return
        posthog = client()
        if posthog is None:
            return
        try:
            posthog.capture_exception(
                record.exc_info[1],
                properties={"logger": record.name, "log_message": record.getMessage()[:500]},
            )
        except Exception:  # noqa: BLE001 — reporting a failure must never become one
            pass


def install(app) -> None:
    """Mount request context and error capture on the ASGI app."""
    posthog = client()
    if posthog is None:
        return
    from posthog.integrations.asgi import PosthogASGIMiddleware

    app.add_middleware(PosthogASGIMiddleware, posthog_client=posthog)
    logging.getLogger().addHandler(_LoggedExceptionHandler(level=logging.ERROR))


def shutdown() -> None:
    """Flush what is queued. Safe to call when analytics is off."""
    if _client is not None:
        _client.shutdown()


def identify_user(user) -> None:
    """Attribute this request's events and errors to a verified user.

    The account UUID is the distinct id, the same one the app's `identify`
    sends from the JWT's `uid`, so a browser session and its API calls are one
    person. The email and name go on the person profile, so a support reply
    can reach someone who hit an error.
    """
    posthog = client()
    if posthog is None:
        return
    from posthog import identify_context

    distinct_id = str(user.id)
    identify_context(distinct_id)

    now = time.monotonic()
    if now - _identified.get(distinct_id, float("-inf")) < _IDENTIFY_TTL_S:
        return
    if len(_identified) >= _IDENTIFY_CACHE_MAX:
        _identified.clear()
    _identified[distinct_id] = now
    properties = {"email": user.email}
    if user.full_name:
        properties["name"] = user.full_name
    posthog.set(distinct_id=distinct_id, properties=properties)


def capture_event(event: str, properties: dict | None = None) -> None:
    """Record a product event for the request's identified user."""
    posthog = client()
    if posthog is not None:
        posthog.capture(event, properties=properties)


def langchain_callback(*, session_id: str, distinct_id: str = ""):
    """A per-turn AI observability callback, or None when analytics is off."""
    posthog = client()
    if posthog is None or not session_id:
        return None
    from agents.core.posthog_ai import build_callback

    return build_callback(posthog, session_id=session_id, distinct_id=distinct_id)
