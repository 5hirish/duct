"""Unit tests for the staged-execution framework (registry, guardrails, routes)."""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models.execution import ExecutionGuardrail  # noqa: E402
from service.execution import ga4_exec, google_ads_exec  # noqa: E402,F401  (registers executors)
from service.execution.guardrails import violations_for  # noqa: E402
from service.execution.registry import (  # noqa: E402
    EXECUTOR_REGISTRY,
    ExecutorSpec,
    get_executor,
    register_executor,
)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def test_builtin_executors_registered_with_rollback():
    expected = {
        "google_ads.add_negative_keywords",
        "google_ads.pause_campaign",
        "ga4.create_key_event",
        "ga4.delete_key_event",
    }
    assert expected <= set(EXECUTOR_REGISTRY)
    for op_type in expected:
        spec = get_executor(op_type)
        assert spec.rollback is not None, f"{op_type} must support rollback"


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


def test_guardrail_blocks_matching_op_type():
    rails = [_guardrail("Never touch campaign 555", {"op_types": ["google_ads.pause_campaign"], "target_contains": "555"})]
    assert violations_for(PAUSE_PMAX, rails) == ["Never touch campaign 555"]


def test_guardrail_target_contains_must_match():
    rails = [_guardrail("Never touch campaign 999", {"op_types": ["google_ads.pause_campaign"], "target_contains": "999"})]
    assert violations_for(PAUSE_PMAX, rails) == []


def test_guardrail_op_type_scoping():
    rails = [_guardrail("No negatives", {"op_types": ["google_ads.add_negative_keywords"]})]
    assert violations_for(PAUSE_PMAX, rails) == []


def test_guardrail_empty_matcher_is_prose_only():
    rails = [_guardrail("Be careful out there", {})]
    assert violations_for(PAUSE_PMAX, rails) == []


def test_guardrail_inactive_skipped():
    rails = [
        _guardrail(
            "Never touch campaign 555",
            {"op_types": ["google_ads.pause_campaign"], "target_contains": "555"},
            active=False,
        )
    ]
    assert violations_for(PAUSE_PMAX, rails) == []


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
    paths = {r.path for r in server.app.routes if r.path.startswith("/api/execute")}
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
