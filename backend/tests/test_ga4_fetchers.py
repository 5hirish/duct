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
        return _Response([_Row(["/pricing", "google / cpc"], [12, 0.4, 0.6, 33.5, 2, 99.0])])


def test_landing_pages_builds_a_filtered_report_request(monkeypatch):
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
    assert req.dimension_filter.filter.field_name == "sessionSourceMedium"
    assert req.dimension_filter.filter.string_filter.value == "google / cpc"
    assert [m.name for m in req.metrics][4] == ga4.KEY_EVENTS_METRIC
    assert result["row_count"] == 1
    assert result["rows"][0]["page_path"] == "/pricing"
    assert result["rows"][0]["conversions"] == 2.0
