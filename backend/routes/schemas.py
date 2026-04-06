"""Shared request/response models for API routes."""

from __future__ import annotations

from typing import Annotated, Any, Self

from pydantic import BaseModel, BeforeValidator, Field, model_validator

from agents.reporter.goals import ReportGenerationGoal, parse_goal_value


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
    """Optional business context for goal-aware LLM reasoning."""

    industry: str = ""           # "ecommerce", "saas", "lead_gen", "agency"
    monthly_budget: float = 0.0
    target_cpa: float = 0.0
    target_roas: float = 0.0
    notes: str = ""


class GenerateRequest(BaseModel):
    connections: list[str] = Field(default_factory=list)  # e.g. ["google_ads"]
    goal: Annotated[ReportGenerationGoal, BeforeValidator(parse_goal_value)]
    custom_goal: str = Field(
        default="",
        description='Required when goal is "custom": free-text objective for the report.',
    )
    context: str = ""
    date_from: str = ""
    date_to: str = ""
    refresh_token: str = ""
    customer_id: str = ""
    account_name: str = ""
    currency_code: str = "USD"
    login_customer_id: str = ""
    business_context: BusinessContext = Field(default_factory=BusinessContext)

    @model_validator(mode="after")
    def _custom_goal_required(self) -> Self:
        if self.goal == ReportGenerationGoal.CUSTOM and not self.custom_goal.strip():
            raise ValueError('custom_goal is required when goal is "custom"')
        return self


class ReportMetadata(BaseModel):
    """Envelope-level metadata for a unified report."""

    generated_at: str = ""
    goal: str = ""
    connectors_used: list[str] = Field(default_factory=list)


class UnifiedReport(BaseModel):
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
    metadata: ReportMetadata = Field(default_factory=ReportMetadata)


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
