"""One profile, one ``<user_context>`` block, for every agent that writes prose.

Every agent had its own idea of how to describe the operator, or no idea at
all: audit rendered a ``<user_preferences>`` block of its own, insights
accepted a ``user_context`` string that nothing ever filled, and content had
neither. The profile is one row now (``service/profile.py``), so the rendering
is one function.

What this deliberately does not do is decide *where* the block goes. Each
runner puts it in its user turn, because that is the only place per-user text
may live: the insights system prompt is cache-stable by design, and a
per-customer string in it costs the cached prefix on every call.
"""

from __future__ import annotations

from agents.core.context import UserContext, format_user_context
from service.profile import Profile

#: What each preset asks for, in one line, and the one definition of what a
#: preset means. Each line says what changes in length and content when the
#: preset changes, not what tone to strike: the first three read "money,
#: action, no padding" for all three presets, so a model saw no difference
#: between them (session audit, 2026-09-19). The audit prompt adds an
#: SEO-specific sentence on top (``agents/audit/prompts.py``); it does not
#: restate these.
VOICE_GUIDANCE: dict[str, str] = {
    "executive": (
        "one screen: the decision, the money at stake, at most three actions; "
        "no metric names, no method; the evidence goes below the fold"
    ),
    "practitioner": (
        "the signal, the number behind it, what to do next; name the pages, "
        "campaigns and terms; the method in one line"
    ),
    "technical": (
        "every measurement with its window and definition, the method, and "
        "notes for whoever builds the fix; event and field names as the "
        "platform shows them"
    ),
}


def user_context_block(profile: Profile) -> str:
    """Render the profile as the ``<user_context>`` block, or '' when empty.

    An account that never opened the profile page renders nothing at all,
    rather than a block asserting Duct's defaults as though the person had
    chosen them. The difference matters to a model: "they asked for
    practitioner" and "nobody said" are not the same instruction.
    """
    if profile == Profile():
        return ""
    return format_user_context(
        UserContext(
            name=profile.display_name,
            role=profile.role,
            voice=VOICE_GUIDANCE.get(profile.writing_preset, ""),
            language=_language_instruction(profile.communication_language),
            # The stored value, not ``profile.zone``: an unset timezone should
            # render no line at all, and the UTC default is what an agent does
            # already. Saying "Their timezone: UTC" to someone who never chose
            # one asserts a preference they did not express.
            timezone=profile.timezone,
            notes=profile.notes,
        )
    )


def _language_instruction(language: str) -> str:
    """The language line, or '' for the default.

    Empty means "match the language they wrote in", which needs no instruction:
    it is what a model does anyway. Saying it out loud would spend tokens on
    every run to ask for the behaviour already in place.
    """
    return language.strip()
