"""The error classifier: one code per failure, decided from the cause.

The classifier is name-based on purpose (it must not import a provider SDK),
so these tests build exceptions with the class names providers actually raise
and check that the code, the retry decision and the payload agree.
"""

from __future__ import annotations

import asyncio

import pytest

from agents.core.errors import (
    DESCRIPTIONS,
    ErrorCode,
    classify_error,
    error_payload,
    is_retryable,
    retry_after_seconds,
)


def _named(name: str, message: str = "", **attrs):
    """An exception whose class name is what a provider SDK would use."""
    cls = type(name, (Exception,), attrs)
    return cls(message)


@pytest.mark.parametrize(
    "exc, code",
    [
        (_named("RateLimitError", "429 Too Many Requests"), ErrorCode.RATE_LIMITED),
        (_named("ModelRateLimitError"), ErrorCode.RATE_LIMITED),
        (_named("AuthenticationError", "invalid x-api-key"), ErrorCode.AUTH),
        (_named("PermissionDeniedError"), ErrorCode.PERMISSION),
        (_named("NotFoundError", "model: claude-x"), ErrorCode.MODEL_NOT_FOUND),
        (_named("ContextOverflowError"), ErrorCode.CONTEXT_WINDOW),
        (_named("ModelInvalidRequestError", "prompt is too long: 213000 tokens"), ErrorCode.CONTEXT_WINDOW),
        (_named("ModelInvalidRequestError", "temperature must be <= 1"), ErrorCode.BAD_REQUEST),
        (_named("APITimeoutError"), ErrorCode.TIMEOUT),
        (_named("APIConnectionError", "Connection error."), ErrorCode.NETWORK),
        (_named("InternalServerError"), ErrorCode.UPSTREAM_ERROR),
        (_named("RefreshError", "invalid_grant"), ErrorCode.CONNECTOR_EXPIRED),
        (asyncio.TimeoutError(), ErrorCode.TIMEOUT),
        (asyncio.CancelledError(), ErrorCode.CANCELLED),
        (RuntimeError("provider blew up"), ErrorCode.UNKNOWN),
    ],
)
def test_classifies_by_the_names_providers_use(exc, code):
    assert classify_error(exc) is code


@pytest.mark.parametrize(
    "status, message, code",
    [
        (429, "", ErrorCode.RATE_LIMITED),
        (401, "", ErrorCode.AUTH),
        (403, "", ErrorCode.PERMISSION),
        (529, "overloaded_error", ErrorCode.OVERLOADED),
        (503, "", ErrorCode.OVERLOADED),
        (500, "", ErrorCode.UPSTREAM_ERROR),
        (400, "prompt is too long", ErrorCode.CONTEXT_WINDOW),
        (400, "invalid request", ErrorCode.BAD_REQUEST),
    ],
)
def test_an_unknown_class_with_a_status_code_still_classifies(status, message, code):
    exc = _named("SomeProviderError", message, status_code=status)
    assert classify_error(exc) is code


def test_a_google_http_error_is_a_connector_problem_not_a_model_one():
    class Resp:
        status = 403

    exc = _named("HttpError", "insufficient permissions", resp=Resp())
    assert classify_error(exc) is ErrorCode.CONNECTOR_FORBIDDEN
    exc = _named("HttpError", "", resp=type("R", (), {"status": 401})())
    assert classify_error(exc) is ErrorCode.CONNECTOR_EXPIRED


def test_the_cause_decides_when_a_tool_rewraps_a_provider_error():
    try:
        try:
            raise _named("RateLimitError", "429")
        except Exception as inner:
            raise RuntimeError("fetch_ga4 failed") from inner
    except RuntimeError as outer:
        assert classify_error(outer) is ErrorCode.RATE_LIMITED
        assert is_retryable(outer)


def test_an_exception_group_classifies_by_its_members():
    group = ExceptionGroup("tasks", [ValueError("x"), _named("APIConnectionError")])
    assert classify_error(group) is ErrorCode.NETWORK


def test_only_transient_codes_retry():
    assert is_retryable(_named("RateLimitError"))
    assert is_retryable(_named("InternalServerError"))
    assert not is_retryable(_named("AuthenticationError"))
    assert not is_retryable(_named("ContextOverflowError"))
    assert not is_retryable(RuntimeError("unknown"))


def test_the_payload_never_carries_the_raw_message():
    raw = "AuthenticationError: invalid x-api-key sk-ant-abc123 (request id req_9)"
    payload = error_payload(_named("AuthenticationError", raw))
    assert payload == {
        "code": ErrorCode.AUTH,
        "retryable": False,
        "error": DESCRIPTIONS[ErrorCode.AUTH],
    }
    assert "sk-ant" not in payload["error"]


def test_every_code_has_a_description():
    assert set(DESCRIPTIONS) == set(ErrorCode)


# ---------------------------------------------------------------------------
# Retry-After
# ---------------------------------------------------------------------------

class _Response:
    def __init__(self, headers):
        self.headers = headers


def test_retry_after_prefers_the_millisecond_header():
    exc = _named("RateLimitError", "429", response=_Response({"retry-after-ms": "2500", "retry-after": "7"}))
    assert retry_after_seconds(exc) == 2.5


def test_retry_after_reads_seconds_case_insensitively():
    exc = _named("RateLimitError", "429", response=_Response({"Retry-After": "7"}))
    assert retry_after_seconds(exc) == 7.0


def test_retry_after_reads_an_http_date():
    from datetime import datetime, timedelta, timezone
    from email.utils import format_datetime

    when = datetime.now(timezone.utc) + timedelta(seconds=40)
    exc = _named("RateLimitError", "429", response=_Response({"retry-after": format_datetime(when, usegmt=True)}))
    seconds = retry_after_seconds(exc)
    assert seconds is not None and 37 <= seconds <= 40


def test_retry_after_reads_a_provider_attribute_and_looks_through_a_wrapper():
    try:
        try:
            raise _named("ResourceExhausted", "quota", retry_after=12)
        except Exception as inner:
            raise RuntimeError("tool failed") from inner
    except RuntimeError as outer:
        assert retry_after_seconds(outer) == 12.0


def test_retry_after_is_none_when_the_provider_said_nothing():
    assert retry_after_seconds(_named("RateLimitError", "429")) is None
    assert retry_after_seconds(_named("RateLimitError", "429", response=_Response({"retry-after": "soon"}))) is None
    assert retry_after_seconds(_named("RateLimitError", "429", response=_Response(None))) is None
