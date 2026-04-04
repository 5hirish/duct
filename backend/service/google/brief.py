"""Normalize Google Ads raw JSON into a typed brief payload (library entrypoint)."""

from __future__ import annotations

import copy
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agents.reporter.goals import ReportGenerationGoal
from agents.reporter.prompts import get_synthesis_user_prompt, get_system_prompt
from agents.reporter.schema import SynthesisSchema as _SynthesisSchema
from service.google.schema import (
    AccountSummary,
    ActionPriority,
    ActionType,
    BriefNarrative,
    CampaignPerformance,
    ConfidenceLevel,
    EvidenceDataSource,
    EvidenceEntityType,
    EvidenceSource,
    Finding,
    FindingType,
    GoogleAdsBrief,
    MetricFormatKind,
    PeriodComparison,
    RecommendedAction,
    SourceMetadata,
)

from service.google.constants import GOOGLE_ADS_CONNECTOR_ID, GOOGLE_ADS_RAW_PAYLOAD_PATH
from service.google.metrics import comparison_metric, metric_value
from utils.formatting import money, safe_divide
_BACKEND_ROOT = Path(__file__).resolve().parents[2]


def demo_raw_payload_path(connector_id: str) -> Path:
    """Path to static demo raw JSON: ``data/<connector_id>/raw/demo_raw_payload.json``."""
    if connector_id == GOOGLE_ADS_CONNECTOR_ID:
        return GOOGLE_ADS_RAW_PAYLOAD_PATH
    return _BACKEND_ROOT / "data" / connector_id / "raw" / "demo_raw_payload.json"


def demo_raw_payload(connector_id: str | None = None) -> dict[str, Any]:
    """Load static demo raw payload for a connector (default: Google Ads)."""
    cid = connector_id or GOOGLE_ADS_CONNECTOR_ID
    path = demo_raw_payload_path(cid)
    with path.open(encoding="utf-8") as handle:
        raw = json.load(handle)
    out = copy.deepcopy(raw)
    out["source_metadata"] = dict(out["source_metadata"])
    out["source_metadata"]["generated_at"] = datetime.now(timezone.utc).isoformat()
    return out


def summarize_rows(rows: list[dict[str, Any]]) -> tuple[dict[str, float], dict[str, float]]:
    current_totals = {
        "spend": 0.0,
        "clicks": 0.0,
        "impressions": 0.0,
        "conversions": 0.0,
        "conversion_value": 0.0,
    }
    previous_totals = {key: 0.0 for key in current_totals}
    for row in rows:
        current_totals["spend"] += row.get("spend", 0.0)
        current_totals["clicks"] += row.get("clicks", 0.0)
        current_totals["impressions"] += row.get("impressions", 0.0)
        current_totals["conversions"] += row.get("conversions", 0.0)
        current_totals["conversion_value"] += row.get("conversion_value", 0.0)
        previous = row.get("previous", {})
        previous_totals["spend"] += previous.get("spend", 0.0)
        previous_totals["clicks"] += previous.get("clicks", 0.0)
        previous_totals["impressions"] += previous.get("impressions", 0.0)
        previous_totals["conversions"] += previous.get("conversions", 0.0)
        previous_totals["conversion_value"] += previous.get("conversion_value", 0.0)
    return current_totals, previous_totals


def classify_action(row: dict[str, Any]) -> tuple[ActionType, str]:
    row_roas = row.get("roas", 0.0)
    cpa = row.get("cost_per_conversion", 0.0)
    ctr = row.get("ctr", 0.0)
    conversions = row.get("conversions", 0.0)
    if row_roas >= 3.0 and conversions >= 10:
        return ActionType.SCALE, "High ROAS with meaningful conversion volume."
    if row_roas < 1.0 and cpa > 200:
        return ActionType.PAUSE, "Low ROAS and expensive conversions are wasting budget."
    if ctr < 0.025 and conversions < 10:
        return ActionType.REFRESH, "Low engagement suggests creative or query fatigue."
    if 1.0 <= row_roas < 2.0:
        return (
            ActionType.REFINE,
            "Returns are weak enough to justify refining audience, queries, or keyword themes.",
        )
    return ActionType.MONITOR, "Performance is serviceable but not strong enough to scale yet."


def build_campaign(row: dict[str, Any]) -> CampaignPerformance:
    action, reason = classify_action(row)
    evidence = [
        f"ROAS {row.get('roas', 0.0):.2f}x",
        f"CPA {row.get('cost_per_conversion', 0.0):.2f}",
        f"CTR {row.get('ctr', 0.0) * 100:.1f}%",
    ]
    return CampaignPerformance(
        campaign_name=row.get("campaign_name", "Unnamed Campaign"),
        campaign_id=row.get("campaign_id"),
        channel_type=row.get("channel_type"),
        status=row.get("status"),
        clicks=int(row.get("clicks", 0)),
        impressions=int(row.get("impressions", 0)),
        spend=float(row.get("spend", 0.0)),
        ctr=float(row.get("ctr", 0.0)),
        average_cpc=float(row.get("average_cpc", 0.0)),
        conversions=float(row.get("conversions", 0.0)),
        cost_per_conversion=float(row.get("cost_per_conversion", 0.0)),
        conversion_value=float(row.get("conversion_value", 0.0)),
        roas=float(row.get("roas", 0.0)),
        action=action,
        action_reason=reason,
        evidence=evidence,
        evidence_sources=[
            EvidenceSource(
                source=EvidenceDataSource.GOOGLE_ADS,
                entity_type=EvidenceEntityType.CAMPAIGN,
                entity_name=row.get("campaign_name", "Unnamed Campaign"),
                metric="roas",
                note=f"ROAS {row.get('roas', 0.0):.2f}x",
            ),
            EvidenceSource(
                source=EvidenceDataSource.GOOGLE_ADS,
                entity_type=EvidenceEntityType.CAMPAIGN,
                entity_name=row.get("campaign_name", "Unnamed Campaign"),
                metric="cost_per_conversion",
                note=f"CPA {row.get('cost_per_conversion', 0.0):.2f}",
            ),
        ],
        extra={"previous": row.get("previous", {})},
    )


def build_findings(campaigns: list[CampaignPerformance], currency_code: str) -> tuple[list[Finding], list[Finding]]:
    wins: list[Finding] = []
    risks: list[Finding] = []
    for campaign in campaigns:
        if campaign.action == ActionType.SCALE:
            wins.append(
                Finding(
                    finding_id=f"win-{campaign.campaign_id or campaign.campaign_name.lower().replace(' ', '-')}",
                    type=FindingType.WIN,
                    title=f"{campaign.campaign_name} is outperforming the account baseline",
                    evidence=[
                        f"ROAS is {campaign.roas:.2f}x",
                        f"CPA is {money(campaign.cost_per_conversion, currency_code)}",
                        f"{campaign.conversions:.0f} conversions this period",
                    ],
                    impact="This campaign is producing efficient conversions and can absorb more budget than weaker campaigns.",
                    recommended_action=f"Increase budget on {campaign.campaign_name} in controlled increments.",
                    confidence=ConfidenceLevel.HIGH,
                    related_campaigns=[campaign.campaign_name],
                    evidence_sources=campaign.evidence_sources,
                )
            )
        elif campaign.action in {ActionType.PAUSE, ActionType.REFRESH, ActionType.REFINE}:
            risks.append(
                Finding(
                    finding_id=f"risk-{campaign.campaign_id or campaign.campaign_name.lower().replace(' ', '-')}",
                    type=FindingType.RISK,
                    title=f"{campaign.campaign_name} is underperforming",
                    evidence=[
                        f"ROAS is {campaign.roas:.2f}x",
                        f"CPA is {money(campaign.cost_per_conversion, currency_code)}",
                        campaign.action_reason,
                    ],
                    impact="Budget is being consumed by campaigns that are not returning enough value.",
                    recommended_action=f"{campaign.action.title()} {campaign.campaign_name} this week.",
                    confidence=ConfidenceLevel.HIGH
                    if campaign.action == ActionType.PAUSE
                    else ConfidenceLevel.MEDIUM,
                    related_campaigns=[campaign.campaign_name],
                    evidence_sources=campaign.evidence_sources,
                )
            )
    return wins[:3], risks[:3]


def build_actions(campaigns: list[CampaignPerformance]) -> list[RecommendedAction]:
    priority_map: dict[ActionType, ActionPriority] = {
        ActionType.PAUSE: ActionPriority.URGENT,
        ActionType.SCALE: ActionPriority.HIGH,
        ActionType.REFINE: ActionPriority.MEDIUM,
        ActionType.REFRESH: ActionPriority.MEDIUM,
        ActionType.MONITOR: ActionPriority.LOW,
        ActionType.INVESTIGATE: ActionPriority.MEDIUM,
    }
    owner_map: dict[ActionType, str] = {
        ActionType.PAUSE: "paid team",
        ActionType.SCALE: "paid team",
        ActionType.REFINE: "paid team",
        ActionType.REFRESH: "creative + paid team",
        ActionType.MONITOR: "paid team",
        ActionType.INVESTIGATE: "paid team",
    }
    actions: list[RecommendedAction] = []
    for index, campaign in enumerate(campaigns[:5], start=1):
        actions.append(
            RecommendedAction(
                action_id=f"action-{index}",
                type=campaign.action,
                title=f"{campaign.action.title()} {campaign.campaign_name}",
                detail=campaign.action_reason,
                priority=priority_map.get(campaign.action, ActionPriority.LOW),
                owner=owner_map.get(campaign.action, "paid team"),
                related_campaigns=[campaign.campaign_name],
                evidence=campaign.evidence,
                evidence_sources=campaign.evidence_sources,
            )
        )
    order = (
        ActionPriority.URGENT,
        ActionPriority.HIGH,
        ActionPriority.MEDIUM,
        ActionPriority.LOW,
    )
    rank = {p: i for i, p in enumerate(order)}
    actions.sort(key=lambda item: rank[item.priority])
    return actions


def build_narrative(
    current_totals: dict[str, float],
    previous_totals: dict[str, float],
    campaigns: list[CampaignPerformance],
    _currency_code: str,
) -> BriefNarrative:
    account_roas = safe_divide(current_totals["conversion_value"], current_totals["spend"])
    previous_roas = safe_divide(previous_totals["conversion_value"], previous_totals["spend"])
    strongest = max(campaigns, key=lambda campaign: campaign.roas)
    weakest = min(campaigns, key=lambda campaign: campaign.roas)
    if account_roas >= 2.5:
        verdict = "Healthy efficiency overall, with room to reallocate toward top performers."
    elif account_roas >= 1.5:
        verdict = "Mixed performance: efficient campaigns are being diluted by weaker spend."
    else:
        verdict = "Account efficiency is under pressure and needs active budget correction."
    summary = (
        f"Blended ROAS moved from {previous_roas:.2f}x to {account_roas:.2f}x. "
        f"{strongest.campaign_name} is the strongest campaign, while {weakest.campaign_name} is the clearest budget risk."
    )
    operator_takeaway = (
        f"Protect spend behind {strongest.campaign_name} and cut or rework {weakest.campaign_name} "
        f"before adding net-new budget."
    )
    return BriefNarrative(verdict=verdict, summary=summary, operator_takeaway=operator_takeaway)


def build_brief(raw_payload: dict[str, Any], theme: str = "paid_ads") -> GoogleAdsBrief:
    metadata = raw_payload["source_metadata"]
    rows = raw_payload["rows"]
    currency_code = metadata.get("currency_code", "USD")
    current_totals, previous_totals = summarize_rows(rows)

    current_ctr = safe_divide(current_totals["clicks"], current_totals["impressions"])
    previous_ctr = safe_divide(previous_totals["clicks"], previous_totals["impressions"])
    current_cpc = safe_divide(current_totals["spend"], current_totals["clicks"])
    current_cpa = safe_divide(current_totals["spend"], current_totals["conversions"])
    previous_cpa = safe_divide(previous_totals["spend"], previous_totals["conversions"])
    current_roas = safe_divide(current_totals["conversion_value"], current_totals["spend"])
    previous_roas = safe_divide(previous_totals["conversion_value"], previous_totals["spend"])

    campaigns = [build_campaign(row) for row in rows]
    campaigns.sort(key=lambda campaign: (campaign.action != ActionType.PAUSE, -campaign.spend))
    wins, risks = build_findings(campaigns, currency_code)
    actions = build_actions(campaigns)
    narrative = build_narrative(current_totals, previous_totals, campaigns, currency_code)

    brief = GoogleAdsBrief(
        source_metadata=SourceMetadata(
            **metadata,
            theme=theme,
        ),
        account_summary=AccountSummary(
            spend=metric_value(current_totals["spend"], MetricFormatKind.CURRENCY, currency_code),
            clicks=metric_value(current_totals["clicks"], MetricFormatKind.NUMBER, currency_code),
            impressions=metric_value(
                current_totals["impressions"], MetricFormatKind.NUMBER, currency_code
            ),
            ctr=metric_value(current_ctr, MetricFormatKind.PERCENT, currency_code),
            average_cpc=metric_value(current_cpc, MetricFormatKind.CURRENCY, currency_code),
            conversions=metric_value(
                current_totals["conversions"], MetricFormatKind.NUMBER, currency_code
            ),
            cost_per_conversion=metric_value(current_cpa, MetricFormatKind.CURRENCY, currency_code),
            conversion_value=metric_value(
                current_totals["conversion_value"], MetricFormatKind.CURRENCY, currency_code
            ),
            roas=metric_value(current_roas, MetricFormatKind.MULTIPLIER, currency_code),
        ),
        period_comparison=PeriodComparison(
            spend=comparison_metric(
                current_totals["spend"], previous_totals["spend"], MetricFormatKind.CURRENCY, currency_code
            ),
            conversions=comparison_metric(
                current_totals["conversions"],
                previous_totals["conversions"],
                MetricFormatKind.NUMBER,
                currency_code,
            ),
            cost_per_conversion=comparison_metric(
                current_cpa, previous_cpa, MetricFormatKind.CURRENCY, currency_code
            ),
            conversion_value=comparison_metric(
                current_totals["conversion_value"],
                previous_totals["conversion_value"],
                MetricFormatKind.CURRENCY,
                currency_code,
            ),
            roas=comparison_metric(
                current_roas, previous_roas, MetricFormatKind.MULTIPLIER, currency_code
            ),
            clicks=comparison_metric(
                current_totals["clicks"],
                previous_totals["clicks"],
                MetricFormatKind.NUMBER,
                currency_code,
            ),
            impressions=comparison_metric(
                current_totals["impressions"],
                previous_totals["impressions"],
                MetricFormatKind.NUMBER,
                currency_code,
            ),
            ctr=comparison_metric(
                current_ctr, previous_ctr, MetricFormatKind.PERCENT, currency_code
            ),
        ),
        campaigns=campaigns,
        highlights=wins,
        risks=risks,
        recommended_actions=actions,
        narrative=narrative,
    )
    return brief


def synthesize_with_gemini_dict(
    brief_dict: dict[str, Any],
    raw_payload: dict[str, Any],
    *,
    goal: ReportGenerationGoal | None = None,
    custom_goal: str = "",
    context: str = "",
) -> dict[str, Any]:
    """Gemini synthesis for narrative / highlights / risks / actions; no-op if no API key or error."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return brief_dict

    try:
        from google import genai
        from google.genai import types
    except ImportError:
        return brief_dict

    system_instruction = get_system_prompt(goal=goal, custom_goal=custom_goal, context=context)
    user_text = get_synthesis_user_prompt(brief_dict, raw_payload)

    try:
        client = genai.Client(api_key=api_key)
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json",
            response_schema=_SynthesisSchema,
            thinking_config=types.ThinkingConfig(thinking_budget=1024),
            temperature=0.3,
        )
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=user_text,
            config=config,
        )
        raw_text = (response.text or "").strip()
        if not raw_text:
            return brief_dict
        synthesis = json.loads(raw_text)
        validated = _SynthesisSchema.model_validate(synthesis)
        out = validated.model_dump()
    except Exception:
        return brief_dict

    brief_dict["narrative"] = out.get("narrative", brief_dict.get("narrative", {}))
    brief_dict["highlights"] = out.get("highlights", brief_dict.get("highlights", []))
    brief_dict["risks"] = out.get("risks", brief_dict.get("risks", []))
    brief_dict["recommended_actions"] = out.get(
        "recommended_actions", brief_dict.get("recommended_actions", [])
    )
    return brief_dict
