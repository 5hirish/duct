"""How hard the model thinks — one Duct vocabulary over four provider dialects.

Every frontier provider now sells the same dial and calls it something else:

  Anthropic   ``output_config.effort``   low · medium · high · xhigh · max
  OpenAI      ``reasoning.effort``       none · low · medium · high · xhigh · max
  Google      ``thinking_level``         minimal · low · medium · high
  OpenRouter  ``reasoning.effort``       the union, normalised onto whatever it fronts
  xAI         ``reasoning_effort``       low · medium · high · xhigh (no off rung)

The words do not line up. ``high`` is Anthropic's *default* and Google's
*ceiling*; ``minimal`` exists only on Gemini; ``xhigh`` exists only on the newest
Anthropic and OpenAI models. Asking a growth marketer to hold that in their head
so they can pick a number is the same mistake the deleted wizard made — making
the user carry the vendor's model of the world.

So Duct names four rungs of its own and owns the translation. The user picks
"Deep"; this module decides that means ``high`` on Opus 5, ``high`` on Gemini
3.8 Flash, and ``high`` on GPT-5.6 — and that "Exhaustive" means ``xhigh`` on
Opus 5 but is *the same as Deep* on Gemini 3.8 Flash, which has no rung above
``high``. The UI shows the resolved native value beside the Duct name, so the
abstraction never lies about what was actually sent.

Three rules make this safe to extend:

1. **Mapping is by meaning, not by position.** Each Duct rung carries an ordered
   preference of native values and takes the first the model supports. Scaling
   rung *n* of 4 onto a ladder of 3 or 6 would silently rename things — it would
   make "Balanced" mean ``low`` on Gemini, which is not what balanced means.

2. **Unsupported is a state, not a silence.** A model with no thinking dial
   (gpt-4o, claude-haiku-4-5, the Gemini 2.5 line) returns ``None`` and the
   picker disappears. Sending an ignored parameter, or worse a rejected one, is
   how you get a 400 nobody can explain.

3. **Unset means the provider's default.** Duct never sends a level the user did
   not choose. Defaults differ (Anthropic ``high``, OpenAI ``medium``, Gemini per
   model) and quietly normalising them would change cost and quality for every
   existing project.

This module is deliberately separate from ``agents/models.py``. That module was
where the Claude Agent SDK's wire enums lived, and they left with it; the one
that remains, ``AgentEffort``, is still the API's request field. This is the
portable layer every provider goes through, and it happens to share Anthropic's
spelling because it *is* Anthropic's spelling.

It does import ``ModelName``, though, and keys the table by it: the catalogue is
the list of models Duct actually offers, so a model leaving it should break this
table loudly rather than leave a row that quietly matches nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from agents.models import ModelName


class ThinkingLevel(StrEnum):
    """Duct's four rungs. Ascending; the ordering is load-bearing for the UI."""

    QUICK = "quick"
    BALANCED = "balanced"
    DEEP = "deep"
    EXHAUSTIVE = "exhaustive"


THINKING_LEVELS: tuple[ThinkingLevel, ...] = (
    ThinkingLevel.QUICK,
    ThinkingLevel.BALANCED,
    ThinkingLevel.DEEP,
    ThinkingLevel.EXHAUSTIVE,
)

# What the picker says. Plain words: nobody outside an API doc says "xhigh".
LEVEL_LABELS: dict[ThinkingLevel, str] = {
    ThinkingLevel.QUICK: "Quick",
    ThinkingLevel.BALANCED: "Balanced",
    ThinkingLevel.DEEP: "Deep",
    ThinkingLevel.EXHAUSTIVE: "Exhaustive",
}

LEVEL_BLURBS: dict[ThinkingLevel, str] = {
    ThinkingLevel.QUICK: "Answers fast. Best for a lookup or a number you already trust.",
    ThinkingLevel.BALANCED: "Enough reasoning for most questions, without the wait.",
    ThinkingLevel.DEEP: "Checks its own work. The right setting for anything you'll act on.",
    ThinkingLevel.EXHAUSTIVE: "Everything the model has. Slow and expensive — save it for the hard ones.",
}

# --- Native vocabulary -----------------------------------------------------
# Every value any of the four providers accepts, ascending. Kept as plain
# strings rather than an enum: they are other people's wire values, and a new
# one appearing must not require a Duct release to pass through.

NONE = "none"
MINIMAL = "minimal"
LOW = "low"
MEDIUM = "medium"
HIGH = "high"
XHIGH = "xhigh"
MAX = "max"

# Ordered preferences per Duct rung — first supported value wins. `none` is
# absent on purpose: a model that cannot reason at all is not a thinking level,
# it is the absence of one.
_PREFERENCE: dict[ThinkingLevel, tuple[str, ...]] = {
    ThinkingLevel.QUICK: (MINIMAL, LOW, MEDIUM),
    ThinkingLevel.BALANCED: (MEDIUM, LOW, HIGH),
    ThinkingLevel.DEEP: (HIGH, MEDIUM, XHIGH),
    ThinkingLevel.EXHAUSTIVE: (XHIGH, MAX, HIGH),
}


@dataclass(frozen=True)
class ThinkingSupport:
    """What one model actually accepts, and what it does when we say nothing.

    ``param`` is LangChain's standardised kwarg, which ChatAnthropic,
    ChatOpenAI and ChatGoogleGenerativeAI all accept and translate to their own
    native field — so the v1 engine passes one name for every provider. The
    *values* still differ per model, which is what this table is for.
    """

    native: tuple[str, ...]           # ascending; what the API will accept
    default: str                      # what the provider does when unset
    label: str                        # what the provider calls the dial, for the UI
    param: str = "reasoning_effort"   # LangChain's standard kwarg


_ANTHROPIC_5 = ThinkingSupport(
    native=(LOW, MEDIUM, HIGH, XHIGH, MAX), default=HIGH, label="effort"
)
# 4.6-generation Anthropic models have max but not xhigh.
_ANTHROPIC_46 = ThinkingSupport(
    native=(LOW, MEDIUM, HIGH, MAX), default=HIGH, label="effort"
)
_GPT_5_6 = ThinkingSupport(
    native=(NONE, LOW, MEDIUM, HIGH, XHIGH, MAX), default=MEDIUM, label="reasoning effort"
)
# The GPT-5 family's per-model matrix is not published in full. low/medium/high
# is the subset every member accepts, so the picker offers only what is safe
# rather than risking a 400 on a value we did not verify.
_GPT_5_CONSERVATIVE = ThinkingSupport(
    native=(LOW, MEDIUM, HIGH), default=MEDIUM, label="reasoning effort"
)


# xAI publishes the full ladder per model and says reasoning cannot be
# disabled, so unlike the GPT-5 family there is nothing to be conservative
# about — and no `none` rung to offer. xhigh is grok-4.6 and later; grok-4.5
# silently treats it as high.
_XAI = ThinkingSupport(
    native=(LOW, MEDIUM, HIGH, XHIGH), default=HIGH, label="reasoning effort"
)


def _gemini(native: tuple[str, ...], default: str) -> ThinkingSupport:
    return ThinkingSupport(native=native, default=default, label="thinking level")


_OPEN_WEIGHT = ThinkingSupport(
    native=(LOW, MEDIUM, HIGH), default=MEDIUM, label="reasoning effort"
)

# Keyed by ModelName wherever Duct offers the model, so a rename or removal in
# the catalogue is an import error here rather than a row that silently stops
# matching. ``ModelName`` is a ``str`` enum, so a member and its value hash
# alike and a lookup by plain string still finds the row — which is what lets
# an OpenRouter passthrough slug resolve against the same table.
#
# Absent = no dial, which is a real answer (see rule 2), not an oversight to be
# defaulted away. ``NO_THINKING_DIAL`` below names the catalogue models that are
# deliberately absent, and a test pairs the two so a new model cannot be added
# without deciding which side it falls on.
MODEL_THINKING: dict[str, ThinkingSupport] = {
    # --- Anthropic. Fable 5.1 takes the same effort ladder; what differs is
    # that its thinking cannot be turned off, which is a request-shape concern
    # (agents/core/lc.py), not a ladder concern.
    ModelName.CLAUDE_FABLE: _ANTHROPIC_5,
    ModelName.CLAUDE_OPUS: _ANTHROPIC_5,
    ModelName.CLAUDE_SONNET: _ANTHROPIC_5,

    # --- OpenAI
    ModelName.GPT_5_6_SOL: _GPT_5_6,
    ModelName.GPT_5_6_TERRA: _GPT_5_6,
    ModelName.GPT_5_6_LUNA: _GPT_5_6,
    ModelName.GPT_5_MINI: _GPT_5_CONSERVATIVE,

    # --- Google. thinking_level is Gemini 3 and later; the 2.5 line takes a
    # token budget instead and rejects a level outright.
    # Promoted from the loose-string block below when it joined the catalogue
    # as the Heavy rung of the default triple.
    ModelName.GEMINI_3_1_PRO_PREVIEW: _gemini((LOW, MEDIUM, HIGH), HIGH),
    ModelName.GEMINI_3_8_FLASH: _gemini((LOW, MEDIUM, HIGH), MEDIUM),
    ModelName.GEMINI_3_5_FLASH_LITE: _gemini((MINIMAL, LOW, MEDIUM, HIGH), MINIMAL),

    # --- xAI
    ModelName.GROK_4_6: _XAI,

    # --- OpenRouter open-weight slugs. It normalises the parameter, but what
    # the upstream model does with it varies, so only the middle of the ladder
    # is offered. Vendor-prefixed slugs for models Duct also offers natively
    # (anthropic/claude-opus-5 …) resolve through _strip_vendor to the row
    # above rather than repeating it here.
    ModelName.OR_DEEPSEEK_V4_FLASH: _OPEN_WEIGHT,
    ModelName.OR_DEEPSEEK_V4_PRO: _OPEN_WEIGHT,
    ModelName.OR_KIMI_K3: _OPEN_WEIGHT,
    ModelName.OR_GLM_5_3_FLASH: _OPEN_WEIGHT,

    # --- Models Duct does not offer yet.
    # Plain strings on purpose: adding one to ModelName is a product decision
    # about what appears in the engine picker, and these rows exist only so a
    # BYO-key customer naming one through OpenRouter still gets a correct
    # ladder. Promote a key to ModelName when the model joins the catalogue.
    "claude-opus-4-8": _ANTHROPIC_5,
    "claude-opus-4-7": _ANTHROPIC_5,
    "claude-fable-5": _ANTHROPIC_5,
    "claude-opus-4-6": _ANTHROPIC_46,
    "claude-sonnet-4-6": _ANTHROPIC_46,
    "gemini-3.5-flash": _gemini((MINIMAL, LOW, MEDIUM, HIGH), MEDIUM),
}

# Catalogue models with no thinking dial at all, and why. Being on this list is
# an assertion, not a shrug: the test that pairs it with MODEL_THINKING fails
# when a new ModelName appears on neither, so "does this model have a dial?"
# has to be answered before the model ships.
NO_THINKING_DIAL: frozenset[ModelName] = frozenset({
    # Not reasoning models; the parameter does not exist for them.
    ModelName.GPT_4O,
    ModelName.GPT_4O_MINI,
    # Pre-Gemini-3: thinking_level is rejected outright, and their control is a
    # token budget rather than a level. Supporting budgets is a separate shape.
    ModelName.GEMINI_2_5_FLASH,
    # Absent from Anthropic's effort-supported model list.
    ModelName.CLAUDE_HAIKU,
    # Open weights behind OpenRouter. It lists `reasoning` in the catalogue's
    # supported_parameters but *not* `reasoning_effort` — it reasons, it just
    # takes no level. That is the difference from the rows above, which do
    # carry `reasoning_effort` and therefore get a ladder. kimi-k2.5 was here
    # for the same reason until the k3 that replaced it gained the parameter.
    ModelName.OR_QWEN3_8_FLASH,
})


def _model_id(model) -> str:
    """The provider-facing id, whatever wrapper it arrived in."""
    return str(getattr(model, "value", model) or "").strip()


def _strip_vendor(model_id: str) -> str:
    """``anthropic/claude-opus-5`` → ``claude-opus-5``.

    OpenRouter fronts the same models under a vendor prefix. They are the same
    model with the same ladder, so the table should not carry two rows each.
    """
    return model_id.split("/", 1)[1] if "/" in model_id else model_id


def _strip_variant(model_id: str) -> str:
    """``claude-opus-5[1m]`` → ``claude-opus-5``.

    The bracket suffix is a Claude Code context-window selector, not a
    different model, and it has the same effort ladder.
    """
    return model_id.split("[", 1)[0]


def support_for(model) -> ThinkingSupport | None:
    """What this model accepts, or None when it has no thinking dial."""
    model_id = _model_id(model)
    if not model_id:
        return None
    for candidate in (model_id, _strip_variant(model_id), _strip_vendor(model_id),
                      _strip_vendor(_strip_variant(model_id))):
        found = MODEL_THINKING.get(candidate)
        if found is not None:
            return found
    return None


def normalize_level(value) -> ThinkingLevel | None:
    """A stored or client-supplied level, or None for "use the model's default".

    Unknown values resolve to None rather than to a guess: a typo must not
    quietly buy the most expensive rung.
    """
    raw = str(value or "").strip().lower()
    if not raw:
        return None
    try:
        return ThinkingLevel(raw)
    except ValueError:
        return None


def resolve_native(model, level) -> str:
    """The native value this model should receive for a Duct level.

    Returns "" when the level is unset or the model has no dial. Clamping is
    the interesting case: on a model whose ladder stops at ``high``, both Deep
    and Exhaustive resolve to ``high``, and callers surface that rather than
    implying a difference that does not exist.
    """
    support = support_for(model)
    rung = normalize_level(level)
    if support is None or rung is None:
        return ""
    for candidate in _PREFERENCE[rung]:
        if candidate in support.native:
            return candidate
    # Nothing preferred is on offer — take the model's own ceiling rather than
    # sending a value it will reject.
    return support.native[-1]


def thinking_kwargs(model, level) -> dict:
    """Kwargs for ``init_chat_model``. Empty when there is nothing to say."""
    support = support_for(model)
    native = resolve_native(model, level)
    if support is None or not native:
        return {}
    return {support.param: native}


def describe_model(model) -> dict:
    """What the picker needs, computed once on the server.

    The frontend renders this verbatim. Duplicating the table in JavaScript is
    how the two drift, and a UI that offers a rung the API rejects is worse
    than no picker at all.
    """
    model_id = _model_id(model)
    support = support_for(model)
    if support is None:
        return {"model": model_id, "supported": False, "levels": [], "dial": ""}

    seen: dict[str, ThinkingLevel] = {}
    levels = []
    for rung in THINKING_LEVELS:
        native = resolve_native(model_id, rung)
        # A rung that resolves to the same native value as a lower one adds no
        # choice — say so instead of offering two buttons that do one thing.
        same_as = seen.get(native)
        seen.setdefault(native, rung)
        levels.append({
            "level": rung.value,
            "label": LEVEL_LABELS[rung],
            "blurb": LEVEL_BLURBS[rung],
            "native": native,
            "is_default": native == support.default,
            "same_as": same_as.value if same_as else "",
        })
    return {
        "model": model_id,
        "supported": True,
        "dial": support.label,
        "default_native": support.default,
        "levels": levels,
    }
