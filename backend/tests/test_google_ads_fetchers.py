"""The Google Ads read fetchers hand real GAQL to a real client shape.

``FakeAdsClient`` answers ``search_stream`` with ``GoogleAdsRow`` protos built
by the installed library, so the row-walking code (``r.metrics.cost_micros``,
enum names, aggregation across date segments) runs against the real message
types. ``test_vendor_contracts.py`` already proves every GAQL field exists in
the API version; this proves each fetcher sends the query it documents, to
the customer id it was given, and reads the answer back correctly.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from service.google import fetch
from tests.fakes import FakeAdsClient

_CREDS = {"client_id": "cid", "client_secret": "sec", "refresh_token": "rt"}


@pytest.fixture
def ads(monkeypatch):
    """A fake behind ``GoogleAdsClient.load_from_dict``; ``loaded`` is the
    config dict the fetcher built for it."""
    client = FakeAdsClient()
    client.loaded: list[dict] = []

    def load_from_dict(config):
        client.loaded.append(dict(config))
        return client

    monkeypatch.setattr(fetch, "GoogleAdsClient", SimpleNamespace(load_from_dict=load_from_dict))
    return client


def _campaign_row(client, **overrides):
    fields = {
        "campaign.id": 11, "campaign.name": "Brand", "campaign.status": "ENABLED",
        "campaign.advertising_channel_type": "SEARCH",
        "metrics.clicks": 10, "metrics.impressions": 200, "metrics.cost_micros": 5_000_000,
        "metrics.conversions": 2.0, "metrics.conversions_value": 40.0,
    }
    fields.update(overrides)
    return client.row(**fields)


def test_campaigns_queries_both_windows_and_aggregates_date_segments(ads):
    # Two segments of the same campaign, as the API returns them per day.
    ads.rows = [_campaign_row(ads), _campaign_row(ads, **{"metrics.clicks": 5, "metrics.cost_micros": 1_000_000})]

    payload = fetch.fetch_campaigns(
        "123-456-7890", "cid", "sec", "rt", "2026-09-01", "2026-09-14",
        login_customer_id="999-888-7777",
    )

    assert ads.loaded == [{**_CREDS, "use_proto_plus": True, "login_customer_id": "9998887777"}]
    current, previous = ads.queries
    assert current.customer_id == previous.customer_id == "1234567890"
    assert "FROM campaign" in current.query
    assert "BETWEEN '2026-09-01' AND '2026-09-14'" in current.query
    assert "BETWEEN '2026-08-18' AND '2026-08-31'" in previous.query
    assert "campaign.status != 'REMOVED'" in current.query

    (row,) = payload["rows"]
    assert row["campaign_id"] == "11"
    assert row["status"] == "ENABLED"
    assert row["channel_type"] == "SEARCH"
    assert row["clicks"] == 15
    assert row["spend"] == 6.0
    assert row["cost_per_conversion"] == pytest.approx(6.0 / 4.0)
    assert row["previous"]["spend"] == 6.0  # same fake rows answer the previous window
    assert payload["source_metadata"]["window_previous"] == "2026-08-18 to 2026-08-31"
    assert payload["source_metadata"]["account_id"] == "123-456-7890"


def test_campaigns_omits_the_mcc_when_none_is_given(ads):
    fetch.fetch_campaigns("1234567890", "cid", "sec", "rt", "2026-09-01", "2026-09-14")
    assert "login_customer_id" not in ads.loaded[0]


def test_search_terms_reads_the_search_term_view(ads):
    ads.rows = [_campaign_row(ads, **{
        "search_term_view.search_term": "duct ai", "segments.search_term_match_type": "EXACT",
    })]

    result = fetch.fetch_search_terms("1234567890", "2026-09-01", "2026-09-14", **_CREDS)

    (query,) = ads.queries
    assert "FROM search_term_view" in query.query
    assert "ORDER BY metrics.cost_micros DESC" in query.query
    assert "LIMIT 100" in query.query
    (row,) = result["rows"]
    assert row["search_term"] == "duct ai"
    assert row["match_type"] == "EXACT"  # the enum's name, not its integer
    assert row["campaign_name"] == "Brand"
    assert row["roas"] == pytest.approx(40.0 / 5.0)
    assert result["report_type"] == "search_terms"


def test_device_performance_aggregates_per_campaign_and_device(ads):
    ads.rows = [
        _campaign_row(ads, **{"segments.device": "MOBILE"}),
        _campaign_row(ads, **{"segments.device": "MOBILE", "metrics.clicks": 1, "metrics.cost_micros": 1_000_000}),
        _campaign_row(ads, **{"segments.device": "DESKTOP", "metrics.cost_micros": 9_000_000}),
    ]

    result = fetch.fetch_device_performance("1234567890", "2026-09-01", "2026-09-14", **_CREDS)

    assert "segments.device" in ads.queries[0].query
    assert [(r["device"], r["clicks"], r["spend"]) for r in result["rows"]] == [
        ("DESKTOP", 10, 9.0), ("MOBILE", 11, 6.0),
    ]


def test_geo_performance_reads_the_geographic_view(ads):
    ads.rows = [_campaign_row(ads, **{
        "geographic_view.country_criterion_id": 2724, "geographic_view.location_type": "LOCATION_OF_PRESENCE",
    })]

    result = fetch.fetch_geo_performance("1234567890", "2026-09-01", "2026-09-14", **_CREDS)

    assert "FROM geographic_view" in ads.queries[0].query
    (row,) = result["rows"]
    assert row["country_criterion_id"] == "2724"
    assert row["location_type"] == "LOCATION_OF_PRESENCE"


def test_ad_group_performance_aggregates_per_ad_group(ads):
    ads.rows = [
        _campaign_row(ads, **{"ad_group.id": 7, "ad_group.name": "Exact", "ad_group.status": "ENABLED"}),
        _campaign_row(ads, **{"ad_group.id": 7, "ad_group.name": "Exact", "ad_group.status": "ENABLED",
                              "metrics.conversions": 1.0}),
        _campaign_row(ads, **{"ad_group.id": 8, "ad_group.name": "Broad", "ad_group.status": "PAUSED",
                              "metrics.cost_micros": 0}),
    ]

    result = fetch.fetch_ad_group_performance("1234567890", "2026-09-01", "2026-09-14", **_CREDS)

    assert "FROM ad_group" in ads.queries[0].query
    assert "ad_group.status != 'REMOVED'" in ads.queries[0].query
    exact, broad = result["rows"]
    assert (exact["ad_group_id"], exact["conversions"], exact["spend"]) == ("7", 3.0, 10.0)
    assert (broad["ad_group_id"], broad["status"], broad["cost_per_conversion"]) == ("8", "PAUSED", 0.0)


def test_an_api_failure_surfaces_the_provider_message(ads, monkeypatch):
    from google.ads.googleads.errors import GoogleAdsException

    failure = SimpleNamespace(errors=[SimpleNamespace(message="The customer account can't be accessed")])
    exc = GoogleAdsException(None, None, failure, "req-1")
    monkeypatch.setattr(ads, "_search_stream", lambda *_: (_ for _ in ()).throw(exc))

    with pytest.raises(RuntimeError, match="can't be accessed"):
        fetch.fetch_search_terms("1234567890", "2026-09-01", "2026-09-14", **_CREDS)
