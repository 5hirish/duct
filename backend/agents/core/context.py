"""Unified business context — one model passed equally to every agent.

Replaces the three divergent shapes (routes.schemas.BusinessContext,
audit.AuditBusinessContext, content's brand stanza) and the three copies of
``format_business_context``. Each agent uses the sections relevant to it; the
shared formatter renders only the fields that are populated, so an audit run and
a paid-ads insights run produce a clean, comparable ``<business_context>`` block.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from agents.core.prompts import xml_block


class BusinessContext(BaseModel):
    """Superset of the business context any agent needs.

    ``extra="ignore"`` tolerates legacy/per-agent fields during migration so the
    same payload can be handed to every agent without validation errors.
    """

    model_config = ConfigDict(extra="ignore")

    # --- Identity / shared across all agents ---
    business_name: str = ""
    business_description: str = ""
    industry: str = ""
    business_model: str = ""
    positioning_statement: str = ""
    brand_voice: str = ""
    growth_stage: str = ""
    competitors: list[str] = Field(default_factory=list)
    target_keywords: list[str] = Field(default_factory=list)
    audience_segment: str = ""
    business_goals: str = ""
    period_changes: str = ""
    notes: str = ""

    # --- Paid-ads section (insights, mode="paid_ads") ---
    monthly_budget: float = 0.0
    target_cpa: float = 0.0
    target_roas: float = 0.0
    primary_conversion_action: str = ""
    target_payback_days: float = 0.0
    gross_margin_percent: float = 0.0
    qualified_lead_value: float = 0.0

    # --- Organic section (insights, mode="organic_growth") ---
    primary_organic_kpi: str = ""
    monthly_organic_traffic_target: float = 0.0
    primary_content_type: str = ""

    @classmethod
    def coerce(cls, data: "BusinessContext | dict | None") -> "BusinessContext":
        """Build from this model, a plain dict, or None (→ empty)."""
        if data is None:
            return cls()
        if isinstance(data, BusinessContext):
            return data
        if isinstance(data, BaseModel):
            return cls.model_validate(data.model_dump())
        return cls.model_validate(data)


# Field → human label, grouped. Only populated fields render.
_SHARED_LABELS: list[tuple[str, str]] = [
    ("business_name", "Business"),
    ("business_description", "Description"),
    ("industry", "Industry"),
    ("business_model", "Business model"),
    ("positioning_statement", "Positioning"),
    ("audience_segment", "Audience"),
    ("brand_voice", "Brand voice"),
    ("growth_stage", "Growth stage"),
    ("primary_content_type", "Primary content type"),
    ("business_goals", "Goals"),
    ("period_changes", "Recent changes"),
    ("notes", "Notes"),
]
_PAID_LABELS: list[tuple[str, str]] = [
    ("monthly_budget", "Monthly budget"),
    ("target_cpa", "Target CPA"),
    ("target_roas", "Target ROAS"),
    ("primary_conversion_action", "Primary conversion"),
    ("target_payback_days", "Target payback (days)"),
    ("gross_margin_percent", "Gross margin %"),
    ("qualified_lead_value", "Qualified lead value"),
]
_ORGANIC_LABELS: list[tuple[str, str]] = [
    ("primary_organic_kpi", "Primary organic KPI"),
    ("monthly_organic_traffic_target", "Monthly organic traffic target"),
]
_LIST_LABELS: list[tuple[str, str]] = [
    ("competitors", "Competitors"),
    ("target_keywords", "Target keywords"),
]


def _lines(ctx: BusinessContext, labels: list[tuple[str, str]]) -> list[str]:
    out: list[str] = []
    for field, label in labels:
        value = getattr(ctx, field, "")
        if isinstance(value, (int, float)) and not value:
            continue
        if not value:
            continue
        out.append(f"{label}: {value}")
    return out


def format_business_context(
    data: BusinessContext | dict | None,
    *,
    include_paid: bool = True,
    include_organic: bool = True,
) -> str:
    """Render populated business-context fields as a standard ``<business_context>``
    block. Returns '' when nothing is populated (so prompts stay clean for
    first-run / no-context cases). ``include_paid`` / ``include_organic`` let an
    agent suppress sections irrelevant to its mode.
    """
    ctx = BusinessContext.coerce(data)
    lines = _lines(ctx, _SHARED_LABELS)
    for field, label in _LIST_LABELS:
        items = getattr(ctx, field, []) or []
        if items:
            lines.append(f"{label}: {', '.join(str(i) for i in items)}")
    if include_paid:
        lines += _lines(ctx, _PAID_LABELS)
    if include_organic:
        lines += _lines(ctx, _ORGANIC_LABELS)
    return xml_block("business_context", "\n".join(lines))


class UserContext(BaseModel):
    """The human operator a synthesis is for — used to personalise tone/depth.

    Separate from BusinessContext (which describes the company). Extensible:
    populate ``name`` today; add role/seniority later and the formatter renders
    only the fields that are set. Per-user data is rendered in the USER message
    (via get_synthesis_user_prompt), never the system prompt, so the cached
    system prefix stays byte-identical across users.
    """

    model_config = ConfigDict(extra="ignore")

    name: str = ""
    role: str = ""
    seniority: str = ""

    @classmethod
    def coerce(cls, data: "UserContext | dict | None") -> "UserContext":
        """Build from this model, a plain dict, or None (→ empty)."""
        if data is None:
            return cls()
        if isinstance(data, UserContext):
            return data
        if isinstance(data, BaseModel):
            return cls.model_validate(data.model_dump())
        return cls.model_validate(data)


_USER_LABELS: list[tuple[str, str]] = [
    ("name", "Name"),
    ("role", "Role"),
    ("seniority", "Seniority"),
]


def format_user_context(data: UserContext | dict | None) -> str:
    """Render populated user fields as a standard ``<user_context>`` block.

    Returns '' when nothing is populated, so prompts stay clean when no user
    context is supplied. Like business context, this belongs in the user
    message — never the system prompt.
    """
    ctx = UserContext.coerce(data)
    return xml_block("user_context", "\n".join(_lines(ctx, _USER_LABELS)))
