"""One Duct vocabulary over four provider dialects.

The properties worth pinning are the ones that keep the abstraction honest:
a rung never resolves to a value the model would reject, an unset level never
buys the expensive rung, and a model with no dial contributes nothing at all.
"""

from __future__ import annotations

import pytest

from agents.core.lc import resolve_chat_model
from agents.models import ModelName, Provider
from agents.thinking import (
    MODEL_THINKING,
    NO_THINKING_DIAL,
    THINKING_LEVELS,
    ThinkingLevel,
    describe_model,
    normalize_level,
    resolve_native,
    support_for,
    thinking_kwargs,
)


# ---------------------------------------------------------------------------
# The translation, provider by provider
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "model, expected",
    [
        # Anthropic's ladder is the widest, so every rung is distinct.
        ("claude-opus-5", ["low", "medium", "high", "xhigh"]),
        ("claude-sonnet-5", ["low", "medium", "high", "xhigh"]),
        # 4.6 has max but no xhigh — Exhaustive lands on max, not on high.
        ("claude-sonnet-4-6", ["low", "medium", "high", "max"]),
        # OpenAI names the dial differently and defaults lower.
        ("gpt-5.6-sol", ["low", "medium", "high", "xhigh"]),
        # Gemini stops at high, so the top two rungs collapse.
        ("gemini-3.8-flash", ["low", "medium", "high", "high"]),
        # …and the lite model has a rung below low.
        ("gemini-3.5-flash-lite", ["minimal", "medium", "high", "high"]),
        # xAI publishes the full ladder and cannot turn reasoning off, so all
        # four rungs are distinct and none of them is an "off".
        ("grok-4.6", ["low", "medium", "high", "xhigh"]),
    ],
)
def test_each_rung_lands_on_a_value_that_model_accepts(model, expected):
    got = [resolve_native(model, level) for level in THINKING_LEVELS]
    assert got == expected
    native = support_for(model).native
    assert all(value in native for value in got), "never send a value it would reject"


def test_high_means_different_things_to_different_providers():
    """The reason this module exists, stated as a test.

    `high` is Anthropic's default and Gemini's ceiling. A user picking "Deep"
    should get the same *intent* on both without knowing that.
    """
    assert describe_model("claude-opus-5")["default_native"] == "high"
    assert describe_model("gpt-5.6-sol")["default_native"] == "medium"
    assert resolve_native("gemini-3.8-flash", ThinkingLevel.EXHAUSTIVE) == "high"


def test_a_collapsed_rung_says_so_rather_than_offering_a_dead_choice():
    levels = {row["level"]: row for row in describe_model("gemini-3.8-flash")["levels"]}
    assert levels["exhaustive"]["same_as"] == "deep"
    assert levels["deep"]["same_as"] == "", "the first rung to claim a value owns it"
    # Anthropic has room for all four, so nothing collapses.
    assert all(row["same_as"] == "" for row in describe_model("claude-opus-5")["levels"])


def test_the_default_rung_is_marked_so_the_ui_can_say_which_is_free():
    marked = [row["level"] for row in describe_model("claude-opus-5")["levels"] if row["is_default"]]
    assert marked == ["deep"]
    marked = [row["level"] for row in describe_model("gpt-5.6-sol")["levels"] if row["is_default"]]
    assert marked == ["balanced"]


# ---------------------------------------------------------------------------
# Model identity
# ---------------------------------------------------------------------------

def test_an_openrouter_slug_resolves_to_the_model_it_fronts():
    assert support_for("anthropic/claude-opus-5") is support_for("claude-opus-5")
    assert support_for("openai/gpt-5-mini") is support_for("gpt-5-mini")


def test_the_1m_context_variant_is_the_same_model():
    """`claude-opus-5[1m]` is a context-window selector, not a different model."""
    assert support_for(ModelName.CLAUDE_OPUS_1M) is support_for("claude-opus-5")


def test_a_modelname_enum_resolves_like_its_string():
    assert support_for(ModelName.CLAUDE_OPUS) is support_for("claude-opus-5")


# ---------------------------------------------------------------------------
# The safety properties
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "model", ["claude-haiku-4-5", "gpt-4o", "gpt-4o-mini", "gemini-2.5-flash"]
)
def test_a_model_with_no_dial_contributes_nothing(model):
    """Gemini 2.5 *rejects* thinking_level outright; 4o has no such parameter.
    Either way the safe answer is to send nothing and hide the picker."""
    assert support_for(model) is None
    assert thinking_kwargs(model, "deep") == {}
    assert describe_model(model)["supported"] is False
    assert describe_model(model)["levels"] == []


def test_an_unset_level_leaves_the_model_on_its_own_default():
    """Normalising four different provider defaults into one would change the
    cost and quality of every project that never touched the setting."""
    assert thinking_kwargs("claude-opus-5", "") == {}
    assert thinking_kwargs("claude-opus-5", None) == {}


def test_a_typo_never_buys_the_expensive_rung():
    assert normalize_level("ULTRA") is None
    assert normalize_level("xhigh") is None, "provider words are not Duct words"
    assert thinking_kwargs("claude-opus-5", "ultra") == {}


def test_duct_levels_are_case_and_whitespace_forgiving():
    assert normalize_level("  Deep ") is ThinkingLevel.DEEP


# ---------------------------------------------------------------------------
# Table invariants — cheap guards against a typo in a hand-written map
# ---------------------------------------------------------------------------

_CANONICAL = ["none", "minimal", "low", "medium", "high", "xhigh", "max"]


@pytest.mark.parametrize("model_id", sorted(MODEL_THINKING))
def test_every_row_is_internally_consistent(model_id):
    support = MODEL_THINKING[model_id]
    assert support.native, "a row with no values should be an absent row"
    assert all(v in _CANONICAL for v in support.native), "unknown native value"
    order = [_CANONICAL.index(v) for v in support.native]
    assert order == sorted(order), "native values must be ascending"
    assert len(set(support.native)) == len(support.native), "duplicate native value"
    assert support.default in support.native, "a model's default must be one it accepts"
    assert support.label, "the UI names the provider's dial"


@pytest.mark.parametrize("model_id", sorted(MODEL_THINKING))
def test_every_rung_resolves_on_every_supported_model(model_id):
    for level in THINKING_LEVELS:
        assert resolve_native(model_id, level) in MODEL_THINKING[model_id].native


# ---------------------------------------------------------------------------
# Integration: the one place a model is built
# ---------------------------------------------------------------------------

def _captured(monkeypatch):
    seen = {}

    def fake_init(**kwargs):
        seen.update(kwargs)
        return object()

    monkeypatch.setattr("agents.core.lc.init_chat_model", fake_init)
    return seen


def test_the_model_factory_sends_langchains_standard_parameter(monkeypatch):
    """ChatAnthropic, ChatOpenAI and ChatGoogleGenerativeAI all accept
    `reasoning_effort` and translate it themselves — so one kwarg covers every
    provider and no call site special-cases one."""
    seen = _captured(monkeypatch)
    resolve_chat_model(Provider.ANTHROPIC, "claude-opus-5", "k", thinking="exhaustive")
    assert seen["reasoning_effort"] == "xhigh"


def test_the_model_factory_stays_silent_when_the_model_has_no_dial(monkeypatch):
    seen = _captured(monkeypatch)
    resolve_chat_model(Provider.ANTHROPIC, "claude-haiku-4-5", "k", thinking="exhaustive")
    assert "reasoning_effort" not in seen


def test_the_model_factory_stays_silent_when_nothing_was_chosen(monkeypatch):
    seen = _captured(monkeypatch)
    resolve_chat_model(Provider.GOOGLE_GENAI, "gemini-3.8-flash", "k")
    assert "reasoning_effort" not in seen


def test_the_preference_accepts_exactly_the_duct_levels():
    from agents.preferences import UserPreferences

    for level in THINKING_LEVELS:
        assert UserPreferences(thinking=level.value).thinking == level.value
    assert UserPreferences().thinking == "", "unset is the default"
    with pytest.raises(Exception):
        UserPreferences(thinking="xhigh")  # a provider word, not a Duct one


# ---------------------------------------------------------------------------
# The forcing function
# ---------------------------------------------------------------------------

def test_every_model_duct_offers_has_an_answer_about_thinking():
    """The point of this test is to fail when someone adds a model.

    A new ModelName must either get a row in MODEL_THINKING or be named in
    NO_THINKING_DIAL with a reason. Neither is much work; the failure mode it
    prevents is a model shipping with a picker that silently does nothing,
    which nobody would notice until a customer asked why Deep felt the same
    as Quick.
    """
    unaccounted = [
        model.value
        for model in ModelName
        if support_for(model) is None and model not in NO_THINKING_DIAL
    ]
    assert not unaccounted, (
        "these models have no thinking row and are not on the dial-less list: "
        f"{unaccounted}"
    )


def test_a_model_is_never_both_supported_and_dial_less():
    both = [m.value for m in NO_THINKING_DIAL if support_for(m) is not None]
    assert not both


def test_catalogue_models_are_keyed_by_the_enum_not_by_a_loose_string():
    """A raw string that duplicates a ModelName value would still match, and
    would still stop matching silently if the catalogue renamed it."""
    by_value = {m.value: m for m in ModelName}
    loose = [
        key for key in MODEL_THINKING
        if not isinstance(key, ModelName) and key in by_value
    ]
    assert not loose, f"use ModelName for these: {loose}"


def test_the_1m_variant_and_vendor_slugs_need_no_row_of_their_own():
    """They resolve through _strip_variant / _strip_vendor, so duplicating them
    would mean two rows to keep in step instead of one."""
    for alias in ("claude-opus-5[1m]", "anthropic/claude-opus-5", "openai/gpt-5-mini"):
        assert alias not in MODEL_THINKING
        assert support_for(alias) is not None
