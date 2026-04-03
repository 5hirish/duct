"""FastAPI server: Google Ads report generation for the Next.js app."""

from __future__ import annotations

import json
import os
import secrets
import time
from datetime import date
from pathlib import Path
from urllib.parse import quote

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from google_auth_oauthlib.flow import Flow
from pydantic import BaseModel, Field

from scripts.google_ads_accounts import list_accessible_accounts
from scripts.google_ads_api_fetch import fetch_campaigns
from scripts.google_ads_brief import (
    build_brief,
    demo_raw_payload,
    synthesize_with_gemini_dict,
)

load_dotenv()

REPORTS_DIR = Path(__file__).resolve().parent / "reports"
GOOGLE_OAUTH_CLIENT_ID = os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "").strip()
GOOGLE_OAUTH_CLIENT_SECRET = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "").strip()
GOOGLE_OAUTH_REDIRECT_URI = os.environ.get(
    "GOOGLE_OAUTH_REDIRECT_URI", "http://localhost:8000/auth/google/callback"
).strip()
FRONTEND_ORIGIN = os.environ.get("FRONTEND_ORIGIN", "http://localhost:3000").strip()
GOOGLE_ADS_DEVELOPER_TOKEN = os.environ.get("GOOGLE_ADS_DEVELOPER_TOKEN", "").strip()
OAUTH_STATE_TTL_SECONDS = 300
_oauth_states: dict[str, float] = {}

app = FastAPI(title="Duct backend")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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


def _resolve_ads_credentials(req: ReportRequest) -> tuple[str, str, str, str]:
    dt = GOOGLE_ADS_DEVELOPER_TOKEN
    cid = GOOGLE_OAUTH_CLIENT_ID or os.environ.get("GOOGLE_ADS_CLIENT_ID", "")
    secret = GOOGLE_OAUTH_CLIENT_SECRET or os.environ.get("GOOGLE_ADS_CLIENT_SECRET", "")
    rt = req.refresh_token or os.environ.get("GOOGLE_ADS_REFRESH_TOKEN", "")
    if not all([dt, cid, secret, rt]):
        raise HTTPException(
            status_code=422,
            detail=(
                "Missing Google Ads credentials. Set GOOGLE_ADS_DEVELOPER_TOKEN, "
                "GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET and provide refresh_token."
            ),
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


def _flow_from_env(*, state: str | None = None) -> Flow:
    if not GOOGLE_OAUTH_CLIENT_ID or not GOOGLE_OAUTH_CLIENT_SECRET:
        raise HTTPException(
            status_code=500,
            detail="Missing GOOGLE_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_SECRET backend env vars.",
        )
    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": GOOGLE_OAUTH_CLIENT_ID,
                "client_secret": GOOGLE_OAUTH_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=["https://www.googleapis.com/auth/adwords"],
        state=state,
    )
    flow.redirect_uri = GOOGLE_OAUTH_REDIRECT_URI
    return flow


def _is_valid_oauth_state(state: str) -> bool:
    issued_at = _oauth_states.pop(state, None)
    if issued_at is None:
        return False
    return (time.time() - issued_at) <= OAUTH_STATE_TTL_SECONDS


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


@app.get("/auth/google/authorize")
def google_authorize() -> RedirectResponse:
    state = secrets.token_urlsafe(32)
    _oauth_states[state] = time.time()
    flow = _flow_from_env(state=state)
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    return RedirectResponse(url=auth_url, status_code=307)


@app.get("/auth/google/callback")
def google_callback(code: str = Query(default=""), state: str = Query(default="")) -> RedirectResponse:
    if not code:
        raise HTTPException(status_code=400, detail="Missing OAuth code.")
    if not state or not _is_valid_oauth_state(state):
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state.")

    flow = _flow_from_env(state=state)
    try:
        flow.fetch_token(code=code)
    except Exception as exc:  # pragma: no cover - upstream oauth errors vary
        raise HTTPException(status_code=502, detail=f"OAuth token exchange failed: {exc}") from exc

    refresh_token = (flow.credentials.refresh_token or "").strip()
    if not refresh_token:
        raise HTTPException(
            status_code=502,
            detail="No refresh token returned by Google. Re-consent is required.",
        )

    redirect_url = f"{FRONTEND_ORIGIN}/connections#refresh_token={quote(refresh_token, safe='')}"
    return RedirectResponse(url=redirect_url, status_code=307)


@app.get("/api/google-ads/accounts")
def google_ads_accounts(refresh_token: str = Query(default="")) -> dict:
    req = ReportRequest(refresh_token=refresh_token)
    dt, cid, secret, rt = _resolve_ads_credentials(req)
    accounts = list_accessible_accounts(
        developer_token=dt,
        client_id=cid,
        client_secret=secret,
        refresh_token=rt,
    )
    return {"accounts": accounts}


def _resolve_agent_config() -> tuple[str, "Provider", "ModelName"]:
    """Resolve which LLM provider/model/key to use for the generate agent.

    Reads GENERATE_PROVIDER, GENERATE_MODEL env vars. Falls back to
    google_genai / gemini-2.5-flash / GEMINI_API_KEY.
    """
    from agents.models import ModelName, Provider, resolve_model, resolve_provider

    provider = resolve_provider(os.environ.get("GENERATE_PROVIDER"))
    model = resolve_model(os.environ.get("GENERATE_MODEL"), provider)

    # Resolve API key for the chosen provider
    key_map = {
        Provider.OPENAI: "OPENAI_API_KEY",
        Provider.GOOGLE_GENAI: "GEMINI_API_KEY",
        Provider.ANTHROPIC: "ANTHROPIC_API_KEY",
    }
    api_key = os.environ.get(key_map.get(provider, "GEMINI_API_KEY"), "")
    return api_key, provider, model


@app.post("/api/generate")
async def generate(req: GenerateRequest) -> dict:
    """Interactive generate flow: fetch data for selected connections, build brief,
    synthesize with LangChain agent, and return JSON (no disk write)."""
    if not req.connections:
        raise HTTPException(status_code=422, detail="At least one connection is required.")
    if "google_ads" not in req.connections:
        raise HTTPException(
            status_code=422,
            detail="Only google_ads is supported for now.",
        )
    if not req.date_from or not req.date_to:
        raise HTTPException(status_code=422, detail="date_from and date_to are required.")

    # Resolve credentials using a ReportRequest shim
    shim = ReportRequest(
        customer_id=req.customer_id,
        refresh_token=req.refresh_token,
        login_customer_id=req.login_customer_id,
    )
    customer_id = _resolve_customer_id(shim)
    dt, cid, secret, rt = _resolve_ads_credentials(shim)
    login = (req.login_customer_id or os.environ.get("GOOGLE_ADS_LOGIN_CUSTOMER_ID", "")).strip()

    try:
        raw_payload = fetch_campaigns(
            customer_id=customer_id,
            developer_token=dt,
            client_id=cid,
            client_secret=secret,
            refresh_token=rt,
            date_from=req.date_from,
            date_to=req.date_to,
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

    brief = build_brief(raw_payload, theme="paid_ads")
    brief_dict = brief.to_dict()

    # Use the LangChain agent for synthesis (provider-agnostic)
    api_key, provider, model = _resolve_agent_config()
    if api_key:
        from agents.generate_agent import GenerateAgent

        agent = GenerateAgent(
            api_key=api_key,
            provider=provider,
            model=model,
            temperature=0.3,
        )
        synthesis = await agent.synthesize(
            goal=req.goal,
            context=req.context,
            brief_dict=brief_dict,
            raw_payload=raw_payload,
        )
        brief_dict = agent.merge_synthesis(brief_dict, synthesis)

    return brief_dict


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
