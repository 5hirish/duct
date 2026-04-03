#!/usr/bin/env python3
"""Normalize Google Ads raw data into a brief payload (JSON only).

The web app owns HTML rendering. This script is a pure data pipeline:
  raw source → normalize → typed brief → JSON artifact

Usage:
  python backend/scripts/google_ads_brief.py --demo --theme paid_ads \
      --output-json backend/reports/google-ads-report.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Tuple

from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from briefs.schemas.google_ads_brief import (
    AccountSummary,
    BriefNarrative,
    CampaignPerformance,
    ComparisonMetric,
    DeltaValue,
    EvidenceSource,
    Finding,
    GoogleAdsBrief,
    MetricValue,
    PeriodComparison,
    RecommendedAction,
    SourceMetadata,
)

_BRIEF_TEMPLATE_PATH = (
    Path(__file__).resolve().parents[1] / "briefs" / "templates" / "google_ads_weekly_brief.md"
)


class _SynEvidenceSource(BaseModel):
    source: str = "google_ads"
    entity_type: str = "campaign"
    entity_name: str = ""
    metric: str = ""
    note: str = ""


class _SynFinding(BaseModel):
    finding_id: str
    type: Literal["win", "risk", "watch"]
    title: str
    evidence: List[str] = Field(default_factory=list)
    impact: str = ""
    recommended_action: str = ""
    confidence: Literal["low", "medium", "high"] = "medium"
    related_campaigns: List[str] = Field(default_factory=list)
    evidence_sources: List[_SynEvidenceSource] = Field(default_factory=list)


class _SynRecommendedAction(BaseModel):
    action_id: str
    type: Literal["scale", "monitor", "pause", "refresh", "tighten", "investigate"]
    title: str
    detail: str = ""
    priority: Literal["p1", "p2", "p3"] = "p2"
    owner: str = "paid team"
    related_campaigns: List[str] = Field(default_factory=list)
    evidence: List[str] = Field(default_factory=list)
    evidence_sources: List[_SynEvidenceSource] = Field(default_factory=list)


class _SynNarrative(BaseModel):
    verdict: str
    summary: str
    operator_takeaway: str


class _SynthesisSchema(BaseModel):
    narrative: _SynNarrative
    highlights: List[_SynFinding] = Field(default_factory=list)
    risks: List[_SynFinding] = Field(default_factory=list)
    recommended_actions: List[_SynRecommendedAction] = Field(default_factory=list)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Google Ads MVP brief JSON.")
    parser.add_argument("--input", help="Raw JSON from google_ads_fetch.py")
    parser.add_argument("--output-json", required=True, help="Normalized payload path")
    parser.add_argument("--demo", action="store_true", help="Use built-in demo data")
    parser.add_argument(
        "--theme",
        default="paid_ads",
        help="Theme key embedded in output JSON (e.g. paid_ads, product_intelligence, organic_growth)",
    )
    return parser.parse_args()


def load_raw(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def demo_raw_payload() -> Dict[str, Any]:
    return {
        "source_metadata": {
            "source": "google_ads_manual_export",
            "export_type": "campaign_performance",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "window_current": "last_7_days",
            "window_previous": "previous_7_days",
            "currency_code": "USD",
            "account_name": "Duct Demo Account",
            "account_id": "123-456-7890",
            "source_file": "demo://google_ads_campaign_export.csv",
            "notes": ["Demo data for MVP validation"],
        },
        "rows": [
            {
                "campaign_name": "Brand Search",
                "campaign_id": "cmp_1",
                "channel_type": "SEARCH",
                "status": "ENABLED",
                "clicks": 420,
                "impressions": 3150,
                "spend": 2140.0,
                "ctr": 0.1333,
                "average_cpc": 5.1,
                "conversions": 38.0,
                "cost_per_conversion": 56.32,
                "conversion_value": 12600.0,
                "roas": 5.89,
                "previous": {
                    "clicks": 395,
                    "impressions": 2900,
                    "spend": 2010.0,
                    "conversions": 32.0,
                    "conversion_value": 10800.0,
                },
            },
            {
                "campaign_name": "Non-Brand Search",
                "campaign_id": "cmp_2",
                "channel_type": "SEARCH",
                "status": "ENABLED",
                "clicks": 600,
                "impressions": 10800,
                "spend": 4890.0,
                "ctr": 0.0556,
                "average_cpc": 8.15,
                "conversions": 24.0,
                "cost_per_conversion": 203.75,
                "conversion_value": 5400.0,
                "roas": 1.1,
                "previous": {
                    "clicks": 640,
                    "impressions": 11120,
                    "spend": 4500.0,
                    "conversions": 29.0,
                    "conversion_value": 6900.0,
                },
            },
            {
                "campaign_name": "Competitor Search",
                "campaign_id": "cmp_3",
                "channel_type": "SEARCH",
                "status": "ENABLED",
                "clicks": 220,
                "impressions": 4020,
                "spend": 1850.0,
                "ctr": 0.0547,
                "average_cpc": 8.41,
                "conversions": 7.0,
                "cost_per_conversion": 264.29,
                "conversion_value": 1190.0,
                "roas": 0.64,
                "previous": {
                    "clicks": 245,
                    "impressions": 4155,
                    "spend": 1740.0,
                    "conversions": 9.0,
                    "conversion_value": 1620.0,
                },
            },
            {
                "campaign_name": "Retargeting Display",
                "campaign_id": "cmp_4",
                "channel_type": "DISPLAY",
                "status": "ENABLED",
                "clicks": 310,
                "impressions": 18200,
                "spend": 920.0,
                "ctr": 0.0170,
                "average_cpc": 2.97,
                "conversions": 14.0,
                "cost_per_conversion": 65.71,
                "conversion_value": 3360.0,
                "roas": 3.65,
                "previous": {
                    "clicks": 280,
                    "impressions": 17080,
                    "spend": 860.0,
                    "conversions": 10.0,
                    "conversion_value": 2400.0,
                },
            },
        ],
    }


def money(value: float, currency_code: str) -> str:
    symbol = "$" if currency_code == "USD" else f"{currency_code} "
    return f"{symbol}{value:,.2f}"


def number(value: float) -> str:
    return f"{value:,.0f}"


def percent(value: float) -> str:
    return f"{value * 100:.1f}%"


def roas(value: float) -> str:
    return f"{value:.2f}x"


def safe_divide(a: float, b: float) -> float:
    return a / b if b else 0.0


def metric_value(value: float, kind: str, currency_code: str) -> MetricValue:
    if kind == "money":
        formatted = money(value, currency_code)
    elif kind == "percent":
        formatted = percent(value)
    elif kind == "roas":
        formatted = roas(value)
    else:
        formatted = number(value)
    return MetricValue(value=value, formatted=formatted)


def delta_value(current: float, previous: float, kind: str, currency_code: str) -> DeltaValue:
    absolute = current - previous
    percent_delta = safe_divide(absolute, previous) if previous else 0.0
    if absolute > 0:
        direction = "up"
    elif absolute < 0:
        direction = "down"
    else:
        direction = "flat"
    if kind == "money":
        absolute_text = money(abs(absolute), currency_code)
    elif kind == "percent":
        absolute_text = percent(abs(absolute))
    elif kind == "roas":
        absolute_text = roas(abs(absolute))
    else:
        absolute_text = number(abs(absolute))
    sign = "+" if absolute > 0 else "-" if absolute < 0 else ""
    percent_text = f"{abs(percent_delta) * 100:.1f}%"
    formatted = f"{sign}{absolute_text} ({sign}{percent_text})" if sign else "Flat"
    return DeltaValue(
        absolute=absolute,
        percent=percent_delta,
        direction=direction,
        formatted=formatted,
    )


def comparison_metric(
    current: float, previous: float, kind: str, currency_code: str
) -> ComparisonMetric:
    return ComparisonMetric(
        current=metric_value(current, kind, currency_code),
        previous=metric_value(previous, kind, currency_code),
        delta=delta_value(current, previous, kind, currency_code),
    )


def summarize_rows(rows: List[Dict[str, Any]]) -> Tuple[Dict[str, float], Dict[str, float]]:
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


def classify_action(row: Dict[str, Any]) -> Tuple[str, str]:
    row_roas = row.get("roas", 0.0)
    cpa = row.get("cost_per_conversion", 0.0)
    ctr = row.get("ctr", 0.0)
    conversions = row.get("conversions", 0.0)
    if row_roas >= 3.0 and conversions >= 10:
        return "scale", "High ROAS with meaningful conversion volume."
    if row_roas < 1.0 and cpa > 200:
        return "pause", "Low ROAS and expensive conversions are wasting budget."
    if ctr < 0.025 and conversions < 10:
        return "refresh", "Low engagement suggests creative or query fatigue."
    if 1.0 <= row_roas < 2.0:
        return "tighten", "Returns are weak enough to justify audience or query tightening."
    return "monitor", "Performance is serviceable but not strong enough to scale yet."


def build_campaign(row: Dict[str, Any]) -> CampaignPerformance:
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
                source="google_ads",
                entity_type="campaign",
                entity_name=row.get("campaign_name", "Unnamed Campaign"),
                metric="roas",
                note=f"ROAS {row.get('roas', 0.0):.2f}x",
            ),
            EvidenceSource(
                source="google_ads",
                entity_type="campaign",
                entity_name=row.get("campaign_name", "Unnamed Campaign"),
                metric="cost_per_conversion",
                note=f"CPA {row.get('cost_per_conversion', 0.0):.2f}",
            ),
        ],
        extra={"previous": row.get("previous", {})},
    )


def build_findings(campaigns: List[CampaignPerformance], currency_code: str) -> Tuple[List[Finding], List[Finding]]:
    wins: List[Finding] = []
    risks: List[Finding] = []
    for campaign in campaigns:
        if campaign.action == "scale":
            wins.append(
                Finding(
                    finding_id=f"win-{campaign.campaign_id or campaign.campaign_name.lower().replace(' ', '-')}",
                    type="win",
                    title=f"{campaign.campaign_name} is outperforming the account baseline",
                    evidence=[
                        f"ROAS is {campaign.roas:.2f}x",
                        f"CPA is {money(campaign.cost_per_conversion, currency_code)}",
                        f"{campaign.conversions:.0f} conversions this period",
                    ],
                    impact="This campaign is producing efficient conversions and can absorb more budget than weaker campaigns.",
                    recommended_action=f"Increase budget on {campaign.campaign_name} in controlled increments.",
                    confidence="high",
                    related_campaigns=[campaign.campaign_name],
                    evidence_sources=campaign.evidence_sources,
                )
            )
        elif campaign.action in {"pause", "refresh", "tighten"}:
            risks.append(
                Finding(
                    finding_id=f"risk-{campaign.campaign_id or campaign.campaign_name.lower().replace(' ', '-')}",
                    type="risk",
                    title=f"{campaign.campaign_name} is underperforming",
                    evidence=[
                        f"ROAS is {campaign.roas:.2f}x",
                        f"CPA is {money(campaign.cost_per_conversion, currency_code)}",
                        campaign.action_reason,
                    ],
                    impact="Budget is being consumed by campaigns that are not returning enough value.",
                    recommended_action=f"{campaign.action.title()} {campaign.campaign_name} this week.",
                    confidence="high" if campaign.action == "pause" else "medium",
                    related_campaigns=[campaign.campaign_name],
                    evidence_sources=campaign.evidence_sources,
                )
            )
    return wins[:3], risks[:3]


def build_actions(campaigns: List[CampaignPerformance]) -> List[RecommendedAction]:
    priority_map = {"pause": "p1", "scale": "p1", "tighten": "p2", "refresh": "p2", "monitor": "p3"}
    owner_map = {
        "pause": "paid team",
        "scale": "paid team",
        "tighten": "paid team",
        "refresh": "creative + paid team",
        "monitor": "paid team",
        "investigate": "paid team",
    }
    actions: List[RecommendedAction] = []
    for index, campaign in enumerate(campaigns[:5], start=1):
        actions.append(
            RecommendedAction(
                action_id=f"action-{index}",
                type=campaign.action,
                title=f"{campaign.action.title()} {campaign.campaign_name}",
                detail=campaign.action_reason,
                priority=priority_map.get(campaign.action, "p3"),
                owner=owner_map.get(campaign.action, "paid team"),
                related_campaigns=[campaign.campaign_name],
                evidence=campaign.evidence,
                evidence_sources=campaign.evidence_sources,
            )
        )
    actions.sort(key=lambda item: item.priority)
    return actions


def build_narrative(
    current_totals: Dict[str, float],
    previous_totals: Dict[str, float],
    campaigns: List[CampaignPerformance],
    currency_code: str,
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


def build_brief(raw_payload: Dict[str, Any], theme: str = "paid_ads") -> GoogleAdsBrief:
    metadata = raw_payload["source_metadata"]
    rows = raw_payload["rows"]
    currency_code = metadata.get("currency_code", "USD")
    current_totals, previous_totals = summarize_rows(rows)

    current_ctr = safe_divide(current_totals["clicks"], current_totals["impressions"])
    previous_ctr = safe_divide(previous_totals["clicks"], previous_totals["impressions"])
    current_cpc = safe_divide(current_totals["spend"], current_totals["clicks"])
    previous_cpc = safe_divide(previous_totals["spend"], previous_totals["clicks"])
    current_cpa = safe_divide(current_totals["spend"], current_totals["conversions"])
    previous_cpa = safe_divide(previous_totals["spend"], previous_totals["conversions"])
    current_roas = safe_divide(current_totals["conversion_value"], current_totals["spend"])
    previous_roas = safe_divide(previous_totals["conversion_value"], previous_totals["spend"])

    campaigns = [build_campaign(row) for row in rows]
    campaigns.sort(key=lambda campaign: (campaign.action != "pause", -campaign.spend))
    wins, risks = build_findings(campaigns, currency_code)
    actions = build_actions(campaigns)
    narrative = build_narrative(current_totals, previous_totals, campaigns, currency_code)

    brief = GoogleAdsBrief(
        source_metadata=SourceMetadata(
            **metadata,
            theme=theme,
        ),
        account_summary=AccountSummary(
            spend=metric_value(current_totals["spend"], "money", currency_code),
            clicks=metric_value(current_totals["clicks"], "number", currency_code),
            impressions=metric_value(current_totals["impressions"], "number", currency_code),
            ctr=metric_value(current_ctr, "percent", currency_code),
            average_cpc=metric_value(current_cpc, "money", currency_code),
            conversions=metric_value(current_totals["conversions"], "number", currency_code),
            cost_per_conversion=metric_value(current_cpa, "money", currency_code),
            conversion_value=metric_value(current_totals["conversion_value"], "money", currency_code),
            roas=metric_value(current_roas, "roas", currency_code),
        ),
        period_comparison=PeriodComparison(
            spend=comparison_metric(current_totals["spend"], previous_totals["spend"], "money", currency_code),
            conversions=comparison_metric(current_totals["conversions"], previous_totals["conversions"], "number", currency_code),
            cost_per_conversion=comparison_metric(current_cpa, previous_cpa, "money", currency_code),
            conversion_value=comparison_metric(current_totals["conversion_value"], previous_totals["conversion_value"], "money", currency_code),
            roas=comparison_metric(current_roas, previous_roas, "roas", currency_code),
            clicks=comparison_metric(current_totals["clicks"], previous_totals["clicks"], "number", currency_code),
            impressions=comparison_metric(current_totals["impressions"], previous_totals["impressions"], "number", currency_code),
            ctr=comparison_metric(current_ctr, previous_ctr, "percent", currency_code),
        ),
        campaigns=campaigns,
        highlights=wins,
        risks=risks,
        recommended_actions=actions,
        narrative=narrative,
    )
    return brief


def synthesize_with_gemini_dict(
    brief_dict: Dict[str, Any],
    raw_payload: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Replace narrative, highlights, risks, recommended_actions in brief_dict
    with Gemini 2.5 Flash output. Falls back silently to input dict on any error.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return brief_dict

    try:
        from google import genai
        from google.genai import types
    except ImportError:
        return brief_dict

    try:
        system_instruction = _BRIEF_TEMPLATE_PATH.read_text(encoding="utf-8")
    except OSError:
        return brief_dict

    compact_brief = json.dumps(brief_dict, separators=(",", ":"), default=str)[:120_000]
    compact_raw = json.dumps(raw_payload, separators=(",", ":"), default=str)[:120_000]
    user_text = (
        "You output ONLY fields: narrative (verdict, summary, operator_takeaway), "
        "highlights, risks, recommended_actions. Match the JSON schema exactly. "
        "Use only data from the payloads; do not invent metrics.\n\n"
        f"Deterministic brief JSON:\n{compact_brief}\n\nRaw campaign payload:\n{compact_raw}"
    )

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


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")


def main() -> None:
    args = parse_args()
    if not args.demo and not args.input:
        raise SystemExit("Provide --input or use --demo.")
    raw_payload = demo_raw_payload() if args.demo else load_raw(Path(args.input))
    brief = build_brief(raw_payload, theme=args.theme)
    write_json(Path(args.output_json), brief.to_dict())
    print(f"Wrote {args.output_json}")


if __name__ == "__main__":
    main()
