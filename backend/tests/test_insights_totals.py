"""Duct adds up a pull; the model quotes the sum.

A replay of a real brief reasoned correctly and added wrong: 2,504 sessions
where its 250 landing-page rows summed to 2,681. These pin the arithmetic
that replaced the model's (``agents/insights/totals.py``) and the one mistake
it must never make, which is averaging an average.
"""

from __future__ import annotations

import uuid
from dataclasses import replace

import pytest

from agents.insights import fetchers
from agents.insights.catalog.base import _CATALOGS
from agents.insights.totals import AGG_AVG, summarise


def _landing(sessions: list[int], bounce: list[float]) -> dict:
    return {
        "report_type": "ga4_landing_pages",
        "rows": [
            {"page_path": f"/p{i}", "channel": "Organic Search", "sessions": s,
             "bounce_rate": b, "conversions": 1, "total_revenue": 10.5}
            for i, (s, b) in enumerate(zip(sessions, bounce))
        ],
    }


def test_the_sum_the_replay_got_wrong_is_exact():
    sessions = [11] * 249 + [2681 - 11 * 249]
    out = summarise("ga4_landing_pages", _landing(sessions, [0.5] * 250))
    assert out["totals"]["sessions"] == 2681
    assert out["totals"]["total_revenue"] == 2625  # 250 × 10.5, tidied to an int
    assert out["totals_cover"] == "all 250 rows returned"
    assert "never by adding" in out["note"]


def test_a_rate_is_weighted_never_averaged():
    """Two pages: 900 sessions bouncing 10%, 100 bouncing 90%. The site bounces
    18%, not the 50% an average of the two rows says."""
    out = summarise("ga4_landing_pages", _landing([900, 100], [0.1, 0.9]))
    assert out["rates"]["bounce_rate"] == {"value": 0.18, "weighted_by": "sessions"}


def test_cpa_counts_the_spend_that_converted_nothing():
    """CPA weighted by conversions would drop the $300 below, which is the
    spend a CPA exists to show. It is total spend over total conversions."""
    rows = [
        {"campaign_name": "Brand", "spend": 100.0, "conversions": 10.0, "cost_per_conversion": 10.0,
         "conversion_value": 500.0, "roas": 5.0, "clicks": 50, "impressions": 1000, "ctr": 0.05,
         "previous": {"spend": 80.0, "conversions": 8.0}},
        {"campaign_name": "Generic", "spend": 300.0, "conversions": 0.0, "cost_per_conversion": 0.0,
         "conversion_value": 0.0, "roas": 0.0, "clicks": 150, "impressions": 9000, "ctr": 0.0167,
         "previous": {"spend": 250.0, "conversions": 1.0}},
    ]
    out = summarise("campaign_performance", {"rows": rows})
    assert out["rates"]["cost_per_conversion"] == {"value": 40.0, "ratio": "spend / conversions"}
    assert out["rates"]["roas"]["value"] == 1.25
    assert out["rates"]["ctr"]["value"] == 0.02
    assert out["previous_totals"] == {"spend": 330, "conversions": 9}


def test_search_console_totals_cover_the_whole_window_not_the_listed_rows():
    data = {
        "rows": [{"query": "a", "clicks": 40, "impressions": 1000, "ctr": 0.04, "avg_position": 2.0},
                 {"query": "b", "clicks": 10, "impressions": 1000, "ctr": 0.01, "avg_position": 6.0}],
        "totals": {"rows_available": 9120, "clicks": 1200, "impressions": 60000},
        "truncated": True,
    }
    out = summarise("gsc_query_performance", data)
    assert out["totals"] == {"clicks": 1200, "impressions": 60000}
    assert out["rates"]["ctr"]["value"] == 0.02  # the window's, not the two rows'
    assert out["rates"]["avg_position"] == {"value": 4.0, "weighted_by": "impressions"}
    assert "whole window (9,120 rows)" in out["totals_cover"]


def test_a_report_the_source_cut_says_its_totals_are_a_floor():
    data = _landing([10, 20], [0.1, 0.2]) | {"truncated": True}
    assert "floor" in summarise("ga4_landing_pages", data)["totals_cover"]


@pytest.mark.parametrize("data", [
    {"summary": {"event_totals": {"signup": 40}}},  # Mixpanel did its own arithmetic
    {"rows": []},
    None,
])
def test_nothing_is_invented_for_a_pull_that_is_not_rows(data):
    assert summarise("mixpanel_event_counts", data) == {}
    assert summarise("ga4_landing_pages", data) == {}


def test_a_flag_is_not_summed_as_a_number():
    rows = [{"page_path": "/", "sessions": True, "bounce_rate": 0.1}]
    assert "sessions" not in summarise("ga4_landing_pages", {"rows": rows}).get("totals", {})


@pytest.mark.parametrize("connector", sorted(_CATALOGS))
def test_every_average_says_how_it_totals(connector):
    """An `agg: avg` field with no ratio and no weight would get no rate, and
    one with both is a question nobody answered. Exactly one."""
    for entity in _CATALOGS[connector]["entities"]:
        for name, meta in entity["fields"].items():
            if meta.get("agg") != AGG_AVG:
                continue
            assert bool(meta.get("ratio")) != bool(meta.get("weight")), (
                f"{connector}/{entity['entity_id']}.{name} needs exactly one of ratio / weight"
            )
            if meta.get("ratio"):
                assert len(meta["ratio"]) == 2


def test_the_totals_ride_in_the_fetch_result_before_the_rows(monkeypatch):
    import service.connector_access as access

    class _Src:
        status = "bound"
        account_id = "111"

    monkeypatch.setattr(access, "get_data_source", lambda *a, **k: _Src())
    monkeypatch.setattr(access, "resolve_read_credentials", lambda *a, **k: {"refresh_token": "t"})
    specs = {**fetchers.fetch_specs()}
    specs["ga4_landing_pages"] = replace(
        specs["ga4_landing_pages"], call=lambda *a: _landing([2000, 681], [0.4, 0.6])
    )
    monkeypatch.setattr(fetchers, "fetch_specs", lambda: specs)

    result = fetchers.fetch_entity("ga4_landing_pages", user_id=uuid.uuid4(), project_id=uuid.uuid4())
    assert result["totals"]["sessions"] == 2681
    keys = list(result)
    assert keys.index("totals") < keys.index("data")


def test_a_slice_of_the_report_is_summed_too():
    """"How did organic do" is one channel's share of the report; without a
    subtotal the model is back to adding the rows it was told not to add."""
    rows = [
        {"page_path": "/a", "channel": "Organic Search", "sessions": 700, "conversions": 7},
        {"page_path": "/b", "channel": "Organic Search", "sessions": 281, "conversions": 1},
        {"page_path": "/a", "channel": "Direct", "sessions": 1700, "conversions": 30},
    ]
    out = summarise("ga4_landing_pages", {"rows": rows})
    assert out["subtotals"]["channel"]["Organic Search"] == {"sessions": 981, "conversions": 8}
    # Pages here are two values over three rows: they split, so they total too.
    assert out["subtotals"]["page_path"]["/a"]["sessions"] == 2400


def test_no_slice_where_it_would_not_add_up_to_the_total():
    many = [{"page_path": f"/p{i}", "channel": "Organic Search", "sessions": 1} for i in range(40)]
    assert "page_path" not in summarise("ga4_landing_pages", {"rows": many}).get("subtotals", {})
    campaigns = [{"campaign_name": n, "spend": 1.0, "conversions": 1.0} for n in ("A", "B")]
    assert "subtotals" not in summarise("campaign_performance", {"rows": campaigns})
    gsc = {"rows": [{"query": "a", "page": "/x", "clicks": 1, "impressions": 10}] * 2,
           "totals": {"clicks": 99, "impressions": 999}}
    assert "subtotals" not in summarise("gsc_query_page", gsc)
