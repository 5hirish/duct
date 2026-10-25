"""The crawl's own verdict on whether there is a site to audit.

``fetch`` turns every connection failure into status 0 so one dead page cannot
sink a crawl. For the root that leniency produced a report scoring a page that
never answered, so ``run_crawl`` now refuses to return a result whose root got
no response — while still returning one for a root that answered badly, which
is an SEO finding rather than a missing site.

The HTTP layer is replaced at its seams (plan, text, page fetch); nothing here
touches the network.
"""

from __future__ import annotations

import pytest

import agents.audit.crawl as crawl
from agents.audit.schema import CrawlPlan
from service.crawl.fetcher import FetchResult, SiteUnreachableError

ROOT = "https://getduct.ai"


@pytest.fixture
def offline_http(monkeypatch):
    """Route the crawl's three HTTP seams to canned answers; return the setter
    for the per-page status."""
    statuses: dict[str, int] = {}

    async def plan(_client, root_url, **_kwargs):
        return CrawlPlan(root_url=root_url, landing_pages=[root_url, f"{root_url}/pricing"])

    async def text(_client, _url):
        return "", 404

    async def page(_client, url):
        status = statuses.get(url, 200)
        return FetchResult(text="<html><title>t</title></html>" if status else "", status=status)

    monkeypatch.setattr(crawl, "fetch_crawl_plan", plan)
    monkeypatch.setattr(crawl, "fetch_text", text)
    monkeypatch.setattr(crawl, "fetch", page)
    return statuses


async def test_a_root_that_never_answered_stops_the_crawl(offline_http):
    offline_http[ROOT] = 0

    with pytest.raises(SiteUnreachableError) as excinfo:
        await crawl.run_crawl(ROOT)

    assert excinfo.value.url == ROOT
    assert "no HTTP response" in str(excinfo.value)


async def test_a_root_that_answered_badly_is_still_a_crawl(offline_http):
    """403 from Cloudflare is exactly the kind of thing an audit should say."""
    offline_http[ROOT] = 403
    offline_http[f"{ROOT}/pricing"] = 0

    result = await crawl.run_crawl(ROOT)

    statuses = {p.url: p.http_status for p in result.pages}
    assert statuses[ROOT] == 403
    assert statuses[f"{ROOT}/pricing"] == 0, "a dead inner page stays a lenient status-0 observation"


async def test_the_crawl_fetches_a_few_pages_at_a_time(offline_http, monkeypatch):
    """Every page of the plan used to be opened at once — up to 35 connections
    to one host, which a WAF reads as an attack and a small server as a
    burst. Six at a time is what a polite crawler sends."""
    import asyncio

    urls = [ROOT, *(f"{ROOT}/p{i}" for i in range(19))]  # the root first: the crawl checks it answered

    async def plan(_client, root_url, **_kwargs):
        return CrawlPlan(root_url=root_url, landing_pages=urls)

    in_flight = {"now": 0, "peak": 0}

    async def page(_client, url):
        in_flight["now"] += 1
        in_flight["peak"] = max(in_flight["peak"], in_flight["now"])
        await asyncio.sleep(0.005)
        in_flight["now"] -= 1
        return FetchResult(text="<html><title>t</title></html>", status=200)

    monkeypatch.setattr(crawl, "fetch_crawl_plan", plan)
    monkeypatch.setattr(crawl, "fetch", page)

    result = await crawl.run_crawl(ROOT)

    assert len(result.pages) == 20
    assert 1 < in_flight["peak"] <= crawl.CRAWL_CONCURRENCY
