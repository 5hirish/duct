"""Tiered-autonomy policy — the single decision point for auto-apply.

An agent may *propose* any registered operation, but whether a proposed set
applies without a human click is decided here, in code, once:

- ``change_auto_eligible`` — per change: on the explicit allowlist, executor
  is non-destructive AND has a rollback, no guardrail violations, preview
  succeeded.
- ``should_auto_apply`` — per set: agent-sourced, project autonomy is
  ``assisted``, and **every** change is eligible. Mixed sets never auto-apply
  (one destructive change holds the whole set for review).

The destructive gate is absolute — there is no configuration that lets a
destructive/publish op auto-apply, and no agent-facing approve/apply tool
exists (see agents/tools/execution_tools.py). Approval is human-only by
construction.
"""

from __future__ import annotations

from typing import Any

from models.execution import AUTONOMY_ASSISTED
from models.project import Project
from service.execution.registry import ExecutorSpec

# Ops that MAY auto-apply under assisted autonomy. Deliberately narrow:
# reversible metadata/list edits and workspace-scoped (non-live) GTM edits.
#
# Budget and bid changes (google_ads.set_campaign_budget / set_campaign_bidding)
# are reversible but move money — they stay OFF the allowlist until numeric
# guardrail limits (max % delta, absolute caps) exist. Same for status flips
# (pausing a campaign stops spend instantly). Proposing them still works; they
# just always wait for approval.
AUTO_APPLY_ALLOWLIST: frozenset[str] = frozenset(
    {
        "google_ads.add_negative_keywords",
        "google_ads.add_keywords",
        "ga4.create_key_event",
        "ga4.create_audience",
        # Workspace-only edits — invisible to production until a separate,
        # always-human-approved gtm.publish_version.
        "gtm.upsert_tag",
        "gtm.upsert_variable",
    }
)


def change_auto_eligible(spec: ExecutorSpec, change: dict[str, Any]) -> bool:
    """One change may auto-apply: allowlisted, reversible, clean."""
    if spec.op_type not in AUTO_APPLY_ALLOWLIST:
        return False
    if spec.destructive:  # absolute gate, independent of the allowlist
        return False
    if spec.rollback is None:
        return False
    if change.get("guardrail_violations"):
        return False
    if (change.get("preview") or {}).get("error"):
        return False
    return True


def should_auto_apply(
    project: Project | None,
    source: str,
    changes: list[dict[str, Any]],
) -> bool:
    """Whole-set verdict. Requires an agent source, assisted autonomy on the
    project, and every change individually eligible (``auto_eligible`` computed
    at propose time). An empty or partially-eligible set never auto-applies."""
    if source != "agent":
        return False
    if project is None or project.autonomy_level != AUTONOMY_ASSISTED:
        return False
    if not changes:
        return False
    return all(change.get("auto_eligible") for change in changes)
