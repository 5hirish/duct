"""Lead-magnet mail: the free SEO audit report, and the execution-interest alert.

Deliberately not built on ``shell.py``. The audit report is a cold-audience
marketing email — it opens on a score, not a sentence — and the internal alert
is a plain internal note. Bending one shell around all three would cost each of
them the thing that makes it work.
"""

from __future__ import annotations

from html import escape
from typing import Any
from urllib.parse import urlparse

from service.email.message import Attachment, EmailMessage

_SERVICE_LABELS = {
    "ai_ready_fixes": "AI-ready fixes (schema, meta, llms.txt, FAQ)",
    "content_rewrites": "On-page content rewrites",
    "translation": "Translation / localization",
}


def domain_of(url: str) -> str:
    """Bare hostname from a URL string, falling back to the string itself."""
    try:
        return urlparse(url).hostname or url
    except ValueError:
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
          <td style="padding:10px 12px;border-bottom:1px solid #f3f4f6;font-size:14px;color:#0d0f1a;line-height:1.4">{escape(title)}</td>
          <td style="padding:10px 12px;border-bottom:1px solid #f3f4f6;text-align:center;white-space:nowrap">
            <span style="background:{sev_c}18;color:{sev_c};font-weight:700;font-size:10px;
                         padding:2px 8px;border-radius:20px;letter-spacing:.04em">{escape(sev_l)}</span>
          </td>
        </tr>"""

    # Build wins rows
    win_rows = ""
    for w in wins:
        win_rows += f"""
        <tr>
          <td style="padding:7px 12px;font-size:13px;color:#065f46;border-bottom:1px solid #d1fae5">
            <span style="margin-right:6px">✓</span>{escape(w)}
          </td>
        </tr>"""

    # Key signals snippet for the intro
    signals_html = ""
    if key_signals:
        signals_html = "<br>".join(
            f'<span style="color:#6b7280">→</span> {escape(sig)}' for sig in key_signals
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
<title>Your SEO audit for {escape(domain)}</title></head>
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
              Here's what we found on <strong style="color:#0d0f1a">{escape(domain)}</strong>.
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
                               margin-bottom:4px">{escape(sc_label)}</div>
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

def lead_report(
    *,
    recipient_email: str,
    site_url: str,
    report_json: dict[str, Any],
    pdf: bytes = b"",
    cc: tuple[str, ...] = (),
    sender: str = "",
) -> EmailMessage:
    """The free audit report, with the full PDF breakdown attached."""
    domain = domain_of(site_url)
    structured: dict[str, Any] = report_json.get("structured_data") or report_json or {}
    score = int(structured.get("overall_score", 0))

    attachments = []
    if pdf:
        # A filename is a path component to some mail clients; keep it flat.
        safe_domain = domain.replace("/", "_").replace(":", "")
        attachments.append(
            Attachment(
                filename=f"seo-audit-{safe_domain}.pdf",
                content=pdf,
                content_type="application/pdf",
            )
        )

    return EmailMessage(
        to=recipient_email,
        cc=cc,
        sender=sender,
        subject=f"Your free SEO audit for {domain} \u2014 {score}/100",
        html=_build_html(domain, score, structured),
        text=_build_text(domain, score, structured),
        attachments=attachments,
    )


def execution_interest(
    *,
    team: tuple[str, ...],
    lead_email: str,
    site_url: str,
    services: list[str],
    note: str | None = None,
    sender: str = "",
) -> EmailMessage:
    """Internal alert that a lead asked for paid execution. No lead-facing copy."""
    domain = domain_of(site_url)
    service_lines = (
        "".join(f"<li>{escape(_SERVICE_LABELS.get(s, s))}</li>" for s in services)
        or "<li>(none specified)</li>"
    )
    service_text = (
        "\n".join(f"  - {_SERVICE_LABELS.get(s, s)}" for s in services)
        or "  - (none specified)"
    )
    note_html = f"<p><strong>Note:</strong> {escape(note)}</p>" if note else ""
    note_text = f"\nNote: {note}\n" if note else ""

    return EmailMessage(
        to=team,
        sender=sender,
        subject=f"\U0001F680 Execution interest: {domain} ({lead_email})",
        html=(
            f"<h2>\U0001F680 Execution interest \u2014 {escape(domain)}</h2>"
            f"<p><strong>Lead:</strong> {escape(lead_email)}<br>"
            f"<strong>Site:</strong> {escape(site_url)}</p>"
            f"<p><strong>Wants:</strong></p><ul>{service_lines}</ul>"
            f"{note_html}"
        ),
        text=(
            f"Execution interest \u2014 {domain}\n\n"
            f"Lead: {lead_email}\nSite: {site_url}\n\nWants:\n{service_text}\n{note_text}"
        ),
    )
