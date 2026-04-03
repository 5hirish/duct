"""Shared request/response models for API routes."""

from __future__ import annotations

from pydantic import BaseModel, Field


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


class GenerateRequest(BaseModel):
    connections: list[str] = Field(default_factory=list)  # e.g. ["google_ads"]
    goal: str = ""
    context: str = ""
    date_from: str = ""
    date_to: str = ""
    refresh_token: str = ""
    customer_id: str = ""
    account_name: str = ""
    currency_code: str = "USD"
    login_customer_id: str = ""


class HealthResponse(BaseModel):
    status: str = Field(default="ok")
