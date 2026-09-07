"""The crawler refuses to fetch anything that is not on the public internet.

The check that existed validated the URL the caller passed and nothing else,
which left two ways in. A hostname the attacker controls can simply resolve to
169.254.169.254 — name-based checks never see it. And the client follows up to
five redirects, so a public URL answering ``302 -> http://127.0.0.1:8002/`` put
an internal response body in the caller's hands; ``fetch_page_text`` hands that
straight to a model, and the lead-magnet audit runs pre-auth.

Both close in the same place: a request hook that re-runs the address check on
every hop. Nothing here touches the network — DNS is stubbed at the event loop.
"""

from __future__ import annotations

import ipaddress
import socket

import httpx
import pytest

from service.crawl.fetcher import (
    SSRFError,
    assert_public_url,
    fetch,
    make_client,
    validate_public_url,
)

PUBLIC = "93.184.216.34"


@pytest.fixture
def resolves_to(monkeypatch):
    """Point every hostname at an address of the test's choosing."""

    def _set(ip: str):
        family = (
            socket.AF_INET6
            if ipaddress.ip_address(ip).version == 6
            else socket.AF_INET
        )

        async def fake_getaddrinfo(host, port, *args, **kwargs):
            return [(family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, port or 0))]

        import asyncio

        loop = asyncio.get_event_loop()
        monkeypatch.setattr(type(loop), "getaddrinfo", staticmethod(fake_getaddrinfo))

    return _set


# --- the name-only checks, which run before any client is opened -------------

@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://100.64.0.1/",          # Railway's internal range
        "http://[::1]/",
        "http://[::ffff:127.0.0.1]/",  # loopback in an IPv6 costume
        "http://0.0.0.0/",
        "http://metadata.google.internal/",
        "file:///etc/passwd",
    ],
)
def test_obviously_internal_urls_are_refused_without_dns(url):
    with pytest.raises(SSRFError):
        validate_public_url(url)


def test_a_public_bare_ip_is_allowed():
    validate_public_url(f"http://{PUBLIC}/")


# --- the DNS check ----------------------------------------------------------

async def test_a_hostname_resolving_to_link_local_is_refused(resolves_to):
    """The attack the old check could not see: attacker-controlled DNS."""
    resolves_to("169.254.169.254")

    with pytest.raises(SSRFError, match="resolves to a private/reserved address"):
        await assert_public_url("https://evil.example/")


async def test_a_hostname_resolving_publicly_is_allowed(resolves_to):
    resolves_to(PUBLIC)
    await assert_public_url("https://getduct.ai/")


async def test_an_unresolvable_hostname_is_refused(monkeypatch):
    import asyncio

    async def boom(*_a, **_k):
        raise socket.gaierror("nope")

    loop = asyncio.get_event_loop()
    monkeypatch.setattr(type(loop), "getaddrinfo", staticmethod(boom))

    with pytest.raises(SSRFError, match="Could not resolve"):
        await assert_public_url("https://nx.example/")


# --- the redirect hop, which is what the hook is really for ------------------

def _client_with(transport, resolves_to):
    """A real make_client, with only its transport swapped for a canned one."""
    resolves_to(PUBLIC)
    client = make_client()
    client._transport = transport
    return client


async def test_a_redirect_to_an_internal_address_is_not_followed(resolves_to):
    hops: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        hops.append(str(request.url))
        if request.url.host == "evil.example":
            return httpx.Response(302, headers={"location": "http://169.254.169.254/"})
        return httpx.Response(200, text="SECRET")

    client = _client_with(httpx.MockTransport(handler), resolves_to)
    async with client:
        result = await fetch(client, "https://evil.example/")

    # fetch turns every failure into status 0; the point is the body never came.
    assert result.status == 0
    assert result.text == ""
    assert hops == ["https://evil.example/"], "the internal hop must never be sent"


async def test_an_ordinary_redirect_still_works(resolves_to):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/old":
            return httpx.Response(301, headers={"location": "https://getduct.ai/new"})
        return httpx.Response(200, text="<html>fine</html>")

    client = _client_with(httpx.MockTransport(handler), resolves_to)
    async with client:
        result = await fetch(client, "https://getduct.ai/old")

    assert result.status == 200
    assert "fine" in result.text


async def test_the_guard_is_actually_mounted_on_make_client():
    """Cheap insurance: every crawl client must carry the hook."""
    client = make_client()
    try:
        names = [h.__name__ for h in client.event_hooks["request"]]
        assert "_guard_request" in names
    finally:
        await client.aclose()
