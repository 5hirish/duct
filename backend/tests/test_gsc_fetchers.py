"""The Search Console fetchers build real Search Analytics requests.

Same shape as ``test_ga4_fetchers.py``: only the HTTP transport is faked, so
``googleapiclient`` builds the service from the discovery document it ships
and validates method names and parameters against it. A renamed method, a
misspelled query parameter or a body the API would reject fails here, offline,
rather than as "Search Console returned an API error" in the Data pane.
"""

from __future__ import annotations

from types import SimpleNamespace

from service.connectors import ConnectorAuthContext
from service.google import gsc
from tests.fakes import RecordingHttp, discovery_build_offline

_SITE = "sc-domain:getduct.ai"
_ANALYTICS_ROWS = {
    "rows": [
        {"keys": ["duct ai"], "clicks": 3, "impressions": 40, "ctr": 0.075, "position": 4.2},
        {"keys": ["marketing agent"], "clicks": 9, "impressions": 900, "ctr": 0.01, "position": 12.0},
    ]
}


def test_query_performance_posts_a_query_dimensioned_report(monkeypatch):
    http = RecordingHttp({"searchAnalytics/query": _ANALYTICS_ROWS})
    discovery_build_offline(monkeypatch, http)

    result = gsc.fetch_gsc_query_performance(
        _SITE, "2026-08-14", "2026-09-12", refresh_token="r", client_id="c", client_secret="s"
    )

    (call,) = http.calls
    assert call.method == "POST"
    # The site URL is a path segment, so the `sc-domain:` prefix must be escaped.
    assert call.uri.startswith("https://searchconsole.googleapis.com/webmasters/v3/sites/sc-domain%3Agetduct.ai/")
    body = __import__("json").loads(call.body)
    assert body == {
        "startDate": "2026-08-14",
        "endDate": "2026-09-12",
        "dimensions": ["query"],
        # `final` zeroes the last 2-3 days and reads as a traffic cliff.
        "dataState": "all",
        "rowLimit": 25_000,
        "startRow": 0,
    }
    assert result["report_type"] == "gsc_query_performance"
    assert result["truncated"] is False
    assert result["totals"] == {"rows_available": 2, "clicks": 12.0, "impressions": 940.0}
    # Sorted by impressions, not by the API's clicks-first order.
    assert [r["query"] for r in result["rows"]] == ["marketing agent", "duct ai"]
    assert result["rows"][1] == {
        "query": "duct ai", "clicks": 3.0, "impressions": 40.0, "ctr": 0.075, "avg_position": 4.2,
    }


def test_page_performance_dimensions_by_page_and_sorts_by_impressions(monkeypatch):
    http = RecordingHttp({"searchAnalytics/query": {
        "rows": [
            {"keys": ["https://getduct.ai/"], "clicks": 3, "impressions": 40, "ctr": 0.075, "position": 4.2},
            {"keys": ["https://getduct.ai/pricing"], "clicks": 9, "impressions": 90, "ctr": 0.1, "position": 2.0},
        ]
    }})
    discovery_build_offline(monkeypatch, http)

    result = gsc.fetch_gsc_page_performance(
        f" {_SITE} ", "2026-08-14", "2026-09-12", refresh_token="r", client_id="c", client_secret="s"
    )

    (call,) = http.calls
    assert "/sites/sc-domain%3Agetduct.ai/" in call.uri  # whitespace stripped before it hits the path
    assert __import__("json").loads(call.body)["dimensions"] == ["page"]
    assert [r["page"] for r in result["rows"]] == ["https://getduct.ai/pricing", "https://getduct.ai/"]
    assert result["row_count"] == 2


def test_pages_past_the_first_and_cuts_by_impressions_not_clicks(monkeypatch):
    """The cut used to be the API's clicks-first top 100, which dropped the
    zero-click impression tail an SEO works from. Now every page is fetched,
    the rows kept are the highest-impression ones, and the envelope says how
    much of the whole they cover."""
    http = RecordingHttp({"searchAnalytics/query": {"rows": [
        {"keys": ["earns clicks"], "clicks": 50, "impressions": 100, "ctr": 0.5, "position": 1.0},
        {"keys": ["zero-click tail"], "clicks": 0, "impressions": 900, "ctr": 0.0, "position": 9.0},
    ]}})
    discovery_build_offline(monkeypatch, http)
    # A full page (2 of 2) means "there may be more", so a second is asked for.
    monkeypatch.setattr(gsc, "_API_PAGE_ROWS", 2)
    monkeypatch.setattr(gsc, "RETURN_ROWS", 3)

    result = gsc.fetch_gsc_query_performance(
        _SITE, "2026-08-14", "2026-09-12", refresh_token="r", client_id="c", client_secret="s"
    )

    assert [__import__("json").loads(c.body)["startRow"] for c in http.calls] == [0, 2]
    assert result["totals"]["rows_available"] == 4
    assert result["row_count"] == 3
    assert result["truncated"] is True
    assert result["rows"][0]["query"] == "zero-click tail"
    assert result["impressions_coverage"] == round(1900 / 2000, 3)


def test_query_page_keeps_both_keys_on_each_row(monkeypatch):
    http = RecordingHttp({"searchAnalytics/query": {"rows": [
        {"keys": ["seo audit", "https://getduct.ai/"], "clicks": 1, "impressions": 70, "ctr": 0.01, "position": 11.0},
        {"keys": ["seo audit", "https://getduct.ai/blog/audit"], "clicks": 2, "impressions": 60, "ctr": 0.03, "position": 9.0},
    ]}})
    discovery_build_offline(monkeypatch, http)

    result = gsc.fetch_gsc_query_page(
        _SITE, "2026-08-14", "2026-09-12", refresh_token="r", client_id="c", client_secret="s"
    )

    assert __import__("json").loads(http.calls[0].body)["dimensions"] == ["query", "page"]
    assert result["report_type"] == "gsc_query_page"
    assert {(r["query"], r["page"]) for r in result["rows"]} == {
        ("seo audit", "https://getduct.ai/"),
        ("seo audit", "https://getduct.ai/blog/audit"),
    }


def test_site_listing_reads_the_sites_collection(monkeypatch):
    http = RecordingHttp({"/sites?": {"siteEntry": [
        {"siteUrl": "https://getduct.ai/", "permissionLevel": "siteFullUser"},
        {"siteUrl": "sc-domain:getduct.ai", "permissionLevel": "siteOwner"},
        {"permissionLevel": "siteOwner"},  # no siteUrl: dropped, not a crash
    ]}})
    discovery_build_offline(monkeypatch, http)
    monkeypatch.setattr(gsc, "get_configs", lambda: SimpleNamespace(
        google_oauth_client_id="c", google_oauth_client_secret="s",
        google_ads_client_id="", google_ads_client_secret="",
    ))

    rows = gsc.GSCConnector().list_accounts(ConnectorAuthContext(connector_id="gsc", refresh_token="r"))

    (call,) = http.calls
    assert call.method == "GET"
    assert call.uri.startswith("https://searchconsole.googleapis.com/webmasters/v3/sites")
    assert [r["account_id"] for r in rows] == ["https://getduct.ai/", "sc-domain:getduct.ai"]
    domain = rows[1]
    assert domain["account_name"] == "getduct.ai"
    assert domain["entity_url"] == "https://getduct.ai"
    assert domain["entity_detail"] == "Domain property"
