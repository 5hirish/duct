"""Security response headers on every API response, as a pure-ASGI middleware.

The API renders no pages: its callers are the app's ``fetch`` and SSE readers.
So every response is locked down as though someone could be sent to open it
directly: no MIME sniffing, no framing, no referrer, and a CSP under which
nothing loads or runs.

An HTML response is the one exception, for FastAPI's ``/docs`` and ``/redoc``:
Swagger UI loads its script and styles from a CDN, so an HTML response keeps
its loads and only refuses to be framed. (A stored HTML artifact is HTML too,
but it is only ever read by a ``fetch`` carrying a Bearer token, never opened
as a page on this origin.) A route that sets one of these headers itself keeps
its own value.

Pure ASGI rather than ``BaseHTTPMiddleware`` for the reason
``AccessLogMiddleware`` gives in ``server.py``: it touches only
``http.response.start`` and passes each body message on as it arrives, so an
SSE stream is never buffered.
"""

from __future__ import annotations

# Every response. Names are lowercase because that is how ASGI carries them.
_ALWAYS = (
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    # Nothing here needs to tell the next hop where the caller was, including
    # the OAuth callbacks, which redirect onward with a code in their own URL.
    (b"referrer-policy", b"no-referrer"),
)

_CSP = b"content-security-policy"
_CONTENT_TYPE = b"content-type"
_HTML = b"text/html"
# JSON, event streams, redirects, stored files: nothing on this origin should
# load or run if a browser is ever pointed at one.
_LOCKED_CSP = b"default-src 'none'; frame-ancestors 'none'"
# An HTML document: framing refused, its own subresources left alone.
_DOCUMENT_CSP = b"frame-ancestors 'none'"


class SecurityHeadersMiddleware:
    """Adds the headers above to every HTTP response that does not set them."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def _send(message):
            if message["type"] == "http.response.start":
                message["headers"] = _with_security_headers(list(message.get("headers", ())))
            await send(message)

        await self.app(scope, receive, _send)


def _with_security_headers(headers: list) -> list:
    """``headers`` plus each security header it does not already carry."""
    present = {name.lower() for name, _ in headers}
    content_type = next(
        (value for name, value in headers if name.lower() == _CONTENT_TYPE), b""
    )
    csp = _DOCUMENT_CSP if content_type.lower().startswith(_HTML) else _LOCKED_CSP
    wanted = (*_ALWAYS, (_CSP, csp))
    return [*headers, *((name, value) for name, value in wanted if name not in present)]
