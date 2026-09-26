"""The rules for fetching a URL somebody else chose (service/url_safety.py).

Every test drives the real function over an ``httpx.MockTransport``, so what is
asserted is what would have gone over the wire — including the requests that
must never be sent at all.
"""

from __future__ import annotations

import httpx
import pytest

from service.url_safety import FetchRefused, check_url, fetch_allowlisted, host_on_allowlist

DOMAINS = frozenset({"tiktokcdn.com", "api.apify.com"})
IMAGES = frozenset({"image/jpeg", "image/png"})
JPEG = b"\xff\xd8\xff" + b"x" * 64


class Wire:
    """A transport that answers from a table and records every request."""

    def __init__(self, routes: dict[str, httpx.Response]):
        self.routes = routes
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.routes.get(str(request.url), httpx.Response(404))

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self))


def fetch(wire: Wire, url: str, **kwargs):
    kwargs.setdefault("domains", DOMAINS)
    kwargs.setdefault("content_types", IMAGES)
    kwargs.setdefault("max_bytes", 1024)
    with wire.client() as client:
        return fetch_allowlisted(client, url, **kwargs)


def image(body: bytes = JPEG, content_type: str = "image/jpeg") -> httpx.Response:
    return httpx.Response(200, content=body, headers={"content-type": content_type})


# ---------------------------------------------------------------------------
# The URL itself
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "host, allowed",
    [
        ("tiktokcdn.com", True),
        ("p16-sign-va.tiktokcdn.com", True),
        ("P16-SIGN.TIKTOKCDN.COM.", True),
        ("eviltiktokcdn.com", False),              # the right letters, the wrong domain
        ("tiktokcdn.com.attacker.net", False),
        ("x.api.apify.com", True),
        ("apify.com", False),
    ],
)
def test_hosts_match_on_a_dot_boundary_never_a_substring(host, allowed):
    assert host_on_allowlist(host, DOMAINS) is allowed


@pytest.mark.parametrize(
    "url",
    [
        "http://p16.tiktokcdn.com/a.jpg",                 # not https
        "https://169.254.169.254/latest/meta-data/",      # cloud metadata
        "https://127.0.0.1/a.jpg",
        "https://[::1]/a.jpg",
        "https://p16.tiktokcdn.com:8443/a.jpg",           # an unusual port is a different service
        "https://p16.tiktokcdn.com@evil.example/a.jpg",   # userinfo: the host is evil.example
        "https://evil.example/?next=p16.tiktokcdn.com",
        "file:///etc/passwd",
        "https:///nohost",
    ],
)
def test_a_url_off_the_rules_is_refused_before_any_request(url):
    wire = Wire({})
    with pytest.raises(FetchRefused):
        fetch(wire, url)
    assert wire.requests == []


def test_check_url_names_the_host_it_allowed():
    assert check_url("https://p16.tiktokcdn.com:443/a.jpg", DOMAINS) == "p16.tiktokcdn.com"


# ---------------------------------------------------------------------------
# Redirects
# ---------------------------------------------------------------------------

def test_a_redirect_between_allowed_hosts_is_followed():
    wire = Wire({
        "https://p16.tiktokcdn.com/a.jpg": httpx.Response(302, headers={"location": "https://p19.tiktokcdn.com/a.jpg"}),
        "https://p19.tiktokcdn.com/a.jpg": image(),
    })
    got = fetch(wire, "https://p16.tiktokcdn.com/a.jpg")
    assert got.data == JPEG and got.content_type == "image/jpeg"


@pytest.mark.parametrize(
    "location",
    [
        "http://169.254.169.254/latest/meta-data/",
        "https://10.0.0.7/internal",
        "https://localhost/admin",
        "https://evil.example/a.jpg",
    ],
)
def test_a_redirect_off_the_allowlist_is_never_followed(location):
    wire = Wire({"https://p16.tiktokcdn.com/a.jpg": httpx.Response(302, headers={"location": location})})
    with pytest.raises(FetchRefused):
        fetch(wire, "https://p16.tiktokcdn.com/a.jpg")
    assert [str(r.url) for r in wire.requests] == ["https://p16.tiktokcdn.com/a.jpg"]


def test_a_redirect_loop_gives_up():
    url = "https://p16.tiktokcdn.com/a.jpg"
    wire = Wire({url: httpx.Response(302, headers={"location": url})})
    with pytest.raises(FetchRefused, match="redirects"):
        fetch(wire, url)


def test_headers_do_not_follow_a_redirect_to_another_host():
    """The Apify token is for Apify; a bounce to a CDN must not carry it."""
    token = "test-token-value"
    record = "https://api.apify.com/v2/key-value-stores/s1/records/cover"
    wire = Wire({
        record: httpx.Response(302, headers={"location": "https://p16.tiktokcdn.com/c.jpg"}),
        "https://p16.tiktokcdn.com/c.jpg": image(),
    })
    fetch(wire, record, headers={"Authorization": f"Bearer {token}"})
    first, second = wire.requests
    assert first.headers["authorization"] == f"Bearer {token}"
    assert "authorization" not in second.headers


# ---------------------------------------------------------------------------
# The response
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "response",
    [
        image(content_type="image/svg+xml"),       # a document that runs script
        image(content_type="text/html"),
        httpx.Response(200, content=JPEG),        # no content type at all
        httpx.Response(403, content=b"expired"),  # a signed URL past its expiry
    ],
)
def test_anything_but_an_accepted_image_is_refused(response):
    wire = Wire({"https://p16.tiktokcdn.com/a.jpg": response})
    with pytest.raises(FetchRefused):
        fetch(wire, "https://p16.tiktokcdn.com/a.jpg")


def test_content_type_parameters_are_ignored():
    wire = Wire({"https://p16.tiktokcdn.com/a.jpg": image(content_type="IMAGE/JPEG; charset=binary")})
    assert fetch(wire, "https://p16.tiktokcdn.com/a.jpg").content_type == "image/jpeg"


def test_a_body_over_the_cap_is_refused_whether_declared_or_not():
    big = b"x" * 2048
    declared = Wire({"https://p16.tiktokcdn.com/a.jpg": image(big)})
    with pytest.raises(FetchRefused, match="over"):
        fetch(declared, "https://p16.tiktokcdn.com/a.jpg")

    def chunks():
        yield big

    undeclared = Wire({
        "https://p16.tiktokcdn.com/a.jpg": httpx.Response(200, content=chunks(), headers={"content-type": "image/jpeg"}),
    })
    with pytest.raises(FetchRefused, match="passed"):
        fetch(undeclared, "https://p16.tiktokcdn.com/a.jpg")


def test_a_transport_error_is_a_refusal_not_a_crash():
    def broken(request):
        raise httpx.ConnectError("no route", request=request)

    with httpx.Client(transport=httpx.MockTransport(broken)) as client:
        with pytest.raises(FetchRefused, match="transport"):
            fetch_allowlisted(
                client, "https://p16.tiktokcdn.com/a.jpg",
                domains=DOMAINS, content_types=IMAGES, max_bytes=1024,
            )
