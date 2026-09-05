"""One classifier for what went wrong, used in three places.

A failure reaches the user through a chain — provider SDK, LangChain's
``ModelError`` wrappers, our tools, the runner, the route — and each link used
to describe it in its own words. The frontend then pattern-matched the prose
("rate limit", "429", "timed out") to pick copy, which rots with every new
phrasing, and the runner retried nothing because it could not tell a rate
limit from a bad API key.

So the failure is classified once, into an ``ErrorCode`` that is a wire
contract with the frontend (app/src/lib/agentEvents.js), and that code is what
decides a retry (``is_retryable``), what rides on the failure event
(``error_payload``), and what copy and action the client offers. The raw
message never reaches the user; it goes to the log.

Framework-free on purpose: this file is imported by domain code, so it must
not import LangChain or a provider SDK (tests/test_harness_boundaries.py).
Exceptions are recognised by the class names in their MRO and the attributes
provider SDKs agree on (``status_code``), which also means a provider we have
not met yet degrades to a sensible code instead of an import error.
"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from enum import StrEnum


class ErrorCode(StrEnum):
    """Why a turn or a run failed. Wire contract — add members, never rename."""

    # Transient at the model provider — worth retrying with backoff.
    RATE_LIMITED = "rate_limited"
    OVERLOADED = "overloaded"
    UPSTREAM_ERROR = "upstream_error"
    TIMEOUT = "timeout"
    NETWORK = "network"
    # Permanent for this request — retrying the same call cannot help.
    AUTH = "auth"
    PERMISSION = "permission"
    CONTEXT_WINDOW = "context_window"
    BAD_REQUEST = "bad_request"
    MODEL_NOT_FOUND = "model_not_found"
    # A connector the agent reads through, not the model.
    CONNECTOR_EXPIRED = "connector_expired"
    CONNECTOR_FORBIDDEN = "connector_forbidden"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


RETRYABLE: frozenset[ErrorCode] = frozenset({
    ErrorCode.RATE_LIMITED,
    ErrorCode.OVERLOADED,
    ErrorCode.UPSTREAM_ERROR,
    ErrorCode.TIMEOUT,
    ErrorCode.NETWORK,
})

# Short, user-facing, and code-specific; the frontend has its own copy per
# code and may say more. What matters here is that no raw exception text is
# ever the message.
DESCRIPTIONS: dict[ErrorCode, str] = {
    ErrorCode.RATE_LIMITED: "The model provider is rate limiting us.",
    ErrorCode.OVERLOADED: "The model provider is overloaded right now.",
    ErrorCode.UPSTREAM_ERROR: "The model provider returned an error.",
    ErrorCode.TIMEOUT: "The model took too long to answer.",
    ErrorCode.NETWORK: "Could not reach the model provider.",
    ErrorCode.AUTH: "The model provider rejected the API key.",
    ErrorCode.PERMISSION: "The API key is not allowed to use this model.",
    ErrorCode.CONTEXT_WINDOW: "The conversation no longer fits the model's context.",
    ErrorCode.BAD_REQUEST: "The model provider rejected the request.",
    ErrorCode.MODEL_NOT_FOUND: "That model is not available on this provider.",
    ErrorCode.CONNECTOR_EXPIRED: "A connected account needs to be reconnected.",
    ErrorCode.CONNECTOR_FORBIDDEN: "A connected account does not have access to that data.",
    ErrorCode.CANCELLED: "The run was stopped.",
    ErrorCode.UNKNOWN: "Something went wrong.",
}

# LangChain normalises provider errors into these (langchain_core.exceptions);
# each also inherits the provider SDK's own class, so both tables apply.
_BY_CLASS_NAME: dict[str, ErrorCode] = {
    "ModelRateLimitError": ErrorCode.RATE_LIMITED,
    "ModelAuthenticationError": ErrorCode.AUTH,
    "ModelPermissionDeniedError": ErrorCode.PERMISSION,
    "ModelInvalidRequestError": ErrorCode.BAD_REQUEST,
    "ModelNotFoundError": ErrorCode.MODEL_NOT_FOUND,
    "ContextOverflowError": ErrorCode.CONTEXT_WINDOW,
    "ModelConnectionError": ErrorCode.NETWORK,
    "ModelTimeoutError": ErrorCode.TIMEOUT,
    "ModelAPIError": ErrorCode.UPSTREAM_ERROR,
    # Provider SDKs (anthropic, openai share these names).
    "RateLimitError": ErrorCode.RATE_LIMITED,
    "AuthenticationError": ErrorCode.AUTH,
    "PermissionDeniedError": ErrorCode.PERMISSION,
    "NotFoundError": ErrorCode.MODEL_NOT_FOUND,
    "APITimeoutError": ErrorCode.TIMEOUT,
    "APIConnectionError": ErrorCode.NETWORK,
    "InternalServerError": ErrorCode.UPSTREAM_ERROR,
    # httpx / stdlib.
    "TimeoutException": ErrorCode.TIMEOUT,
    "ConnectError": ErrorCode.NETWORK,
    "ConnectionError": ErrorCode.NETWORK,
    # Google auth: the refresh token behind a connector is gone.
    "RefreshError": ErrorCode.CONNECTOR_EXPIRED,
}

_CONTEXT_WINDOW_RE = re.compile(
    r"prompt is too long|context.?(window|length)|maximum.*tokens|token limit|too many tokens",
    re.IGNORECASE,
)
_RATE_LIMIT_RE = re.compile(r"rate.?limit|too many requests", re.IGNORECASE)
_OVERLOADED_RE = re.compile(r"overloaded", re.IGNORECASE)
_TIMEOUT_RE = re.compile(r"timed?.?out", re.IGNORECASE)
_NETWORK_RE = re.compile(r"connection (refused|reset|error)|network|ECONNREFUSED|unreachable", re.IGNORECASE)


def _from_status(status: int, message: str, *, connector: bool = False) -> ErrorCode | None:
    if status == 429:
        return ErrorCode.RATE_LIMITED
    if status == 401:
        return ErrorCode.CONNECTOR_EXPIRED if connector else ErrorCode.AUTH
    if status == 403:
        return ErrorCode.CONNECTOR_FORBIDDEN if connector else ErrorCode.PERMISSION
    if status == 404:
        return ErrorCode.MODEL_NOT_FOUND
    if status in (408, 504):
        return ErrorCode.TIMEOUT
    if status in (502, 503, 529):
        return ErrorCode.OVERLOADED
    if status >= 500:
        return ErrorCode.UPSTREAM_ERROR
    if status == 400:
        return ErrorCode.CONTEXT_WINDOW if _CONTEXT_WINDOW_RE.search(message) else ErrorCode.BAD_REQUEST
    return None


def _classify_one(exc: BaseException) -> ErrorCode | None:
    if isinstance(exc, asyncio.CancelledError):
        return ErrorCode.CANCELLED
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
        return ErrorCode.TIMEOUT
    names = [cls.__name__ for cls in type(exc).__mro__]
    message = str(exc)
    # Google API client errors (connectors) carry the status on ``resp``.
    if "HttpError" in names:
        status = getattr(getattr(exc, "resp", None), "status", None)
        if isinstance(status, int):
            return _from_status(status, message, connector=True)
    for name in names:
        code = _BY_CLASS_NAME.get(name)
        if code is None:
            continue
        # A 400 from the SDK is the one class that hides two meanings.
        if name == "ModelInvalidRequestError" and _CONTEXT_WINDOW_RE.search(message):
            return ErrorCode.CONTEXT_WINDOW
        return code
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        code = _from_status(status, message)
        if code is not None:
            return code
    if _CONTEXT_WINDOW_RE.search(message):
        return ErrorCode.CONTEXT_WINDOW
    if _RATE_LIMIT_RE.search(message):
        return ErrorCode.RATE_LIMITED
    if _OVERLOADED_RE.search(message):
        return ErrorCode.OVERLOADED
    if _TIMEOUT_RE.search(message):
        return ErrorCode.TIMEOUT
    if _NETWORK_RE.search(message):
        return ErrorCode.NETWORK
    return None


def _chain(exc: BaseException):
    """The exception and everything it wraps, nearest first."""
    seen: set[int] = set()
    stack: list[BaseException] = [exc]
    while stack:
        current = stack.pop(0)
        if id(current) in seen:
            continue
        seen.add(id(current))
        yield current
        for inner in getattr(current, "exceptions", None) or ():  # ExceptionGroup
            if isinstance(inner, BaseException):
                stack.append(inner)
        for attr in ("__cause__", "__context__"):
            inner = getattr(current, attr, None)
            if isinstance(inner, BaseException):
                stack.append(inner)


_RETRY_AFTER_HEADERS = (("retry-after-ms", 1000.0), ("retry-after", 1.0))


def _header(headers: Any, name: str) -> Any:
    """A header by case-insensitive name from whatever the SDK exposes —
    ``httpx.Headers``, a dict, ``requests``' structure — without importing any
    of them."""
    if headers is None:
        return None
    try:
        value = headers.get(name)
        if value is None and hasattr(headers, "items"):
            wanted = name.lower()
            for key, candidate in headers.items():
                if str(key).lower() == wanted:
                    value = candidate
                    break
    except Exception:  # noqa: BLE001 - not a mapping after all
        return None
    return value


def _parse_retry_after(value: Any, divisor: float) -> float | None:
    """Seconds from a Retry-After value: a number, or an HTTP date."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        seconds = float(text) / divisor
    except ValueError:
        try:
            when = parsedate_to_datetime(text)
        except (TypeError, ValueError):
            return None
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        seconds = (when - datetime.now(timezone.utc)).total_seconds()
    return max(0.0, seconds)


def retry_after_seconds(exc: BaseException) -> float | None:
    """How long the provider asked us to wait before retrying, if it said.

    Anthropic and OpenAI put it on the response (``retry-after-ms`` first,
    then ``retry-after`` as seconds or an HTTP date); some SDKs surface it as a
    ``retry_after`` attribute. Backing off on our own schedule when the
    provider has told us the real one only makes the retry fail again.
    """
    for current in _chain(exc):
        for holder in (current, getattr(current, "response", None)):
            if holder is None:
                continue
            direct = getattr(holder, "retry_after", None)
            if isinstance(direct, (int, float)) and not isinstance(direct, bool):
                return max(0.0, float(direct))
            headers = getattr(holder, "headers", None)
            for name, divisor in _RETRY_AFTER_HEADERS:
                parsed = _parse_retry_after(_header(headers, name), divisor)
                if parsed is not None:
                    return parsed
    return None


def classify_error(exc: BaseException) -> ErrorCode:
    """The ``ErrorCode`` for an exception, looking through what it wraps.

    A tool that catches a provider error and re-raises it as its own type
    still classifies by the cause — the user cares that the key was rejected,
    not which layer noticed.
    """
    for current in _chain(exc):
        code = _classify_one(current)
        if code is not None:
            return code
    return ErrorCode.UNKNOWN


def is_retryable(exc: BaseException) -> bool:
    """Whether the same request may succeed if sent again shortly."""
    return classify_error(exc) in RETRYABLE


def error_payload(exc: BaseException) -> dict:
    """The failure fields for a STEP_FAILED / PIPELINE_FAILED event.

    ``error`` is a short sentence, never ``str(exc)`` — that carried tracebacks,
    request ids and once a URL with a key in it to the browser.
    """
    code = classify_error(exc)
    return {"code": code, "retryable": code in RETRYABLE, "error": DESCRIPTIONS[code]}
