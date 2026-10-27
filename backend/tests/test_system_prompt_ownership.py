"""Duct owns the final system prompt, byte for byte, on every model it ships.

`deepagents` layers a per-model harness profile onto whatever `create_deep_agent`
is given: a `system_prompt_suffix` (coding-agent guidance such as "Never
speculate about code you have not opened") appended after Duct's prompt for
the models it registers, and packages may register more. Nothing in the
assembly would have said so — the prompt dump renders Duct's text, and a bump
that added a profile for a model in the catalogue would have changed what
every customer's run was sent without a diff anywhere. Rulebook gap 6.
"""

from __future__ import annotations

from deepagents.profiles.harness.harness_profiles import (
    _apply_profile_prompt,
    _harness_profile_for_model,
)

from agents.core.lc import resolve_chat_model
from agents.models import PRICING, ModelName, provider_of

# The catalogue ids deepagents is known to suffix. Each entry is a deliberate
# acceptance re-read at every bump of the pin, not a default: a new id here
# means someone read the suffix and decided Duct's prompt survives it. Empty
# since Haiku 5.5 replaced Haiku 4.5, the one id 0.7.32 suffixes.
KNOWN_SUFFIXED: frozenset[str] = frozenset()


def _appended_for(model: ModelName) -> str:
    llm = resolve_chat_model(provider_of(model), model, "unused-no-network")
    return _apply_profile_prompt(_harness_profile_for_model(llm, None), "")


def test_no_harness_profile_appends_to_ducts_prompt_unannounced():
    appended = {}
    for model in PRICING:
        if provider_of(model) is None:
            continue
        text = _appended_for(model)
        if text:
            appended[model.value] = text[:120]
    assert set(appended) == KNOWN_SUFFIXED, (
        "deepagents appends a harness-profile suffix to Duct's system prompt for these "
        f"models; read it, then add the id to KNOWN_SUFFIXED or exclude the middleware: {appended}"
    )


def test_a_known_suffix_is_still_only_a_suffix():
    """The profile may append; it must never replace. `base_system_prompt`
    set on a profile would drop Duct's prompt outright."""
    for value in KNOWN_SUFFIXED:
        model = ModelName(value)
        llm = resolve_chat_model(provider_of(model), model, "unused-no-network")
        profile = _harness_profile_for_model(llm, None)
        assert not getattr(profile, "base_system_prompt", None), value
        assert _apply_profile_prompt(profile, "DUCT").startswith("DUCT"), value
