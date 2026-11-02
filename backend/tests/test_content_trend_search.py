"""The content agent's TikTok search (``service/trend_search.py``).

Discover could search TikTok and the agent could only read what was saved
there. These pin what the agent's own search may ask for (Discover's inputs,
nothing more), that it reads back a summary rather than thirty raw posts,
that every failure is a sentence the agent can relay, and that a project with
no Apify account is told where to connect one instead of failing a turn.
Apify is faked at the transport (``tests.fakes.ApifyRuns``).
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import pytest
from sqlmodel import Session

import agents.content.tools as content_tools
import service.apify.run_cache as run_cache
import service.vendor_keys as vendor_keys
from agents.content.v1.runner import make_session
from models.auth import User
from models.project import Project
from service.apify import get_default_actor_ids
from service.trend_search import (
    GENERIC_TAGS,
    MAX_SEARCH_HASHTAGS,
    TrendSearchFailed,
    run_trend_search,
    search_input,
)
from tests.conftest import make_sqlite_engine
from tests.fakes import ApifyRuns

ACTORS = get_default_actor_ids()


def _item(n: int, *, plays: int, slideshow: bool = True, tags=("buildinpublic", "fyp"), sound: str = "") -> dict:
    return {
        "id": f"7300000000000000{n:03d}",
        "text": f"Post {n}: what I shipped this week #buildinpublic",
        "webVideoUrl": f"https://www.tiktok.com/@maker{n}/video/7300000000000000{n:03d}",
        "isSlideshow": slideshow,
        "playCount": plays,
        "diggCount": plays // 20,
        "collectCount": plays // 50,
        "shareCount": plays // 100,
        "commentCount": plays // 200,
        "authorMeta": {"name": f"maker{n}", "fans": 1_000},
        "musicMeta": {"musicName": sound} if sound else None,
        "hashtags": list(tags),
    }


@pytest.fixture(autouse=True)
def fresh_run_cache(monkeypatch):
    monkeypatch.setattr(run_cache, "apify_runs", run_cache.RunCache())


async def _no_wait(_seconds: float) -> None:
    return None


def test_a_search_asks_only_for_what_discover_could():
    actor, payload, query = search_input(["#BuildInPublic", "buildinpublic", " indiehackers ", "a", "b", "c", "d"], "")
    assert actor == ACTORS["post_by_hashtag"]
    assert payload["hashtags"] == ["buildinpublic", "indiehackers", "a", "b", "c"][:MAX_SEARCH_HASHTAGS]
    assert payload["shouldDownloadVideos"] is False and payload["resultsPerPage"] == 30
    assert query == "#buildinpublic #indiehackers #a #b #c"

    actor, payload, query = search_input([], "gb")
    assert actor == ACTORS["trend_feed"] and payload["region"] == "GB" and query == "trending in GB"


def test_the_agent_reads_a_summary_not_thirty_posts():
    items = [_item(i, plays=1_000 * (i + 1), slideshow=i % 3 != 0, sound="Lo-fi loop" if i < 3 else "") for i in range(14)]
    apify = ApifyRuns(statuses=("RUNNING", "SUCCEEDED"), items=items)

    out = asyncio.run(run_trend_search(apify.client(), ["buildinpublic"], sleep=_no_wait))

    assert out["query"] == "#buildinpublic" and out["found"] == 14
    assert len(out["posts"]) == 10
    assert [p["plays"] for p in out["posts"]] == sorted((p["plays"] for p in out["posts"]), reverse=True)
    tags = [t["name"] for t in out["patterns"]["hashtags"]]
    assert tags == ["buildinpublic"], "a tag every niche shares says nothing about this one"
    assert out["patterns"]["sounds"] == [{"name": "Lo-fi loop", "posts": 3}]
    assert out["patterns"]["formats"]["slideshow"]["posts"] + out["patterns"]["formats"]["video"]["posts"] == 14
    assert len(out["sources"]) == 10 and out["sources"][0]["url"].startswith("https://www.tiktok.com/@maker13/")
    assert len(apify.starts) == 1


def test_the_same_search_again_joins_the_earlier_run():
    apify = ApifyRuns(start_as="SUCCEEDED", items=[_item(1, plays=500)])
    for _ in range(2):
        asyncio.run(run_trend_search(apify.client(), ["buildinpublic"], sleep=_no_wait))
    assert len(apify.starts) == 1


@pytest.mark.parametrize("apify, says", [
    (ApifyRuns(statuses=("FAILED",)), "ended failed"),
    (ApifyRuns(statuses=("RUNNING",)), "still running"),
    (ApifyRuns(start_status=402), "Apify refused the search (402)"),
])
def test_every_failure_is_a_sentence_the_agent_can_relay(apify, says):
    with pytest.raises(TrendSearchFailed, match=re.escape(says)):
        asyncio.run(run_trend_search(apify.client(), ["buildinpublic"], timeout=6, sleep=_no_wait))


def test_a_project_with_no_apify_account_is_told_where_to_connect_one(monkeypatch):
    engine = make_sqlite_engine()
    with Session(engine) as db:
        owner = User(email="maker@example.com")
        db.add(owner)
        db.commit()
        project = Project(user_id=owner.id, name="Duct", slug="duct")
        db.add(project)
        db.commit()
        db.refresh(project)
    monkeypatch.setattr(content_tools, "_open_db", lambda: Session(engine))
    # The owner saved no key, and a hosted instance never lends its own.
    monkeypatch.setattr(vendor_keys, "allow_server_provider_keys", lambda: False)

    async def _emit(_event):
        return None

    session = make_session("trends-no-key", project.id, "plan_month")
    tools = {t.name: t for t in content_tools.build_content_tools_lc(project.id, _emit, session)}
    result = json.loads(asyncio.run(tools["search_trends"].ainvoke({"hashtags": ["buildinpublic"]})))
    assert result["status"] == "error" and "Discover" in result["message"]


def test_the_generic_tags_match_the_discover_read_out():
    source = (Path(__file__).resolve().parents[2] / "app/src/lib/discoverSynthesis.js").read_text()
    listed = source.split("const GENERIC_TAGS = new Set([")[1].split("]);")[0]
    assert set(re.findall(r'"([^"]+)"', listed)) == GENERIC_TAGS
