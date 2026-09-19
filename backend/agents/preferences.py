"""Shared UserPreferences model — applied across all Duct agent types.

These fields are agent-agnostic: they apply equally to SEO audit,
organic growth insights, paid ads, blog writer, and future agents.
Stored client-side as `duct_user_preferences` in localStorage and
sent as a top-level field on every agent request.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class UserPreferences(BaseModel):
    model_config = ConfigDict(extra="ignore")  # forward-compatible — ignore unknown keys

    role: str = ""
    # One of: "Founder / CEO", "Executive (CMO, VP, Director)", "Product Manager",
    #         "Growth Manager", "SEO / Content Lead", "Developer / Engineer",
    #         "Consultant / Agency", "Other"

    communication_style: Literal["executive", "practitioner", "technical"] = "practitioner"
    # executive    — strategic summaries, business impact, dollar amounts
    # practitioner — actionable specifics, signal-driven (default)
    # technical    — deep technical detail, developer-friendly

    report_depth: Literal["summary", "balanced", "detailed"] = "balanced"
    # summary  — key points only
    # balanced — full context with recommendations (default)
    # detailed — comprehensive, all supporting evidence

    primary_outcome: Literal["revenue", "efficiency", "risk", "quality", ""] = ""
    # revenue    — Revenue & Growth
    # efficiency — Efficiency & Speed
    # risk       — Risk & Compliance
    # quality    — Quality & Standards

    # How hard the model should think, in Duct's words rather than the
    # provider's. Empty = the model's own default, which is deliberate: the
    # four providers default differently and normalising them would change the
    # cost and quality of every existing project. See agents/thinking.py.
    thinking: Literal["", "quick", "balanced", "deep", "exhaustive"] = ""

    # Which tier the run's main job starts on — the composer's per-run lift
    # over Duct's own job→tier assignment (agents/tiers.py). Empty = Duct's
    # pick. A lift only moves the starting rung: a tier that cannot run still
    # steps down the same ladder.
    tier: Literal["", "heavy", "standard", "light"] = ""

    context_compression: bool = True
    # Whether a connector payload is folded to typed CSV before it is handed to
    # the model. On by default because off is not "the model sees everything" —
    # off is the mid-structure cut in agents/insights/data_tools.py, which on a
    # large pull drops rows the brief then reasons without. The fold is
    # lossless, so this changes how the rows are written, never which numbers
    # they carry. It stays a preference rather than a constant only so someone
    # who suspects the shape can rule it out in one click.

    preferred_artifact_format: Literal["markdown", "html", "auto"] = "html"
    # html     — a self-contained styled page with its own charts (default):
    #            the thing that gets forwarded; costs more output tokens
    # markdown — a written brief: faster and cheaper, renders in-app, copies
    #            into a doc, diffs cleanly between versions
    # auto     — the agent picks per deliverable, and says which it chose
    #
    # "dashboard" (the block renderers under app/src/components/insight-blocks)
    # is deliberately absent: those blocks resolve their rows from an assembled
    # source bundle that only the legacy synthesis pipeline produces, so an
    # agent-written dashboard artifact today would render mostly-empty blocks.
    # It returns with that pipeline in the phase that retires it.
