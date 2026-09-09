"""Transactional email.

One narrow seam — ``send_email`` — over swappable providers in
``service.email.providers``; see ``sender.py`` for how one is chosen. Callers
never branch on which is active, and no module outside ``providers/`` names a
vendor.

Templates live in ``service.email.templates`` and return a ready-to-send
``EmailMessage``; they never touch the database, config, or the network.
"""

from __future__ import annotations

from service.email.message import Attachment, EmailMessage, EmailResult
from service.email.sender import PROVIDERS, active_backend, send_email

__all__ = [
    "PROVIDERS",
    "Attachment",
    "EmailMessage",
    "EmailResult",
    "active_backend",
    "send_email",
]
