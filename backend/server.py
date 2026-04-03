"""FastAPI server: Google Ads report generation for the Next.js app."""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

load_dotenv()

from scripts.google_ads_api_fetch import fetch_campaigns
from scripts.google_ads_brief import (
    build_brief,
    demo_raw_payload,
    synthesize_with_gemini_dict,
)

REPORTS_DIR = Path(__file__).resolve().parent / "reports"

app = FastAPI(title="Duct backend")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ReportRequest(BaseModel):
    customer_id: str = ""
    developer_token: str = ""
    client_id: str = ""
    client_secret: str = ""
    refresh_token: str = ""
    date_from: str = ""
    date_to: str = ""
    account_name: str = ""
    currency_code: str = "USD"
    theme: str = "paid_ads"
    login_customer_id: str = ""
    use_demo: bool = False


class HealthResponse(BaseModel):
    status: str = Field(default="ok")


def _resolve_ads_credentials(req: ReportRequest) -> tuple[str, str, str, str]:
    dt = req.developer_token or os.environ.get("GOOGLE_ADS_DEVELOPER_TOKEN", "")
    cid = req.client_id or os.environ.get("GOOGLE_ADS_CLIENT_ID", "")
    secret = req.client_secret or os.environ.get("GOOGLE_ADS_CLIENT_SECRET", "")
    rt = req.refresh_token or os.environ.get("GOOGLE_ADS_REFRESH_TOKEN", "")
    if not all([dt, cid, secret, rt]):
        raise HTTPException(
            status_code=422,
            detail="Missing Google Ads credentials (body or GOOGLE_ADS_* env vars).",
        )
    return dt, cid, secret, rt


def _resolve_customer_id(req: ReportRequest) -> str:
    cid = (req.customer_id or os.environ.get("GOOGLE_ADS_CUSTOMER_ID", "")).strip()
    if not cid:
        raise HTTPException(status_code=422, detail="Missing customer_id.")
    return cid


def _report_basename(customer_stripped: str, date_to: str, *, demo: bool) -> str:
    if demo:
        return f"demo-{date_to}.json"
    return f"{customer_stripped}-{date_to}.json"


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse()


@app.get("/api/report/latest")
def report_latest() -> dict:
    if not REPORTS_DIR.is_dir():
        raise HTTPException(status_code=404, detail="No reports directory.")
    json_files = sorted(
        REPORTS_DIR.glob("*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not json_files:
        raise HTTPException(status_code=404, detail="No report files.")
    path = json_files[0]
    return json.loads(path.read_text(encoding="utf-8"))


@app.post("/api/report/google-ads")
def report_google_ads(req: ReportRequest) -> dict:
    if req.use_demo:
        raw_payload = demo_raw_payload()
        date_to = req.date_to.strip() or date.today().isoformat()
        customer_stripped = "demo"
    else:
        customer_id = _resolve_customer_id(req)
        customer_stripped = customer_id.replace("-", "")
        date_from = req.date_from.strip()
        date_to = req.date_to.strip()
        if not date_from or not date_to:
            raise HTTPException(status_code=422, detail="date_from and date_to are required.")
        dt, cid, secret, rt = _resolve_ads_credentials(req)
        login = (req.login_customer_id or os.environ.get("GOOGLE_ADS_LOGIN_CUSTOMER_ID", "")).strip()
        try:
            raw_payload = fetch_campaigns(
                customer_id=customer_id,
                developer_token=dt,
                client_id=cid,
                client_secret=secret,
                refresh_token=rt,
                date_from=date_from,
                date_to=date_to,
                account_name=req.account_name,
                currency_code=req.currency_code,
                login_customer_id=login,
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        if not raw_payload.get("rows"):
            raise HTTPException(
                status_code=422,
                detail="No campaigns returned for this customer and date range.",
            )

    brief = build_brief(raw_payload, theme=req.theme)
    brief_dict = brief.to_dict()
    if os.environ.get("GEMINI_API_KEY"):
        brief_dict = synthesize_with_gemini_dict(brief_dict, raw_payload)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out_name = _report_basename(customer_stripped, date_to, demo=req.use_demo)
    out_path = REPORTS_DIR / out_name
    out_path.write_text(json.dumps(brief_dict, indent=2) + "\n", encoding="utf-8")

    return brief_dict
