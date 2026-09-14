"""The shared turn builder: ordering, toggles, and the cache invariant.

Two things are being defended here, and only one of them is ordinary.

The ordinary one is that a spec's toggles are honoured and blocks come out in
:data:`BLOCK_ORDER`. The other is the reason the module exists: **per-user and
per-project text must never reach a system prompt.** That rule was held by
comments in three modules and was broken anyway — not by someone ignoring the
comments, but by an agent growing a second way to describe the operator, which
nobody thought of as "the system prompt" question at all. A comment cannot fail
CI. This can.
"""

from __future__ import annotations

import pytest

from agents.core.turn import (
    BLOCK_ORDER,
    ContextSpec,
    TurnContext,
    build_turn,
    spec_for,
)

# A profile with every field set to something a grep can find in a prompt.
_NEEDLES = {
    "display_name": "Zerbina Quirkwood",
    "role": "Product Manager",
    "notes": "Lead with money.",
}


def _full_context() -> TurnContext:
    ctx = TurnContext()
    for tag in BLOCK_ORDER:
        if tag == "request":
            continue
        ctx.set(tag, f"<{tag}>x</{tag}>")
    return ctx


# ---------------------------------------------------------------------------
# Ordering
# ---------------------------------------------------------------------------

def test_blocks_render_in_canonical_order():
    out = build_turn(context=_full_context(), request="do the thing")
    positions = [out.index(f"<{tag}>") for tag in BLOCK_ORDER]
    assert positions == sorted(positions), (
        "blocks came out of BLOCK_ORDER — that order is a cache decision, see "
        "agents/core/turn.py"
    )


def test_the_request_is_last():
    out = build_turn(context=_full_context(), request="do the thing")
    assert out.rindex("<request>") > max(
        out.index(f"<{tag}>") for tag in BLOCK_ORDER if tag != "request"
    )


def test_stable_blocks_precede_volatile_ones():
    """The whole point: what two runs share comes before what they don't.

    Business and user context are identical across runs of the same project;
    the memory digest and the data-source inventory are not. Stable-first is
    what lets the second run's cached prefix reach past the system prompt.
    """
    order = list(BLOCK_ORDER)
    for stable in ("business_context", "user_context"):
        for volatile in ("project_memory", "data_sources", "request"):
            assert order.index(stable) < order.index(volatile)


def test_an_unknown_block_lands_after_the_ordered_ones_and_before_the_request():
    ctx = _full_context()
    ctx.set("crawl_data", "<crawl_data>x</crawl_data>")
    out = build_turn(context=ctx, request="go")
    assert out.index("<data_sources>") < out.index("<crawl_data>") < out.index("<request>")


# ---------------------------------------------------------------------------
# Toggles
# ---------------------------------------------------------------------------

def test_a_disabled_block_is_dropped_even_when_rendered():
    """The toggle is honoured at one point, not at every call site.

    A caller that renders a block the spec has switched off is the normal case,
    not a bug: routes render what they loaded and specs decide who reads it.
    """
    out = build_turn(
        spec=ContextSpec(project_memory=False), context=_full_context(), request="go"
    )
    assert "<project_memory>" not in out
    assert "<business_context>" in out


def test_an_agent_that_declares_nothing_gets_everything():
    out = build_turn(spec=spec_for("an-agent-nobody-has-written"), context=_full_context())
    for tag in BLOCK_ORDER:
        if tag != "request":
            assert f"<{tag}>" in out


def test_empty_blocks_never_render_as_empty_tags():
    ctx = TurnContext()
    ctx.set("business_context", "")
    ctx.set("user_context", "   ")
    assert build_turn(context=ctx, request="go").strip() == "<request>\ngo\n</request>"


def test_the_request_falls_back_when_the_user_said_nothing():
    out = build_turn(context=TurnContext(), request="", request_fallback="greet them")
    assert "greet them" in out


def test_wrap_request_false_leaves_the_ask_untagged():
    out = build_turn(context=TurnContext(), request="already composed", wrap_request=False)
    assert out == "already composed"


# ---------------------------------------------------------------------------
# The cache invariant
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "builder",
    [
        pytest.param("insights", id="insights"),
        pytest.param("audit", id="audit"),
    ],
)
def test_no_system_prompt_carries_per_user_text(builder):
    """A system prompt is the cached prefix. One customer's name in it gives
    every account a prefix of its own and loses the hit on every call.

    Built with a profile whose every field is a distinctive string, then the
    system prompt is searched for any of them. This is the check that would
    have caught the operator block being assembled in the wrong half.
    """
    if builder == "insights":
        from agents.insights.prompts.autonomous import build_insights_system_prompt

        system = build_insights_system_prompt()
    else:
        from agents.audit.prompts import build_audit_system_prompt

        system = build_audit_system_prompt()

    for field, needle in _NEEDLES.items():
        assert needle not in system, (
            f"{builder}'s system prompt contains the operator's {field}. "
            "Per-user text belongs in the user turn — see agents/core/turn.py."
        )


def test_the_operator_reaches_every_agent_that_wants_them():
    """The regression that motivated the module.

    ``display_name`` reached insights and content and silently missed audit,
    because audit described the operator its own way. Any agent whose spec says
    ``user_context`` must actually render the name it was given.
    """
    from agents.core.voice import user_context_block
    from service.profile import Profile

    profile = Profile(**_NEEDLES, writing_preset="executive")
    block = user_context_block(profile)
    for needle in _NEEDLES.values():
        assert needle in block


def test_audit_renders_the_operators_name():
    """Audit specifically — the agent that had its own spelling of this."""
    from agents.audit.prompts import build_audit_user_prompt
    from agents.audit.schema import AuditBusinessContext, CrawlPlan, CrawlResult
    from service.profile import Profile

    out = build_audit_user_prompt(
        CrawlResult(plan=CrawlPlan(root_url="https://example.test")),
        AuditBusinessContext(),
        profile=Profile(**_NEEDLES),
    )
    assert _NEEDLES["display_name"] in out


def test_audit_suppresses_the_paid_section_it_declared_off():
    from agents.audit.prompts import build_audit_user_prompt
    from agents.audit.schema import AuditBusinessContext, CrawlPlan, CrawlResult

    out = build_audit_user_prompt(
        CrawlResult(plan=CrawlPlan(root_url="https://example.test")),
        AuditBusinessContext(business_name="Acme", monthly_budget=5000, target_cpa=40),
        None,
    )
    assert "Acme" in out
    assert "5000" not in out and "Target CPA" not in out
