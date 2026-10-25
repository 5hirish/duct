"""A fetch is bounded in bytes and in time, on the way in.

The body cap used to be applied after ``aread()`` had buffered the whole
response, so it bounded what reached the parser and not what reached memory.
A page the audit is pointed at — the target itself, a search result, a link
the model followed — that streams gigabytes quickly was an out-of-memory on
the one-gigabyte API container, and every tenant's live session went with it.
Nothing here touches the network: the transport is canned and DNS is stubbed.
"""

from __future__ import annotations

import asyncio
import socket

import httpx
import pytest

from service.crawl import fetcher
from service.crawl.fetcher import fetch, fetch_bytes, make_client

CHUNK = 1024 * 1024
PUBLIC = "93.184.216.34"


@pytest.fixture
async def public_dns(monkeypatch):
    """Every hostname resolves to a public address, so the SSRF hook lets the
    canned transport answer. Async, because the loop to patch is the test's."""

    async def fake_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (PUBLIC, port or 0))]

    loop = asyncio.get_running_loop()
    monkeypatch.setattr(type(loop), "getaddrinfo", staticmethod(fake_getaddrinfo))


def _client_with(transport):
    """A real make_client, with only its transport swapped for a canned one."""
    client = make_client()
    client._transport = transport
    return client


class _Endless(httpx.AsyncByteStream):
    """A body that never ends. ``served`` counts the chunks handed over."""

    def __init__(self, delay: float = 0.0):
        self.served = 0
        self.delay = delay

    async def __aiter__(self):
        while True:
            if self.delay:
                await asyncio.sleep(self.delay)
            self.served += 1
            yield b"x" * CHUNK

    async def aclose(self) -> None:  # httpx closes the stream when the caller leaves
        return None


def _client_streaming(stream):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=stream)

    return _client_with(httpx.MockTransport(handler))


async def test_the_body_stops_at_the_cap_instead_of_after_it(public_dns):
    stream = _Endless()
    async with _client_streaming(stream) as client:
        result = await fetch(client, "https://big.example/")

    assert result.status == 200
    assert len(result.text) == fetcher._MAX_BYTES
    # One chunk past the cap at most: the response was abandoned, not drained.
    assert stream.served <= fetcher._MAX_BYTES // CHUNK + 1


async def test_fetch_bytes_stops_at_the_cap_too(public_dns):
    stream = _Endless()
    async with _client_streaming(stream) as client:
        body, status = await fetch_bytes(client, "https://big.example/")

    assert status == 200
    assert len(body) == fetcher._MAX_BYTES
    assert stream.served <= fetcher._MAX_BYTES // CHUNK + 1


async def test_a_server_that_drips_is_cut_off_by_the_deadline(public_dns, monkeypatch):
    """Per-read timeouts never fire on a server that sends a little, often;
    the whole exchange has a budget of its own."""
    monkeypatch.setattr(fetcher, "_TOTAL_DEADLINE", 0.05)
    stream = _Endless(delay=0.03)
    async with _client_streaming(stream) as client:
        result = await fetch(client, "https://slow.example/")

    assert result.status == 0
    assert result.text == ""
    assert stream.served < 5


async def test_a_small_page_is_returned_whole(public_dns):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>fine</html>", headers={"x-robots-tag": "all"})

    async with _client_with(httpx.MockTransport(handler)) as client:
        result = await fetch(client, "https://small.example/")

    assert result.status == 200
    assert result.text == "<html>fine</html>"
    assert result.headers["x-robots-tag"] == "all"
