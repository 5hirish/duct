"""Backwards-compatible aliases for the SEO Audit Agent's event vocabulary.

Event/step names are now defined once in agents/core/events.py and shared across
all agent types (audit emits the subset it supports). These aliases keep existing
imports working; the frontend still mirrors the same string values in
app/src/lib/auditEvents.js.
"""

from __future__ import annotations

from agents.core.events import STEP_LABELS, AgentEvent, AgentStep, StepStatus

# Aliases — same class objects; existing `AuditEvent.X` / `AuditStep.X` access works.
AuditEvent = AgentEvent
AuditStep = AgentStep

__all__ = ["STEP_LABELS", "AuditEvent", "AuditStep", "StepStatus"]
