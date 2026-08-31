"""Tiered-autonomy policy — the single decision point for auto-apply.

An agent may *propose* any registered operation, but whether a proposed set
applies without a human click is decided here, in code, once:

- ``change_auto_eligible`` — per change: on the explicit allowlist, executor
  is non-destructive AND has a rollback, no guardrail violations, preview
  succeeded.
- ``should_auto_apply`` — per set: agent-sourced, project autonomy is
  ``assisted`` or ``auto``, and **every** change is eligible. Mixed sets never
  auto-apply (one destructive change holds the whole set for review).

The destructive gate is absolute — there is no configuration that lets a
destructive/publish op auto-apply, and no agent-facing approve/apply tool
exists (see agents/tools/execution_tools.py). Approval is human-only by
construction.

``auto`` is a posture, not a wider allowlist. It changes how much the agent
interrupts; ``AUTO_APPLY_ALLOWLIST`` and the destructive gate are byte-identical
at ``assisted`` and ``auto``. ``effective_autonomy`` is the second half of that
statement: a model outside ``AUTO_POSTURE_MODELS`` runs an ``auto`` project at
``assisted``, so an unattended loop on a cheap model is not *invited*. It is a
prompt-level mitigation and it says so — the gates below hold regardless of
which model is driving, which is what actually makes this safe.
"""

from __future__ import annotations

from typing import Any

from models.execution import AUTO_APPLY_LEVELS, AUTONOMY_ASSISTED, AUTONOMY_AUTO, normalize_autonomy
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
        # A dated note on the analytics timeline — no data moves, deleting it
        # is the rollback. The framework annotating its own applied changes
        # is the point.
        "mixpanel.create_annotation",
    }
)


# Models trusted to run an `auto` project's reduced-interruption posture.
# Matched on a prefix, so a dated snapshot of an allowlisted family qualifies
# without an edit here. Deliberately a short list of frontier models: `auto`
# means "state an assumption instead of asking", and a model that assumes badly
# and rarely asks is the failure this list exists to avoid inviting.
AUTO_POSTURE_MODEL_PREFIXES: tuple[str, ...] = (
    "claude-opus-",
    "claude-sonnet-",
    "gpt-5",
    "gemini-3-pro",
)


def model_allows_auto_posture(model: str) -> bool:
    """True when this model may run at the `auto` posture."""
    name = (getattr(model, "value", model) or "").strip().lower()
    return bool(name) and name.startswith(AUTO_POSTURE_MODEL_PREFIXES)


def effective_autonomy(configured: str | None, model: str = "") -> str:
    """The level a run actually operates at.

    A model can only ever *lower* the posture, never raise it: an `auto`
    project on a model outside the allowlist runs at `assisted`, which means
    it goes back to asking when a question would change the conclusion. It
    does not change what may auto-apply — that is the same at both levels.
    """
    level = normalize_autonomy(configured)
    if level == AUTONOMY_AUTO and not model_allows_auto_posture(model):
        return AUTONOMY_ASSISTED
    return level


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
    """Whole-set verdict. Requires an agent source, autonomy at ``assisted`` or
    ``auto`` on the project, and every change individually eligible
    (``auto_eligible`` computed at propose time). An empty or
    partially-eligible set never auto-applies.

    Note what is NOT consulted: the model. Raising a project to ``auto`` buys
    fewer interruptions, not a wider allowlist, so this function's answer is
    the same at both levels — which is why ``effective_autonomy`` lives
    alongside it rather than inside it.
    """
    if source != "agent":
        return False
    if project is None:
        return False
    if normalize_autonomy(project.autonomy_level) not in AUTO_APPLY_LEVELS:
        return False
    if not changes:
        return False
    return all(change.get("auto_eligible") for change in changes)
