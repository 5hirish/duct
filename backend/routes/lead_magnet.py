"""Lead magnet capture routes.

Endpoints (no API key required — Turnstile provides abuse prevention):
  POST /api/lead-magnet/submit   — validate Turnstile, store lead, return access token
  POST /api/lead-magnet/validate — validate access token in POST body (not query param)
  POST /api/lead-magnet/report   — persist completed audit report against a lead (first write wins)
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator
from sqlmodel import Session, select

from db.session import get_session
from models.lead_magnet import ExecutionInterest, LeadMagnet
from service.crawl.fetcher import SSRFError, validate_public_url
from service.lead_access import find_live_lead
from service.turnstile import verify_turnstile

logger = logging.getLogger(__name__)

router = APIRouter(tags=["lead-magnet"])

# Token TTL lives in service/lead_access.py — imported above so the three
# endpoints here and agent session creation cannot drift apart.
_REPORT_CACHE_TTL_HOURS = 24  # reuse a cached report generated within this window

# Paid execution services a lead can express interest in (demand-validation test).
_VALID_EXECUTION_SERVICES = {"ai_ready_fixes", "content_rewrites", "translation"}


class SubmitLeadRequest(BaseModel):
    email: str
    website_url: str
    turnstile_token: str  # required — always validated (server skips only when secret key unconfigured)
    magnet_type: str = "seo_audit"

    @field_validator("email")
    @classmethod
    def _email_valid(cls, v: str) -> str:
        v = v.strip().lower()
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("Invalid email address")
        return v


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
    email: Optional[str] = None
    cached_report: Optional[dict[str, Any]] = None
    cached_at: Optional[datetime] = None


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
    lead = find_live_lead(session, body.token)
    if not lead:
        raise HTTPException(status_code=404, detail="Invalid or expired access token.")

    # Look for a recent report for the same URL — avoids re-running the audit
    cache_cutoff = datetime.now(timezone.utc) - timedelta(hours=_REPORT_CACHE_TTL_HOURS)
    cached = session.exec(
        select(LeadMagnet)
        .where(
            LeadMagnet.website_url == lead.website_url,
            LeadMagnet.report_json.isnot(None),
            LeadMagnet.report_generated_at >= cache_cutoff,
        )
        .order_by(LeadMagnet.report_generated_at.desc())
        .limit(1)
    ).first()

    return ValidateTokenResponse(
        website_url=lead.website_url,
        email=lead.email,
        cached_report=cached.report_json if cached else None,
        cached_at=cached.report_generated_at if cached else None,
    )


@router.post("/report", status_code=200)
async def save_report(
    body: SaveReportRequest,
    session: Session = Depends(get_session),
) -> dict[str, str]:
    lead = find_live_lead(session, body.token)
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

    # Fire email in background with retry + idempotency guard.
    # Captures all values by reference so the background task has no DB dependency.
    _lead_id, _email, _url, _report = lead.id, lead.email, lead.website_url, body.report

    async def _send_with_retry() -> None:
        from service.email_cf import send_lead_report_email
        from db.session import get_engine
        from sqlmodel import Session as _Session

        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            try:
                success = await send_lead_report_email(_email, _url, _report)
                if success:
                    # Stamp email_sent_at so we never re-send on future runs
                    engine = get_engine()
                    if engine:
                        with _Session(engine) as s:
                            m = s.get(LeadMagnet, _lead_id)
                            if m and m.email_sent_at is None:
                                m.email_sent_at = datetime.now(timezone.utc)
                                s.add(m)
                                s.commit()
                    logger.info("email: sent (attempt %d) to %s", attempt, _email)
                    return
                logger.warning("email: attempt %d returned failure for %s", attempt, _email)
            except Exception:
                logger.exception("email: attempt %d raised for %s", attempt, _email)

            if attempt < max_attempts:
                await asyncio.sleep(5 * (2 ** (attempt - 1)))  # 5s, 10s

        logger.error("email: all %d attempts failed for %s — report not delivered", max_attempts, _email)

    asyncio.create_task(_send_with_retry())

    return {"status": "saved"}


class ExecutionInterestRequest(BaseModel):
    token: str
    services: list[str]
    finding_ids: Optional[list[str]] = None
    note: Optional[str] = None

    @field_validator("token")
    @classmethod
    def _token_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("token must not be empty")
        return v.strip()

    @field_validator("services")
    @classmethod
    def _services_valid(cls, v: list[str]) -> list[str]:
        cleaned = [s.strip() for s in v if s and s.strip()]
        if not cleaned:
            raise ValueError("at least one service must be selected")
        invalid = [s for s in cleaned if s not in _VALID_EXECUTION_SERVICES]
        if invalid:
            raise ValueError(f"unknown service(s): {', '.join(invalid)}")
        # de-dupe, preserve order
        return list(dict.fromkeys(cleaned))

    @field_validator("note")
    @classmethod
    def _note_trim(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        return v[:1000] if v else None


@router.post("/execution-interest", status_code=200)
async def record_execution_interest(
    body: ExecutionInterestRequest,
    session: Session = Depends(get_session),
) -> dict[str, str]:
    """Record a lead's interest in paid execution (demand-validation test).

    Auditing stays free; this captures which execution service(s) a lead wants so
    we can prioritise what to build. No execution is performed. A background
    notification is sent to the internal team.
    """
    lead = find_live_lead(session, body.token)
    if not lead:
        raise HTTPException(status_code=404, detail="Invalid or expired access token.")

    interest = ExecutionInterest(
        lead_magnet_id=lead.id,
        email=lead.email,
        website_url=lead.website_url,
        services=body.services,
        finding_ids=body.finding_ids,
        note=body.note,
    )
    session.add(interest)
    session.commit()

    logger.info(
        "lead_magnet: execution interest email=%s url=%s services=%s",
        lead.email, lead.website_url, body.services,
    )

    # Notify the team in the background — never blocks the response.
    _email, _url, _services, _note = lead.email, lead.website_url, body.services, body.note

    async def _notify() -> None:
        from service.email_cf import send_execution_interest_notification
        try:
            await send_execution_interest_notification(_email, _url, _services, _note)
        except Exception:
            logger.exception("email: execution-interest notify task raised for %s", _email)

    asyncio.create_task(_notify())

    return {"status": "received"}


@router.get("/check-url")
async def check_url(url: str) -> dict:
    """Lightweight reachability pre-flight called from the URL input form.

    Validates the URL is public, then attempts a HEAD (falling back to GET) with
    a short timeout. Returns {ok: true} or {ok: false, reason: "..."}.
    No auth required — abuse is mitigated by rate limits and the cheap cost of a
    HEAD request.
    """
    import httpx

    try:
        validate_public_url(url)
    except (SSRFError, Exception):
        return {"ok": False, "reason": "That doesn't look like a valid public URL."}

    try:
        # Do NOT follow redirects — a redirect target could be an internal address,
        # bypassing validate_public_url. Any non-5xx response (including 3xx) proves
        # the server is reachable, which is all we need.
        async with httpx.AsyncClient(
            follow_redirects=False,
            timeout=httpx.Timeout(5.0, connect=3.0),
        ) as client:
            try:
                r = await client.head(url, headers={"User-Agent": "DuctBot/1.0"})
                reachable = r.status_code < 500
            except httpx.UnsupportedProtocol:
                reachable = False
            except Exception:
                # Some servers reject HEAD — try a byte-capped GET
                try:
                    r = await client.get(
                        url,
                        headers={"User-Agent": "DuctBot/1.0", "Range": "bytes=0-1023"},
                    )
                    reachable = r.status_code < 500
                except Exception:
                    reachable = False
    except Exception:
        reachable = False

    if reachable:
        return {"ok": True}
    return {"ok": False, "reason": "We couldn't reach that site — please double-check the URL."}
