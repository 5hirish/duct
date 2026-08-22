"""Transactional email templates.

Table-based HTML with inline styles — the only layout most mail clients render
predictably — plus a plain-text alternative for every message. Templates take
plain arguments and return a ready-to-send ``EmailMessage``; they never touch
the database or config.

Keep these boring. A duct email should read like a short note from a colleague,
not a marketing blast.
"""

from __future__ import annotations

from html import escape

from service.email.sender import EmailMessage

BRAND_ORANGE = "#FF5C00"
INK = "#12151c"
MUTED = "#5b6472"
BORDER = "#e6e8ec"
PAPER = "#f6f7f9"


def _layout(*, preheader: str, body_html: str) -> str:
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


def _button(url: str, label: str) -> str:
    return (
        f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:24px 0;">'
        f'<tr><td style="background:{BRAND_ORANGE};border-radius:10px;">'
        f'<a href="{escape(url, quote=True)}" '
        f'style="display:inline-block;padding:12px 22px;font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',Helvetica,Arial,sans-serif;'
        f'font-size:15px;font-weight:600;color:#ffffff;text-decoration:none;">{escape(label)}</a>'
        f"</td></tr></table>"
    )


def _p(text_html: str, *, color: str = INK, size: int = 15) -> str:
    return (
        f'<p style="margin:0 0 14px;font-size:{size}px;line-height:1.6;color:{color};">'
        f"{text_html}</p>"
    )


def project_invitation(
    *,
    project_name: str,
    inviter_name: str,
    inviter_email: str,
    accept_url: str,
    expires_in_days: int,
    recipient_email: str,
) -> EmailMessage:
    """Invite an email address to collaborate on a project."""
    inviter = inviter_name.strip() or inviter_email
    project = project_name.strip() or "a project"
    day_word = "day" if expires_in_days == 1 else "days"

    body = (
        f'<p style="margin:0 0 6px;font-size:13px;font-weight:600;letter-spacing:.06em;'
        f'text-transform:uppercase;color:{BRAND_ORANGE};">Project invitation</p>'
        + f'<h1 style="margin:0 0 16px;font-family:Georgia,\'Times New Roman\',serif;'
        f'font-size:24px;line-height:1.3;font-weight:400;color:{INK};">'
        f"{escape(inviter)} invited you to <em>{escape(project)}</em></h1>"
        + _p(
            "You've been added as a <strong>collaborator</strong>. That means you can open the "
            "project, run audits and insights, and work on content alongside the rest of the team."
        )
        + _button(accept_url, "Accept invitation")
        + _p(
            f"The link expires in {expires_in_days} {day_word} and works only for "
            f"<strong>{escape(recipient_email)}</strong>. Sign in with that address &mdash; "
            f"you'll be asked to create an account if you don't have one yet.",
            color=MUTED,
            size=13,
        )
        + _p(
            f'Questions? Reply to this email and it reaches {escape(inviter_email)}.',
            color=MUTED,
            size=13,
        )
    )

    text = (
        f"{inviter} invited you to collaborate on {project} in duct.\n\n"
        f"Accept the invitation:\n{accept_url}\n\n"
        f"The link expires in {expires_in_days} {day_word} and works only for {recipient_email}. "
        f"Sign in with that address — you'll be asked to create an account if you don't have one yet.\n\n"
        f"Questions? Reply to this email and it reaches {inviter_email}.\n"
    )

    return EmailMessage(
        to=recipient_email,
        subject=f"{inviter} invited you to {project} on duct",
        html=_layout(
            preheader=f"{inviter} invited you to collaborate on {project}.",
            body_html=body,
        ),
        text=text,
        reply_to=inviter_email or None,
    )


def invitation_accepted(
    *,
    project_name: str,
    member_name: str,
    member_email: str,
    project_url: str,
    recipient_email: str,
) -> EmailMessage:
    """Tell the project owner that an invite was redeemed."""
    member = member_name.strip() or member_email
    project = project_name.strip() or "your project"

    body = (
        f'<h1 style="margin:0 0 16px;font-family:Georgia,\'Times New Roman\',serif;'
        f'font-size:22px;line-height:1.3;font-weight:400;color:{INK};">'
        f"{escape(member)} joined <em>{escape(project)}</em></h1>"
        + _p(
            f"{escape(member)} ({escape(member_email)}) accepted your invitation and can now "
            f"collaborate on the project."
        )
        + _button(project_url, "Open project members")
    )

    text = (
        f"{member} ({member_email}) accepted your invitation and can now collaborate on {project}.\n\n"
        f"Manage members:\n{project_url}\n"
    )

    return EmailMessage(
        to=recipient_email,
        subject=f"{member} joined {project}",
        html=_layout(preheader=f"{member} accepted your invitation.", body_html=body),
        text=text,
    )
