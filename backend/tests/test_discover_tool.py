"""discover_tiktok: the content agents search TikTok only after a yes.

What the tool promises (agents/content/discover.py), each pinned here:

* nothing is spent before the person approves: no key means no question, no
  pause means no run, and a skip sends nothing to Apify;
* an approved search goes through Discover's own policy, so the input is the
  one the Discover page would send, downloads off;
* the agent gets a digest, best first, and the count a reopened thread reads;
* a refused key is a sentence the person can act on, never a stack trace.

Apify is faked at the transport (``httpx.MockTransport``) under the real
``ApifyClient``, so the request asserted on is the one that would have left.
"""

from __future__ import annotations

import asyncio
import json
import uuid

import httpx
import pytest

import service.apify.run_cache as run_cache
from agents.content import discover
from agents.core.events import AgentEvent
from service.apify import ApifyClient

PROJECT = uuid.uuid4()


def item(post_id: str, plays: int, **overrides) -> dict:
    """One dataset item, camelCase as the actor returns it."""
    return {
        "id": post_id,
        "text": f"Glass skin in three steps {post_id}",
        "webVideoUrl": f"https://www.tiktok.com/@kestrel/video/{post_id}",
        "isSlideshow": False,
        "playCount": plays,
        "diggCount": plays // 10,
        "collectCount": plays // 40,
        "shareCount": plays // 80,
        "commentCount": plays // 200,
        "authorMeta": {"name": "kestrel", "fans": 41_000},
        "musicMeta": {"musicName": "original sound", "musicAuthor": "kestrel"},
        "hashtags": ["glassskin"],
        **overrides,
    }


class Apify:
    """Apify's run, status and dataset endpoints, with the requests recorded."""

    def __init__(self, items: list[dict], *, polls_until_done: int = 1, status: int = 200):
        self.items = items
        self.polls_left = polls_until_done
        self.status = status
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.status != 200:
            return httpx.Response(self.status, json={"error": {"message": "nope"}})
        path = request.url.path
        if request.method == "POST" and path.endswith("/runs"):
            return httpx.Response(201, json={"data": {"id": "run1", "status": "READY", "defaultDatasetId": "ds1"}})
        if path.startswith("/v2/actor-runs/"):
            self.polls_left -= 1
            status = "SUCCEEDED" if self.polls_left <= 0 else "RUNNING"
            return httpx.Response(200, json={"data": {"id": "run1", "status": status, "defaultDatasetId": "ds1"}})
        if path == "/v2/datasets/ds1/items":
            return httpx.Response(200, json=self.items)
        return httpx.Response(404, json={"error": {"message": f"unexpected {path}"}})

    def client(self, key: str) -> ApifyClient:
        return ApifyClient(key, client=httpx.AsyncClient(transport=httpx.MockTransport(self)))


class Pause:
    """A person at the card: records what they were shown, answers as told."""

    def __init__(self, approved: bool):
        self.approved = approved
        self.asked: list[tuple[str, dict]] = []

    async def __call__(self, event: str, payload: dict, *, timeout: float | None = None) -> dict:
        self.asked.append((event, payload))
        return {"approved": self.approved}


@pytest.fixture(autouse=True)
def fresh_run_cache(monkeypatch):
    monkeypatch.setattr(run_cache, "apify_runs", run_cache.RunCache())


async def _no_sleep(_seconds: float) -> None:
    return None


def search(apify: Apify, pause, *, key: str = "apify-test-key", **kw) -> dict:
    return asyncio.run(
        discover.search_tiktok(
            PROJECT,
            reason=kw.pop("reason", "To see which hooks pull saves this week."),
            pause=pause,
            key_for=lambda _project: key,
            client_for=apify.client,
            sleep=_no_sleep,
            **kw,
        )
    )


def test_an_approved_search_runs_discovers_policy_and_returns_the_best_first():
    apify = Apify([item("1", 900), item("2", 120_000), item("3", 40_000)], polls_until_done=2)
    pause = Pause(approved=True)

    out = search(apify, pause, hashtags=["#glassskin", " skincareroutine "])

    assert out["status"] == "ok"
    assert [p["plays"] for p in out["posts"]] == [120_000, 40_000, 900]
    assert out["count"] == 3 and out["found"] == 3
    assert out["posts"][0]["url"].endswith("/video/2") and out["posts"][0]["sound"] == "original sound — kestrel"
    sent = json.loads(apify.requests[0].content)
    # The Discover policy's input, rebuilt from known fields: no '#', downloads pinned off.
    assert sent["hashtags"] == ["glassskin", "skincareroutine"]
    assert sent["shouldDownloadVideos"] is False and sent["shouldDownloadCovers"] is False


def test_the_card_names_the_credits_and_shows_exactly_what_will_be_sent():
    apify = Apify([item("1", 10)])
    pause = Pause(approved=True)

    search(apify, pause, hashtags=["glassskin"], reason="Fresh hooks for Thursday.")

    [(event, card)] = pause.asked
    assert event == AgentEvent.TOOL_APPROVAL_REQUIRED
    assert card["why"] == discover.WHY_SPENDS_CREDITS and card["server_name"] == "Apify"
    assert card["reason"] == "Fresh hooks for Thursday."
    assert json.loads(card["arguments"]) == json.loads(apify.requests[0].content)


def test_a_skip_sends_nothing_to_apify():
    apify = Apify([item("1", 10)])

    out = search(apify, Pause(approved=False), hashtags=["glassskin"])

    assert out["status"] == "skipped"
    assert apify.requests == []


def test_without_a_key_nobody_is_asked_and_nothing_runs():
    apify = Apify([item("1", 10)])
    pause = Pause(approved=True)

    out = search(apify, pause, key="", hashtags=["glassskin"])

    assert out["status"] == "not_connected"
    assert pause.asked == [] and apify.requests == []


def test_an_unattended_run_never_spends():
    apify = Apify([item("1", 10)])

    out = search(apify, None, hashtags=["glassskin"])

    assert out["status"] == "needs_approval"
    assert apify.requests == []


def test_a_search_the_policy_refuses_is_never_put_to_the_person():
    pause = Pause(approved=True)

    out = search(Apify([]), pause, hashtags=[f"tag{i}" for i in range(11)])

    assert out["status"] == "invalid"
    assert pause.asked == []


def test_no_hashtags_is_the_trending_feed_for_the_region():
    apify = Apify([item("1", 10)])

    out = search(apify, Pause(approved=True), region="us")

    assert out["status"] == "ok"
    assert json.loads(apify.requests[0].content) == {"type": "TREND", "resultsPerPage": 30, "region": "US"}


def test_a_refused_key_says_where_to_fix_it():
    out = search(Apify([], status=401), Pause(approved=True), hashtags=["glassskin"])

    assert out["status"] == "error"
    assert "Content → Discover" in out["message"]


def test_a_run_past_the_wait_says_it_is_still_going():
    apify = Apify([item("1", 10)], polls_until_done=10_000)
    ticks = iter(range(0, 10_000, 60))

    out = asyncio.run(
        discover.search_tiktok(
            PROJECT,
            reason="r",
            hashtags=["glassskin"],
            pause=Pause(approved=True),
            key_for=lambda _p: "apify-test-key",
            client_for=apify.client,
            sleep=_no_sleep,
            clock=lambda: float(next(ticks)),
        )
    )

    assert out["status"] == "still_running"
    assert not any(r.url.path.startswith("/v2/datasets/") for r in apify.requests)
