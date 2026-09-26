"""The Apify client builds a URL Apify serves, and one odd row never empties a scrape.

Both failures were silent in the Discover page: a store slug written as
``user/actor`` became an extra path segment (404 before the actor ever ran),
and a hashtag the actor sent as an object failed the whole post, which was then
dropped at DEBUG. The transport is an ``httpx.MockTransport``, so the real
client code builds and parses every request.
"""

from __future__ import annotations

import logging

import httpx

from service.apify.client import ApifyClient, get_default_actor_ids
from service.apify.schema import ScrapedPost


def _client(handler) -> ApifyClient:
    return ApifyClient("test-key", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))


async def test_a_store_slug_is_addressed_with_a_tilde():
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return httpx.Response(201, json={"data": {"id": "run1", "defaultDatasetId": "ds1"}})

    async with _client(handler) as client:
        await client.start_run(get_default_actor_ids()["post_by_hashtag"], {})

    assert seen == ["/v2/acts/clockworks~tiktok-scraper/runs"]


def test_hashtags_are_bare_names_whatever_shape_the_actor_sends():
    post = ScrapedPost.model_validate({
        "id": "1",
        "hashtags": [{"id": "9", "name": "skincare", "title": "", "cover": ""}, " glow ", {"name": ""}, None],
    })

    assert post.hashtags == ["skincare", "glow"]


async def test_a_dropped_item_is_a_warning_that_names_the_field(caplog):
    items = [{"id": "good"}, {"id": "bad", "playCount": "lots"}]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=items)

    with caplog.at_level(logging.WARNING, logger="service.apify.client"):
        async with _client(handler) as client:
            posts = await client.get_dataset_posts("ds1")

    assert [p.id for p in posts] == ["good"]
    (record,) = [r for r in caplog.records if "dropped invalid item" in r.getMessage()]
    assert record.levelno == logging.WARNING
    assert "playCount" in record.getMessage()



def test_discover_runs_only_the_two_actors_with_bounded_input():
    """The route passed the browser's actor and input straight to Apify on
    Duct's key; any signed-in user could run any store actor on our bill."""
    import pytest

    from service.apify.policy import MAX_RESULTS_PER_PAGE, discover_run_input

    actors = get_default_actor_ids()
    run_input = discover_run_input(actors["post_by_hashtag"], {
        "hashtags": ["skincare"], "resultsPerPage": 10_000,
        "shouldDownloadVideos": True, "proxyConfiguration": {"useApifyProxy": True},
    })
    assert run_input == {
        "hashtags": ["skincare"], "resultsPerPage": MAX_RESULTS_PER_PAGE,
        "shouldDownloadVideos": False, "shouldDownloadCovers": False, "shouldDownloadSubtitles": False,
    }
    assert discover_run_input(actors["trend_feed"], {"type": "ANYTHING", "region": "US"}) == {
        "type": "TREND", "resultsPerPage": 30, "region": "US",
    }
    for actor, payload in (
        ("apify/web-scraper", {"startUrls": [{"url": "https://example.com"}]}),
        (actors["post_by_hashtag"], {"hashtags": []}),
        (actors["post_by_hashtag"], {"hashtags": ["x"] * 11}),
        (actors["trend_feed"], {"resultsPerPage": "all"}),
    ):
        with pytest.raises(ValueError):
            discover_run_input(actor, payload)
