"""Google Ads executors — negative keywords + campaign pause.

Both are approval-gated writes via the official SDK. Credentials arrive
per-request (BYO developer token + OAuth refresh token); nothing here reads
env. Rollback handles are returned from ``apply`` so the framework can revert:
created criteria are removed, a paused campaign is restored to its snapshotted
prior status.
"""

from __future__ import annotations

from typing import Any

from service.execution.registry import ExecutorSpec, register_executor
from service.google.fetch import _build_client, _norm_customer_id, _run_query

_MATCH_TYPES = {"BROAD", "PHRASE", "EXACT"}


def _client(creds: dict[str, Any]):
    for key in ("developer_token", "client_id", "client_secret", "refresh_token"):
        if not (creds.get(key) or "").strip():
            raise ValueError(f"Missing Google Ads credential: {key}")
    return _build_client(
        developer_token=creds["developer_token"],
        client_id=creds["client_id"],
        client_secret=creds["client_secret"],
        refresh_token=creds["refresh_token"],
        login_customer_id=creds.get("login_customer_id", ""),
    )


def _require(change: dict, section: str, key: str) -> Any:
    value = (change.get(section) or {}).get(key)
    if value in (None, ""):
        raise ValueError(f"change.{section}.{key} is required for {change.get('op_type')}")
    return value


# ---------------------------------------------------------------------------
# google_ads.add_negative_keywords
# ---------------------------------------------------------------------------

def _normalized_keywords(change: dict) -> list[dict[str, str]]:
    raw = _require(change, "payload", "keywords")
    if not isinstance(raw, list) or not raw:
        raise ValueError("payload.keywords must be a non-empty list")
    keywords: list[dict[str, str]] = []
    for item in raw:
        text = (item.get("text") or "").strip() if isinstance(item, dict) else ""
        match_type = (item.get("match_type") or "PHRASE").upper() if isinstance(item, dict) else ""
        if not text:
            raise ValueError("Every negative keyword needs non-empty text")
        if match_type not in _MATCH_TYPES:
            raise ValueError(f"match_type must be one of {sorted(_MATCH_TYPES)}, got {match_type!r}")
        keywords.append({"text": text, "match_type": match_type})
    return keywords


def _negatives_preview(change: dict, creds: dict) -> dict:
    customer_id = _norm_customer_id(str(_require(change, "target", "customer_id")))
    campaign_id = str(_require(change, "target", "campaign_id"))
    keywords = _normalized_keywords(change)

    client = _client(creds)
    rows = _run_query(
        client,
        customer_id,
        "SELECT campaign_criterion.keyword.text, campaign_criterion.keyword.match_type "
        "FROM campaign_criterion "
        f"WHERE campaign_criterion.campaign = 'customers/{customer_id}/campaigns/{campaign_id}' "
        "AND campaign_criterion.negative = TRUE "
        "AND campaign_criterion.type = KEYWORD",
    )
    existing = {row.campaign_criterion.keyword.text.lower() for row in rows}
    duplicates = [k["text"] for k in keywords if k["text"].lower() in existing]
    return {
        "current": {"existing_negative_count": len(existing)},
        "diff": (
            f"Add {len(keywords)} negative keyword(s) to campaign {campaign_id}: "
            + ", ".join(f"[{k['match_type']}] {k['text']}" for k in keywords)
        ),
        "warnings": ([f"Already negative on this campaign: {', '.join(duplicates)}"] if duplicates else []),
        "mutate_payload": {"operations": [{"create": {"negative": True, "keyword": k}} for k in keywords]},
    }


def _negatives_apply(change: dict, creds: dict) -> dict:
    customer_id = _norm_customer_id(str(_require(change, "target", "customer_id")))
    campaign_id = str(_require(change, "target", "campaign_id"))
    keywords = _normalized_keywords(change)

    client = _client(creds)
    service = client.get_service("CampaignCriterionService")
    campaign_path = client.get_service("CampaignService").campaign_path(customer_id, campaign_id)

    operations = []
    for keyword in keywords:
        op = client.get_type("CampaignCriterionOperation")
        criterion = op.create
        criterion.campaign = campaign_path
        criterion.negative = True
        criterion.keyword.text = keyword["text"]
        criterion.keyword.match_type = client.enums.KeywordMatchTypeEnum[keyword["match_type"]]
        operations.append(op)

    try:
        response = service.mutate_campaign_criteria(customer_id=customer_id, operations=operations)
    except Exception as exc:  # GoogleAdsException and transport errors alike
        raise RuntimeError(f"Google Ads mutate failed: {exc}") from exc

    resource_names = [result.resource_name for result in response.results]
    return {
        "created": resource_names,
        "rollback": {"remove_criteria": resource_names},
    }


def _negatives_rollback(change: dict, creds: dict) -> dict:
    customer_id = _norm_customer_id(str(_require(change, "target", "customer_id")))
    resource_names = ((change.get("result") or {}).get("rollback") or {}).get("remove_criteria") or []
    if not resource_names:
        raise ValueError("No rollback handle recorded for this change")

    client = _client(creds)
    service = client.get_service("CampaignCriterionService")
    operations = []
    for name in resource_names:
        op = client.get_type("CampaignCriterionOperation")
        op.remove = name
        operations.append(op)
    try:
        service.mutate_campaign_criteria(customer_id=customer_id, operations=operations)
    except Exception as exc:
        raise RuntimeError(f"Google Ads rollback failed: {exc}") from exc
    return {"removed": resource_names}


# ---------------------------------------------------------------------------
# google_ads.pause_campaign
# ---------------------------------------------------------------------------

def _campaign_status(client, customer_id: str, campaign_id: str) -> str:
    rows = _run_query(
        client,
        customer_id,
        "SELECT campaign.id, campaign.name, campaign.status FROM campaign "
        f"WHERE campaign.id = {campaign_id}",
    )
    if not rows:
        raise ValueError(f"Campaign {campaign_id} not found on customer {customer_id}")
    return rows[0].campaign.status.name


def _set_campaign_status(client, customer_id: str, campaign_id: str, status: str) -> str:
    from google.api_core import protobuf_helpers

    service = client.get_service("CampaignService")
    op = client.get_type("CampaignOperation")
    campaign = op.update
    campaign.resource_name = service.campaign_path(customer_id, campaign_id)
    campaign.status = client.enums.CampaignStatusEnum[status]
    client.copy_from(op.update_mask, protobuf_helpers.field_mask(None, campaign._pb))
    try:
        response = service.mutate_campaigns(customer_id=customer_id, operations=[op])
    except Exception as exc:
        raise RuntimeError(f"Google Ads mutate failed: {exc}") from exc
    return response.results[0].resource_name


def _pause_preview(change: dict, creds: dict) -> dict:
    customer_id = _norm_customer_id(str(_require(change, "target", "customer_id")))
    campaign_id = str(_require(change, "target", "campaign_id"))
    client = _client(creds)
    status = _campaign_status(client, customer_id, campaign_id)
    warnings = []
    if status == "PAUSED":
        warnings.append("Campaign is already paused — applying is a no-op.")
    if status == "REMOVED":
        warnings.append("Campaign is REMOVED and cannot be paused.")
    return {
        "current": {"status": status},
        "diff": f"Campaign {campaign_id}: {status} → PAUSED",
        "warnings": warnings,
        "mutate_payload": {"update": {"status": "PAUSED"}, "update_mask": "status"},
    }


def _pause_apply(change: dict, creds: dict) -> dict:
    customer_id = _norm_customer_id(str(_require(change, "target", "customer_id")))
    campaign_id = str(_require(change, "target", "campaign_id"))
    client = _client(creds)
    previous = (change.get("current") or {}).get("status") or _campaign_status(
        client, customer_id, campaign_id
    )
    if previous == "REMOVED":
        raise ValueError("Campaign is REMOVED and cannot be paused.")
    resource_name = _set_campaign_status(client, customer_id, campaign_id, "PAUSED")
    return {
        "resource_name": resource_name,
        "rollback": {"restore_status": previous},
    }


def _pause_rollback(change: dict, creds: dict) -> dict:
    customer_id = _norm_customer_id(str(_require(change, "target", "customer_id")))
    campaign_id = str(_require(change, "target", "campaign_id"))
    previous = ((change.get("result") or {}).get("rollback") or {}).get("restore_status")
    if not previous:
        raise ValueError("No rollback handle recorded for this change")
    if previous == "PAUSED":
        return {"restored": "PAUSED", "note": "Campaign was already paused before the change."}
    client = _client(creds)
    resource_name = _set_campaign_status(client, customer_id, campaign_id, previous)
    return {"restored": previous, "resource_name": resource_name}


register_executor(
    ExecutorSpec(
        op_type="google_ads.add_negative_keywords",
        connector_type="google_ads",
        label="Add negative keywords",
        preview=_negatives_preview,
        apply=_negatives_apply,
        rollback=_negatives_rollback,
    )
)

register_executor(
    ExecutorSpec(
        op_type="google_ads.pause_campaign",
        connector_type="google_ads",
        label="Pause campaign",
        preview=_pause_preview,
        apply=_pause_apply,
        rollback=_pause_rollback,
    )
)
