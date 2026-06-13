"""Shared request/response models for API routes."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, Self

from pydantic import BaseModel, BeforeValidator, Field, model_validator

from agents.core.context import BusinessContext
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


# BusinessContext is the shared, unified model (agents/core/context.py),
# passed equally to every agent. It is a superset (identity + paid + organic
# fields) with extra="ignore", so existing insights form payloads validate
# unchanged. Imported above; re-exported here for backwards-compatible imports.


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
    engine: str = Field(default="", description="Engine override: 'v1', 'v2', or 'v3'. Falls back to GENERATE_ENGINE env var.")

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

    version: str = "3"
    connectors_used: list[str] = Field(default_factory=list)
    briefs: dict[str, Any] = Field(default_factory=dict)
    supplementary: dict[str, Any] = Field(default_factory=dict)
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


class EngineStatus(BaseModel):
    """Availability of a single inference engine, for the engine picker UI."""

    key: str = Field(description="Engine key: v1 | v2 | v3")
    status: str = Field(description="active | needs_auth | inactive")
    auth_method: str | None = Field(
        default=None, description="How an active engine is authenticated: api_key | oauth"
    )
    supports_oauth: bool = Field(
        default=False, description="True if the engine can authenticate without an API key"
    )
    detail: str | None = Field(
        default=None, description="Human-readable guidance, shown when status is needs_auth"
    )


class EngineStatusResponse(BaseModel):
    engines: list[EngineStatus]


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


class ProjectConfigOption(BaseModel):
    value: str
    label: str


class ProjectConfigResponse(BaseModel):
    industry_options: list[ProjectConfigOption] = Field(default_factory=list)
    business_model_options: list[ProjectConfigOption] = Field(default_factory=list)
    north_star_metric_options: list[ProjectConfigOption] = Field(default_factory=list)
    growth_stage_milestone_options: list[ProjectConfigOption] = Field(default_factory=list)
