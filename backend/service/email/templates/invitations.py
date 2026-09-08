"""Project collaboration mail: the invitation, and its receipt."""

from __future__ import annotations

from html import escape

from service.email.message import EmailMessage
from service.email.templates.shell import BRAND_ORANGE, INK, MUTED, button, layout, p

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
        + p(
            "You've been added as a <strong>collaborator</strong>. That means you can open the "
            "project, run audits and insights, and work on content alongside the rest of the team."
        )
        + button(accept_url, "Accept invitation")
        + p(
            f"The link expires in {expires_in_days} {day_word} and works only for "
            f"<strong>{escape(recipient_email)}</strong>. Sign in with that address &mdash; "
            f"you'll be asked to create an account if you don't have one yet.",
            color=MUTED,
            size=13,
        )
        + p(
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
        html=layout(
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
        + p(
            f"{escape(member)} ({escape(member_email)}) accepted your invitation and can now "
            f"collaborate on the project."
        )
        + button(project_url, "Open project members")
    )

    text = (
        f"{member} ({member_email}) accepted your invitation and can now collaborate on {project}.\n\n"
        f"Manage members:\n{project_url}\n"
    )

    return EmailMessage(
        to=recipient_email,
        subject=f"{member} joined {project}",
        html=layout(preheader=f"{member} accepted your invitation.", body_html=body),
        text=text,
    )
