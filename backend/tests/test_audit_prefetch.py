"""The crawl that runs while the user connects a provider.

``start_prefetch`` must answer fast with the root page and keep crawling in
the background; ``take_crawl`` must hand the finished crawl to the pipeline
and nothing else — not another user's, not an expired one, not one that
failed. The HTTP layer is replaced at the module's own seams; the crawl
itself is a stub that records it was asked.

No network.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import pytest

import agents.audit.crawl as audit_crawl
import agents.audit.prefetch as prefetch
from agents.audit.schema import CrawlPlan, CrawlResult, PageSignals
from service.crawl.fetcher import SiteUnreachableError

ROOT = "https://acme.example/"
HTML = """<html><head><title>Meal plans | Acme</title>
<meta name="description" content="Weeknight dinners, planned.">
<link rel="icon" href="/favicon.ico"></head><body><h1>Acme</h1></body></html>"""


@dataclass
class _Fetched:
    """The shape of ``service.crawl.fetcher.FetchResult`` — status, not
    status_code, and the final address only via the redirect chain."""

    status: int = 200
    text: str = HTML
    headers: dict = field(default_factory=dict)
    redirect_chain: list = field(default_factory=lambda: [{"url": ROOT, "status": 200}])


class _Client:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False


@pytest.fixture
def offline(monkeypatch):
    """Root fetch and background crawl replaced; the crawl records its calls."""
    calls: list[str] = []
    fetched = {"result": _Fetched()}

    async def public(_url):
        return None

    async def fetch(_client, url):
        return fetched["result"]

    async def crawl(url, **_kwargs):
        calls.append(url)
        await asyncio.sleep(0)  # yield once, so "still running" is observable
        return CrawlResult(
            plan=CrawlPlan(root_url=url, landing_pages=[url, url + "pricing"]),
            pages=[PageSignals(url=url, title="Meal plans | Acme"), PageSignals(url=url + "pricing", title="Pricing")],
        )

    monkeypatch.setattr(prefetch, "assert_public_url", public)
    monkeypatch.setattr(prefetch, "make_client", lambda: _Client())
    monkeypatch.setattr(prefetch, "fetch", fetch)
    monkeypatch.setattr(audit_crawl, "run_crawl", crawl)
    prefetch._entries.clear()
    return {"calls": calls, "fetched": fetched}


async def test_the_root_page_answers_immediately_and_the_crawl_continues(offline):
    entry = await prefetch.start_prefetch(ROOT, owner_id="guest-1")
    status = entry.status()

    assert status["state"] == prefetch.STATE_RUNNING
    assert status["site"]["title"] == "Meal plans | Acme"
    assert status["site"]["favicon"] == "https://acme.example/favicon.ico"
    assert status["site"]["blocked"] is False
    assert status["draft"]["fields"]["name"]["value"] == "Acme", "layer one, from the root alone"

    crawl = await prefetch.take_crawl(entry.crawl_id, owner_id="guest-1")
    assert crawl is not None and len(crawl.pages) == 2
    assert offline["calls"] == [ROOT], "the background crawl ran exactly once"
    assert entry.status()["state"] == prefetch.STATE_DONE
    assert entry.status()["pages"] == 2


async def test_a_crawl_is_only_handed_to_its_owner(offline):
    entry = await prefetch.start_prefetch(ROOT, owner_id="guest-1")
    await entry.task
    assert await prefetch.take_crawl(entry.crawl_id, owner_id="someone-else") is None
    assert prefetch.get_prefetch(entry.crawl_id, owner_id="someone-else") is None
    assert prefetch.get_prefetch(entry.crawl_id) is not None, "no owner asked → any live entry"


async def test_an_expired_crawl_is_gone(offline, monkeypatch):
    entry = await prefetch.start_prefetch(ROOT, owner_id="guest-1")
    await entry.task
    monkeypatch.setattr(prefetch, "TTL_SECONDS", 0)
    assert await prefetch.take_crawl(entry.crawl_id) is None


async def test_a_failed_crawl_is_reported_not_raised(offline, monkeypatch):
    async def broken(url, **_kwargs):
        raise RuntimeError("sitemap exploded")

    monkeypatch.setattr(audit_crawl, "run_crawl", broken)
    entry = await prefetch.start_prefetch(ROOT, owner_id="guest-1")
    await entry.task
    assert entry.status()["state"] == prefetch.STATE_FAILED
    assert "exploded" in entry.status()["error"]
    assert await prefetch.take_crawl(entry.crawl_id) is None, "the pipeline crawls for itself instead"


async def test_a_bot_wall_is_a_result_the_user_can_see(offline):
    offline["fetched"]["result"] = _Fetched(status=403, text="<html><title>Just a moment...</title></html>")
    entry = await prefetch.start_prefetch(ROOT, owner_id="guest-1")
    assert entry.status()["site"]["blocked"] is True


async def test_no_response_at_all_is_unreachable(offline):
    offline["fetched"]["result"] = _Fetched(status=0, text="", redirect_chain=[])
    with pytest.raises(SiteUnreachableError):
        await prefetch.start_prefetch(ROOT, owner_id="guest-1")
