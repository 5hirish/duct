"""Message bodies, grouped by the audience they speak to.

Templates take plain arguments and return a ready-to-send ``EmailMessage``.
They never touch the database, config, or the network — which is what lets a
test assert on rendered copy without a provider, and what keeps the choice of
provider out of the copy entirely.
"""

from __future__ import annotations

from service.email.templates.invitations import invitation_accepted, project_invitation
from service.email.templates.lead import execution_interest, lead_report

__all__ = [
    "execution_interest",
    "invitation_accepted",
    "lead_report",
    "project_invitation",
]
