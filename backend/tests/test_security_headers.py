"""SecurityHeadersMiddleware: every response locked down, no stream held back."""

from __future__ import annotations

import asyncio

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.testclient import TestClient

from utils.security_headers import SecurityHeadersMiddleware

LOCKED_CSP = "default-src 'none'; frame-ancestors 'none'"


def _app(log: list | None = None) -> FastAPI:
    app = FastAPI()

    @app.get("/data")
    def data():
        return {"ok": True}

    @app.get("/page")
    def page():
        return HTMLResponse("<h1>docs</h1>")

    @app.get("/own")
    def own():
        return JSONResponse({}, headers={"Referrer-Policy": "same-origin"})

    @app.get("/stream")
    def stream():
        async def frames():
            for n in range(3):
                log.append(f"made {n}")
                yield f"data: {n}\n\n"

        return StreamingResponse(frames(), media_type="text/event-stream")

    app.add_middleware(SecurityHeadersMiddleware)
    return app


def test_json_response_is_locked_down():
    res = TestClient(_app()).get("/data")
    assert res.json() == {"ok": True}
    assert res.headers["x-content-type-options"] == "nosniff"
    assert res.headers["x-frame-options"] == "DENY"
    assert res.headers["referrer-policy"] == "no-referrer"
    assert res.headers["content-security-policy"] == LOCKED_CSP


def test_html_document_keeps_its_loads_and_refuses_framing():
    # /docs pulls Swagger UI from a CDN; default-src 'none' would blank it.
    res = TestClient(_app()).get("/page")
    assert res.headers["content-security-policy"] == "frame-ancestors 'none'"
    assert res.headers["x-frame-options"] == "DENY"


def test_a_route_that_sets_a_header_keeps_its_value():
    res = TestClient(_app()).get("/own")
    assert res.headers.get_list("referrer-policy") == ["same-origin"]


def test_event_stream_is_forwarded_frame_by_frame():
    """Each frame reaches the server before the next one is made.

    TestClient collects the whole body before returning, so it cannot tell a
    streaming middleware from a buffering one. Driving the ASGI app directly
    can: a buffering middleware would log every "made" before any "sent".
    """
    log: list[str] = []
    started: list[dict] = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        if message["type"] == "http.response.start":
            started.append(message)
        elif message.get("body"):
            log.append(f"sent {message['body'].decode().split()[1]}")  # "data: 0" → "0"

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.4"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/stream",
        "raw_path": b"/stream",
        "query_string": b"",
        "root_path": "",
        "headers": [],
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
    }
    asyncio.run(_app(log)(scope, receive, send))

    assert log == ["made 0", "sent 0", "made 1", "sent 1", "made 2", "sent 2"]
    headers = dict(started[0]["headers"])
    assert headers[b"content-type"].startswith(b"text/event-stream")
    assert headers[b"content-security-policy"] == LOCKED_CSP.encode()
