"""Unit tests for the staged-execution framework (registry, guardrails, routes)."""

from __future__ import annotations

import importlib
import os

import pytest

from models.execution import ExecutionGuardrail
from service.execution import ga4_exec, google_ads_exec  # noqa: F401  (registers executors)
from service.execution.guardrails import violations_for
from service.execution.registry import (
    EXECUTOR_REGISTRY,
    ExecutorSpec,
    get_executor,
    register_executor,
)
from tests.conftest import api_routes


# ---------------------------------------------------------------------------
# Registry
#
# The "which executors are registered and reversible" assertion lives once, in
# tests/test_execution_policy.py::test_executors_registered — it covers the same
# four ops this file used to re-list, plus the rest of the registry and the
# auto-apply allowlist invariants.
# ---------------------------------------------------------------------------

def test_unknown_op_type_raises():
    with pytest.raises(KeyError, match="Unknown execution op_type"):
        get_executor("meta_ads.pause_campaign")


def test_register_executor_roundtrip():
    spec = ExecutorSpec(
        op_type="test.noop",
        connector_type="test",
        label="No-op",
        preview=lambda change, creds: {"diff": "noop"},
        apply=lambda change, creds: {},
    )
    register_executor(spec)
    try:
        assert get_executor("test.noop") is spec
    finally:
        EXECUTOR_REGISTRY.pop("test.noop", None)


# ---------------------------------------------------------------------------
# Guardrails
# ---------------------------------------------------------------------------

def _guardrail(rule: str, match: dict, active: bool = True) -> ExecutionGuardrail:
    return ExecutionGuardrail(
        connector_type="google_ads", rule=rule, match=match, active=active
    )


PAUSE_PMAX = {
    "op_type": "google_ads.pause_campaign",
    "target": {"customer_id": "1112223333", "campaign_id": "555", "campaign_name": "PMax poison"},
    "payload": {},
}


# One rail, one change (PAUSE_PMAX), one question: does the matcher fire? Each
# row turns exactly one knob relative to the first.
@pytest.mark.parametrize(
    ("case", "rule", "match", "active", "expected"),
    [
        (
            "op_type + target both match",
            "Never touch campaign 555",
            {"op_types": ["google_ads.pause_campaign"], "target_contains": "555"},
            True,
            ["Never touch campaign 555"],
        ),
        (
            "target_contains misses",
            "Never touch campaign 999",
            {"op_types": ["google_ads.pause_campaign"], "target_contains": "999"},
            True,
            [],
        ),
        (
            "op_type out of scope",
            "No negatives",
            {"op_types": ["google_ads.add_negative_keywords"]},
            True,
            [],
        ),
        ("empty matcher is prose only", "Be careful out there", {}, True, []),
        (
            "inactive rail is skipped",
            "Never touch campaign 555",
            {"op_types": ["google_ads.pause_campaign"], "target_contains": "555"},
            False,
            [],
        ),
    ],
    ids=lambda v: v if isinstance(v, str) else "",
)
def test_guardrail_matching(case, rule, match, active, expected):
    assert violations_for(PAUSE_PMAX, [_guardrail(rule, match, active=active)]) == expected, case


def test_guardrail_target_contains_without_op_types_blocks_all_ops():
    rails = [_guardrail("Campaign 555 is off-limits", {"target_contains": "555"})]
    negatives = {
        "op_type": "google_ads.add_negative_keywords",
        "target": {"customer_id": "1112223333", "campaign_id": "555"},
        "payload": {"keywords": [{"text": "free", "match_type": "PHRASE"}]},
    }
    assert violations_for(negatives, rails) == ["Campaign 555 is off-limits"]
    assert violations_for(PAUSE_PMAX, rails) == ["Campaign 555 is off-limits"]


# ---------------------------------------------------------------------------
# Executor input validation (pure parts — no network)
# ---------------------------------------------------------------------------

def test_negative_keywords_validation():
    good = {
        "op_type": "google_ads.add_negative_keywords",
        "payload": {"keywords": [{"text": "free download", "match_type": "phrase"}]},
    }
    assert google_ads_exec._normalized_keywords(good) == [
        {"text": "free download", "match_type": "PHRASE"}
    ]

    with pytest.raises(ValueError, match="non-empty list"):
        google_ads_exec._normalized_keywords({"op_type": "x", "payload": {"keywords": []}})
    with pytest.raises(ValueError, match="match_type"):
        google_ads_exec._normalized_keywords(
            {"op_type": "x", "payload": {"keywords": [{"text": "a", "match_type": "NEGATIVE"}]}}
        )
    with pytest.raises(ValueError, match="non-empty text"):
        google_ads_exec._normalized_keywords(
            {"op_type": "x", "payload": {"keywords": [{"text": "  ", "match_type": "EXACT"}]}}
        )


def test_missing_target_field_raises():
    with pytest.raises(ValueError, match="target.customer_id"):
        google_ads_exec._require({"op_type": "google_ads.pause_campaign", "target": {}}, "target", "customer_id")


def test_missing_credentials_raise_before_any_network():
    with pytest.raises(ValueError, match="developer_token"):
        google_ads_exec._client({"refresh_token": "rt", "client_id": "c", "client_secret": "s"})
    with pytest.raises(ValueError, match="refresh_token"):
        ga4_exec._admin_service({"client_id": "c", "client_secret": "s", "refresh_token": ""})


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------

def test_execution_routes_registered():
    os.environ.setdefault("DUCT_API_KEY", "test-duct-api-key")
    os.environ.pop("DATABASE_URL", None)
    import config

    config.get_configs.cache_clear()
    import server

    server = importlib.reload(server)
    paths = {r.path for r in api_routes(server.app) if r.path.startswith("/api/execute")}
    expected = {
        "/api/execute",
        "/api/execute/ops",
        "/api/execute/guardrails",
        "/api/execute/guardrails/{guardrail_id}",
        "/api/execute/{change_set_id}",
        "/api/execute/{change_set_id}/approve",
        "/api/execute/{change_set_id}/reject",
        "/api/execute/{change_set_id}/apply",
        "/api/execute/{change_set_id}/rollback",
    }
    assert expected <= paths
