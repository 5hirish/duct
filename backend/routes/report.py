"""Report JSON artifacts and connector-keyed report generation."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from fastapi import APIRouter, HTTPException
from starlette.status import HTTP_404_NOT_FOUND, HTTP_501_NOT_IMPLEMENTED

from config import get_configs
from service.connectors import CAP_CAMPAIGN_REPORT, get_connector, normalize_connector_id
from service.google.constants import GOOGLE_ADS_CONNECTOR_ID
from service.google.credentials import report_basename, resolve_ads_credentials, resolve_customer_id
from service.google.fetch import fetch_campaigns
from service.google.brief import build_brief, demo_raw_payload, synthesize_with_gemini_dict
from routes.schemas import ReportRequest

router = APIRouter(tags=["report"])

REPORTS_DIR = Path(__file__).resolve().parents[1] / "reports"


@router.get("/latest")
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


def _persisted_report_google_ads(req: ReportRequest) -> dict:
    if req.use_demo:
        raw_payload = demo_raw_payload()
        date_to = req.date_to.strip() or date.today().isoformat()
        customer_stripped = "demo"
    else:
        customer_id = resolve_customer_id(request_customer_id=req.customer_id)
        customer_stripped = customer_id.replace("-", "")
        date_from = req.date_from.strip()
        date_to = req.date_to.strip()
        if not date_from or not date_to:
            raise HTTPException(status_code=422, detail="date_from and date_to are required.")
        dt, cid, secret, rt = resolve_ads_credentials(request_refresh_token=req.refresh_token)
        login = (req.login_customer_id or get_configs().google_ads_login_customer_id).strip()
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
    if get_configs().gemini_api_key:
        brief_dict = synthesize_with_gemini_dict(brief_dict, raw_payload)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out_name = report_basename(customer_stripped, date_to, demo=req.use_demo)
    out_path = REPORTS_DIR / out_name
    out_path.write_text(json.dumps(brief_dict, indent=2) + "\n", encoding="utf-8")

    return brief_dict


def post_persisted_report(connector_id: str, req: ReportRequest) -> dict:
    """Validate connector and capability, then build and write report JSON."""
    cid = normalize_connector_id(connector_id)
    try:
        meta, _ = get_connector(cid)
    except KeyError as exc:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail="Unknown connector",
        ) from exc

    if CAP_CAMPAIGN_REPORT not in meta.capabilities:
        raise HTTPException(
            status_code=HTTP_501_NOT_IMPLEMENTED,
            detail=f"Connector {cid!r} does not support persisted campaign reports.",
        )

    if cid == GOOGLE_ADS_CONNECTOR_ID:
        return _persisted_report_google_ads(req)

    raise HTTPException(
        status_code=HTTP_501_NOT_IMPLEMENTED,
        detail=f"Report generation for connector {cid!r} is not implemented yet.",
    )


@router.post("/{connector_id}")
def post_report(connector_id: str, req: ReportRequest) -> dict:
    """Build a report for a connector (e.g. ``google_ads``) and write JSON to ``reports/``."""
    return post_persisted_report(connector_id, req)
