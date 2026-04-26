"""Shared request/response models for API routes."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, Self

from pydantic import BaseModel, BeforeValidator, Field, model_validator

from agents.insights.goals import InsightGenerationGoal, parse_goal_value
from agents.insights.goals.organic_growth import OrganicGrowthGoal, parse_goal_value as parse_organic_goal_value


def _parse_any_goal(value: object) -> InsightGenerationGoal | OrganicGrowthGoal:
    """Coerce goal value — tries paid ads first, then organic growth."""
    try:
        return parse_goal_value(value)
    except ValueError:
        pass
    try:
        return parse_organic_goal_value(value)
    except ValueError:
        raise ValueError(
            f"Unknown goal {value!r}. Not a valid paid ads or organic growth goal."
        )


class ReportRequest(BaseModel):
    customer_id: str = ""
    developer_token: str = ""  # deprecated; token now resolves from backend env
    client_id: str = ""  # deprecated; client id now resolves from backend env
    client_secret: str = ""  # deprecated; secret now resolves from backend env
    refresh_token: str = ""
    date_from: str = ""
    date_to: str = ""
    account_name: str = ""
    currency_code: str = "USD"
    theme: str = "paid_ads"
    login_customer_id: str = ""  # optional MCC override
    use_demo: bool = False


class BusinessContext(BaseModel):
    """Optional business context for goal-aware LLM reasoning.

    Paid ads fields (used when mode="paid_ads"):
      monthly_budget, target_cpa, target_roas, primary_conversion_action,
      target_payback_days, gross_margin_percent, qualified_lead_value

    Organic growth fields (used when mode="organic_growth"):
      primary_organic_kpi, monthly_organic_traffic_target, primary_content_type

    Shared fields: industry, period_changes, notes
    """

    industry: str = ""
    # Paid ads
    monthly_budget: float = 0.0
    target_cpa: float = 0.0
    target_roas: float = 0.0
    primary_conversion_action: str = ""
    target_payback_days: float = 0.0
    gross_margin_percent: float = 0.0
    qualified_lead_value: float = 0.0
    # Organic growth
    primary_organic_kpi: str = ""           # "organic_traffic", "keyword_rankings", etc.
    monthly_organic_traffic_target: float = 0.0
    primary_content_type: str = ""          # "blog_articles", "product_pages", etc.
    # Shared
    period_changes: str = ""
    notes: str = ""


class GenerateRequest(BaseModel):
    connections: list[str] = Field(default_factory=list)
    mode: str = Field(default="paid_ads", description="Intelligence mode: 'paid_ads' or 'organic_growth'")
    goal: Annotated[InsightGenerationGoal | OrganicGrowthGoal, BeforeValidator(_parse_any_goal)]
    custom_goal: str = Field(
        default="",
        description='Required when goal is "custom": free-text objective for the report.',
    )
    context: str = ""
    date_from: str = ""
    date_to: str = ""
    refresh_token: str = ""
    customer_id: str = ""
    ga4_property_id: str = ""
    ga4_refresh_token: str = ""
    gsc_site_url: str = ""
    gsc_refresh_token: str = ""
    account_name: str = ""
    currency_code: str = "USD"
    login_customer_id: str = ""
    business_context: BusinessContext = Field(default_factory=BusinessContext)
    mode_context: str = ""  # optional frontend-supplied mode context, appended to system prompt

    @model_validator(mode="after")
    def _custom_goal_required(self) -> Self:
        from agents.insights.goals.organic_growth import OrganicGrowthGoal as OGGoal
        is_custom = (
            self.goal == InsightGenerationGoal.CUSTOM
            or (isinstance(self.goal, OGGoal) and self.goal == OGGoal.CUSTOM)
        )
        if is_custom and not self.custom_goal.strip():
            raise ValueError('custom_goal is required when goal is "custom"')
        return self


class InsightMetadata(BaseModel):
    """Envelope-level metadata for a unified insight."""

    generated_at: str = ""
    goal: str = ""
    connectors_used: list[str] = Field(default_factory=list)


class UnifiedInsight(BaseModel):
    """Envelope wrapping one or more connector briefs plus a synthesis layer.

    ``briefs`` maps connector_id → connector-specific brief dict.
    ``synthesis`` holds the LLM-produced analysis (narrative, findings, actions).
    When no LLM is configured, ``synthesis`` is ``None`` and the frontend
    falls back to the deterministic narrative/highlights/risks inside each brief.
    """

    version: str = "2"
    connectors_used: list[str] = Field(default_factory=list)
    briefs: dict[str, Any] = Field(default_factory=dict)
    synthesis: dict[str, Any] | None = None
    metadata: InsightMetadata = Field(default_factory=InsightMetadata)


class RefreshRoutineTarget(BaseModel):
    customer_id: str = ""
    account_name: str = ""
    currency_code: str = "USD"
    login_customer_id: str = ""
    property_id: str = ""
    site_url: str = ""


class InsightRefreshRequest(BaseModel):
    connections: list[str] = Field(default_factory=list)
    date_preset: str = "30"
    date_from: str = ""
    date_to: str = ""
    refresh_token: str = ""
    ga4_refresh_token: str = ""
    gsc_refresh_token: str = ""
    targets: dict[str, RefreshRoutineTarget] = Field(default_factory=dict)


class InsightRefreshResponse(BaseModel):
    refreshed_at: str
    briefs: dict[str, Any] = Field(default_factory=dict)
    date_from: str
    date_to: str


class HealthResponse(BaseModel):
    status: str = Field(default="ok")


class RootLinks(BaseModel):
    """Public entrypoints for humans and tooling hitting the API host root."""

    health: str = "/health"
    openapi: str | None = Field(default=None, description="OpenAPI schema URL when exposed")
    docs: str | None = Field(default=None, description="Swagger UI when exposed")


class RootResponse(BaseModel):
    service: str = "Duct API"
    version: str
    links: RootLinks = Field(default_factory=RootLinks)


class BusinessContextFieldType(StrEnum):
    TEXT = "text"
    NUMBER = "number"
    SELECT = "select"
    TEXTAREA = "textarea"


class BusinessContextFieldShowIf(StrEnum):
    ALWAYS = "always"
    ADS_SELECTED = "ads_selected"


class BusinessContextFieldOption(BaseModel):
    value: str
    label: str


class BusinessContextField(BaseModel):
    key: str
    label: str
    type: BusinessContextFieldType
    placeholder: str = ""
    options: list[BusinessContextFieldOption] = Field(default_factory=list)
    min: float | int | None = None
    max: float | int | None = None
    step: float | int | None = None
    rows: int | None = None
    full_width: bool = False
    empty_if_zero: bool = False
    show_if: BusinessContextFieldShowIf = BusinessContextFieldShowIf.ALWAYS


class InsightGoalDescriptor(BaseModel):
    key: str
    icon: str = ""
    label: str
    description: str = ""


class InsightMode(BaseModel):
    key: str
    emoji: str = ""
    label: str
    short_label: str = ""
    tagline: str = ""
    active: bool = False
    locked_connections: list[str] = Field(default_factory=list)
    goals: list[InsightGoalDescriptor] = Field(default_factory=list)
    business_context_fields: list[BusinessContextField] = Field(default_factory=list)


class InsightModesResponse(BaseModel):
    modes: list[InsightMode] = Field(default_factory=list)

