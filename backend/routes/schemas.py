"""Shared request/response models for API routes."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


# The wizard's request/response contract used to live here: ReportRequest,
# GenerateRequest (connectors + accounts + goal + date range) and the
# UnifiedInsight envelope they produced. All four went with the six-step form
# that filled them in — the autonomous session takes a project and a sentence.
# See docs/engineering/autonomous-insights-agent-plan.md.


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
    developer_token: str = ""
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
