"""The Google Ads executors, against real protos and a recorded transport.

These eight executors are the code in Duct that changes what a customer spends.
Every one of them had a tested *policy* wrapper and an untested body: building a
`GoogleAdsClient` refreshes OAuth against Google at construction time, so before
`FakeAdsClient` there was no way to run an apply or a rollback without a real
account. What that left uncovered is the half where the money is.

The fake keeps the library's local machinery — `get_type`, `enums`, `copy_from`,
the GAPIC path helpers — so these assertions run against the same protos the API
would validate. A misspelled field or a non-member enum raises here.

Two invariants carry most of the file's weight, because both are unrecoverable
if they break in production rather than in CI:

- **REMOVED is never set, and never overwritten.** Google Ads removal is
  irreversible; a rollback cannot undo it, so the executors must refuse it on
  the way in rather than discover it on the way out.
- **The rollback handle is recorded from state read *before* the mutation.**
  A handle derived after the fact restores the value the change just wrote,
  which is a rollback that silently does nothing.
"""

from __future__ import annotations

import pytest

from service.execution import google_ads_exec as gads
from service.execution.registry import EXECUTOR_REGISTRY
from tests.fakes import FakeAdsClient

CREDS = {
    "developer_token": "dev",
    "client_id": "cid",
    "client_secret": "secret",
    "refresh_token": "refresh",
}

CUSTOMER = "123-456-7890"
CUSTOMER_NORM = "1234567890"
CAMPAIGN = "555"
AD_GROUP = "777"


@pytest.fixture
def ads(monkeypatch):
    """Install a FakeAdsClient behind both seams the executors reach through.

    `_build_client` and `_run_query` are imported into the executor's own
    namespace, so they are patched there rather than on `service.google.fetch` —
    patching the source module would leave the already-bound names alone.
    """
    client = FakeAdsClient()
    monkeypatch.setattr(gads, "_build_client", lambda **kwargs: client)
    monkeypatch.setattr(gads, "_run_query", lambda c, cid, query: client.rows)
    return client


def _change(op_type: str, **sections) -> dict:
    change = {"op_type": op_type, "target": {"customer_id": CUSTOMER}}
    for key, value in sections.items():
        change.setdefault(key, {}).update(value) if key in change else change.update({key: value})
    return change


# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("missing", ["developer_token", "client_id", "client_secret", "refresh_token"])
def test_a_missing_credential_is_named_before_any_call(missing):
    creds = {k: v for k, v in CREDS.items() if k != missing}
    with pytest.raises(ValueError, match=missing):
        gads._client(creds)


def test_a_blank_credential_counts_as_missing():
    with pytest.raises(ValueError, match="refresh_token"):
        gads._client({**CREDS, "refresh_token": "   "})


# ---------------------------------------------------------------------------
# add_negative_keywords
# ---------------------------------------------------------------------------

def test_negatives_preview_flags_keywords_the_campaign_already_excludes(ads):
    ads.rows = [ads.row(**{"campaign_criterion.keyword.text": "Free"})]
    change = {
        "op_type": "google_ads.add_negative_keywords",
        "target": {"customer_id": CUSTOMER, "campaign_id": CAMPAIGN},
        "payload": {"keywords": [{"text": "free", "match_type": "PHRASE"}, {"text": "cheap"}]},
    }
    out = gads._negatives_preview(change, CREDS)

    # Matching is case-insensitive — "Free" on the account excludes "free" here.
    assert out["warnings"] == ["Already negative on this campaign: free"]
    assert out["current"] == {"existing_negative_count": 1}
    # An unspecified match_type defaults to PHRASE rather than failing.
    assert "[PHRASE] cheap" in out["diff"]


def test_negatives_apply_sends_the_keywords_as_negatives_and_records_the_undo(ads):
    ads._resource_names = ["customers/1/campaignCriteria/555~1"]
    change = {
        "op_type": "google_ads.add_negative_keywords",
        "target": {"customer_id": CUSTOMER, "campaign_id": CAMPAIGN},
        "payload": {"keywords": [{"text": "free", "match_type": "EXACT"}]},
    }
    out = gads._negatives_apply(change, CREDS)

    sent = ads.mutations[0]
    assert sent.method == "mutate_campaign_criteria"
    assert sent.customer_id == CUSTOMER_NORM, "the dashed customer id must be normalised"
    criterion = sent.operations[0].create
    assert criterion.negative is True, "a positive keyword here would buy the traffic, not block it"
    assert criterion.keyword.text == "free"
    assert criterion.keyword.match_type.name == "EXACT"
    assert criterion.campaign == f"customers/{CUSTOMER_NORM}/campaigns/{CAMPAIGN}"

    # The undo handle is the resource names the API just returned.
    assert out["rollback"] == {"remove_criteria": ["customers/1/campaignCriteria/555~1"]}


def test_negatives_rollback_removes_exactly_what_apply_created(ads):
    names = ["customers/1/campaignCriteria/555~1", "customers/1/campaignCriteria/555~2"]
    change = {
        "op_type": "google_ads.add_negative_keywords",
        "target": {"customer_id": CUSTOMER, "campaign_id": CAMPAIGN},
        "result": {"rollback": {"remove_criteria": names}},
    }
    out = gads._negatives_rollback(change, CREDS)

    assert [op.remove for op in ads.mutations[0].operations] == names
    assert out == {"removed": names}


def test_rollback_without_a_handle_refuses_rather_than_guessing(ads):
    change = {
        "op_type": "google_ads.add_negative_keywords",
        "target": {"customer_id": CUSTOMER, "campaign_id": CAMPAIGN},
        "result": {},
    }
    with pytest.raises(ValueError, match="No rollback handle"):
        gads._negatives_rollback(change, CREDS)


@pytest.mark.parametrize(
    ("keywords", "expected"),
    [
        ([], "non-empty list"),
        ("free", "non-empty list"),
        ([{"text": "  "}], "non-empty text"),
        ([{"text": "free", "match_type": "FUZZY"}], "match_type must be one of"),
    ],
)
def test_malformed_negative_keywords_are_refused_before_the_api_sees_them(keywords, expected):
    change = {
        "op_type": "google_ads.add_negative_keywords",
        "target": {"customer_id": CUSTOMER, "campaign_id": CAMPAIGN},
        "payload": {"keywords": keywords},
    }
    with pytest.raises(ValueError, match=expected):
        gads._normalized_keywords(change)


def test_an_upstream_rejection_surfaces_as_a_runtime_error(ads):
    ads.fail_with = RuntimeError("PERMISSION_DENIED")
    change = {
        "op_type": "google_ads.add_negative_keywords",
        "target": {"customer_id": CUSTOMER, "campaign_id": CAMPAIGN},
        "payload": {"keywords": [{"text": "free"}]},
    }
    # ValueError means "your input was bad" (422); RuntimeError means "the API
    # said no" (recorded on the change). Conflating them mislabels the failure.
    with pytest.raises(RuntimeError, match="Google Ads mutate failed"):
        gads._negatives_apply(change, CREDS)


# ---------------------------------------------------------------------------
# pause_campaign / set_campaign_status
# ---------------------------------------------------------------------------

def _campaign_row(client, status: str, name: str = "Brand"):
    return client.row(**{
        "campaign.id": int(CAMPAIGN),
        "campaign.name": name,
        "campaign.status": status,
    })


def test_pause_preview_warns_when_the_campaign_is_already_paused(ads):
    ads.rows = [_campaign_row(ads, "PAUSED")]
    change = {"op_type": "google_ads.pause_campaign",
              "target": {"customer_id": CUSTOMER, "campaign_id": CAMPAIGN}}
    out = gads._pause_preview(change, CREDS)
    assert out["current"] == {"status": "PAUSED"}
    assert "already paused" in out["warnings"][0]


def test_pause_apply_records_the_status_it_replaced(ads):
    ads.rows = [_campaign_row(ads, "ENABLED")]
    ads._resource_names = [f"customers/{CUSTOMER_NORM}/campaigns/{CAMPAIGN}"]
    change = {"op_type": "google_ads.pause_campaign",
              "target": {"customer_id": CUSTOMER, "campaign_id": CAMPAIGN}}
    out = gads._pause_apply(change, CREDS)

    campaign = ads.mutations[0].operations[0].update
    assert campaign.status.name == "PAUSED"
    # The mask is what stops the mutation clearing every unset field.
    assert set(ads.mutations[0].operations[0].update_mask.paths) == {"resource_name", "status"}
    assert out["rollback"] == {"restore_status": "ENABLED"}


def test_pause_apply_refuses_a_removed_campaign(ads):
    ads.rows = [_campaign_row(ads, "REMOVED")]
    change = {"op_type": "google_ads.pause_campaign",
              "target": {"customer_id": CUSTOMER, "campaign_id": CAMPAIGN}}
    with pytest.raises(ValueError, match="REMOVED"):
        gads._pause_apply(change, CREDS)
    assert ads.mutations == [], "a refused change must not have reached the API"


def test_pause_rollback_of_an_already_paused_campaign_touches_nothing(ads):
    change = {
        "op_type": "google_ads.pause_campaign",
        "target": {"customer_id": CUSTOMER, "campaign_id": CAMPAIGN},
        "result": {"rollback": {"restore_status": "PAUSED"}},
    }
    out = gads._pause_rollback(change, CREDS)
    assert out["restored"] == "PAUSED"
    assert ads.mutations == [], "restoring PAUSED to PAUSED is a no-op, not a mutation"


def test_removed_can_never_be_the_requested_status():
    """Removal is irreversible in Google Ads, so no rollback can undo it."""
    change = {"op_type": "google_ads.set_campaign_status", "payload": {"status": "removed"}}
    with pytest.raises(ValueError, match="irreversible"):
        gads._wanted_status(change)


@pytest.mark.parametrize("status", ["ENABLED", "paused"])
def test_the_settable_statuses_round_trip_case_insensitively(status):
    change = {"op_type": "google_ads.set_campaign_status", "payload": {"status": status}}
    assert gads._wanted_status(change) == status.upper()


def test_an_unknown_status_is_refused():
    change = {"op_type": "google_ads.set_campaign_status", "payload": {"status": "ARCHIVED"}}
    with pytest.raises(ValueError, match="must be one of"):
        gads._wanted_status(change)


# ---------------------------------------------------------------------------
# add_keywords
# ---------------------------------------------------------------------------

def test_a_cpc_bid_is_converted_to_micros():
    change = {"payload": {"keywords": [{"text": "seo audit", "cpc_bid": 1.25}]}}
    assert gads._positive_keywords(change)[0]["cpc_bid_micros"] == 1_250_000


@pytest.mark.parametrize("bid", [0, -1, 0.0000001])
def test_a_non_positive_cpc_bid_is_refused(bid):
    change = {"payload": {"keywords": [{"text": "seo audit", "cpc_bid": bid}]}}
    with pytest.raises(ValueError, match="cpc_bid must be positive"):
        gads._positive_keywords(change)


def test_add_keywords_apply_builds_enabled_positive_criteria(ads):
    change = {
        "op_type": "google_ads.add_keywords",
        "target": {"customer_id": CUSTOMER, "ad_group_id": AD_GROUP},
        "payload": {"keywords": [{"text": "seo audit", "match_type": "EXACT", "cpc_bid": 2}]},
    }
    gads._add_keywords_apply(change, CREDS)

    criterion = ads.mutations[0].operations[0].create
    assert criterion.ad_group == f"customers/{CUSTOMER_NORM}/adGroups/{AD_GROUP}"
    assert criterion.status.name == "ENABLED"
    assert criterion.keyword.match_type.name == "EXACT"
    assert criterion.cpc_bid_micros == 2_000_000


# ---------------------------------------------------------------------------
# set_campaign_budget
# ---------------------------------------------------------------------------

def _budget_row(client, *, amount_micros: int, shared: bool = False, refs: int = 1):
    return client.row(**{
        "campaign.id": int(CAMPAIGN),
        "campaign.name": "Brand",
        "campaign.campaign_budget": f"customers/{CUSTOMER_NORM}/campaignBudgets/9",
        "campaign_budget.amount_micros": amount_micros,
        "campaign_budget.explicitly_shared": shared,
        "campaign_budget.reference_count": refs,
    })


def test_a_shared_budget_is_called_out_before_anyone_approves_it(ads):
    """Raising a shared budget raises spend on every campaign attached to it."""
    ads.rows = [_budget_row(ads, amount_micros=10_000_000, shared=True, refs=4)]
    change = {
        "op_type": "google_ads.set_campaign_budget",
        "target": {"customer_id": CUSTOMER, "campaign_id": CAMPAIGN},
        "payload": {"daily_budget": 25},
    }
    out = gads._budget_preview(change, CREDS)

    assert "SHARED budget" in out["warnings"][0]
    assert "4 campaigns" in out["warnings"][0]
    assert out["current"]["amount_micros"] == 10_000_000
    assert out["diff"].endswith("10 → 25")


def test_an_unshared_budget_used_by_two_campaigns_still_warns(ads):
    """`explicitly_shared` is false for an implicitly reused budget; the
    reference count is what makes it dangerous either way."""
    ads.rows = [_budget_row(ads, amount_micros=5_000_000, shared=False, refs=2)]
    change = {
        "op_type": "google_ads.set_campaign_budget",
        "target": {"customer_id": CUSTOMER, "campaign_id": CAMPAIGN},
        "payload": {"daily_budget": 7},
    }
    assert "SHARED budget" in gads._budget_preview(change, CREDS)["warnings"][0]


def test_budget_apply_records_the_prior_amount_read_before_the_write(ads):
    ads.rows = [_budget_row(ads, amount_micros=10_000_000)]
    change = {
        "op_type": "google_ads.set_campaign_budget",
        "target": {"customer_id": CUSTOMER, "campaign_id": CAMPAIGN},
        "payload": {"daily_budget": 25},
    }
    out = gads._budget_apply(change, CREDS)

    budget = ads.mutations[0].operations[0].update
    assert budget.amount_micros == 25_000_000
    assert set(ads.mutations[0].operations[0].update_mask.paths) == {"resource_name", "amount_micros"}
    assert out["rollback"]["restore_amount_micros"] == 10_000_000


def test_budget_apply_trusts_the_snapshot_the_preview_took(ads):
    """When preview already read the account, apply must not re-read it — the
    value it would get back is the one a concurrent change just wrote."""
    change = {
        "op_type": "google_ads.set_campaign_budget",
        "target": {"customer_id": CUSTOMER, "campaign_id": CAMPAIGN},
        "payload": {"daily_budget": 25},
        "current": {
            "budget_resource": f"customers/{CUSTOMER_NORM}/campaignBudgets/9",
            "amount_micros": 10_000_000,
        },
    }
    out = gads._budget_apply(change, CREDS)
    assert out["rollback"]["restore_amount_micros"] == 10_000_000


def test_budget_rollback_restores_the_recorded_amount(ads):
    change = {
        "op_type": "google_ads.set_campaign_budget",
        "target": {"customer_id": CUSTOMER, "campaign_id": CAMPAIGN},
        "result": {"rollback": {
            "budget_resource": f"customers/{CUSTOMER_NORM}/campaignBudgets/9",
            "restore_amount_micros": 10_000_000,
        }},
    }
    out = gads._budget_rollback(change, CREDS)
    assert ads.mutations[0].operations[0].update.amount_micros == 10_000_000
    assert out["restored_amount_micros"] == 10_000_000


@pytest.mark.parametrize("payload", [{}, {"daily_budget": 0}, {"amount_micros": -5}])
def test_a_missing_or_non_positive_budget_is_refused(payload):
    with pytest.raises(ValueError):
        gads._budget_micros({"payload": payload})


# ---------------------------------------------------------------------------
# Registry-wide invariants
# ---------------------------------------------------------------------------

def test_every_google_ads_executor_can_be_undone():
    """A change that can be applied but not reverted is one a human has to fix
    by hand in the Google Ads UI, which is the state this framework exists to
    avoid. Adding an executor without a rollback should fail here."""
    specs = [s for s in EXECUTOR_REGISTRY.values() if s.connector_type == "google_ads"]
    assert specs, "the google_ads executors did not register"
    assert [s.op_type for s in specs if s.rollback is None] == []


def test_every_google_ads_executor_declares_the_adwords_scope():
    for spec in EXECUTOR_REGISTRY.values():
        if spec.connector_type == "google_ads":
            assert spec.required_scopes == frozenset(
                {"https://www.googleapis.com/auth/adwords"}
            ), spec.op_type
