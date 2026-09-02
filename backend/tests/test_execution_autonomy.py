"""The three-level autonomy ladder, and the invariant it must not break.

Phase 5 of `docs/engineering/autonomous-insights-agent-plan.md`. `manual |
assisted` becomes `ask | assisted | auto`, a ladder that governs three things
together — how freely the agent asks, whether it proposes, and whether an
eligible proposal applies without a click.

The load-bearing claim, and most of what this file exists to hold:

    **`auto` does not widen what may auto-apply.**

It reduces interruption, not oversight. AUTO_APPLY_ALLOWLIST and the absolute
destructive gate are byte-identical at `assisted` and at `auto`, no
configuration reaches them, and no agent-facing approve or apply tool exists in
either harness binder. If a future change makes `auto` mean "more", these tests
are what should stop it.

`tests/test_execution_policy.py` holds the eligibility matrix itself; this file
holds the level vocabulary, the model gate, and the tool surface.
"""

from __future__ import annotations

import uuid

import pytest

from agents.insights.prompts.autonomous import (
    AUTONOMY_POSTURE,
    build_insights_system_prompt,
    build_insights_user_prompt,
)
from agents.tools import execution_tools
from agents.tools.execution_tools import (
    build_execution_mcp_server,
    build_execution_tools_lc,
)
from models.execution import (
    AUTO_APPLY_LEVELS,
    AUTONOMY_ASK,
    AUTONOMY_ASSISTED,
    AUTONOMY_AUTO,
    AUTONOMY_LEVELS,
    AUTONOMY_MANUAL,
    is_writable_autonomy,
    normalize_autonomy,
)
from models.project import Project
from service.execution.policy import (
    AUTO_APPLY_ALLOWLIST,
    change_auto_eligible,
    effective_autonomy,
    model_allows_auto_posture,
    should_auto_apply,
)
from service.execution.registry import ExecutorSpec

# A frontier model (allowlisted for the `auto` posture) and one that is not.
TRUSTED_MODEL = "claude-opus-5"
UNTRUSTED_MODEL = "mistralai/mistral-7b-instruct"


def _proj(level):
    return Project(name="p", user_id=None, autonomy_level=level)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# The vocabulary
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(("stored", "expected"), [
    (AUTONOMY_ASK, AUTONOMY_ASK),
    (AUTONOMY_ASSISTED, AUTONOMY_ASSISTED),
    (AUTONOMY_AUTO, AUTONOMY_AUTO),
    ("  Assisted  ", AUTONOMY_ASSISTED),
    (AUTONOMY_MANUAL, AUTONOMY_ASK),   # the legacy spelling, still stored on rows
    ("", AUTONOMY_ASK),
    (None, AUTONOMY_ASK),
])
def test_normalize_reads_every_stored_value(stored, expected):
    assert normalize_autonomy(stored) == expected


def test_an_unrecognised_level_reads_as_the_least_autonomy():
    """A typo, a truncated write, a value from a newer version — none of them
    may be read as more autonomy than the owner granted."""
    assert normalize_autonomy("fully-autonomous") == AUTONOMY_ASK
    assert normalize_autonomy("AUTO;DROP") == AUTONOMY_ASK


@pytest.mark.parametrize(("value", "writable"), [
    (AUTONOMY_ASK, True),
    (AUTONOMY_ASSISTED, True),
    (AUTONOMY_AUTO, True),
    (AUTONOMY_MANUAL, True),      # an older client still setting the old name
    ("  AUTO ", True),
    ("fully-autonomous", False),  # a typo is a 422, never a silent downgrade
    ("", False),
    (None, False),
])
def test_only_a_real_level_may_be_written(value, writable):
    assert is_writable_autonomy(value) is writable


def test_a_project_stored_as_manual_never_auto_applies():
    """The alias has to hold end to end: existing rows say "manual" and there
    is no data migration behind them."""
    assert should_auto_apply(_proj(AUTONOMY_MANUAL), "agent", [{"auto_eligible": True}]) is False


# ---------------------------------------------------------------------------
# auto is a posture, not a wider allowlist
# ---------------------------------------------------------------------------

def test_auto_and_assisted_permit_exactly_the_same_sets():
    changes = [{"auto_eligible": True}, {"auto_eligible": True}]

    assert should_auto_apply(_proj(AUTONOMY_ASSISTED), "agent", changes) is True
    assert should_auto_apply(_proj(AUTONOMY_AUTO), "agent", changes) is True
    assert should_auto_apply(_proj(AUTONOMY_ASK), "agent", changes) is False


def test_auto_does_not_make_a_destructive_change_eligible():
    """The absolute gate. There is no level, flag or model at which this flips."""
    destructive = ExecutorSpec(
        op_type=next(iter(AUTO_APPLY_ALLOWLIST)),  # even ON the allowlist
        connector_type="google_ads",
        label="destructive",
        preview=lambda c, k: {},
        apply=lambda c, k: {},
        rollback=lambda c, k: {},
        destructive=True,
    )

    assert change_auto_eligible(destructive, {}) is False


def test_auto_does_not_make_an_unlisted_op_eligible():
    unlisted = ExecutorSpec(
        op_type="google_ads.set_campaign_budget",  # reversible, deliberately off-list
        connector_type="google_ads",
        label="budget",
        preview=lambda c, k: {},
        apply=lambda c, k: {},
        rollback=lambda c, k: {},
        destructive=False,
    )

    assert unlisted.op_type not in AUTO_APPLY_ALLOWLIST
    assert change_auto_eligible(unlisted, {}) is False


def test_the_auto_apply_levels_are_the_two_that_apply():
    assert AUTO_APPLY_LEVELS == {AUTONOMY_ASSISTED, AUTONOMY_AUTO}
    assert AUTONOMY_ASK not in AUTO_APPLY_LEVELS
    assert AUTONOMY_LEVELS == {AUTONOMY_ASK, AUTONOMY_ASSISTED, AUTONOMY_AUTO}


# ---------------------------------------------------------------------------
# The model gate — it lowers the posture, and touches nothing else
# ---------------------------------------------------------------------------

def test_a_weak_model_runs_an_auto_project_at_assisted():
    assert effective_autonomy(AUTONOMY_AUTO, TRUSTED_MODEL) == AUTONOMY_AUTO
    assert effective_autonomy(AUTONOMY_AUTO, UNTRUSTED_MODEL) == AUTONOMY_ASSISTED
    assert effective_autonomy(AUTONOMY_AUTO, "") == AUTONOMY_ASSISTED


def test_a_model_can_lower_the_posture_but_never_raise_it():
    """A frontier model does not promote a project its owner set to `ask`."""
    assert effective_autonomy(AUTONOMY_ASK, TRUSTED_MODEL) == AUTONOMY_ASK
    assert effective_autonomy(AUTONOMY_ASSISTED, TRUSTED_MODEL) == AUTONOMY_ASSISTED
    assert effective_autonomy(AUTONOMY_MANUAL, TRUSTED_MODEL) == AUTONOMY_ASK


def test_the_model_gate_does_not_reach_auto_apply():
    """The gate is about not *inviting* an unattended loop on a weak model. The
    code gates hold regardless of model, which is what actually makes this
    safe — so should_auto_apply deliberately never asks which model is driving.
    """
    import inspect

    assert "model" not in inspect.signature(should_auto_apply).parameters


def test_dated_model_snapshots_stay_trusted():
    """The allowlist matches on a prefix, so a dated snapshot of an allowlisted
    family does not need an edit here to keep working."""
    assert model_allows_auto_posture("claude-sonnet-5-20260101") is True
    assert model_allows_auto_posture("claude-haiku-4-5-20251001") is False
    assert model_allows_auto_posture("") is False


# ---------------------------------------------------------------------------
# The tool surface — the same asymmetry in both harnesses
# ---------------------------------------------------------------------------

EXPECTED_TOOLS = {
    "ListExecutableOps", "ProposeChanges", "GetChangeSetStatus", "RollbackChangeSet",
}


async def _sdk_tool_names() -> set[str]:
    """The MCP server's advertised tools — asked of the server, not of the
    source, so a tool added by any route shows up here."""
    import mcp.types as mcp_types

    server = build_execution_mcp_server(user_id=uuid.uuid4(), project_id=uuid.uuid4())
    handler = server["instance"].request_handlers[mcp_types.ListToolsRequest]
    result = await handler(mcp_types.ListToolsRequest(method="tools/list"))
    return {tool.name for tool in result.root.tools}


async def test_both_binders_mount_the_same_four_tools():
    lc = {t.name for t in build_execution_tools_lc(
        user_id=uuid.uuid4(), project_id=uuid.uuid4()
    )}

    assert lc == EXPECTED_TOOLS
    assert await _sdk_tool_names() == EXPECTED_TOOLS


async def test_no_binder_offers_a_way_to_approve_or_apply():
    """The safety property is the *absence* of a tool, which is exactly the kind
    of thing that gets added back by accident. Asked of both harnesses, because
    a tool added to one binder and not the other is the likelier accident."""
    lc = {t.name.lower() for t in build_execution_tools_lc(
        user_id=uuid.uuid4(), project_id=uuid.uuid4()
    )}

    for name in lc | {n.lower() for n in await _sdk_tool_names()}:
        assert "approve" not in name, f"{name} approves a change set"
        assert not name.startswith("apply"), f"{name} applies one"


def test_execution_tools_need_a_membership_checked_project():
    """Acting on someone's ad account needs a user AND a project. Mounting tools
    that fail when called is worse than not mounting them."""
    assert build_execution_tools_lc(user_id=uuid.uuid4()) == []
    assert build_execution_tools_lc(project_id=uuid.uuid4()) == []
    assert build_execution_tools_lc() == []


def test_both_binders_describe_one_contract():
    """Two harnesses, one set of descriptions and arg schemas — so the models
    behind them cannot be told different rules."""
    assert "cannot apply them" in execution_tools.PROPOSE_DESCRIPTION
    assert "ALWAYS wait" in execution_tools.PROPOSE_DESCRIPTION
    assert "never widens" in execution_tools.PROPOSE_DESCRIPTION

    lc = {t.name: t for t in build_execution_tools_lc(
        user_id=uuid.uuid4(), project_id=uuid.uuid4()
    )}
    assert lc["ProposeChanges"].description == execution_tools.PROPOSE_DESCRIPTION
    assert lc["ProposeChanges"].args_schema is execution_tools.ProposeChangesArgs


# ---------------------------------------------------------------------------
# What the agent is told
# ---------------------------------------------------------------------------

def test_every_level_has_a_posture():
    assert set(AUTONOMY_POSTURE) == AUTONOMY_LEVELS


def test_the_auto_posture_says_what_does_not_change():
    """A model that reads "auto" and infers a wider reach is the failure the
    level's design rules out in code; the prompt must not imply otherwise."""
    posture = AUTONOMY_POSTURE[AUTONOMY_AUTO]

    assert "does NOT change" in posture
    assert "destructive changes still wait" in posture
    assert "not a wider reach" in posture


def test_the_posture_is_in_the_user_turn_not_the_cached_prefix():
    turn = build_insights_user_prompt(prompt="x", autonomy=AUTONOMY_AUTO)

    assert "<autonomy>" in turn
    assert "AUTO buys fewer interruptions" in turn
    for level in AUTONOMY_LEVELS:
        assert AUTONOMY_POSTURE[level] not in build_insights_system_prompt(can_execute=True)


def test_the_execution_contract_is_cached_but_only_when_mounted():
    """Two fixed prefixes — one per tool set — never one per project."""
    without = build_insights_system_prompt(can_execute=False)
    with_exec = build_insights_system_prompt(can_execute=True)

    assert "ProposeChanges" not in without
    assert "ProposeChanges" in with_exec
    assert "cannot approve or apply a change set" in with_exec
    assert "Destructive operations always wait" in with_exec
    # Stable across calls: the prefix is what gets cached.
    assert build_insights_system_prompt(can_execute=True) == with_exec
