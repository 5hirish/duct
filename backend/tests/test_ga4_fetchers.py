"""The GA4 fetchers build real Data API requests.

``fetch_ga4_landing_pages`` imported ``StringFilter`` from the types module,
but the library nests it as ``Filter.StringFilter`` — so every filtered
landing-page pull raised ``ImportError`` from the connector's first commit
until 2026-09-13, and the agent reported "Google Analytics returned an API
error". Nothing caught it because every caller was faked one layer up. This
builds the request against the real library with only the client faked.
"""

from __future__ import annotations

from service.google import ga4


class _Value:
    def __init__(self, value):
        self.value = value


class _Row:
    def __init__(self, dims, metrics):
        self.dimension_values = [_Value(d) for d in dims]
        self.metric_values = [_Value(str(m)) for m in metrics]


class _Response:
    def __init__(self, rows):
        self.rows = rows


class _FakeClient:
    requests: list = []

    def __init__(self, credentials=None):
        self.credentials = credentials

    def run_report(self, req):
        type(self).requests.append(req)
        # One canned row, shaped to whichever report asked: landing pages carry
        # a channel between the page and the source/medium, conversion paths
        # do not.
        dims = ["/pricing", "Paid Search", "google / cpc"] if len(req.dimensions) == 3 else ["/pricing", "google / cpc"]
        return _Response([_Row(dims, [12, 0.4, 0.6, 33.5, 2, 99.0])])


def test_landing_pages_returns_every_channel_tagged(monkeypatch):
    """This report was filtered to `google / cpc`, so the organic goals were
    handed paid traffic under an 'organic landing pages' guide. It is
    unfiltered now, and each row says which channel it is."""
    import google.analytics.data_v1beta as data_api

    monkeypatch.setattr(data_api, "BetaAnalyticsDataClient", _FakeClient)
    monkeypatch.setattr(ga4, "_build_credentials", lambda **_: object())
    _FakeClient.requests = []

    result = ga4.fetch_ga4_landing_pages(
        "360006549", "2026-08-14", "2026-09-12",
        refresh_token="r", client_id="c", client_secret="s",
    )

    req = _FakeClient.requests[0]
    assert req.property == "properties/360006549"
    assert not req.dimension_filter.filter.field_name  # no channel filter at all
    assert [d.name for d in req.dimensions] == ["pagePath", "sessionDefaultChannelGroup", "sessionSourceMedium"]
    assert [m.name for m in req.metrics][4] == ga4.KEY_EVENTS_METRIC
    assert result["row_count"] == 1
    assert result["rows"][0]["page_path"] == "/pricing"
    assert result["rows"][0]["conversions"] == 2.0
    assert result["rows"][0]["channel"] == "Paid Search"


def test_conversion_paths_orders_channels_by_key_events(monkeypatch):
    import google.analytics.data_v1beta as data_api

    monkeypatch.setattr(data_api, "BetaAnalyticsDataClient", _FakeClient)
    monkeypatch.setattr(ga4, "_build_credentials", lambda **_: object())
    _FakeClient.requests = []

    result = ga4.fetch_ga4_conversion_paths(
        " 360006549 ", "2026-08-14", "2026-09-12",
        refresh_token="r", client_id="c", client_secret="s",
    )

    req = _FakeClient.requests[0]
    assert req.property == "properties/360006549"  # whitespace never reaches the resource name
    assert [d.name for d in req.dimensions] == ["sessionSourceMedium", "sessionDefaultChannelGroup"]
    assert [m.name for m in req.metrics] == [ga4.KEY_EVENTS_METRIC, "totalRevenue", "sessions", "engagedSessions"]
    assert req.order_bys[0].metric.metric_name == ga4.KEY_EVENTS_METRIC
    assert req.order_bys[0].desc is True
    assert req.limit == 100
    # The fake answers with the landing-page row shape; only the first four
    # metric cells are read here, and the dimension pair maps positionally.
    row = result["rows"][0]
    assert row["session_source_medium"] == "/pricing"
    assert row["session_default_channel_group"] == "google / cpc"
    assert (row["conversions"], row["total_revenue"], row["sessions"], row["engaged_sessions"]) == (12.0, 0.4, 0, 33)


def test_property_listing_reads_account_summaries_from_the_admin_api(monkeypatch):
    from types import SimpleNamespace

    from service.connectors import ConnectorAuthContext
    from tests.fakes import RecordingHttp, discovery_build_offline

    http = RecordingHttp({"accountSummaries": {"accountSummaries": [
        {"displayName": "Acme", "propertySummaries": [
            {"property": "properties/2", "displayName": "Website"},
            {"property": "properties/1", "displayName": "App"},
            {"displayName": "no resource name"},
        ]},
    ]}})
    discovery_build_offline(monkeypatch, http)
    monkeypatch.setattr(ga4, "get_configs", lambda: SimpleNamespace(
        google_oauth_client_id="c", google_oauth_client_secret="s",
        google_ads_client_id="", google_ads_client_secret="",
    ))

    rows = ga4.GA4Connector().list_accounts(ConnectorAuthContext(connector_id="ga4", refresh_token="r"))

    (call,) = http.calls
    assert call.uri.startswith("https://analyticsadmin.googleapis.com/v1beta/accountSummaries?pageSize=200")
    assert [(r["account_id"], r["account_name"], r["parent_account_name"]) for r in rows] == [
        ("1", "App", "Acme"), ("2", "Website", "Acme"),
    ]
