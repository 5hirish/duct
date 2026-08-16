"""Transactional email delivery.

One narrow seam — ``send_email`` — with two backends chosen at call time:

- **resend** when ``RESEND_API_KEY`` is set (the roadmap provider).
- **console** otherwise: the message is logged and reported as sent so local
  dev, CI, and self-hosted installs work with no vendor account. Callers never
  branch on which one is active.

Templates live in ``service.email.templates`` and return plain data
(``subject`` / ``html`` / ``text``); this module only ships them.
"""

from __future__ import annotations

from service.email.sender import EmailMessage, EmailResult, active_backend, send_email

__all__ = ["EmailMessage", "EmailResult", "active_backend", "send_email"]
