"""Unit tests for the Phase-7 manual-credential connectors.

Each test pins one of the encoded gotchas from the Gads corpus: Apple string
money + report totals rules, Meta minor-units + purchase dedup, Stripe
never-paid exclusion + refund netting, RevenueCat key-shape rejection +
relative next_page, OpenAI repeated-array params + the pixel 100× trap.
No network — transport calls are monkeypatched.
"""

from __future__ import annotations


import pytest

import service.apple.ads.client as asa
import service.apple.ads.fetch as asa_fetch  # noqa: F401 — registers connector
import service.meta.ads.client as meta
import service.meta.ads.fetch as meta_fetch  # noqa: F401
import service.openai.ads.client as oai
import service.openai.ads.fetch as oai_fetch  # noqa: F401
import service.revenuecat.client as rc
import service.revenuecat.fetch as rc_fetch  # noqa: F401
import service.stripe.client as st
import service.stripe.fetch as st_fetch
from service.connectors import CAP_ACCOUNTS, CONNECTOR_REGISTRY


# ---------------------------------------------------------------------------
# Registry + framework wiring
# ---------------------------------------------------------------------------

def test_all_five_connectors_registered_with_accounts_capability():
    for cid in ("apple_ads", "meta_ads", "stripe", "revenuecat", "openai_ads"):
        meta_row, adapter = CONNECTOR_REGISTRY[cid]
        assert meta_row.oauth_scope is None  # manual-credential by design
        assert CAP_ACCOUNTS in meta_row.capabilities
        assert hasattr(adapter, "list_accounts")


def test_allowed_types_and_pipeline_support():
    from routes.user_connectors import ALLOWED_CONNECTOR_TYPES
    from service.pipeline import MANUAL_CREDENTIAL_CONNECTORS, SUPPORTED_CONNECTORS

    five = {"apple_ads", "meta_ads", "stripe", "revenuecat", "openai_ads"}
    wave2 = {"mixpanel", "clarity", "growthbook"}
    assert five | wave2 <= ALLOWED_CONNECTOR_TYPES
    assert five | wave2 <= SUPPORTED_CONNECTORS
    assert five | wave2 == MANUAL_CREDENTIAL_CONNECTORS


def test_knowledge_packs_exist_and_load():
    from agents.knowledge import load_knowledge_pack

    for name in ("apple_ads", "meta", "stripe", "revenuecat", "openai_ads", "reconciliation"):
        content = load_knowledge_pack(name)
        assert content.strip(), f"knowledge pack {name} is empty"


# ---------------------------------------------------------------------------
# Apple Search Ads
# ---------------------------------------------------------------------------

def test_apple_money_parses_string_amounts():
    assert asa.money({"amount": "12.34", "currency": "USD"}) == 12.34
    assert asa.money({"amount": None}) == 0.0
    assert asa.money(None) == 0.0


def test_apple_report_totals_rule():
    # No granularity → row totals MUST be true.
    body = asa.report_body("2026-08-01", "2026-08-27", level="campaigns")
    assert body["returnRowTotals"] is True
    assert body["returnGrandTotals"] is False
    # With granularity → both MUST be false.
    body = asa.report_body("2026-08-01", "2026-08-27", level="campaigns", granularity="DAILY")
    assert body["returnRowTotals"] is False
    assert body["granularity"] == "DAILY"
    # group_by override: both totals flags false even without granularity.
    body = asa.report_body("2026-08-01", "2026-08-27", level="campaigns", row_totals=False)
    assert body["returnRowTotals"] is False


def test_apple_default_order_by_per_level():
    body = asa.report_body("a", "b", level="campaigns")
    assert body["selector"]["orderBy"] == [{"field": "campaignId", "sortOrder": "DESCENDING"}]
    # searchterms is the one level where the id field is rejected.
    body = asa.report_body("a", "b", level="searchterms")
    assert body["selector"]["orderBy"][0]["field"] == "impressions"


def test_apple_rejects_bad_granularity():
    with pytest.raises(ValueError, match="granularity"):
        asa.report_body("a", "b", level="campaigns", granularity="MINUTELY")


def test_apple_require_credentials_names_missing_pieces():
    with pytest.raises(ValueError, match="team_id"):
        asa.require_credentials({"client_id": "x", "key_id": "k", "private_key": "BEGIN"})
    with pytest.raises(ValueError, match="PEM"):
        asa.require_credentials(
            {"client_id": "x", "team_id": "t", "key_id": "k", "private_key": "not-a-pem"}
        )


def test_apple_client_secret_is_valid_es256_jwt():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    creds = {"client_id": "CLIENT", "team_id": "TEAM", "key_id": "KEYID", "private_key": pem}
    token = asa.client_secret(creds)

    import jwt as pyjwt

    header = pyjwt.get_unverified_header(token)
    assert header["alg"] == "ES256"
    assert header["kid"] == "KEYID"
    payload = pyjwt.decode(
        token, key.public_key(), algorithms=["ES256"], audience=asa.AUDIENCE
    )
    assert payload["sub"] == "CLIENT"
    assert payload["iss"] == "TEAM"


def test_apple_slim_report_row_handles_v5_install_rename():
    row = {
        "metadata": {"campaignId": 1, "campaignName": "C"},
        "total": {
            "impressions": 10, "taps": 2,
            "tapInstalls": 1, "totalInstalls": 3,
            "localSpend": {"amount": "5.50", "currency": "USD"},
        },
    }
    slim = asa_fetch._slim_report_row(row)
    assert slim["tap_installs"] == 1
    assert slim["total_installs"] == 3
    assert slim["spend"] == 5.5


# ---------------------------------------------------------------------------
# Meta
# ---------------------------------------------------------------------------

def test_meta_minor_vs_major_units():
    assert meta.minor("1999") == 19.99   # budgets: cents
    assert meta.money("19.99") == 19.99  # spend: dollars
    assert meta.minor(None) == 0.0


def test_meta_purchases_picks_one_action_type_never_sums():
    row = {
        "actions": [
            {"action_type": "purchase", "value": "3"},
            {"action_type": "offsite_conversion.fb_pixel_purchase", "value": "3"},
            {"action_type": "omni_purchase", "value": "3"},
        ],
        "action_values": [
            {"action_type": "purchase", "value": "90"},
            {"action_type": "offsite_conversion.fb_pixel_purchase", "value": "90"},
            {"action_type": "omni_purchase", "value": "90"},
        ],
    }
    count, value = meta.purchases(row)
    # The same 3 orders appear under 3 types — summing would report 9/$270.
    assert count == 3.0
    assert value == 90.0


def test_meta_purchases_prefers_pixel_over_aggregate():
    row = {
        "actions": [
            {"action_type": "purchase", "value": "5"},
            {"action_type": "offsite_conversion.fb_pixel_purchase", "value": "4"},
        ],
        "action_values": [],
    }
    count, _ = meta.purchases(row)
    assert count == 4.0  # pixel is first preference


def test_meta_api_error_branches_on_code_not_status():
    err = meta.ApiError(400, '{"error":{"message":"x","type":"OAuthException","code":190}}')
    assert err.api_code == 190
    assert "System User" in err.hint()
    throttled = meta.ApiError(400, '{"error":{"code":80004,"message":"limit"}}')
    assert throttled.is_throttle
    bounce = meta.ApiError(400, '{"error":{"code":1,"message":"Please reduce the amount of data"}}')
    assert bounce.too_much_data


def test_meta_normalize_account_id():
    assert meta.normalize_account_id("123") == "act_123"
    assert meta.normalize_account_id("act_123") == "act_123"
    assert meta.normalize_account_id("") == ""


def test_meta_get_all_follows_cursor(monkeypatch):
    pages = [
        {"data": [{"id": 1}], "paging": {"next": "https://graph/np"}},
        {"data": [{"id": 2}], "paging": {}},
    ]
    calls = []

    def fake_api(path, creds, params=None, method="GET", retries=5):
        calls.append(path)
        return pages[len(calls) - 1]

    monkeypatch.setattr(meta, "api", fake_api)
    rows = meta.get_all("act_1/campaigns", {"access_token": "t"})
    assert [r["id"] for r in rows] == [1, 2]
    assert calls[1] == "https://graph/np"  # follows paging.next verbatim


# ---------------------------------------------------------------------------
# Stripe
# ---------------------------------------------------------------------------

def _sub(status, amount=1999, change_type=None, interval="month", created=1756200000):
    return {
        "id": f"sub_{status}_{change_type}",
        "created": created,
        "status": status,
        "items": {"data": [{"price": {"unit_amount": amount, "currency": "usd",
                                      "nickname": "Pro", "recurring": {"interval": interval}},
                            "quantity": 1}]},
        "metadata": ({"change_type": change_type} if change_type else {}),
    }


def test_stripe_never_paid_subscriptions_are_not_sales():
    subs = [st_fetch.slim_subscription(s) for s in (
        _sub("active"), _sub("incomplete"), _sub("incomplete_expired"), _sub("trialing"),
    )]
    summary = st_fetch.summarise(subs, [])
    assert summary["paid_new_subs"] == 2       # active + trialing
    assert summary["never_paid_subs"] == 2     # incomplete twins — NOT sales


def test_stripe_upgrades_are_expansion_not_acquisition():
    subs = [st_fetch.slim_subscription(s) for s in (
        _sub("active"), _sub("active", change_type="upgrade"),
    )]
    summary = st_fetch.summarise(subs, [])
    assert summary["paid_new_subs"] == 1
    assert summary["upgrades"] == 1


def test_stripe_refunds_are_netted_and_mrr_annualizes():
    subs = [st_fetch.slim_subscription(_sub("active", amount=12000, interval="year"))]
    charges = [st_fetch.slim_charge({
        "id": "ch_1", "created": 1756200000, "status": "succeeded", "amount": 5000,
        "amount_refunded": 1000, "currency": "usd", "paid": True, "refunded": False,
    })]
    summary = st_fetch.summarise(subs, charges)
    assert summary["gross_revenue"] == 50.0
    assert summary["net_revenue"] == 40.0
    assert summary["new_mrr_equivalent"] == 10.0  # $120/year → $10 MRR


def test_stripe_price_comes_from_items_not_legacy_plan():
    s = _sub("active", amount=1000)
    s["items"]["data"].append({"price": {"unit_amount": 500, "currency": "usd",
                                         "recurring": {"interval": "month"}}, "quantity": 2})
    s["plan"] = None  # legacy field null for multi-item subscriptions
    slim = st_fetch.slim_subscription(s)
    assert slim["amount"] == 20.0  # 1000 + 500*2 cents
    assert slim["items"] == 2


def test_stripe_money_zero_decimal_currencies():
    assert st.money(1999, "usd") == 19.99
    assert st.money(1999, "jpy") == 1999  # zero-decimal passes through


def test_stripe_flatten_nested_filters():
    pairs = st._flatten({"created": {"gte": 1, "lte": 2}, "status": "all"})
    assert ("created[gte]", "1") in pairs
    assert ("created[lte]", "2") in pairs
    assert ("status", "all") in pairs


def test_stripe_get_all_paginates_by_last_id(monkeypatch):
    pages = [
        {"data": [{"id": "ch_1"}, {"id": "ch_2"}], "has_more": True},
        {"data": [{"id": "ch_3"}], "has_more": False},
    ]
    seen_params = []

    def fake_api(path, creds, params=None, retries=4):
        seen_params.append(dict(params or {}))
        return pages[len(seen_params) - 1]

    monkeypatch.setattr(st, "api", fake_api)
    rows = st.get_all("charges", {"api_key": "rk_test"})
    assert len(rows) == 3
    assert seen_params[1]["starting_after"] == "ch_2"


# ---------------------------------------------------------------------------
# RevenueCat
# ---------------------------------------------------------------------------

def test_revenuecat_rejects_public_sdk_keys():
    for prefix in ("appl_", "goog_", "amzn_", "rcb_"):
        with pytest.raises(ValueError, match="public SDK"):
            rc.require_credentials({"api_key": prefix + "abc"})
    with pytest.raises(ValueError, match="api_key missing"):
        rc.require_credentials({})
    assert rc.require_credentials({"api_key": "sk_abc"}) == "sk_abc"


def test_revenuecat_get_all_handles_relative_next_page(monkeypatch):
    pages = {
        "first": {"items": [{"id": 1}], "next_page": "/v2/projects/p/customers?starting_after=1"},
        "next": {"items": [{"id": 2}], "next_page": None},
    }
    urls = []

    def fake_api(path, creds, params=None, retries=5, throttle=False):
        urls.append(path)
        return pages["next"] if path.startswith("http") else pages["first"]

    monkeypatch.setattr(rc, "api", fake_api)
    rows = rc.get_all("projects/p/customers", {"api_key": "sk_x"})
    assert [r["id"] for r in rows] == [1, 2]
    # Relative next_page joined onto the HOST, not API_BASE (no double /v2).
    assert urls[1] == "https://api.revenuecat.com/v2/projects/p/customers?starting_after=1"


def test_revenuecat_customer_redaction_hashes_user_ids():
    rows = rc_fetch.redact_customers([
        {"id": "user@example.com", "first_seen_at": 1, "last_seen_country": "US"},
    ])
    assert "user@example.com" not in str(rows)
    assert rows[0]["id_hash"] and len(rows[0]["id_hash"]) == 16
    # Deterministic — joinable across pulls.
    again = rc_fetch.redact_customers([{"id": "user@example.com"}])
    assert again[0]["id_hash"] == rows[0]["id_hash"]


def test_revenuecat_error_hints():
    assert "secret" in rc.ApiError(401, "{}").hint().lower()
    assert "charts_metrics:overview:read" in rc.ApiError(403, "{}").hint()


# ---------------------------------------------------------------------------
# OpenAI Ads
# ---------------------------------------------------------------------------

def test_openai_encode_repeats_array_keys_and_jsonifies_dicts():
    pairs = oai._encode({
        "fields[]": ["a", "b"],
        "time_ranges[]": [{"type": "date_range", "since": "2026-08-01", "until": "2026-08-27"}],
        "limit": 500,
    })
    keys = [k for k, _ in pairs]
    assert keys.count("fields[]") == 2
    tr = dict(pairs).get("time_ranges[]") or [v for k, v in pairs if k == "time_ranges[]"][0]
    assert '"type":"date_range"' in tr
    assert ("limit", "500") in pairs


def test_openai_insights_projects_full_metric_set(monkeypatch):
    captured = {}

    def fake_get_all(path, creds, params=None, limit=500, cap=None):
        captured["path"] = path
        captured["params"] = params
        return []

    monkeypatch.setattr(oai, "get_all", fake_get_all)
    oai.insights({"api_key": "k"}, days=7, aggregation_level="campaign")
    fields = captured["params"]["fields[]"]
    # Omitting fields returns almost nothing — the full set must be projected.
    for m in oai.INSIGHT_METRICS:
        assert f"campaign.{m}" in fields
    assert "campaign.id" in fields and "campaign.name" in fields
    assert captured["path"] == "ad_account/insights"


def test_openai_pixel_amount_is_minor_units():
    # Pixel 1499 = $14.99 while insights spend "18.42" is already dollars.
    assert oai.pixel_amount(1499) == 14.99
    assert oai.pixel_amount(None) == 0.0


def test_openai_get_all_follows_last_id_cursor(monkeypatch):
    pages = [
        {"data": [{"id": "c1"}], "has_more": True, "last_id": "c1"},
        {"data": [{"id": "c2"}], "has_more": False},
    ]
    seen = []

    def fake_api(path, creds, params=None, retries=4, payload=None):
        seen.append(dict(params or {}))
        return pages[len(seen) - 1]

    monkeypatch.setattr(oai, "api", fake_api)
    rows = oai.get_all("campaigns", {"api_key": "k"})
    assert [r["id"] for r in rows] == ["c1", "c2"]
    assert seen[1]["after"] == "c1"
