"""The content agent's ``<duct_artifact>`` payload — parsing, and the nudge.

Framework-free on purpose: the tag is the harness-neutral half of the
artifact port (``agents/core/stream.py``), and what a payload *means* to the
content agent — a plan or a post, discriminated by ``type`` — is domain
knowledge that outlives whichever runner streams it.
"""

from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger(__name__)

# The two shapes a content artifact can take; the value of the ``type`` key.
ARTIFACT_PLAN = "plan"
ARTIFACT_POST = "post"

# A model occasionally emits slides_html with unescaped quotes, which breaks
# the JSON. The field is derived by the writer tool anyway (templates.py
# renders it from structured slides), so stripping it recovers the payload
# with nothing of value lost.
_HTML_FIELD_RE = re.compile(
    r',?\s*"slides_html"\s*:\s*"(?:[^"\\]|\\.)*"',
    re.DOTALL,
)

# One-shot recovery nudges. With planning and sub-agent dispatch the model
# occasionally ends its opening turn having analysed everything but WITHOUT
# persisting the deliverable (it never calls submit_plan / submit_post_draft).
# Nudging once to persist salvages most of these; the same pattern the audit
# runner uses for a missing <duct_artifact>.
RECOVERY_NUDGE_PLAN = (
    "You analysed everything but did not persist the plan. Emit the complete "
    '<duct_artifact>{"type":"plan", …}</duct_artifact> now and then call submit_plan '
    "with the same payload — do not run more research, just produce and save the plan."
)
RECOVERY_NUDGE_POST = (
    "You analysed everything but did not persist the post draft. Emit the complete "
    '<duct_artifact>{"type":"post", …}</duct_artifact> now and then call '
    "submit_post_draft with the same payload — do not run more research, just "
    "produce and save the draft."
)


def parse_artifact_json(raw: str) -> dict | None:
    """Parse the JSON inside ``<duct_artifact>``; None when nothing usable.

    Accepts a markdown fence around the object (some models love them) and
    falls back to stripping ``slides_html`` when unescaped HTML quotes broke
    the parse. Never raises: the runner logs and continues, and the writer
    tool re-validates whatever the model actually submits.
    """
    candidate = raw.strip()
    fenced = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", candidate)
    if fenced:
        candidate = fenced.group(1).strip()
    try:
        return json.loads(candidate)
    except Exception:  # noqa: BLE001 - try the recovery path
        pass
    stripped = _HTML_FIELD_RE.sub("", candidate)
    try:
        payload = json.loads(stripped)
        payload.setdefault("slides_html", "")
        return payload
    except Exception as exc:  # noqa: BLE001 - reported, never raised
        logger.warning("content: <duct_artifact> JSON parse failed: %s", exc)
        return None


__all__ = [
    "ARTIFACT_PLAN",
    "ARTIFACT_POST",
    "RECOVERY_NUDGE_PLAN",
    "RECOVERY_NUDGE_POST",
    "parse_artifact_json",
]
