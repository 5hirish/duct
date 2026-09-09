"""The GA4 executors, against a faked Admin API.

Key-event repair is the highest-value execution Duct offers — the `signup` vs
`sign_up` rename that silently dropped conversions is the case it was built
for — and it was also the least covered, because `discovery.build()` fetches
the API's discovery document over the network before it returns a client. So
these six executors could not be reached offline at all.

Three properties carry the file, each because getting it wrong is expensive in
a way a passing preview would hide:

- **`analytics.edit` denial is a `ValueError`, not a `RuntimeError`.** Read-only
  is the normal state of a GA4 connection: Google's consent screen is
  per-scope, so someone can connect GA4 successfully and still be unable to run
  any of this. That has to surface as "reconnect with manage access", which is
  actionable, rather than as an upstream fault.
- **Archiving an audience is permanent.** The rollback recreates the
  definition, never the members, and the preview has to say so before a human
  approves it.
- **Delete snapshots what it deletes.** A key event removed without its
  countingMethod recorded cannot be put back the way it was.
"""

from __future__ import annotations

import pytest

from service.execution import ga4_exec
from service.execution.registry import EXECUTOR_REGISTRY
from tests.fakes import FakeDiscoveryService

CREDS = {"client_id": "cid", "client_secret": "secret", "refresh_token": "refresh"}
PROPERTY = "123456"
PARENT = f"properties/{PROPERTY}"


@pytest.fixture
def admin(monkeypatch):
    """One fake behind both Admin API builders.

    `ga4_exec` builds v1beta for key events and Ads links and v1alpha for
    audiences, because audiences are not in v1beta. The fake answers by call
    path rather than by version, so one instance serves both and a test does
    not have to know which surface it is on.
    """
    service = FakeDiscoveryService()
    monkeypatch.setattr(ga4_exec, "_admin_service", lambda creds: service)
    monkeypatch.setattr(ga4_exec, "_admin_service_alpha", lambda creds: service)
    return service


def _http_error(status: int):
    """A real `HttpError`, because `_translate` branches on its `resp.status`."""
    from googleapiclient.errors import HttpError

    class _Resp:
        def __init__(self, status):
            self.status = status
            self.reason = "denied"

    return HttpError(_Resp(status), b'{"error": {"message": "no"}}')


# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("missing", ["client_id", "client_secret", "refresh_token"])
def test_a_missing_ga4_credential_is_named(missing):
    creds = {k: v for k, v in CREDS.items() if k != missing}
    with pytest.raises(ValueError, match=missing):
        ga4_exec._admin_service(creds)


# ---------------------------------------------------------------------------
# The scope failure, which is the common one
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("status", [401, 403])
def test_a_read_only_token_is_reported_as_something_the_user_can_fix(admin, status):
    admin.responses["properties.keyEvents.list"] = _http_error(status)
    change = {"op_type": "ga4.create_key_event",
              "target": {"property_id": PROPERTY},
              "payload": {"event_name": "sign_up"}}
    # ValueError, not RuntimeError: this is a 422 the user resolves by
    # reconnecting, not an upstream fault to record and retry.
    with pytest.raises(ValueError, match="read-only"):
        ga4_exec._create_preview(change, CREDS)


def test_a_genuine_api_fault_stays_a_runtime_error(admin):
    admin.responses["properties.keyEvents.list"] = _http_error(500)
    change = {"op_type": "ga4.create_key_event",
              "target": {"property_id": PROPERTY},
              "payload": {"event_name": "sign_up"}}
    with pytest.raises(RuntimeError, match="GA4 Admin API error"):
        ga4_exec._create_preview(change, CREDS)


def test_every_ga4_executor_demands_the_edit_scope():
    """Declared so the check runs before apply time rather than as a 403 after
    a human already approved the change."""
    specs = [s for s in EXECUTOR_REGISTRY.values() if s.connector_type == "ga4"]
    assert len(specs) == 6, "the ga4 executors did not all register"
    for spec in specs:
        assert spec.required_scopes == frozenset(
            {"https://www.googleapis.com/auth/analytics.edit"}
        ), spec.op_type


def test_the_irreversible_ga4_ops_are_flagged_destructive():
    destructive = {s.op_type for s in EXECUTOR_REGISTRY.values()
                   if s.connector_type == "ga4" and s.destructive}
    assert destructive == {
        "ga4.delete_key_event", "ga4.archive_audience", "ga4.delete_google_ads_link",
    }


# ---------------------------------------------------------------------------
# create_key_event
# ---------------------------------------------------------------------------

def test_create_key_event_preview_warns_when_it_is_already_registered(admin):
    admin.responses["properties.keyEvents.list"] = {
        "keyEvents": [{"eventName": "sign_up", "name": f"{PARENT}/keyEvents/1"}]
    }
    change = {"op_type": "ga4.create_key_event",
              "target": {"property_id": PROPERTY},
              "payload": {"event_name": "sign_up"}}
    out = ga4_exec._create_preview(change, CREDS)

    assert out["warnings"] == [f"'sign_up' is already a key event on property {PROPERTY}."]
    assert out["current"]["key_events"] == ["sign_up"]
    assert out["mutate_payload"] == {"eventName": "sign_up", "countingMethod": "ONCE_PER_EVENT"}


def test_an_unknown_counting_method_is_refused_before_any_call(admin):
    change = {"op_type": "ga4.create_key_event",
              "target": {"property_id": PROPERTY},
              "payload": {"event_name": "sign_up", "counting_method": "ONCE_PER_USER"}}
    with pytest.raises(ValueError, match="counting_method must be one of"):
        ga4_exec._create_preview(change, CREDS)
    assert admin.calls == []


def test_create_key_event_apply_records_the_resource_to_delete(admin):
    admin.responses["properties.keyEvents.create"] = {
        "name": f"{PARENT}/keyEvents/9", "eventName": "sign_up"
    }
    change = {"op_type": "ga4.create_key_event",
              "target": {"property_id": PROPERTY},
              "payload": {"event_name": "  sign_up  ", "counting_method": "once_per_session"}}
    out = ga4_exec._create_apply(change, CREDS)

    path, kwargs = admin.calls[0]
    assert path == "properties.keyEvents.create"
    assert kwargs["parent"] == PARENT
    assert kwargs["body"] == {"eventName": "sign_up", "countingMethod": "ONCE_PER_SESSION"}
    assert out["rollback"] == {"delete_resource": f"{PARENT}/keyEvents/9"}


def test_create_key_event_rollback_deletes_what_it_made(admin):
    change = {"op_type": "ga4.create_key_event",
              "result": {"rollback": {"delete_resource": f"{PARENT}/keyEvents/9"}}}
    assert ga4_exec._create_rollback(change, CREDS)["deleted"] == f"{PARENT}/keyEvents/9"
    assert admin.calls == [("properties.keyEvents.delete", {"name": f"{PARENT}/keyEvents/9"})]


def test_create_key_event_rollback_without_a_handle_refuses(admin):
    with pytest.raises(ValueError, match="No rollback handle"):
        ga4_exec._create_rollback({"op_type": "ga4.create_key_event", "result": {}}, CREDS)


# ---------------------------------------------------------------------------
# delete_key_event — the one that has to snapshot before it destroys
# ---------------------------------------------------------------------------

def test_delete_key_event_apply_snapshots_the_counting_method(admin):
    """Recreating a key event without its countingMethod puts back something
    that counts differently, which is a silent conversion-data change."""
    admin.responses["properties.keyEvents.list"] = {"keyEvents": [{
        "name": f"{PARENT}/keyEvents/4",
        "eventName": "signup",
        "countingMethod": "ONCE_PER_SESSION",
    }]}
    change = {"op_type": "ga4.delete_key_event",
              "target": {"property_id": PROPERTY, "event_name": "signup"}}
    out = ga4_exec._delete_apply(change, CREDS)

    assert out["rollback"]["recreate"] == {
        "parent": PARENT, "eventName": "signup", "countingMethod": "ONCE_PER_SESSION",
    }


def test_delete_key_event_preview_says_so_when_there_is_nothing_to_delete(admin):
    admin.responses["properties.keyEvents.list"] = {"keyEvents": []}
    change = {"op_type": "ga4.delete_key_event",
              "target": {"property_id": PROPERTY, "event_name": "signup"}}
    out = ga4_exec._delete_preview(change, CREDS)
    assert out["warnings"] == ["'signup' is not currently a key event — applying would fail."]
    assert out["mutate_payload"] == {}


def test_delete_key_event_apply_refuses_when_the_event_is_absent(admin):
    admin.responses["properties.keyEvents.list"] = {"keyEvents": []}
    change = {"op_type": "ga4.delete_key_event",
              "target": {"property_id": PROPERTY, "event_name": "signup"}}
    with pytest.raises(ValueError, match="is not a key event"):
        ga4_exec._delete_apply(change, CREDS)
    assert [p for p, _ in admin.calls] == ["properties.keyEvents.list"], "nothing was deleted"


def test_delete_key_event_rollback_recreates_from_the_snapshot(admin):
    admin.responses["properties.keyEvents.create"] = {"name": f"{PARENT}/keyEvents/12"}
    change = {"op_type": "ga4.delete_key_event", "result": {"rollback": {"recreate": {
        "parent": PARENT, "eventName": "signup", "countingMethod": "ONCE_PER_SESSION",
    }}}}
    out = ga4_exec._delete_rollback(change, CREDS)

    _, kwargs = admin.calls[0]
    assert kwargs["body"] == {"eventName": "signup", "countingMethod": "ONCE_PER_SESSION"}
    assert out["recreated"] == f"{PARENT}/keyEvents/12"


# ---------------------------------------------------------------------------
# Audiences
# ---------------------------------------------------------------------------

_CLAUSES = [{"clauseType": "INCLUDE", "simpleFilter": {}}]


def test_an_audience_needs_a_name_and_at_least_one_clause():
    with pytest.raises(ValueError, match="display_name"):
        ga4_exec._audience_body({"payload": {"filter_clauses": _CLAUSES}})
    with pytest.raises(ValueError, match="filter_clauses"):
        ga4_exec._audience_body({"payload": {"display_name": "Buyers"}})


def test_audience_defaults_fill_in_membership_and_description():
    body = ga4_exec._audience_body(
        {"payload": {"display_name": "Buyers", "filter_clauses": _CLAUSES}}
    )
    assert body["membershipDurationDays"] == 30
    assert body["description"] == ""


def test_a_full_audience_dict_and_the_convenience_fields_merge():
    body = ga4_exec._audience_body({"payload": {
        "audience": {"displayName": "Raw", "filterClauses": _CLAUSES},
        "display_name": "Buyers",
        "membership_duration_days": "60",
    }})
    assert body["displayName"] == "Buyers", "the explicit field wins over the raw dict"
    assert body["membershipDurationDays"] == 60, "and arrives as an int"


def test_audience_create_preview_warns_on_a_duplicate_name(admin):
    admin.responses["properties.audiences.list"] = {
        "audiences": [{"displayName": "Buyers", "name": f"{PARENT}/audiences/1"}]
    }
    change = {"op_type": "ga4.create_audience", "target": {"property_id": PROPERTY},
              "payload": {"display_name": "Buyers", "filter_clauses": _CLAUSES}}
    out = ga4_exec._audience_create_preview(change, CREDS)
    assert "already exists" in out["warnings"][0]
    assert out["current"]["audience_count"] == 1


def test_archiving_an_audience_is_previewed_as_permanent(admin):
    """A human approving this has to see that no rollback restores members."""
    admin.responses["properties.audiences.list"] = {"audiences": [{
        "name": f"{PARENT}/audiences/7", "displayName": "Buyers",
        "membershipDurationDays": 30, "filterClauses": _CLAUSES,
    }]}
    change = {"op_type": "ga4.archive_audience",
              "target": {"property_id": PROPERTY, "display_name": "Buyers"}}
    out = ga4_exec._audience_archive_preview(change, CREDS)

    assert "PERMANENT" in out["diff"]
    assert "re-accumulates members from zero" in out["diff"]
    assert out["warnings"] == ["GA4 audiences cannot be unarchived."]


def test_an_audience_is_found_by_resource_name_as_well_as_display_name(admin):
    admin.responses["properties.audiences.list"] = {"audiences": [
        {"name": f"{PARENT}/audiences/7", "displayName": "Buyers"},
        {"name": f"{PARENT}/audiences/8", "displayName": "Browsers"},
    ]}
    change = {"op_type": "ga4.archive_audience",
              "target": {"property_id": PROPERTY, "audience_resource": f"{PARENT}/audiences/8"}}
    match = ga4_exec._find_audience(admin, PROPERTY, change)
    assert match["displayName"] == "Browsers"


def test_archiving_without_a_way_to_identify_the_audience_is_refused(admin):
    admin.responses["properties.audiences.list"] = {"audiences": []}
    with pytest.raises(ValueError, match="audience_resource or target.display_name"):
        ga4_exec._find_audience(admin, PROPERTY, {"op_type": "ga4.archive_audience", "target": {}})


def test_audience_archive_apply_snapshots_the_definition_it_destroys(admin):
    admin.responses["properties.audiences.list"] = {"audiences": [{
        "name": f"{PARENT}/audiences/7", "displayName": "Buyers",
        "description": "Bought once", "membershipDurationDays": 45,
        "filterClauses": _CLAUSES,
    }]}
    change = {"op_type": "ga4.archive_audience",
              "target": {"property_id": PROPERTY, "display_name": "Buyers"}}
    out = ga4_exec._audience_archive_apply(change, CREDS)

    assert ("properties.audiences.archive", {"name": f"{PARENT}/audiences/7", "body": {}}) in admin.calls
    assert out["rollback"]["recreate"] == {
        "displayName": "Buyers", "description": "Bought once",
        "membershipDurationDays": 45, "filterClauses": _CLAUSES,
    }


def test_archiving_an_audience_that_is_not_there_refuses_before_mutating(admin):
    admin.responses["properties.audiences.list"] = {"audiences": []}
    change = {"op_type": "ga4.archive_audience",
              "target": {"property_id": PROPERTY, "display_name": "Buyers"}}
    with pytest.raises(ValueError, match="Audience not found"):
        ga4_exec._audience_archive_apply(change, CREDS)
    assert [p for p, _ in admin.calls] == ["properties.audiences.list"]
