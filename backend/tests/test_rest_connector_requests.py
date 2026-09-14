"""Each REST connector's pull, run end to end with only ``httpx.request`` faked.

Every one of these (Meta, Apple Ads, Stripe, RevenueCat) reaches the network
through ``service.rest.Endpoint``, which is one ``httpx.request`` call. Faking
that single seam lets the vendor's own request code run for real: URL
assembly, query encoding (Stripe's ``created[gte]``, Meta's JSON-in-query),
auth headers, pagination, the per-section isolation in each ``fetch_*``. What
a test reads is what would have crossed the wire.

The earlier connector tests (``test_connector_clients.py``) cover the parsing
and counting rules with ``api()`` itself patched out. These sit beneath
``api()`` so the request-building half is exercised too.
"""

from __future__ import annotations

import time

import pytest

from tests.fakes import FakeWire


@pytest.fixture
def wire(monkeypatch):
    return FakeWire().install(monkeypatch)


# ---------------------------------------------------------------------------
# Meta Marketing API
# ---------------------------------------------------------------------------

_META_CREDS = {"access_token": "EAAB-token", "account_id": "123", "app_secret": "shh"}


def _meta_wire(wire: FakeWire) -> FakeWire:
    insights_row = {
        "campaign_id": "c1", "campaign_name": "Launch", "spend": "120.50", "impressions": "1000",
        "clicks": "40", "account_currency": "EUR",
        "actions": [
            {"action_type": "purchase", "value": "3"},
            {"action_type": "offsite_conversion.fb_pixel_purchase", "value": "3"},
        ],
        "action_values": [{"action_type": "offsite_conversion.fb_pixel_purchase", "value": "300.00"}],
    }
    return (
        wire
        .on("GET", "/act_123/campaigns", {"data": [
            {"id": "c1", "name": "Launch", "effective_status": "ACTIVE"},
            {"id": "c2", "name": "Other product", "effective_status": "PAUSED"},
        ]})
        .on("GET", "/act_123/adsets", {"data": [{"id": "s1", "campaign_id": "c1"}, {"id": "s2", "campaign_id": "c2"}]})
        .on("GET", "/act_123/adspixels", {"data": [{"id": "p1", "last_fired_time": "2026-09-13T00:00:00+0000"}]})
        .on("GET", "/act_123/customconversions", {"data": []})
        .on("GET", "/act_123/ads", {"data": [{"id": "a1", "campaign_id": "c1"}]})
        .on("GET", "/act_123/insights", {"data": [insights_row]})
        .on("GET", "/act_123?", {"id": "act_123", "name": "Acme", "currency": "EUR"})
    )


def test_meta_pull_scopes_a_campaign_filter_server_side(wire):
    from service.meta.ads import client as meta
    from service.meta.ads.fetch import fetch_meta_ads

    _meta_wire(wire)

    payload = fetch_meta_ads(_META_CREDS, days=14, campaign_filter=["launch"])

    assert payload["errors"] == {}
    assert payload["api"] == f"meta-marketing-{meta.API_VERSION}"
    for call in wire.calls:
        assert call.url.startswith(meta.API_BASE + "/")
        # The token rides in the header, never the query string.
        assert call.headers["Authorization"] == "Bearer EAAB-token"
        assert "access_token" not in call.query
        assert len(call.query["appsecret_proof"]) == 64

    (campaigns,) = wire.sent("GET", "/act_123/campaigns")
    # Without this list Meta returns only ACTIVE campaigns; it goes as a JSON string.
    assert campaigns.query["effective_status"] == '["ACTIVE","PAUSED","CAMPAIGN_PAUSED","ARCHIVED","IN_PROCESS","WITH_ISSUES"]'
    assert campaigns.query["limit"] == "200"
    assert campaigns.query["fields"].startswith("id,name,status,effective_status")

    current, prior, daily = wire.sent("GET", "/act_123/insights")
    assert current.query["level"] == "campaign"
    assert current.query["time_range"] == '{"since":"%s","until":"%s"}' % tuple(payload["window"])
    assert prior.query["time_range"] == '{"since":"%s","until":"%s"}' % tuple(payload["prior_window"])
    assert daily.query["time_increment"] == "1"
    assert current.query["action_attribution_windows"] == '["1d_click","7d_click","1d_view"]'
    # The filter is pushed into the request, not applied to the answer.
    assert current.query["filtering"] == '[{"field":"campaign.id","operator":"IN","value":["c1"]}]'

    assert payload["data"]["target_campaign_ids"] == ["c1"]
    assert [s["id"] for s in payload["data"]["ad_sets"]] == ["s1"]
    assert payload["summary"]["purchases"] == 3.0  # one action_type, never the sum
    assert payload["summary"]["purchase_value"] == 300.0
    assert payload["summary"]["currency"] == "EUR"


def test_meta_pull_without_a_filter_sends_no_filtering_clause(wire):
    from service.meta.ads.fetch import fetch_meta_ads

    _meta_wire(wire)

    payload = fetch_meta_ads({"access_token": "t", "account_id": "act_123"}, days=7)

    assert payload["errors"] == {}
    (current, *_rest) = wire.sent("GET", "/act_123/insights")
    assert "filtering" not in current.query
    assert "appsecret_proof" not in current.query  # no app_secret, no proof
    assert payload["data"]["name_filter"] is None
    assert payload["data"]["target_campaign_ids"] == ["c1", "c2"]


def test_meta_falls_back_to_an_async_report_when_the_sync_query_is_too_big(wire, monkeypatch):
    from service.meta.ads import client as meta

    monkeypatch.setattr(meta.time, "sleep", lambda *_: None)
    too_much = {"error": {"message": "Please reduce the amount of data you're asking for", "code": 1, "error_subcode": 99}}
    (
        wire
        .on("GET", "/act_123/insights", too_much, status=400)
        .on("POST", "/act_123/insights", {"report_run_id": "run9"})
        .on("GET", "/run9?", {"async_status": "Job Completed", "async_percent_completion": 100})
        .on("GET", "/run9/insights", {"data": [{"campaign_id": "c1", "spend": "1.00"}]})
    )

    rows = meta.insights("act_123", {"access_token": "t"}, level="campaign", start="2026-09-01", end="2026-09-07")

    assert rows == [{"campaign_id": "c1", "spend": "1.00"}]
    (job,) = wire.sent("POST", "/act_123/insights")
    # The async job carries the identical query the sync call was refused on.
    assert job.query["level"] == "campaign"
    assert job.query["time_range"] == '{"since":"2026-09-01","until":"2026-09-07"}'


# ---------------------------------------------------------------------------
# Apple Search Ads
# ---------------------------------------------------------------------------


@pytest.fixture
def apple_creds():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    from service.apple.ads import client as asa

    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    # The token cache is module-global and keyed by (client_id, key_id); a
    # previous test's token would otherwise skip the mint this test asserts on.
    asa._TOKEN_CACHE.clear()
    return {
        "client_id": "SEARCHADS.abc", "team_id": "SEARCHADS.team", "key_id": "kid-1",
        "private_key": pem, "org_id": "4242",
    }, key.public_key()


def _apple_report(rows):
    return {"data": {"reportingDataResponse": {"row": rows}}, "pagination": {"totalResults": len(rows)}}


def test_apple_pull_mints_a_token_then_scopes_every_report_to_the_campaigns(wire, apple_creds):
    import jwt as pyjwt

    from service.apple.ads import client as asa
    from service.apple.ads.fetch import fetch_apple_ads

    creds, public_key = apple_creds
    row = {
        "metadata": {"campaignId": 1, "campaignName": "Brand", "campaignStatus": "ENABLED"},
        "total": {"impressions": 10, "taps": 2, "tapInstalls": 1, "totalInstalls": 1,
                  "localSpend": {"amount": "3.50", "currency": "USD"}, "avgCPT": {"amount": "1.75", "currency": "USD"}},
    }
    (
        wire
        .on("POST", "appleid.apple.com/auth/oauth2/token", {"access_token": "bearer-1", "expires_in": 3600})
        .on("GET", "/campaigns?", {"data": [{"id": 1, "name": "Brand"}, {"id": 2, "name": "Generic"}],
                                  "pagination": {"totalResults": 2}})
        .on("POST", "/reports/campaigns", _apple_report([row]))
    )

    payload = fetch_apple_ads(creds, days=14)

    assert payload["errors"] == {}
    (mint,) = wire.sent("POST", "oauth2/token")
    assert mint.data["grant_type"] == "client_credentials"
    assert mint.data["scope"] == asa.SCOPE
    claims = pyjwt.decode(mint.data["client_secret"], public_key, algorithms=["ES256"], audience=asa.AUDIENCE)
    assert (claims["sub"], claims["iss"]) == ("SEARCHADS.abc", "SEARCHADS.team")

    (campaigns,) = wire.sent("GET", "/campaigns?")
    assert campaigns.url.startswith(asa.API_BASE + "/campaigns?")
    assert campaigns.headers["Authorization"] == "Bearer bearer-1"
    assert campaigns.headers["X-AP-Context"] == "orgId=4242"
    assert (campaigns.query["limit"], campaigns.query["offset"]) == ("1000", "0")

    current, prior, daily = wire.sent("POST", "/reports/campaigns")
    scope = [{"field": "campaignId", "operator": "IN", "values": ["1", "2"]}]
    for report in (current, prior, daily):
        assert report.json["selector"]["conditions"] == scope  # org-scoped endpoint, so always conditioned
        assert report.json["selector"]["orderBy"] == [{"field": "campaignId", "sortOrder": "DESCENDING"}]
        assert report.json["returnGrandTotals"] is False
    assert (current.json["startTime"], current.json["endTime"]) == tuple(payload["window"])
    assert (prior.json["startTime"], prior.json["endTime"]) == tuple(payload["prior_window"])
    assert current.json["returnRowTotals"] is True and "granularity" not in current.json
    assert daily.json["granularity"] == "DAILY" and daily.json["returnRowTotals"] is False

    assert payload["summary"] == {
        "spend": 3.5, "impressions": 10, "taps": 2, "tap_installs": 1, "total_installs": 1,
        "note": payload["summary"]["note"],
    }
    assert payload["data"]["report_campaigns"][0]["avg_cpt"] == 1.75


def test_apple_pull_with_no_campaigns_never_asks_for_a_report(wire, apple_creds):
    from service.apple.ads.fetch import fetch_apple_ads

    creds, _ = apple_creds
    (
        wire
        .on("POST", "oauth2/token", {"access_token": "bearer-1", "expires_in": 3600})
        .on("GET", "/campaigns?", {"data": [], "pagination": {"totalResults": 0}})
    )

    payload = fetch_apple_ads(creds, days=14)

    assert payload["data"]["campaign_count"] == 0
    assert wire.sent("POST", "/reports/campaigns") == []
    assert payload["summary"] == {}


# ---------------------------------------------------------------------------
# Stripe
# ---------------------------------------------------------------------------


def test_stripe_pull_filters_by_window_in_bracket_notation(wire):
    from service.stripe import client as st
    from service.stripe.fetch import fetch_stripe

    started = int(time.time())
    subscription = {
        "id": "sub_1", "created": started - 3600, "status": "active", "metadata": {},
        "items": {"data": [{"quantity": 2, "price": {"unit_amount": 1500, "currency": "usd",
                                                     "nickname": "Pro", "recurring": {"interval": "month"}}}]},
    }
    never_paid = {"id": "sub_2", "created": started - 7200, "status": "incomplete_expired", "items": {"data": []}}
    charge = {"id": "ch_1", "created": started - 60, "status": "succeeded", "paid": True,
              "amount": 3000, "amount_refunded": 500, "currency": "usd", "refunded": False}
    (
        wire
        .on("GET", "/v1/subscriptions", {"object": "list", "data": [subscription, never_paid], "has_more": False})
        .on("GET", "/v1/charges", {"object": "list", "data": [charge], "has_more": False})
    )

    payload = fetch_stripe({"api_key": "<restricted-key>"}, days=30)

    assert payload["errors"] == {}
    assert payload["api"] == f"stripe-{st.STRIPE_VERSION}"
    (subs,) = wire.sent("GET", "/v1/subscriptions")
    assert subs.headers["Authorization"] == "Bearer <restricted-key>"
    assert subs.headers["Stripe-Version"] == st.STRIPE_VERSION
    # Nested filters flatten to Stripe's bracket form; the window is the last 30 days.
    assert subs.query["status"] == "all"
    assert subs.query["limit"] == str(st.PAGE_LIMIT)
    assert started - 30 * 86400 - 5 <= int(subs.query["created[gte]"]) <= started - 30 * 86400 + 5
    (charges,) = wire.sent("GET", "/v1/charges")
    assert "created[gte]" in charges.query and "status" not in charges.query

    summary = payload["summary"]
    assert summary["paid_new_subs"] == 1
    assert summary["never_paid_subs"] == 1  # an incomplete_expired subscription never charged
    assert summary["new_mrr_equivalent"] == 30.0  # 2 × $15, off the items, not the legacy plan
    assert (summary["gross_revenue"], summary["refunded"], summary["net_revenue"]) == (30.0, 5.0, 25.0)


def test_stripe_pull_follows_starting_after_across_pages(wire):
    from service.stripe.fetch import fetch_stripe

    def subscriptions(call):
        if "starting_after" not in call.query:
            return {"object": "list", "data": [{"id": "sub_a", "created": 1, "status": "canceled", "items": {"data": []}}],
                    "has_more": True}
        assert call.query["starting_after"] == "sub_a"
        return {"object": "list", "data": [{"id": "sub_b", "created": 1, "status": "canceled", "items": {"data": []}}],
                "has_more": False}

    (
        wire
        .on("GET", "/v1/subscriptions", subscriptions)
        .on("GET", "/v1/charges", {"object": "list", "data": [], "has_more": False})
    )

    payload = fetch_stripe({"api_key": "<restricted-key>"}, days=30)

    assert [s["id"] for s in payload["data"]["subscriptions"]] == ["sub_a", "sub_b"]
    assert len(wire.sent("GET", "/v1/subscriptions")) == 2


# ---------------------------------------------------------------------------
# RevenueCat
# ---------------------------------------------------------------------------


def _rc_list(items):
    return {"object": "list", "items": items, "next_page": None}


def test_revenuecat_pull_walks_the_project_and_redacts_customers(wire):
    from service.revenuecat import client as rc
    from service.revenuecat.fetch import fetch_revenuecat

    (
        wire
        .on("GET", "/v2/projects/proj1/apps", _rc_list([{"id": "app1", "name": "iOS"}]))
        .on("GET", "/v2/projects/proj1/products", _rc_list([]))
        .on("GET", "/v2/projects/proj1/entitlements", _rc_list([{"id": "pro"}]))
        .on("GET", "/v2/projects/proj1/offerings", _rc_list([]))
        .on("GET", "/v2/projects/proj1/metrics/overview", {"metrics": [
            {"id": "active_subscriptions", "value": 12}, {"id": "mrr", "value": 480.0},
        ]})
        .on("GET", "/v2/projects/proj1/customers", _rc_list([
            {"id": "$RCAnonymousID:abc", "first_seen_at": 1, "last_seen_country": "ES", "email": "leak@example.com"},
        ]))
    )

    payload = fetch_revenuecat({"api_key": "sk_x", "project_id": "proj1"}, days=30)

    assert payload["errors"] == {}
    assert payload["api"] == "revenuecat-v2"
    assert wire.sent("GET", "/v2/projects?") == []  # a known project id skips discovery
    for call in wire.calls:
        assert call.url.startswith(rc.API_BASE + "/projects/proj1/")
        assert call.headers["Authorization"] == "Bearer sk_x"
    (apps,) = wire.sent("GET", "/apps")
    assert apps.query == {"limit": "100"}

    assert payload["summary"]["active_subscriptions"] == 12
    assert payload["summary"]["mrr"] == 480.0
    (customer,) = payload["data"]["customers"]
    assert payload["data"]["customers_redacted"] is True
    assert "id" not in customer and "email" not in customer
    assert customer["id_hash"] != "$RCAnonymousID:abc" and len(customer["id_hash"]) == 16
    assert customer["last_seen_country"] == "ES"


def test_revenuecat_pull_discovers_the_project_when_none_is_stored(wire):
    from service.revenuecat.fetch import fetch_revenuecat

    (
        wire
        .on("GET", "/v2/projects?", _rc_list([{"id": "found", "name": "Found"}]))
        .on("GET", "/v2/projects/found/metrics/overview", {"metrics": []})
        .on("GET", "/v2/projects/found/", _rc_list([]))
    )

    payload = fetch_revenuecat({"api_key": "sk_x"}, days=30)

    assert payload["project_id"] == "found"
    assert payload["data"]["projects_visible"] == [{"id": "found", "name": "Found"}]
    assert payload["errors"] == {}


def test_revenuecat_pull_isolates_a_failed_section_but_not_a_rejected_key(wire):
    from service.revenuecat.fetch import fetch_revenuecat

    (
        wire
        .on("GET", "/v2/projects/proj1/apps", {"type": "server_error", "message": "boom"}, status=500)
        .on("GET", "/v2/projects/proj1/", _rc_list([]))
        .on("GET", "/v2/projects/proj1/metrics/overview", {"metrics": []})
    )
    import service.rest as rest
    # The retry policy would sleep between the 500s; the test only cares that
    # the section fails and the pull continues.
    import unittest.mock as mock
    with mock.patch.object(rest.time, "sleep"):
        payload = fetch_revenuecat({"api_key": "sk_x", "project_id": "proj1"}, days=30)

    assert "apps" in payload["errors"] and payload["errors"].keys() == {"apps"}
    assert payload["data"]["products"] == []

    wire.routes.clear()
    wire.on("GET", "/v2/projects/proj1/apps", {"type": "unauthorized", "message": "bad key"}, status=401)
    with pytest.raises(ValueError, match="rejected the key"):
        fetch_revenuecat({"api_key": "sk_x", "project_id": "proj1"}, days=30)
