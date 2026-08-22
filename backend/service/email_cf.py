"""Cloudflare Email Service — lead report delivery.

Sends a warm, Duct-branded email with the SEO audit PDF attached.
Uses the Cloudflare Email Service REST API (httpx, already installed).
"""

from __future__ import annotations

import base64
import logging
from html import escape as _esc
from typing import Any
from urllib.parse import urlparse

import httpx

from config import get_configs
from service.report_pdf import generate_report_pdf

logger = logging.getLogger(__name__)


def _domain(url: str) -> str:
    """Extract bare hostname from a URL string."""
    try:
        return urlparse(url).hostname or url
    except Exception:
        return url


def _score_label(score: int) -> str:
    if score >= 85:
        return "Healthy"
    if score >= 70:
        return "Good"
    if score >= 55:
        return "Needs Work"
    return "Critical"


def _score_color(score: int) -> str:
    if score >= 85:
        return "#10b981"
    if score >= 70:
        return "#f59e0b"
    return "#ef4444"


def _build_html(domain: str, score: int, structured: dict[str, Any]) -> str:
    """Build the Duct-branded HTML email body from StructuredAuditData fields."""
    top_priorities = structured.get("top_priorities", [])[:3]
    wins = structured.get("wins", [])[:2]
    key_signals = structured.get("key_signals", [])[:2]

    sc_color = _score_color(score)
    sc_label = _score_label(score)

    _SEV_COLOR = {
        "fail":        "#ef4444",
        "warn":        "#f59e0b",
        "opportunity": "#f97316",
        "pass":        "#10b981",
    }
    _SEV_LABEL = {
        "fail":        "ERROR",
        "warn":        "WARNING",
        "opportunity": "OPP",
        "pass":        "PASS",
    }

    # Build priority rows
    priority_rows = ""
    for p in top_priorities:
        sev = p.get("severity", "")
        sev_c = _SEV_COLOR.get(sev, "#6b7280")
        sev_l = _SEV_LABEL.get(sev, sev.upper())
        title = p.get("title", "")
        priority_rows += f"""
        <tr>
          <td style="padding:10px 12px;border-bottom:1px solid #f3f4f6;font-size:14px;color:#0d0f1a;line-height:1.4">{_esc(title)}</td>
          <td style="padding:10px 12px;border-bottom:1px solid #f3f4f6;text-align:center;white-space:nowrap">
            <span style="background:{sev_c}18;color:{sev_c};font-weight:700;font-size:10px;
                         padding:2px 8px;border-radius:20px;letter-spacing:.04em">{_esc(sev_l)}</span>
          </td>
        </tr>"""

    # Build wins rows
    win_rows = ""
    for w in wins:
        win_rows += f"""
        <tr>
          <td style="padding:7px 12px;font-size:13px;color:#065f46;border-bottom:1px solid #d1fae5">
            <span style="margin-right:6px">✓</span>{_esc(w)}
          </td>
        </tr>"""

    # Key signals snippet for the intro
    signals_html = ""
    if key_signals:
        signals_html = "<br>".join(
            f'<span style="color:#6b7280">→</span> {_esc(sig)}' for sig in key_signals
        )
        signals_html = f"""
        <p style="margin:16px 0 0;font-size:13px;color:#374151;line-height:1.7;
                  background:#f9fafb;border-left:3px solid #ff5c00;
                  padding:10px 14px;border-radius:0 6px 6px 0">
          {signals_html}
        </p>"""

    priorities_section = ""
    if priority_rows:
        priorities_section = f"""
      <!-- Fix These First -->
      <p style="margin:28px 0 8px;font-size:15px;font-weight:700;color:#0d0f1a">
        Fix these first
      </p>
      <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;
             border:1px solid #e5e7eb;border-radius:8px;overflow:hidden">
        <thead>
          <tr style="background:#0d0f1a">
            <th style="padding:8px 12px;text-align:left;font-size:10px;font-weight:700;
                       color:#f4ece2;letter-spacing:.06em;text-transform:uppercase">Finding</th>
            <th style="padding:8px 12px;text-align:center;font-size:10px;font-weight:700;
                       color:#f4ece2;letter-spacing:.06em;text-transform:uppercase;width:90px">Severity</th>
          </tr>
        </thead>
        <tbody>{priority_rows}</tbody>
      </table>"""

    wins_section = ""
    if win_rows:
        wins_section = f"""
      <!-- Wins -->
      <p style="margin:24px 0 8px;font-size:15px;font-weight:700;color:#0d0f1a">
        What's working well
      </p>
      <table width="100%" cellpadding="0" cellspacing="0"
             style="border-collapse:collapse;border:1px solid #d1fae5;
                    border-radius:8px;overflow:hidden;background:#f0fdf4">
        <tbody>{win_rows}</tbody>
      </table>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Your SEO audit for {_esc(domain)}</title></head>
<body style="margin:0;padding:0;background:#f3f4f6;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif">

  <!-- Outer wrapper -->
  <table width="100%" cellpadding="0" cellspacing="0">
    <tr><td align="center" style="padding:32px 16px">

      <!-- Card -->
      <table width="600" cellpadding="0" cellspacing="0"
             style="max-width:600px;background:#ffffff;border-radius:12px;
                    overflow:hidden;box-shadow:0 1px 8px rgba(0,0,0,.08)">

        <!-- ── Header ── -->
        <tr>
          <td style="background:#0d0f1a;padding:18px 28px">
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr>
                <td style="font-size:18px;font-weight:800;color:#ffffff;
                           letter-spacing:-.02em">DUCT</td>
                <td align="right" style="font-size:12px;color:#ff5c00;
                                          font-weight:600">getduct.ai</td>
              </tr>
            </table>
          </td>
        </tr>
        <!-- orange rule -->
        <tr><td style="height:3px;background:linear-gradient(90deg,#ff5c00,#ff8c42 60%,transparent)"></td></tr>

        <!-- ── Body ── -->
        <tr>
          <td style="padding:32px 28px 28px">

            <p style="margin:0 0 16px;font-size:16px;color:#0d0f1a">Hi there 👋</p>

            <p style="margin:0 0 8px;font-size:15px;color:#374151;line-height:1.6">
              Here's what we found on <strong style="color:#0d0f1a">{_esc(domain)}</strong>.
            </p>
            {signals_html}

            <!-- Score card -->
            <table width="100%" cellpadding="0" cellspacing="0"
                   style="margin:24px 0;border:1px solid #e5e7eb;border-radius:10px;
                          overflow:hidden;background:#f9fafb">
              <tr>
                <td style="padding:20px 24px;border-right:1px solid #e5e7eb;
                           text-align:center;width:110px">
                  <div style="font-size:48px;font-weight:800;color:{sc_color};
                               line-height:1">{score}</div>
                  <div style="font-size:11px;color:#6b7280;margin-top:2px">/ 100</div>
                </td>
                <td style="padding:20px 24px">
                  <div style="font-size:16px;font-weight:700;color:{sc_color};
                               margin-bottom:4px">{_esc(sc_label)}</div>
                  <div style="font-size:13px;color:#6b7280;line-height:1.5">
                    The full breakdown — 9 SEO categories, a prioritised action plan,
                    and specific fixes — is attached as a PDF.
                  </div>
                </td>
              </tr>
            </table>

            {priorities_section}
            {wins_section}

            <!-- CTA -->
            <p style="margin:28px 0 0;font-size:14px;color:#374151;line-height:1.7">
              If you want to go deeper — competitor analysis, keyword gaps, and a
              90-day action plan tailored to your goals — just reply to this email
              or head to
              <a href="https://getduct.ai" style="color:#ff5c00;font-weight:600;
                 text-decoration:none">getduct.ai</a>.
            </p>

            <p style="margin:24px 0 0;font-size:14px;color:#374151">
              — Shirish &amp; Marvin<br>
              <span style="color:#6b7280;font-size:13px">Duct · hello@getduct.ai</span>
            </p>

          </td>
        </tr>

        <!-- ── Footer ── -->
        <tr>
          <td style="background:#f4ece2;padding:14px 28px;text-align:center">
            <p style="margin:0;font-size:11px;color:#6b7280">
              Free SEO audit · No credit card needed ·
              <a href="https://getduct.ai/seo-audit" style="color:#ff5c00;text-decoration:none">
                getduct.ai/seo-audit
              </a>
            </p>
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""


def _build_text(domain: str, score: int, structured: dict[str, Any]) -> str:
    """Plain-text fallback."""
    top = structured.get("top_priorities", [])[:3]
    wins = structured.get("wins", [])[:2]
    priority_lines = "\n".join(
        f"  {p.get('rank', i+1)}. {p.get('title', '')} [{p.get('severity','').upper()}]"
        for i, p in enumerate(top)
    )
    win_lines = "\n".join(f"  ✓ {w}" for w in wins)

    return f"""Hi there 👋

Here's what we found on {domain}.

Score: {score}/100 — {_score_label(score)}

Top issues to fix:
{priority_lines or '  (see attached PDF)'}

What's working well:
{win_lines or '  (see attached PDF)'}

The full breakdown is attached as a PDF — it covers all 9 SEO categories,
a prioritised action plan, and specific fixes.

If you want to go deeper, reply to this email or visit getduct.ai.

— Shirish & Marvin
Duct · hello@getduct.ai
──────────────────────────────
Free SEO audit · getduct.ai/seo-audit
"""


async def send_lead_report_email(
    to_email: str,
    site_url: str,
    report_json: dict[str, Any],
) -> bool:
    """Send the branded audit email with PDF attachment via Cloudflare Email Service.

    Returns True on success, False on failure. Never raises — errors are logged.
    """
    cfg = get_configs()
    if not cfg.cloudflare_email_api_token or not cfg.cloudflare_account_id:
        logger.warning("email: CLOUDFLARE_EMAIL_API_TOKEN or CLOUDFLARE_ACCOUNT_ID not set — skipping")
        return False

    domain = _domain(site_url)
    structured: dict[str, Any] = report_json.get("structured_data") or report_json or {}
    score = int(structured.get("overall_score", 0))

    try:
        pdf_bytes = generate_report_pdf(report_json)
    except Exception:
        logger.exception("email: PDF generation failed for %s", site_url)
        pdf_bytes = b""

    cc_list = [a.strip() for a in cfg.lead_email_cc.split(",") if a.strip()]

    payload: dict[str, Any] = {
        "from": cfg.lead_email_from or cfg.email_from,
        "to": [to_email],
        "subject": f"Your free SEO audit for {domain} — {score}/100",
        "html": _build_html(domain, score, structured),
        "text": _build_text(domain, score, structured),
    }
    if cc_list:
        payload["cc"] = cc_list
    if pdf_bytes:
        safe_domain = domain.replace("/", "_").replace(":", "")
        payload["attachments"] = [{
            "filename": f"seo-audit-{safe_domain}.pdf",
            "content": base64.b64encode(pdf_bytes).decode(),
            "type": "application/pdf",
        }]

    url = (
        f"https://api.cloudflare.com/client/v4/accounts"
        f"/{cfg.cloudflare_account_id}/email-service/send"
    )
    headers = {
        "Authorization": f"Bearer {cfg.cloudflare_email_api_token}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code in (200, 201, 202):
            logger.info("email: sent to %s (cc %s) — %s", to_email, cc_list, site_url)
            return True
        logger.warning(
            "email: Cloudflare returned %d for %s — %s",
            resp.status_code, to_email, resp.text[:300],
        )
        return False
    except Exception:
        logger.exception("email: failed to send to %s", to_email)
        return False


_SERVICE_LABELS = {
    "ai_ready_fixes": "AI-ready fixes (schema, meta, llms.txt, FAQ)",
    "content_rewrites": "On-page content rewrites",
    "translation": "Translation / localization",
}


async def send_execution_interest_notification(
    lead_email: str,
    site_url: str,
    services: list[str],
    note: str | None = None,
) -> bool:
    """Notify the internal team that a lead requested paid execution.

    Plain internal alert sent to ``lead_email_cc`` (the team). No PDF, no lead-facing copy.
    Returns True on success, False on failure. Never raises — errors are logged.
    """
    cfg = get_configs()
    if not cfg.cloudflare_email_api_token or not cfg.cloudflare_account_id:
        logger.warning("email: execution-interest notify skipped — Cloudflare email not configured")
        return False

    team = [a.strip() for a in cfg.lead_email_cc.split(",") if a.strip()]
    if not team:
        logger.warning("email: execution-interest notify skipped — no team recipients (LEAD_EMAIL_CC empty)")
        return False

    domain = _domain(site_url)
    service_lines = "".join(
        f"<li>{_esc(_SERVICE_LABELS.get(s, s))}</li>" for s in services
    ) or "<li>(none specified)</li>"
    service_text = "\n".join(f"  - {_SERVICE_LABELS.get(s, s)}" for s in services) or "  - (none specified)"
    note_html = f"<p><strong>Note:</strong> {_esc(note)}</p>" if note else ""
    note_text = f"\nNote: {note}\n" if note else ""

    html = (
        f"<h2>🚀 Execution interest — {_esc(domain)}</h2>"
        f"<p><strong>Lead:</strong> {_esc(lead_email)}<br>"
        f"<strong>Site:</strong> {_esc(site_url)}</p>"
        f"<p><strong>Wants:</strong></p><ul>{service_lines}</ul>"
        f"{note_html}"
    )
    text = (
        f"Execution interest — {domain}\n\n"
        f"Lead: {lead_email}\nSite: {site_url}\n\nWants:\n{service_text}\n{note_text}"
    )

    payload: dict[str, Any] = {
        "from": cfg.lead_email_from or cfg.email_from,
        "to": team,
        "subject": f"🚀 Execution interest: {domain} ({lead_email})",
        "html": html,
        "text": text,
    }

    url = (
        f"https://api.cloudflare.com/client/v4/accounts"
        f"/{cfg.cloudflare_account_id}/email-service/send"
    )
    headers = {
        "Authorization": f"Bearer {cfg.cloudflare_email_api_token}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code in (200, 201, 202):
            logger.info("email: execution-interest notify sent to team for %s (%s)", lead_email, domain)
            return True
        logger.warning(
            "email: execution-interest notify returned %d — %s",
            resp.status_code, resp.text[:300],
        )
        return False
    except Exception:
        logger.exception("email: execution-interest notify failed for %s", lead_email)
        return False
