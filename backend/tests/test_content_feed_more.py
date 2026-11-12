"""RSS feeds and milestones (#564): the connector reads only public feeds it
fetched itself, and a milestone is claimed only where the data proves it."""

from __future__ import annotations

from datetime import date

import pytest

from agents.content.feed import FeedOptions, FeedSource, build_digest
from agents.content.feed_more import rss_items
from agents.content.feed_mcp import McpFeed
from agents.content.milestones import best_week, star_milestone
from service.rss import fetch as rss

WINDOW = (date(2026, 10, 29), date(2026, 11, 11))

ATOM = b"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Acme changelog</title>
  <entry><title>Invoices in two clicks</title><link href="https://acme.test/changelog/invoices"/>
    <published>2026-11-04T09:00:00Z</published><summary>Send an invoice from the <b>job card</b>.</summary></entry>
  <entry><title>Old news</title><link href="https://acme.test/changelog/old"/>
    <published>2026-08-01T09:00:00Z</published></entry>
</feed>"""


# --- the connector -----------------------------------------------------------


def test_feed_addresses_are_https_public_deduplicated_and_bounded():
    assert rss.parse_urls("https://a.test/feed\nhttps://a.test/feed, https://b.test/rss") == [
        "https://a.test/feed", "https://b.test/rss"]
    for bad in ("http://a.test/feed", "https://127.0.0.1/feed", "https://localhost/feed", ""):
        with pytest.raises(ValueError):
            rss.parse_urls(bad)
    with pytest.raises(ValueError):
        rss.parse_urls("\n".join(f"https://a.test/{i}" for i in range(rss.MAX_FEEDS + 1)))


def test_one_account_id_carries_the_whole_list_whatever_its_order():
    assert rss.feeds_id(["https://b.test", "https://a.test"]) == rss.feeds_id(["https://a.test", "https://b.test"])


def test_entries_parse_from_bytes_with_dates_and_plain_summaries():
    feed = rss.parse_feed(ATOM, "https://acme.test/changelog.atom")
    assert feed["title"] == "Acme changelog"
    first = feed["rows"][0]
    assert first["published"] == "2026-11-04" and first["link"].endswith("/invoices")
    assert first["summary"] == "Send an invoice from the job card ."


def test_a_web_page_is_refused_and_a_feed_is_read_through_the_pinned_transport(monkeypatch):
    import httpx2

    import service.compatible as compatible

    pinned: list[str] = []

    class Wire(httpx2.MockTransport):
        def handle_request(self, request):
            pinned.append(request.url.host)
            return super().handle_request(request)

    def answer(request):
        if request.url.path.endswith(".atom"):
            return httpx2.Response(200, content=ATOM, headers={"content-type": "application/atom+xml"})
        return httpx2.Response(200, content=b"<html><body>hi</body></html>", headers={"content-type": "text/html"})

    monkeypatch.setattr(compatible, "_PinnedTransport", lambda: Wire(answer))
    assert rss.fetch_bytes("https://acme.test/changelog.atom") == ATOM
    with pytest.raises(RuntimeError, match="web page, not a feed"):
        rss.fetch_bytes("https://acme.test/changelog")
    assert pinned == ["acme.test", "acme.test"]

    result = rss.fetch_rss({"feeds": "https://acme.test/changelog.atom\nhttps://acme.test/page"},
                           "2026-10-29", "2026-11-11")
    assert [r["title"] for r in result["data"]] == ["Invoices in two clicks"]
    assert len(result["errors"]) == 1  # the page is named, the feed still came back


def test_an_oversized_feed_is_cut_off(monkeypatch):
    import httpx2

    import service.compatible as compatible

    big = b"<rss>" + b"x" * (rss.MAX_FEED_BYTES + 10)
    monkeypatch.setattr(compatible, "_PinnedTransport", lambda: httpx2.MockTransport(
        lambda r: httpx2.Response(200, content=big, headers={"content-type": "application/rss+xml"})))
    with pytest.raises(RuntimeError, match="larger than"):
        rss.fetch_bytes("https://acme.test/feed")


# --- the feed ------------------------------------------------------------------


def test_feed_entries_become_cited_stories_once():
    rows = [{"title": "Invoices", "link": "https://acme.test/a", "published": "2026-11-04", "feed": "Acme"},
            {"title": "Invoices", "link": "https://acme.test/a", "published": "2026-11-04", "feed": "Acme"},
            {"title": "", "link": "https://acme.test/b", "published": "2026-11-05"}]
    kept, _ = rss_items(rows, already=set())
    assert len(kept) == 1 and kept[0].ref.startswith("rs:") and kept[0].kind == "post"


def test_a_round_star_count_crossed_in_the_window_is_a_milestone():
    newest_first = ["2026-11-10"] * 30 + ["2026-10-20"]
    star = star_milestone(1012, newest_first, WINDOW, repo="acme/app", already=set())
    assert star.ref == "ms:stars-1000" and star.title == "1,000 GitHub stars"
    assert star.at == "2026-11-10"
    assert star_milestone(1012, ["2026-11-10"] * 5 + ["2026-10-20"], WINDOW, repo="acme/app", already=set()) is None
    assert star_milestone(1012, newest_first, WINDOW, repo="acme/app", already={"ms:stars-1000"}) is None


def test_a_read_that_stopped_short_still_claims_only_what_it_proves():
    # 500 stars seen in the window and the read ran out: at least 500 were new,
    # so 2,500 was crossed whatever the rest of the window held.
    star = star_milestone(2_700, ["2026-11-09"] * 500, WINDOW, repo="acme/app", already=set())
    assert star.ref == "ms:stars-2500"


def test_best_week_needs_history_a_complete_week_and_a_real_record():
    rows = [{"iso_week": f"2026{w:02d}", "active_users": 1000 + w} for w in range(38, 44)]
    rows.append({"iso_week": "202644", "active_users": 1600})  # ends Sunday 1 Nov, inside the window
    week = best_week(rows, WINDOW, already=set())
    assert week.ref == "ms:ga4-week-202644" and week.at == "2026-11-01"
    assert best_week(rows[-3:], WINDOW, already=set()) is None                      # too little history
    assert best_week(rows[:-1] + [{"iso_week": "202644", "active_users": 900}], WINDOW, already=set()) is None
    partial = rows + [{"iso_week": "202646", "active_users": 9000}]                  # ends 15 Nov, after the window
    assert best_week(partial, WINDOW, already=set()).ref == "ms:ga4-week-202644"


def test_a_milestone_alone_clears_the_gate():
    star = star_milestone(1012, ["2026-11-10"] * 30, WINDOW, repo="acme/app", already=set())
    options = FeedOptions(sources=[FeedSource.MILESTONES])
    digest = build_digest(options, WINDOW, github_rows=None, duct=None, already=set(), extra=[McpFeed(items=[star])])
    assert digest.worth_a_plan and "ms:stars-1000" in digest.refs()


def test_a_feed_is_recognised_by_a_scan_that_cannot_backtrack():
    import time

    assert rss.looks_like_feed(b'  <?xml version="1.0"?>\n<!-- generator -->\n<rss version="2.0">')
    assert rss.looks_like_feed(b"<!DOCTYPE x><feed xmlns='http://www.w3.org/2005/Atom'>")
    assert not rss.looks_like_feed(b"<html><body>")
    assert not rss.looks_like_feed(b"<!-- never closed")
    crafted = b"<!--" + b"--><!--" * 5000
    started = time.perf_counter()
    assert not rss.looks_like_feed(crafted)
    assert time.perf_counter() - started < 0.1
