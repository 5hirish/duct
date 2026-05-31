"""Lead magnet capture routes.

Endpoints (no API key required — Turnstile provides abuse prevention):
  POST /api/lead-magnet/submit   — validate Turnstile, store lead, return access token
  POST /api/lead-magnet/validate — validate access token in POST body (not query param)
  POST /api/lead-magnet/report   — persist completed audit report against a lead (first write wins)
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, field_validator
from sqlmodel import Session, select

from db.session import get_session
from models.lead_magnet import LeadMagnet
from service.crawl.fetcher import SSRFError, validate_public_url
from service.turnstile import verify_turnstile

logger = logging.getLogger(__name__)

router = APIRouter(tags=["lead-magnet"])

_TOKEN_TTL_HOURS = 24


class SubmitLeadRequest(BaseModel):
    email: EmailStr
    website_url: str
    turnstile_token: str  # required — always validated (server skips only when secret key unconfigured)
    magnet_type: str = "seo_audit"


class SubmitLeadResponse(BaseModel):
    token: str


class ValidateTokenRequest(BaseModel):
    token: str

    @field_validator("token")
    @classmethod
    def _token_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("token must not be empty")
        return v.strip()


class ValidateTokenResponse(BaseModel):
    website_url: str


class SaveReportRequest(BaseModel):
    token: str
    report: dict[str, Any]

    @field_validator("token")
    @classmethod
    def _token_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("token must not be empty")
        return v.strip()

    @field_validator("report")
    @classmethod
    def _report_not_empty(cls, v: dict[str, Any]) -> dict[str, Any]:
        if not v:
            raise ValueError("report must not be empty")
        return v


@router.post("/submit", response_model=SubmitLeadResponse)
async def submit_lead(
    req: Request,
    body: SubmitLeadRequest,
    session: Session = Depends(get_session),
) -> SubmitLeadResponse:
    client_ip = req.client.host if req.client else ""

    valid = await verify_turnstile(body.turnstile_token, client_ip)
    if not valid:
        raise HTTPException(status_code=400, detail="Security check failed. Please try again.")

    try:
        validate_public_url(body.website_url)
    except SSRFError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid URL.") from exc

    access_token = str(uuid.uuid4())
    lead = LeadMagnet(
        email=body.email,
        website_url=body.website_url,
        magnet_type=body.magnet_type,
        access_token=access_token,
    )
    session.add(lead)
    session.commit()

    logger.info("lead_magnet: captured lead email=%s url=%s", body.email, body.website_url)
    return SubmitLeadResponse(token=access_token)


@router.post("/validate", response_model=ValidateTokenResponse)
def validate_token(
    body: ValidateTokenRequest,
    session: Session = Depends(get_session),
) -> ValidateTokenResponse:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=_TOKEN_TTL_HOURS)
    stmt = select(LeadMagnet).where(
        LeadMagnet.access_token == body.token,
        LeadMagnet.created_at >= cutoff,
    )
    lead = session.exec(stmt).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Invalid or expired access token.")
    return ValidateTokenResponse(website_url=lead.website_url)


@router.post("/report", status_code=200)
def save_report(
    body: SaveReportRequest,
    session: Session = Depends(get_session),
) -> dict[str, str]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=_TOKEN_TTL_HOURS)
    stmt = select(LeadMagnet).where(
        LeadMagnet.access_token == body.token,
        LeadMagnet.created_at >= cutoff,
    )
    lead = session.exec(stmt).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Invalid or expired access token.")

    # First write wins — reject subsequent saves to prevent overwriting with stale data
    if lead.report_generated_at is not None:
        raise HTTPException(status_code=409, detail="Report already saved for this lead.")

    lead.report_json = body.report
    lead.report_generated_at = datetime.now(timezone.utc)
    session.add(lead)
    session.commit()

    logger.info("lead_magnet: saved report for email=%s url=%s", lead.email, lead.website_url)
    return {"status": "saved"}
