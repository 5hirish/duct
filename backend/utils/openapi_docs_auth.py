"""Optional HTTP Basic auth for /docs, /redoc, and /openapi.json when they are enabled."""

from __future__ import annotations

import base64
import binascii
import secrets
from collections.abc import Callable
from typing import Any

from config import get_configs


def _is_docs_path(path: str) -> bool:
    if path == "/openapi.json":
        return True
    return (
        path == "/docs"
        or path.startswith("/docs/")
        or path == "/redoc"
        or path.startswith("/redoc/")
    )


def _authorization_header(scope: dict[str, Any]) -> str | None:
    for key, value in scope.get("headers") or []:
        if key.lower() == b"authorization":
            return value.decode("latin-1")
    return None


def _parse_basic(auth_header: str) -> tuple[str, str] | None:
    if not auth_header.startswith("Basic "):
        return None
    try:
        raw = base64.b64decode(auth_header.removeprefix("Basic ").strip(), validate=True)
        decoded = raw.decode("utf-8")
    except (ValueError, binascii.Error, UnicodeDecodeError):
        return None
    if ":" not in decoded:
        return None
    user, _, password = decoded.partition(":")
    return user, password


async def _unauthorized(send: Callable[..., Any]) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": 401,
            "headers": [
                (b"content-type", b"text/plain; charset=utf-8"),
                (b"www-authenticate", b'Basic realm="Duct API documentation"'),
            ],
        }
    )
    await send({"type": "http.response.body", "body": b"Authorization required"})


class OpenapiDocsBasicAuthMiddleware:
    """Require HTTP Basic auth for OpenAPI UI and schema when a password is configured."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Callable, send: Callable) -> Any:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        settings = get_configs()
        if not settings.expose_openapi_docs or not settings.openapi_docs_basic_password:
            return await self.app(scope, receive, send)

        path = scope.get("path", "")
        if not _is_docs_path(path):
            return await self.app(scope, receive, send)

        parsed = _parse_basic(_authorization_header(scope) or "")
        if parsed is None:
            return await _unauthorized(send)
        user, password = parsed
        if not secrets.compare_digest(
            user.encode("utf-8"),
            settings.openapi_docs_basic_user.encode("utf-8"),
        ) or not secrets.compare_digest(
            password.encode("utf-8"),
            settings.openapi_docs_basic_password.encode("utf-8"),
        ):
            return await _unauthorized(send)

        return await self.app(scope, receive, send)
