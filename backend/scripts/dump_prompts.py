#!/usr/bin/env python3
"""Render every agent's prompts to one reviewable Markdown file.

The problem this solves is not where prompts are stored. It is that you cannot
read what a model actually receives without running a session: the insights
system prompt is ~4,700 tokens of composed text, and the user turn is assembled
at runtime from blocks whose order is a cache decision. A reviewer looking at a
pull request sees a Python string edit and has to assemble the result in their
head.

So this renders the assembled result and checks it in. Three things follow that
a prompt file format would not have given us:

  * Prompts read like docs, because they are docs.
  * A prompt change lands in the diff **as prose**. The Python diff says a
    constant moved; this one says what the model will now be told.
  * ``--check`` fails when the file is stale, so it cannot drift the way the
    old root ``AGENTS.md`` did.

**Output must be deterministic.** No timestamps, no run ids, no dict iteration
order that depends on insertion — a non-deterministic byte makes ``--check``
fail on every unrelated pull request, and a check that cries wolf is worse than
no check. The fixtures below are constants for the same reason.

Usage:
    python scripts/dump_prompts.py            # write the file
    python scripts/dump_prompts.py --check    # fail if it would change
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND = REPO_ROOT / "backend"
OUTPUT = REPO_ROOT / "docs" / "engineering" / "agent-prompts.md"

if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


# ---------------------------------------------------------------------------
# Fixtures — a plausible operator and project, held constant
# ---------------------------------------------------------------------------
#
# Deliberately filled in rather than empty. An empty profile renders no
# ``<user_context>`` at all (that is the point of the block), so an empty
# fixture would document the one case where the interesting part is missing.
# The name is invented; using a real customer's would put their details in a
# public repository.

FIXTURE_PROFILE = dict(
    display_name="Zerbina Quirkwood",
    role="Product Manager",
    writing_preset="executive",
    communication_language="Spanish",
    timezone="Europe/Madrid",
    notes="Lead with the money. Tell me what you could not verify.",
)

FIXTURE_BUSINESS = dict(
    business_name="Northwind Tools",
    business_description="Scheduling software for independent trades.",
    industry="B2B SaaS",
    business_model="Subscription",
    audience_segment="Solo electricians and plumbers",
    business_goals="Cut blended CAC below 90 days payback",
    competitors=["Jobber", "ServiceTitan"],
    target_keywords=["trade scheduling app", "electrician invoicing"],
    monthly_budget=12000.0,
    target_cpa=85.0,
    primary_organic_kpi="Signups from organic",
)

FIXTURE_MEMORY = (
    "<project_memory>\n"
    "Decision: paused Performance Max in June, CPA fell 22%.\n"
    "Fact: trial-to-paid sits at 11% and has not moved in three months.\n"
    "</project_memory>"
)

FIXTURE_DATA_SOURCES = (
    "<data_sources>\n"
    "google_ads: bound (Northwind — Search)\n"
    "ga4: available (no property chosen)\n"
    "gsc: not_connected\n"
    "</data_sources>"
)

FIXTURE_REQUEST = "Why did CPA jump last week?"

#: Rough token estimate. Not a tokenizer: the number is here to show which
#: prompts are large enough for the cache minimum (~1024 tokens) and which are
#: growing, and a tokenizer dependency for that is not worth the install.
CHARS_PER_TOKEN = 3.6


def approx_tokens(text: str) -> int:
    return int(len(text) / CHARS_PER_TOKEN)


def fenced(text: str) -> str:
    """Fence a prompt without its own backticks ending the block."""
    fence = "`" * max(3, _longest_backtick_run(text) + 1)
    return f"{fence}text\n{text}\n{fence}"


def _longest_backtick_run(text: str) -> int:
    longest = run = 0
    for ch in text:
        run = run + 1 if ch == "`" else 0
        longest = max(longest, run)
    return longest


def section(title: str, body: str, *, level: int = 3) -> str:
    return f"{'#' * level} {title}\n\n{body}\n"


# ---------------------------------------------------------------------------
# Per-agent renderers
# ---------------------------------------------------------------------------

def _profile():
    from service.profile import Profile

    return Profile(**FIXTURE_PROFILE)


def _business():
    from agents.core.context import BusinessContext

    return BusinessContext(**FIXTURE_BUSINESS)


def render_insights() -> str:
    from agents.core.voice import user_context_block
    from agents.core.context import format_business_context
    from agents.insights.prompts.autonomous import (
        build_insights_system_prompt,
        build_insights_user_prompt,
    )

    out = []
    system = build_insights_system_prompt()
    out.append(section(
        f"System prompt · ~{approx_tokens(system):,} tokens",
        "Cache-stable: identical for every account, so it is the shared prefix.\n\n"
        + fenced(system),
    ))
    turn = build_insights_user_prompt(
        prompt=FIXTURE_REQUEST,
        business_context=format_business_context(_business()),
        user_context=user_context_block(_profile()),
        memory=FIXTURE_MEMORY,
        data_sources=FIXTURE_DATA_SOURCES,
    )
    out.append(section(
        f"Opening user turn · ~{approx_tokens(turn):,} tokens",
        fenced(turn),
    ))
    return "\n".join(out)


def render_audit() -> str:
    from agents.audit.prompts import build_audit_user_prompt, build_system_prompt
    from agents.audit.schema import CrawlPlan, CrawlResult
    from agents.preferences import UserPreferences

    out = []
    system = build_system_prompt()
    out.append(section(
        f"System prompt · ~{approx_tokens(system):,} tokens",
        fenced(system),
    ))
    # Appended to the system prompt only when the in-depth audit of a project
    # mounts FetchData (agents/audit/v1/runner.mounts_connected_data).
    from agents.audit.prompts import _CONNECTED_DATA_SECTION

    out.append(section(
        f"In-depth audit addition · ~{approx_tokens(_CONNECTED_DATA_SECTION):,} tokens",
        fenced(_CONNECTED_DATA_SECTION.rstrip()),
    ))
    turn = build_audit_user_prompt(
        CrawlResult(plan=CrawlPlan(root_url="https://northwind.example")),
        _business(),
        UserPreferences(communication_style="executive", report_depth="summary"),
        extra_context=FIXTURE_MEMORY,
        profile=_profile(),
    )
    # The crawl payload is this run's own data and dwarfs everything shared;
    # cutting it keeps the file about the part a reviewer can act on.
    head, sep, _ = turn.partition("<crawl_data>")
    body = head + (sep and "<crawl_data>\n  … this run's crawl, elided …\n</crawl_data>")
    out.append(section(
        f"Opening user turn · ~{approx_tokens(turn):,} tokens (crawl elided)",
        fenced(body.rstrip()),
    ))
    return "\n".join(out)


def render_content() -> str:
    from agents.content.prompts import build_orchestrator_system_prompt
    from agents.content.schema import ContentBrandContext

    out = []
    for mode in ("plan_month", "draft_post"):
        # The brand argument is accepted for backwards compatibility and
        # ignored: brand context rides in the first user message, precisely so
        # this prefix stays cache-stable. A stub satisfies the signature.
        system = build_orchestrator_system_prompt(
            ContentBrandContext(project_id="00000000-0000-0000-0000-000000000000"),
            mode,
            vision=True,
        )
        out.append(section(
            f"System prompt · mode={mode} · ~{approx_tokens(system):,} tokens",
            fenced(system),
        ))
    return "\n".join(out)


RENDERERS = {
    "insights": ("Growth Insights", render_insights),
    "audit_seo": ("SEO Audit", render_audit),
    "tiktok_studio": ("Content Studio", render_content),
}


# ---------------------------------------------------------------------------
# The document
# ---------------------------------------------------------------------------

HEADER = """\
# Agent prompts

**Generated — do not edit.** Run `python backend/scripts/dump_prompts.py` from
the repository root, or `make dump-prompts`. CI regenerates this and fails if
it differs, so a prompt change that skips it cannot merge.

This file exists because a prompt change is otherwise invisible in review. The
Python diff shows a string constant moving; this shows what the model will
actually be told. Read it as the deliverable of a prompt change, not as a
by-product of one.

Everything below is rendered against one fixed fictional operator and project
(see `dump_prompts.py`) so that a diff here is a prompt change and never a
fixture change.

## How a turn is assembled

Per-user and per-project text lives in the **user turn**, never the system
prompt: the system prompt is the cached prefix, and one customer's name in it
gives every account a prefix of its own. Blocks render most-stable first,
because two runs on one project a week apart share the system prompt, and
identical opening blocks extend the cached prefix past it into the turn.

`agents/core/turn.py` holds the order and the reasoning; `agents/registry.py`
holds each agent's `ContextSpec`.
"""


def build_document() -> str:
    from agents.core.turn import BLOCK_ORDER
    from agents.registry import AGENT_REGISTRY

    parts = [HEADER]

    parts.append("\n### Canonical block order\n")
    parts.append("| # | Block | |")
    parts.append("|---|-------|---|")
    for i, tag in enumerate(BLOCK_ORDER, 1):
        note = "most stable" if i == 1 else ("the ask" if tag == "request" else "")
        parts.append(f"| {i} | `<{tag}>` | {note} |")

    parts.append("\n### What each agent declares\n")
    parts.append("| Agent | Turned off |")
    parts.append("|-------|------------|")
    for agent_type, (label, _) in sorted(RENDERERS.items()):
        spec = getattr(AGENT_REGISTRY.get(agent_type), "context", None)
        off = sorted(f"`{f}`" for f in vars(spec) if not getattr(spec, f)) if spec else []
        parts.append(f"| {label} (`{agent_type}`) | {', '.join(off) if off else 'nothing'} |")

    for agent_type, (label, render) in sorted(RENDERERS.items()):
        parts.append(f"\n---\n\n## {label} (`{agent_type}`)\n")
        parts.append(render())

    return "\n".join(parts).rstrip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero if the checked-in file is not what this would write",
    )
    args = ap.parse_args()

    rendered = build_document()
    current = OUTPUT.read_text() if OUTPUT.exists() else ""

    if args.check:
        if rendered == current:
            print(f"{OUTPUT.relative_to(REPO_ROOT)} is up to date")
            return 0
        print(
            f"{OUTPUT.relative_to(REPO_ROOT)} is stale — a prompt changed without "
            f"regenerating it.\nRun: make dump-prompts",
            file=sys.stderr,
        )
        return 1

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(rendered)
    print(f"wrote {OUTPUT.relative_to(REPO_ROOT)} ({len(rendered):,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
