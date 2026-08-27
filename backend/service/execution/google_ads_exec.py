"""Google Ads executors — keywords, statuses, budget, and bidding.

All are staged writes via the official SDK. Credentials arrive per-request
(BYO developer token + OAuth refresh token); nothing here reads env. Every
``apply`` returns a rollback handle so the framework can revert: created
criteria are removed, status/budget/bidding changes restore their snapshotted
prior values.

Safety invariants (Gads corpus):
- Status changes accept only ENABLED|PAUSED — ``REMOVED`` is irreversible in
  Google Ads and is rejected at validation time, never sent.
- Budget previews surface *shared* budgets: mutating one changes spend for
  every campaign attached to it.
- Bidding changes refuse campaigns on portfolio bidding strategies — switching
  them to a campaign-local scheme cannot be rolled back from here.
"""

from __future__ import annotations

from typing import Any

from service.execution.registry import ExecutorSpec, register_executor
from service.google.fetch import _build_client, _norm_customer_id, _run_query

_MATCH_TYPES = {"BROAD", "PHRASE", "EXACT"}
# REMOVED is deliberately absent: removal is irreversible in Google Ads.
_SETTABLE_STATUSES = {"ENABLED", "PAUSED"}


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


# ---------------------------------------------------------------------------
# Shared status helpers — google_ads.set_{campaign,ad_group,keyword}_status
# ---------------------------------------------------------------------------

def _wanted_status(change: dict) -> str:
    status = str(_require(change, "payload", "status")).upper()
    if status == "REMOVED":
        raise ValueError("REMOVED is irreversible in Google Ads and cannot be set here.")
    if status not in _SETTABLE_STATUSES:
        raise ValueError(f"payload.status must be one of {sorted(_SETTABLE_STATUSES)}, got {status!r}")
    return status


def _status_preview(entity: str, entity_id: str, name: str, current: str, wanted: str) -> dict:
    warnings = []
    if current == wanted:
        warnings.append(f"{entity} is already {wanted} — applying is a no-op.")
    if current == "REMOVED":
        warnings.append(f"{entity} is REMOVED; its status cannot be changed.")
    return {
        "current": {"status": current, "name": name},
        "diff": f"{entity} {entity_id} ({name}): {current} → {wanted}",
        "warnings": warnings,
        "mutate_payload": {"update": {"status": wanted}, "update_mask": "status"},
    }


def _guard_removed(previous: str, entity: str) -> None:
    if previous == "REMOVED":
        raise ValueError(f"{entity} is REMOVED; its status cannot be changed.")


# ---------------------------------------------------------------------------
# google_ads.set_campaign_status — generalizes pause_campaign (ENABLED|PAUSED)
# ---------------------------------------------------------------------------

def _campaign_status_preview(change: dict, creds: dict) -> dict:
    customer_id = _norm_customer_id(str(_require(change, "target", "customer_id")))
    campaign_id = str(_require(change, "target", "campaign_id"))
    wanted = _wanted_status(change)
    client = _client(creds)
    rows = _run_query(
        client,
        customer_id,
        "SELECT campaign.id, campaign.name, campaign.status FROM campaign "
        f"WHERE campaign.id = {campaign_id}",
    )
    if not rows:
        raise ValueError(f"Campaign {campaign_id} not found on customer {customer_id}")
    return _status_preview(
        "Campaign", campaign_id, rows[0].campaign.name, rows[0].campaign.status.name, wanted
    )


def _campaign_status_apply(change: dict, creds: dict) -> dict:
    customer_id = _norm_customer_id(str(_require(change, "target", "customer_id")))
    campaign_id = str(_require(change, "target", "campaign_id"))
    wanted = _wanted_status(change)
    client = _client(creds)
    previous = (change.get("current") or {}).get("status") or _campaign_status(
        client, customer_id, campaign_id
    )
    _guard_removed(previous, "Campaign")
    resource_name = _set_campaign_status(client, customer_id, campaign_id, wanted)
    return {"resource_name": resource_name, "rollback": {"restore_status": previous}}


def _campaign_status_rollback(change: dict, creds: dict) -> dict:
    customer_id = _norm_customer_id(str(_require(change, "target", "customer_id")))
    campaign_id = str(_require(change, "target", "campaign_id"))
    previous = ((change.get("result") or {}).get("rollback") or {}).get("restore_status")
    if not previous:
        raise ValueError("No rollback handle recorded for this change")
    client = _client(creds)
    resource_name = _set_campaign_status(client, customer_id, campaign_id, previous)
    return {"restored": previous, "resource_name": resource_name}


# ---------------------------------------------------------------------------
# google_ads.set_ad_group_status
# ---------------------------------------------------------------------------

def _ad_group_status(client, customer_id: str, ad_group_id: str) -> tuple[str, str]:
    rows = _run_query(
        client,
        customer_id,
        "SELECT ad_group.id, ad_group.name, ad_group.status FROM ad_group "
        f"WHERE ad_group.id = {ad_group_id}",
    )
    if not rows:
        raise ValueError(f"Ad group {ad_group_id} not found on customer {customer_id}")
    return rows[0].ad_group.status.name, rows[0].ad_group.name


def _set_ad_group_status(client, customer_id: str, ad_group_id: str, status: str) -> str:
    from google.api_core import protobuf_helpers

    service = client.get_service("AdGroupService")
    op = client.get_type("AdGroupOperation")
    ad_group = op.update
    ad_group.resource_name = service.ad_group_path(customer_id, ad_group_id)
    ad_group.status = client.enums.AdGroupStatusEnum[status]
    client.copy_from(op.update_mask, protobuf_helpers.field_mask(None, ad_group._pb))
    try:
        response = service.mutate_ad_groups(customer_id=customer_id, operations=[op])
    except Exception as exc:
        raise RuntimeError(f"Google Ads mutate failed: {exc}") from exc
    return response.results[0].resource_name


def _ad_group_status_preview(change: dict, creds: dict) -> dict:
    customer_id = _norm_customer_id(str(_require(change, "target", "customer_id")))
    ad_group_id = str(_require(change, "target", "ad_group_id"))
    wanted = _wanted_status(change)
    status, name = _ad_group_status(_client(creds), customer_id, ad_group_id)
    return _status_preview("Ad group", ad_group_id, name, status, wanted)


def _ad_group_status_apply(change: dict, creds: dict) -> dict:
    customer_id = _norm_customer_id(str(_require(change, "target", "customer_id")))
    ad_group_id = str(_require(change, "target", "ad_group_id"))
    wanted = _wanted_status(change)
    client = _client(creds)
    previous = (change.get("current") or {}).get("status") or _ad_group_status(
        client, customer_id, ad_group_id
    )[0]
    _guard_removed(previous, "Ad group")
    resource_name = _set_ad_group_status(client, customer_id, ad_group_id, wanted)
    return {"resource_name": resource_name, "rollback": {"restore_status": previous}}


def _ad_group_status_rollback(change: dict, creds: dict) -> dict:
    customer_id = _norm_customer_id(str(_require(change, "target", "customer_id")))
    ad_group_id = str(_require(change, "target", "ad_group_id"))
    previous = ((change.get("result") or {}).get("rollback") or {}).get("restore_status")
    if not previous:
        raise ValueError("No rollback handle recorded for this change")
    client = _client(creds)
    resource_name = _set_ad_group_status(client, customer_id, ad_group_id, previous)
    return {"restored": previous, "resource_name": resource_name}


# ---------------------------------------------------------------------------
# google_ads.set_keyword_status — ad-group keyword criterion ENABLED|PAUSED
# ---------------------------------------------------------------------------

def _keyword_row(client, customer_id: str, ad_group_id: str, criterion_id: str):
    rows = _run_query(
        client,
        customer_id,
        "SELECT ad_group_criterion.criterion_id, ad_group_criterion.status, "
        "ad_group_criterion.keyword.text, ad_group_criterion.keyword.match_type "
        "FROM ad_group_criterion "
        f"WHERE ad_group.id = {ad_group_id} "
        f"AND ad_group_criterion.criterion_id = {criterion_id}",
    )
    if not rows:
        raise ValueError(
            f"Keyword criterion {criterion_id} not found in ad group {ad_group_id} "
            f"on customer {customer_id}"
        )
    return rows[0].ad_group_criterion


def _set_keyword_status(
    client, customer_id: str, ad_group_id: str, criterion_id: str, status: str
) -> str:
    from google.api_core import protobuf_helpers

    service = client.get_service("AdGroupCriterionService")
    op = client.get_type("AdGroupCriterionOperation")
    criterion = op.update
    criterion.resource_name = service.ad_group_criterion_path(
        customer_id, ad_group_id, criterion_id
    )
    criterion.status = client.enums.AdGroupCriterionStatusEnum[status]
    client.copy_from(op.update_mask, protobuf_helpers.field_mask(None, criterion._pb))
    try:
        response = service.mutate_ad_group_criteria(customer_id=customer_id, operations=[op])
    except Exception as exc:
        raise RuntimeError(f"Google Ads mutate failed: {exc}") from exc
    return response.results[0].resource_name


def _keyword_status_preview(change: dict, creds: dict) -> dict:
    customer_id = _norm_customer_id(str(_require(change, "target", "customer_id")))
    ad_group_id = str(_require(change, "target", "ad_group_id"))
    criterion_id = str(_require(change, "target", "criterion_id"))
    wanted = _wanted_status(change)
    row = _keyword_row(_client(creds), customer_id, ad_group_id, criterion_id)
    label = f"[{row.keyword.match_type.name}] {row.keyword.text}"
    return _status_preview("Keyword", criterion_id, label, row.status.name, wanted)


def _keyword_status_apply(change: dict, creds: dict) -> dict:
    customer_id = _norm_customer_id(str(_require(change, "target", "customer_id")))
    ad_group_id = str(_require(change, "target", "ad_group_id"))
    criterion_id = str(_require(change, "target", "criterion_id"))
    wanted = _wanted_status(change)
    client = _client(creds)
    previous = (change.get("current") or {}).get("status") or _keyword_row(
        client, customer_id, ad_group_id, criterion_id
    ).status.name
    _guard_removed(previous, "Keyword")
    resource_name = _set_keyword_status(client, customer_id, ad_group_id, criterion_id, wanted)
    return {"resource_name": resource_name, "rollback": {"restore_status": previous}}


def _keyword_status_rollback(change: dict, creds: dict) -> dict:
    customer_id = _norm_customer_id(str(_require(change, "target", "customer_id")))
    ad_group_id = str(_require(change, "target", "ad_group_id"))
    criterion_id = str(_require(change, "target", "criterion_id"))
    previous = ((change.get("result") or {}).get("rollback") or {}).get("restore_status")
    if not previous:
        raise ValueError("No rollback handle recorded for this change")
    client = _client(creds)
    resource_name = _set_keyword_status(client, customer_id, ad_group_id, criterion_id, previous)
    return {"restored": previous, "resource_name": resource_name}


# ---------------------------------------------------------------------------
# google_ads.add_keywords — positive ad-group keywords
# ---------------------------------------------------------------------------

def _positive_keywords(change: dict) -> list[dict[str, Any]]:
    raw = _require(change, "payload", "keywords")
    if not isinstance(raw, list) or not raw:
        raise ValueError("payload.keywords must be a non-empty list")
    keywords: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("Each keyword must be an object with text/match_type")
        text = (item.get("text") or "").strip()
        match_type = (item.get("match_type") or "PHRASE").upper()
        if not text:
            raise ValueError("Every keyword needs non-empty text")
        if match_type not in _MATCH_TYPES:
            raise ValueError(f"match_type must be one of {sorted(_MATCH_TYPES)}, got {match_type!r}")
        entry: dict[str, Any] = {"text": text, "match_type": match_type}
        if item.get("cpc_bid") not in (None, ""):
            micros = round(float(item["cpc_bid"]) * 1_000_000)
            if micros <= 0:
                raise ValueError("cpc_bid must be positive")
            entry["cpc_bid_micros"] = micros
        keywords.append(entry)
    return keywords


def _add_keywords_preview(change: dict, creds: dict) -> dict:
    customer_id = _norm_customer_id(str(_require(change, "target", "customer_id")))
    ad_group_id = str(_require(change, "target", "ad_group_id"))
    keywords = _positive_keywords(change)

    client = _client(creds)
    rows = _run_query(
        client,
        customer_id,
        "SELECT ad_group_criterion.keyword.text, ad_group_criterion.keyword.match_type "
        "FROM ad_group_criterion "
        f"WHERE ad_group.id = {ad_group_id} "
        "AND ad_group_criterion.type = KEYWORD "
        "AND ad_group_criterion.negative = FALSE",
    )
    existing = {row.ad_group_criterion.keyword.text.lower() for row in rows}
    duplicates = [k["text"] for k in keywords if k["text"].lower() in existing]
    return {
        "current": {"existing_keyword_count": len(existing)},
        "diff": (
            f"Add {len(keywords)} keyword(s) to ad group {ad_group_id}: "
            + ", ".join(f"[{k['match_type']}] {k['text']}" for k in keywords)
        ),
        "warnings": ([f"Already in this ad group: {', '.join(duplicates)}"] if duplicates else []),
        "mutate_payload": {"operations": [{"create": {"keyword": k}} for k in keywords]},
    }


def _add_keywords_apply(change: dict, creds: dict) -> dict:
    customer_id = _norm_customer_id(str(_require(change, "target", "customer_id")))
    ad_group_id = str(_require(change, "target", "ad_group_id"))
    keywords = _positive_keywords(change)

    client = _client(creds)
    service = client.get_service("AdGroupCriterionService")
    ad_group_path = client.get_service("AdGroupService").ad_group_path(customer_id, ad_group_id)

    operations = []
    for keyword in keywords:
        op = client.get_type("AdGroupCriterionOperation")
        criterion = op.create
        criterion.ad_group = ad_group_path
        criterion.status = client.enums.AdGroupCriterionStatusEnum.ENABLED
        criterion.keyword.text = keyword["text"]
        criterion.keyword.match_type = client.enums.KeywordMatchTypeEnum[keyword["match_type"]]
        if keyword.get("cpc_bid_micros"):
            criterion.cpc_bid_micros = keyword["cpc_bid_micros"]
        operations.append(op)

    try:
        response = service.mutate_ad_group_criteria(customer_id=customer_id, operations=operations)
    except Exception as exc:
        raise RuntimeError(f"Google Ads mutate failed: {exc}") from exc

    resource_names = [result.resource_name for result in response.results]
    return {"created": resource_names, "rollback": {"remove_criteria": resource_names}}


def _add_keywords_rollback(change: dict, creds: dict) -> dict:
    customer_id = _norm_customer_id(str(_require(change, "target", "customer_id")))
    resource_names = ((change.get("result") or {}).get("rollback") or {}).get("remove_criteria") or []
    if not resource_names:
        raise ValueError("No rollback handle recorded for this change")

    client = _client(creds)
    service = client.get_service("AdGroupCriterionService")
    operations = []
    for name in resource_names:
        op = client.get_type("AdGroupCriterionOperation")
        op.remove = name
        operations.append(op)
    try:
        service.mutate_ad_group_criteria(customer_id=customer_id, operations=operations)
    except Exception as exc:
        raise RuntimeError(f"Google Ads rollback failed: {exc}") from exc
    return {"removed": resource_names}


# ---------------------------------------------------------------------------
# google_ads.set_campaign_budget — shared-budget aware daily budget change
# ---------------------------------------------------------------------------

def _budget_micros(change: dict) -> int:
    payload = change.get("payload") or {}
    if payload.get("amount_micros") not in (None, ""):
        micros = int(payload["amount_micros"])
    elif payload.get("daily_budget") not in (None, ""):
        micros = round(float(payload["daily_budget"]) * 1_000_000)
    else:
        raise ValueError("payload.daily_budget (currency units) or payload.amount_micros is required")
    if micros <= 0:
        raise ValueError("Budget must be positive")
    return micros


def _campaign_budget_row(client, customer_id: str, campaign_id: str):
    rows = _run_query(
        client,
        customer_id,
        "SELECT campaign.id, campaign.name, campaign.campaign_budget, "
        "campaign_budget.id, campaign_budget.amount_micros, "
        "campaign_budget.explicitly_shared, campaign_budget.reference_count "
        f"FROM campaign WHERE campaign.id = {campaign_id}",
    )
    if not rows:
        raise ValueError(f"Campaign {campaign_id} not found on customer {customer_id}")
    return rows[0]


def _set_budget_amount(client, customer_id: str, budget_resource: str, micros: int) -> str:
    from google.api_core import protobuf_helpers

    service = client.get_service("CampaignBudgetService")
    op = client.get_type("CampaignBudgetOperation")
    budget = op.update
    budget.resource_name = budget_resource
    budget.amount_micros = micros
    client.copy_from(op.update_mask, protobuf_helpers.field_mask(None, budget._pb))
    try:
        response = service.mutate_campaign_budgets(customer_id=customer_id, operations=[op])
    except Exception as exc:
        raise RuntimeError(f"Google Ads mutate failed: {exc}") from exc
    return response.results[0].resource_name


def _budget_preview(change: dict, creds: dict) -> dict:
    customer_id = _norm_customer_id(str(_require(change, "target", "customer_id")))
    campaign_id = str(_require(change, "target", "campaign_id"))
    micros = _budget_micros(change)

    row = _campaign_budget_row(_client(creds), customer_id, campaign_id)
    budget = row.campaign_budget
    current_micros = int(budget.amount_micros)
    shared = bool(budget.explicitly_shared) or int(budget.reference_count or 0) > 1
    warnings = []
    if shared:
        warnings.append(
            f"This is a SHARED budget (used by {int(budget.reference_count or 0)} campaigns) — "
            "changing it changes spend for every campaign attached to it."
        )
    if current_micros == micros:
        warnings.append("Budget already at the requested amount — applying is a no-op.")
    return {
        "current": {
            "amount_micros": current_micros,
            "daily_budget": current_micros / 1_000_000,
            "budget_resource": row.campaign.campaign_budget,
            "explicitly_shared": bool(budget.explicitly_shared),
            "reference_count": int(budget.reference_count or 0),
        },
        "diff": (
            f"Campaign {campaign_id} ({row.campaign.name}) daily budget: "
            f"{current_micros / 1_000_000:g} → {micros / 1_000_000:g}"
        ),
        "warnings": warnings,
        "mutate_payload": {"update": {"amount_micros": micros}, "update_mask": "amount_micros"},
    }


def _budget_apply(change: dict, creds: dict) -> dict:
    customer_id = _norm_customer_id(str(_require(change, "target", "customer_id")))
    campaign_id = str(_require(change, "target", "campaign_id"))
    micros = _budget_micros(change)

    client = _client(creds)
    current = change.get("current") or {}
    budget_resource = current.get("budget_resource")
    prior_micros = current.get("amount_micros")
    if not budget_resource or prior_micros in (None, ""):
        row = _campaign_budget_row(client, customer_id, campaign_id)
        budget_resource = row.campaign.campaign_budget
        prior_micros = int(row.campaign_budget.amount_micros)

    resource_name = _set_budget_amount(client, customer_id, budget_resource, micros)
    return {
        "resource_name": resource_name,
        "rollback": {"budget_resource": budget_resource, "restore_amount_micros": int(prior_micros)},
    }


def _budget_rollback(change: dict, creds: dict) -> dict:
    customer_id = _norm_customer_id(str(_require(change, "target", "customer_id")))
    handle = (change.get("result") or {}).get("rollback") or {}
    budget_resource = handle.get("budget_resource")
    prior_micros = handle.get("restore_amount_micros")
    if not budget_resource or prior_micros in (None, ""):
        raise ValueError("No rollback handle recorded for this change")
    client = _client(creds)
    resource_name = _set_budget_amount(client, customer_id, budget_resource, int(prior_micros))
    return {"restored_amount_micros": int(prior_micros), "resource_name": resource_name}


# ---------------------------------------------------------------------------
# google_ads.set_campaign_bidding — tCPA / tROAS via the modern schemes
# ---------------------------------------------------------------------------

_BIDDING_STRATEGIES = {"MAXIMIZE_CONVERSIONS", "MAXIMIZE_CONVERSION_VALUE"}


def _bidding_inputs(change: dict) -> tuple[str, int, float]:
    payload = change.get("payload") or {}
    strategy = str(payload.get("strategy") or "").upper()
    if strategy not in _BIDDING_STRATEGIES:
        raise ValueError(
            f"payload.strategy must be one of {sorted(_BIDDING_STRATEGIES)} "
            "(tCPA rides on MAXIMIZE_CONVERSIONS, tROAS on MAXIMIZE_CONVERSION_VALUE)"
        )
    target_cpa_micros = 0
    if payload.get("target_cpa") not in (None, ""):
        target_cpa_micros = round(float(payload["target_cpa"]) * 1_000_000)
        if target_cpa_micros <= 0:
            raise ValueError("target_cpa must be positive")
    target_roas = 0.0
    if payload.get("target_roas") not in (None, ""):
        target_roas = float(payload["target_roas"])
        if target_roas <= 0:
            raise ValueError("target_roas must be positive")
    return strategy, target_cpa_micros, target_roas


def _bidding_snapshot(client, customer_id: str, campaign_id: str) -> dict[str, Any]:
    rows = _run_query(
        client,
        customer_id,
        "SELECT campaign.id, campaign.name, campaign.bidding_strategy_type, "
        "campaign.bidding_strategy, "
        "campaign.maximize_conversions.target_cpa_micros, "
        "campaign.maximize_conversion_value.target_roas "
        f"FROM campaign WHERE campaign.id = {campaign_id}",
    )
    if not rows:
        raise ValueError(f"Campaign {campaign_id} not found on customer {customer_id}")
    campaign = rows[0].campaign
    return {
        "name": campaign.name,
        "strategy_type": campaign.bidding_strategy_type.name,
        "portfolio_strategy": campaign.bidding_strategy or "",
        "target_cpa_micros": int(campaign.maximize_conversions.target_cpa_micros or 0),
        "target_roas": float(campaign.maximize_conversion_value.target_roas or 0.0),
    }


def _set_campaign_bidding(
    client, customer_id: str, campaign_id: str, strategy: str,
    target_cpa_micros: int, target_roas: float,
) -> str:
    from google.protobuf import field_mask_pb2

    service = client.get_service("CampaignService")
    op = client.get_type("CampaignOperation")
    campaign = op.update
    campaign.resource_name = service.campaign_path(customer_id, campaign_id)
    if strategy == "MAXIMIZE_CONVERSIONS":
        campaign.maximize_conversions.target_cpa_micros = target_cpa_micros
        paths = ["maximize_conversions.target_cpa_micros"] if target_cpa_micros else ["maximize_conversions"]
    else:
        campaign.maximize_conversion_value.target_roas = target_roas
        paths = ["maximize_conversion_value.target_roas"] if target_roas else ["maximize_conversion_value"]
    # Explicit mask: zero-valued targets are proto3 defaults, so an inferred
    # mask would come back empty and the oneof would never switch.
    client.copy_from(op.update_mask, field_mask_pb2.FieldMask(paths=paths))
    try:
        response = service.mutate_campaigns(customer_id=customer_id, operations=[op])
    except Exception as exc:
        raise RuntimeError(f"Google Ads mutate failed: {exc}") from exc
    return response.results[0].resource_name


def _describe_bidding(strategy_type: str, target_cpa_micros: int, target_roas: float) -> str:
    if strategy_type == "MAXIMIZE_CONVERSIONS":
        return (
            f"MAXIMIZE_CONVERSIONS (tCPA {target_cpa_micros / 1_000_000:g})"
            if target_cpa_micros else "MAXIMIZE_CONVERSIONS"
        )
    if strategy_type == "MAXIMIZE_CONVERSION_VALUE":
        return (
            f"MAXIMIZE_CONVERSION_VALUE (tROAS {target_roas:g})"
            if target_roas else "MAXIMIZE_CONVERSION_VALUE"
        )
    return strategy_type


def _bidding_preview(change: dict, creds: dict) -> dict:
    customer_id = _norm_customer_id(str(_require(change, "target", "customer_id")))
    campaign_id = str(_require(change, "target", "campaign_id"))
    strategy, target_cpa_micros, target_roas = _bidding_inputs(change)

    snapshot = _bidding_snapshot(_client(creds), customer_id, campaign_id)
    warnings = []
    if snapshot["portfolio_strategy"]:
        warnings.append(
            "Campaign uses a PORTFOLIO bidding strategy "
            f"({snapshot['portfolio_strategy']}) — switching it to a campaign-local "
            "scheme cannot be rolled back from here. Applying will be refused."
        )
    return {
        "current": snapshot,
        "diff": (
            f"Campaign {campaign_id} ({snapshot['name']}) bidding: "
            f"{_describe_bidding(snapshot['strategy_type'], snapshot['target_cpa_micros'], snapshot['target_roas'])}"
            f" → {_describe_bidding(strategy, target_cpa_micros, target_roas)}"
        ),
        "warnings": warnings,
        "mutate_payload": {
            "strategy": strategy,
            "target_cpa_micros": target_cpa_micros,
            "target_roas": target_roas,
        },
    }


def _bidding_apply(change: dict, creds: dict) -> dict:
    customer_id = _norm_customer_id(str(_require(change, "target", "customer_id")))
    campaign_id = str(_require(change, "target", "campaign_id"))
    strategy, target_cpa_micros, target_roas = _bidding_inputs(change)

    client = _client(creds)
    snapshot = change.get("current") or {}
    if not snapshot.get("strategy_type"):
        snapshot = _bidding_snapshot(client, customer_id, campaign_id)
    if snapshot.get("portfolio_strategy"):
        raise ValueError(
            "Campaign uses a portfolio bidding strategy — changing it here cannot "
            "be rolled back. Detach it from the portfolio strategy in Google Ads first."
        )
    resource_name = _set_campaign_bidding(
        client, customer_id, campaign_id, strategy, target_cpa_micros, target_roas
    )
    return {
        "resource_name": resource_name,
        "rollback": {
            "restore_strategy_type": snapshot.get("strategy_type", ""),
            "restore_target_cpa_micros": int(snapshot.get("target_cpa_micros") or 0),
            "restore_target_roas": float(snapshot.get("target_roas") or 0.0),
        },
    }


def _bidding_rollback(change: dict, creds: dict) -> dict:
    customer_id = _norm_customer_id(str(_require(change, "target", "customer_id")))
    campaign_id = str(_require(change, "target", "campaign_id"))
    handle = ((change.get("result") or {}).get("rollback")) or {}
    strategy = handle.get("restore_strategy_type") or ""
    if not strategy:
        raise ValueError("No rollback handle recorded for this change")
    if strategy not in _BIDDING_STRATEGIES:
        raise ValueError(
            f"Prior bidding scheme {strategy!r} cannot be restored from here — "
            "restore it manually in Google Ads."
        )
    client = _client(creds)
    resource_name = _set_campaign_bidding(
        client,
        customer_id,
        campaign_id,
        strategy,
        int(handle.get("restore_target_cpa_micros") or 0),
        float(handle.get("restore_target_roas") or 0.0),
    )
    return {"restored": strategy, "resource_name": resource_name}


register_executor(
    ExecutorSpec(
        op_type="google_ads.set_campaign_status",
        connector_type="google_ads",
        label="Set campaign status",
        preview=_campaign_status_preview,
        apply=_campaign_status_apply,
        rollback=_campaign_status_rollback,
    )
)

register_executor(
    ExecutorSpec(
        op_type="google_ads.set_ad_group_status",
        connector_type="google_ads",
        label="Set ad group status",
        preview=_ad_group_status_preview,
        apply=_ad_group_status_apply,
        rollback=_ad_group_status_rollback,
    )
)

register_executor(
    ExecutorSpec(
        op_type="google_ads.set_keyword_status",
        connector_type="google_ads",
        label="Set keyword status",
        preview=_keyword_status_preview,
        apply=_keyword_status_apply,
        rollback=_keyword_status_rollback,
    )
)

register_executor(
    ExecutorSpec(
        op_type="google_ads.add_keywords",
        connector_type="google_ads",
        label="Add keywords",
        preview=_add_keywords_preview,
        apply=_add_keywords_apply,
        rollback=_add_keywords_rollback,
    )
)

register_executor(
    ExecutorSpec(
        op_type="google_ads.set_campaign_budget",
        connector_type="google_ads",
        label="Set campaign daily budget",
        preview=_budget_preview,
        apply=_budget_apply,
        rollback=_budget_rollback,
    )
)

register_executor(
    ExecutorSpec(
        op_type="google_ads.set_campaign_bidding",
        connector_type="google_ads",
        label="Set campaign bidding (tCPA/tROAS)",
        preview=_bidding_preview,
        apply=_bidding_apply,
        rollback=_bidding_rollback,
    )
)
