"""The shared visual shell for duct's own transactional mail.

Table-based HTML with inline styles — the only layout most mail clients render
predictably. Keep it boring: a duct email should read like a short note from a
colleague, not a marketing blast.

The lead-magnet audit report deliberately does not use this shell. It is a
cold-audience marketing email with a different job, and forcing one layout to
serve both would make each worse; see ``lead.py``.
"""

from __future__ import annotations

from html import escape

BRAND_ORANGE = "#FF5C00"
INK = "#12151c"
MUTED = "#5b6472"
BORDER = "#e6e8ec"
PAPER = "#f6f7f9"


def layout(*, preheader: str, body_html: str) -> str:
    """Wrap body markup in the shared duct shell (logo, card, footer)."""
    return f"""\
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
</head>
<body style="margin:0;padding:0;background:{PAPER};">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;">{escape(preheader)}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:{PAPER};padding:32px 16px;">
<tr><td align="center">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:520px;">
<tr><td style="padding-bottom:20px;">
<span style="font-family:Georgia,'Times New Roman',serif;font-size:20px;color:{INK};letter-spacing:-.02em;">duct</span><span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:{BRAND_ORANGE};margin-left:4px;"></span>
</td></tr>
<tr><td style="background:#ffffff;border:1px solid {BORDER};border-radius:14px;padding:28px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;">
{body_html}
</td></tr>
<tr><td style="padding-top:18px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;font-size:12px;color:{MUTED};line-height:1.6;">
You received this email because someone using duct entered your address.
If it wasn't meant for you, you can ignore it &mdash; no account is created until you sign in.
</td></tr>
</table>
</td></tr>
</table>
</body>
</html>"""


def button(url: str, label: str) -> str:
    return (
        f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:24px 0;">'
        f'<tr><td style="background:{BRAND_ORANGE};border-radius:10px;">'
        f'<a href="{escape(url, quote=True)}" '
        f'style="display:inline-block;padding:12px 22px;font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',Helvetica,Arial,sans-serif;'
        f'font-size:15px;font-weight:600;color:#ffffff;text-decoration:none;">{escape(label)}</a>'
        f"</td></tr></table>"
    )


def p(text_html: str, *, color: str = INK, size: int = 15) -> str:
    return (
        f'<p style="margin:0 0 14px;font-size:{size}px;line-height:1.6;color:{color};">'
        f"{text_html}</p>"
    )
