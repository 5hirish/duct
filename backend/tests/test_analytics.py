"""The analytics seam's three promises: quiet on a laptop, one person write a
day, and a logged traceback reaches error tracking like an uncaught one."""

from __future__ import annotations

import logging
import uuid
from types import SimpleNamespace

import pytest

from service import analytics


class _FakeClient:
    def __init__(self):
        self.sets, self.events, self.exceptions = [], [], []

    def set(self, *, distinct_id, properties):
        self.sets.append((distinct_id, properties))

    def capture(self, event, properties=None):
        self.events.append((event, properties))

    def capture_exception(self, exc, properties=None):
        self.exceptions.append((exc, properties))


@pytest.fixture
def fake(monkeypatch):
    client = _FakeClient()
    monkeypatch.setattr(analytics, "_client", client)
    monkeypatch.setattr(analytics, "_client_built", True)
    monkeypatch.setattr(analytics, "_identified", {})
    return client


def _user(**overrides):
    return SimpleNamespace(id=uuid.uuid4(), email="a@example.com", full_name="Ada", **overrides)


def test_a_loopback_deployment_sends_nothing_even_with_a_key(monkeypatch):
    cfg = SimpleNamespace(
        posthog_api_key="phc_test", posthog_host="https://example.invalid",
        posthog_enable_localhost=False, api_public_url="http://127.0.0.1:8002", app_env="local",
    )
    monkeypatch.setattr(analytics, "get_configs", lambda: cfg)
    monkeypatch.setattr(analytics, "_client", None)
    monkeypatch.setattr(analytics, "_client_built", False)
    assert analytics.client() is None


def test_no_key_means_no_client(monkeypatch):
    cfg = SimpleNamespace(posthog_api_key="", api_public_url="https://api.example.com")
    monkeypatch.setattr(analytics, "get_configs", lambda: cfg)
    monkeypatch.setattr(analytics, "_client", None)
    monkeypatch.setattr(analytics, "_client_built", False)
    assert analytics.client() is None
    analytics.capture_event("anything")  # a no-op, not an error


def test_the_person_write_happens_once_per_user_not_once_per_request(fake):
    user = _user()
    for _ in range(5):
        analytics.identify_user(user)
    assert fake.sets == [(str(user.id), {"email": "a@example.com", "name": "Ada"})]


def test_a_logged_traceback_is_reported_with_its_logger(fake):
    handler = analytics._LoggedExceptionHandler(level=logging.ERROR)
    log = logging.getLogger("duct.test.analytics")
    log.addHandler(handler)
    try:
        try:
            raise ValueError("pull failed")
        except ValueError:
            log.exception("connector pull failed")
        log.error("no traceback here")
    finally:
        log.removeHandler(handler)
    assert len(fake.exceptions) == 1
    exc, props = fake.exceptions[0]
    assert isinstance(exc, ValueError)
    assert props == {"logger": "duct.test.analytics", "log_message": "connector pull failed"}


def test_uvicorns_own_report_of_an_uncaught_error_is_not_sent_twice(fake):
    handler = analytics._LoggedExceptionHandler(level=logging.ERROR)
    log = logging.getLogger("uvicorn.error")
    log.addHandler(handler)
    try:
        try:
            raise RuntimeError("boom")
        except RuntimeError:
            log.exception("Exception in ASGI application")
    finally:
        log.removeHandler(handler)
    assert fake.exceptions == []


def test_the_middleware_mounts_and_serves_with_a_real_client(monkeypatch):
    """Only the production deploy has a key, so only it mounts the middleware.
    Build the stack with the real SDK, the way the first request does."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from posthog import Posthog

    real = Posthog("phc_test", host="https://example.invalid", disabled=True, sync_mode=True)
    monkeypatch.setattr(analytics, "_client", real)
    monkeypatch.setattr(analytics, "_client_built", True)
    app = FastAPI()
    app.get("/health")(lambda: {"ok": True})
    root = logging.getLogger()
    handlers_before = list(root.handlers)
    try:
        analytics.install(app)
        assert TestClient(app).get("/health").status_code == 200
    finally:
        root.handlers[:] = handlers_before
