"""Searching the MCP Registry, from its response to the route.

The page is shaped like the registry's own ``/v0/servers`` answer for
"stripe" on 2026-11-03, trimmed: Stripe's server among gateways, a copy at a
lookalike host, a deprecated entry, a URL template, an SSE-only remote and a
local package. What these hold is the one claim the Connections page makes
about each result, who runs it, and that nothing Duct cannot call is offered.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import routes.mcp_servers as mcp_routes
import service.auth as auth_service
import service.mcp.registry as registry
from config import Configs
from models.auth import User
from service.mcp.oauth import AUTH_KEY

OFFICIAL = "io.modelcontextprotocol.registry/official"


def _entry(name, url=None, *, title=None, description="", status="active", kind="streamable-http", headers=(), **extra):
    server = {"name": name, "description": description, "version": "1.0.0", **extra}
    if title:
        server["title"] = title
    if url:
        server["remotes"] = [{"type": kind, "url": url, "headers": list(headers)}]
    else:
        server["packages"] = [{"registryType": "npm", "identifier": name.split("/")[-1]}]
    return {"server": server, "_meta": {OFFICIAL: {"status": status, "isLatest": True}}}


KEY = {"name": "Authorization", "isRequired": True, "isSecret": True, "description": "Your secret key, as Bearer sk_..."}

STRIPE_PAGE = {
    "servers": [
        _entry("app.vercel.stripecheckup/stripecheckup", "https://stripecheckup.vercel.app/api/mcp",
               description="Audit a Stripe account's checkout setup."),
        _entry("com.insightfulpipe/stripe", "https://stripe.insightfulmcp.com/",
               title="Stripe MCP by InsightfulPipe", description="Stripe data through InsightfulPipe."),
        _entry("com.stripe/mcp", "https://mcp.stripe.com", description="Stripe's own server for payments.",
               websiteUrl="https://docs.stripe.com/mcp"),
        _entry("com.evil/stripe", "https://stripe.evil.com/mcp", title="Stripe", description="Stripe tools."),
        _entry("eu.nordicmcp/stripe", "https://nordicmcp.eu/mcp/stripe/{token}", description="Stripe."),
        _entry("io.github.csoai/stripe-checkout", "https://api.meok.ai/v1/stripe", status="deprecated"),
        _entry("io.github.friendlygeorge/stripe-mcp-server", description="Run Stripe tools locally."),
        _entry("io.github.pipeworx-io/stripe", "https://gateway.pipeworx.io/stripe/mcp",
               title="Stripe", description="Stripe through Pipeworx."),
        _entry("io.github.legacy/stripe", "https://legacy.example.com/sse", kind="sse", description="Stripe."),
        _entry("com.keyed/stripe-reports", "https://mcp.keyed.com/mcp", title="Stripe Reports MCP Server",
               description="Stripe revenue reports.", headers=[KEY]),
        _entry("com.custom/stripe", "https://mcp.custom.com/mcp", description="Stripe.",
               headers=[{"name": "X-Api-Key", "isRequired": True}]),
        # A copy of Stripe's address under someone else's name.
        _entry("io.github.copycat/stripe", "https://mcp.stripe.com", description="Stripe, again."),
    ]
}


def _by_url(listings):
    return {listing.url: listing for listing in listings}


def test_the_vendors_own_server_comes_first_and_is_the_only_official_one():
    listings = registry.parse(STRIPE_PAGE, ["stripe"])
    assert listings[0].url == "https://mcp.stripe.com"
    assert listings[0].official and listings[0].runs_host
    assert [x.url for x in listings if x.official] == ["https://mcp.stripe.com"]
    # The copy of the same address is folded into the vendor's entry.
    assert listings[0].name == "com.stripe/mcp"


def test_a_lookalike_host_and_a_platform_subdomain_are_not_the_vendor():
    found = _by_url(registry.parse(STRIPE_PAGE, ["stripe"]))
    # evil.com proved evil.com: it runs stripe.evil.com, and is not Stripe.
    evil = found["https://stripe.evil.com/mcp"]
    assert evil.runs_host and not evil.official
    checkup = found["https://stripecheckup.vercel.app/api/mcp"]
    assert checkup.runs_host and not checkup.official


def test_a_platform_that_hands_out_subdomains_vouches_for_nobody():
    # Proving a name under vercel.app proves that name, not Vercel: on
    # 2026-11-04 a search for "vercel" tagged 29 strangers Official this way.
    assert not registry.is_official("app.vercel.agent-svg/mcp", "agent-svg.vercel.app", ["vercel"])
    assert not registry.is_official("app.railway.up.widgets/mcp", "widgets.up.railway.app", ["railway"])
    assert not registry.is_official("co.supabase.abcd/mcp", "abcd.supabase.co", ["supabase"])
    # The name itself is no better: whoever registered stripe.vercel.app first.
    assert registry.runs_host("app.vercel.stripe/mcp", "stripe.vercel.app")
    assert not registry.is_official("app.vercel.stripe/mcp", "stripe.vercel.app", ["stripe"])
    # The platform's own server, on its own domain, still is.
    assert registry.is_official("com.vercel/mcp", "mcp.vercel.com", ["vercel"])
    # A GitHub login proves nothing there: its owner picks the subdomain too.
    assert not registry.runs_host("io.github.widgets/mcp", "widgets.vercel.app")
    assert not registry.runs_host("io.github.vercel-fan/mcp", "widgets.vercel.app")


def test_a_tenant_is_not_the_vendor_even_on_a_platform_nobody_listed():
    # Toolbox suggests these names, so a tenant of the vendor is the attack:
    # a free site and a GitHub login containing the word were enough.
    for name, host, tool in [
        ("io.webflow.stranger/mcp", "stranger.webflow.io", "webflow"),
        ("io.github.webflow-fan/mcp", "stranger.webflow.io", "webflow"),
        ("site.figma.stranger/mcp", "stranger.figma.site", "figma"),
        ("site.canva.stranger/mcp", "stranger.canva.site", "canva"),
        ("com.airtable.stranger/mcp", "stranger.airtable.com", "airtable"),
        ("com.sentry.stranger/mcp", "stranger.sentry.com", "sentry"),
        # Listed nowhere: refused for its shape.
        ("app.someplatform.stranger/mcp", "stranger.someplatform.app", "someplatform"),
        ("io.github.someplatform-fan/mcp", "stranger.someplatform.app", "someplatform"),
    ]:
        assert not registry.is_official(name, host, [tool]), host
    # A listed platform refuses even the name a real vendor would use.
    assert not registry.is_official("io.webflow.mcp/mcp", "mcp.webflow.io", ["webflow"])


def test_a_vendor_is_official_at_its_domain_or_one_service_label_under_it():
    for name, host, tool in [
        ("com.figma.mcp/mcp", "mcp.figma.com", "figma"),
        ("com.widgets/mcp", "widgets.com", "widgets"),
        ("com.widgets/mcp", "api.widgets.com", "widgets"),
        ("com.widgets/mcp", "app.widgets.com", "widgets"),
    ]:
        assert registry.is_official(name, host, [tool]), host
    # An unusual place costs the tag, not the listing.
    assert registry.runs_host("com.cloudflare/docs", "docs.mcp.cloudflare.com")
    assert not registry.is_official("com.cloudflare/docs", "docs.mcp.cloudflare.com", ["cloudflare"])


def test_who_runs_the_host_is_read_from_the_name_the_publisher_proved():
    assert registry.runs_host("com.notion/mcp", "mcp.notion.com")
    assert registry.runs_host("com.figma.mcp/mcp", "mcp.figma.com")
    assert not registry.runs_host("com.insightfulpipe/stripe", "stripe.insightfulmcp.com")
    # A GitHub login vouches for the site it names.
    assert registry.runs_host("io.github.getsentry/sentry-mcp", "mcp.sentry.dev")
    assert registry.runs_host("io.github.PostHog/mcp", "mcp.posthog.com")
    assert registry.runs_host("io.github.pipeworx-io/stripe", "gateway.pipeworx.io")
    assert not registry.runs_host("io.github.sadri-dridi/figma", "sensor.nolimit-observatory.workers.dev")
    assert registry.is_official("io.github.getsentry/sentry-mcp", "mcp.sentry.dev", ["sentry"])
    assert not registry.is_official("io.github.pipeworx-io/figma", "gateway.pipeworx.io", ["figma"])


def test_only_what_duct_can_call_is_offered():
    urls = set(_by_url(registry.parse(STRIPE_PAGE, ["stripe"])))
    assert "https://nordicmcp.eu/mcp/stripe/{token}" not in urls  # a credential in the address
    assert "https://api.meok.ai/v1/stripe" not in urls  # deprecated
    assert "https://legacy.example.com/sse" not in urls  # SSE only
    assert "https://mcp.custom.com/mcp" not in urls  # a header Duct cannot send
    assert all(u.startswith("https://") for u in urls)
    assert len(urls) == 6  # local packages have no address at all


def test_a_required_authorization_header_means_a_key():
    keyed = _by_url(registry.parse(STRIPE_PAGE, ["stripe"]))["https://mcp.keyed.com/mcp"]
    assert keyed.auth == AUTH_KEY
    assert keyed.key_hint.startswith("Your secret key")
    assert keyed.title == "Stripe Reports"  # "MCP Server" says what every result is


def test_titles_come_from_the_name_when_the_publisher_gave_none():
    found = _by_url(registry.parse(STRIPE_PAGE, ["stripe"]))
    assert found["https://mcp.stripe.com"].title == "Stripe"
    assert found["https://stripecheckup.vercel.app/api/mcp"].title == "Stripecheckup"
    assert found["https://mcp.stripe.com"].website == "https://docs.stripe.com/mcp"


def test_every_word_of_the_query_must_appear():
    assert [x.url for x in registry.parse(STRIPE_PAGE, ["stripe", "revenue"])] == ["https://mcp.keyed.com/mcp"]
    assert registry.parse(STRIPE_PAGE, ["stripe", "zebra"]) == []
    assert registry.words("  A  Google-Ads ") == ["google-ads"]


# ---------------------------------------------------------------------------
# The request, the cache, the switch
# ---------------------------------------------------------------------------


@pytest.fixture
def wire(monkeypatch):
    """The registry over an ``httpx.MockTransport``: what was asked, and what it answers."""
    state = {"requests": [], "answer": STRIPE_PAGE, "status": 200}

    def handle(request: httpx.Request) -> httpx.Response:
        state["requests"].append(request)
        return httpx.Response(state["status"], json=state["answer"])

    config = Configs(mcp_registry_url="https://registry.example.test/")
    monkeypatch.setattr(registry, "get_configs", lambda: config)
    monkeypatch.setattr(registry, "_transport", httpx.MockTransport(handle))
    registry.clear_cache()
    yield state
    registry.clear_cache()


async def test_a_search_asks_for_the_longest_word_latest_versions_only(wire):
    await registry.search("Stripe reports")
    (request,) = wire["requests"]
    assert request.url.path == "/v0/servers"
    assert dict(request.url.params) == {"search": "reports", "limit": "100", "version": "latest"}


async def test_the_same_search_twice_asks_the_registry_once(wire):
    first = await registry.search("stripe")
    again = await registry.search(" STRIPE ")
    assert first == again and len(wire["requests"]) == 1


async def test_a_registry_that_fails_says_so_in_words(wire):
    wire["status"] = 503
    with pytest.raises(registry.RegistryUnavailable) as caught:
        await registry.search("stripe")
    assert "MCP Registry" in str(caught.value)


async def test_no_address_means_no_search(wire, monkeypatch):
    monkeypatch.setattr(registry, "get_configs", lambda: Configs(mcp_registry_url=""))
    assert await registry.search("stripe") == []
    assert await registry.search("s") == []
    assert wire["requests"] == []


def _client(user):
    app = FastAPI()
    app.include_router(mcp_routes.router, prefix="/api/user/mcp")
    app.dependency_overrides[auth_service.get_current_user] = lambda: user
    return TestClient(app)


def test_the_route_answers_listings_and_says_when_search_is_off(wire, monkeypatch):
    http = _client(User(email="alice@example.com"))
    answer = http.get("/api/user/mcp/registry", params={"q": "stripe"}).json()
    assert answer["available"] is True
    assert answer["servers"][0]["url"] == "https://mcp.stripe.com" and answer["servers"][0]["official"] is True

    monkeypatch.setattr(registry, "get_configs", lambda: Configs(mcp_registry_url=""))
    assert http.get("/api/user/mcp/registry", params={"q": "stripe"}).json() == {"available": False, "servers": []}


def test_the_route_turns_a_registry_failure_into_a_502(wire):
    wire["status"] = 500
    answer = _client(User(email="alice@example.com")).get("/api/user/mcp/registry", params={"q": "stripe"})
    assert answer.status_code == 502
