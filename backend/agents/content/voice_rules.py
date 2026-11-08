"""A project's own voice for its text posts (issue #271): writing samples the
writer matches, and the rules it keeps, as settings rather than constants.

The text prompt used to hard-code three rules for every project: a list of
banned buzzwords, never naming a client, and "protect the edge". They were
right for the first project and wrong for the next one — a build-in-public
founder wants the mechanism shown, an agency names its clients — and nobody
could change them. They live in the project's ``content_brand`` JSON now
(``PUT /content/brand``, no migration), and those constants are the
defaults: a project that never touched them writes exactly as before.

Where each piece goes, because the cache rule decides it: the system prompt
says only that the rules and samples exist; the project's values ride in the
opening USER turn (``render_voice_stanza``), so one customer's banned words
never cost every account its cached prefix. The writer enforces the banned
words deterministically (``banned_words_in``), the way it enforces length,
because a rule the model may forget is a suggestion.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field

# Keys inside a project's content_brand JSON.
SAMPLES_KEY = "writing_samples"
RULES_KEY = "voice_rules"

# A few posts carry a voice; more is tokens on every draft for little gain,
# and one long essay teaches the length of an essay, not a post.
MAX_SAMPLES = 5
MAX_SAMPLE_CHARS = 1500
MAX_BANNED_WORDS = 50
MAX_BANNED_WORD_CHARS = 60

# The list the text prompt carried for every project until #271, kept as the
# default so nothing changes until someone edits it.
DEFAULT_BANNED_WORDS: tuple[str, ...] = (
    "game-changer",
    "revolutionary",
    "excited to share",
    "dive in",
    "unpopular opinion",
    "hot take",
    "here's a thread",
    "a few thoughts on",
    "today I learned",
    "quick reminder",
    "let that sink in",
)


class VoiceRules(BaseModel):
    """What a text post may not do, per project. The defaults are the rules
    every project had before they were settings."""

    model_config = ConfigDict(extra="ignore")

    banned_words: list[str] = Field(default_factory=lambda: list(DEFAULT_BANNED_WORDS))
    # Never name a customer, client or partner unless allowed.
    no_client_names: bool = True
    # Share the lesson, never the mechanism that is working right now.
    protect_the_edge: bool = True


def _clean_words(words: object) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for w in words if isinstance(words, list) else []:
        word = " ".join(str(w).split())[:MAX_BANNED_WORD_CHARS] if isinstance(w, str) else ""
        if word and word.lower() not in seen:
            seen.add(word.lower())
            out.append(word)
    return out[:MAX_BANNED_WORDS]


def voice_rules_of(content_brand: dict | None) -> VoiceRules:
    """The project's rules, defaults filled in. A missing key is the default;
    an empty banned list is a choice, kept as empty. Never raises: a malformed
    row reads as the defaults rather than failing a draft."""
    raw = (content_brand or {}).get(RULES_KEY)
    if not isinstance(raw, dict):
        return VoiceRules()
    # The list is cleaned word by word rather than validated whole, so one
    # bad entry costs that entry and not the project's whole list.
    switches = {k: v for k, v in raw.items() if k != "banned_words"}
    try:
        rules = VoiceRules.model_validate(switches)
    except ValueError:
        rules = VoiceRules()
    if "banned_words" in raw:
        rules.banned_words = _clean_words(raw.get("banned_words"))
    return rules


def writing_samples_of(content_brand: dict | None) -> list[str]:
    """The project's writing samples, blanks dropped, held to the caps."""
    raw = (content_brand or {}).get(SAMPLES_KEY)
    samples = [s.strip()[:MAX_SAMPLE_CHARS] for s in raw if isinstance(s, str) and s.strip()] if isinstance(raw, list) else []
    return samples[:MAX_SAMPLES]


def voice_problems(content_brand: dict | None) -> list[str]:
    """What is wrong with a saved brand's voice fields, as sentences for a 422.
    The Brand tab holds the same caps, so this only answers a caller that
    skipped it."""
    blob = content_brand or {}
    out: list[str] = []
    samples = blob.get(SAMPLES_KEY)
    if samples is not None:
        if not isinstance(samples, list) or not all(isinstance(s, str) for s in samples):
            out.append("Writing samples must be a list of posts.")
        elif len(samples) > MAX_SAMPLES:
            out.append(f"Keep it to {MAX_SAMPLES} writing samples.")
        elif any(len(s) > MAX_SAMPLE_CHARS for s in samples):
            out.append(f"A writing sample can be up to {MAX_SAMPLE_CHARS:,} characters.")
    rules = blob.get(RULES_KEY)
    if rules is not None:
        words = rules.get("banned_words") if isinstance(rules, dict) else None
        if not isinstance(rules, dict):
            out.append("Voice rules must be an object.")
        elif words is not None and (not isinstance(words, list) or not all(isinstance(w, str) for w in words)):
            out.append("Banned words must be a list of words or phrases.")
        elif words is not None and len(words) > MAX_BANNED_WORDS:
            out.append(f"Keep it to {MAX_BANNED_WORDS} banned words.")
        elif words is not None and any(len(w) > MAX_BANNED_WORD_CHARS for w in words):
            out.append(f"A banned word or phrase can be up to {MAX_BANNED_WORD_CHARS} characters.")
    return out


def _fold(text: str) -> str:
    # A curly apostrophe must not slip "here’s a thread" past "here's a thread".
    return text.replace("’", "'").replace("‘", "'").lower()


def banned_words_in(text: str, words: list[str]) -> list[str]:
    """Each banned word or phrase the text uses, in list order. Matched whole
    and case-blind, with any run of spaces between a phrase's words: "dive
    in" catches "Dive  in," and leaves "dive into" alone."""
    folded = _fold(text or "")
    found: list[str] = []
    for word in words:
        parts = _fold(word).split()
        if not parts:
            continue
        pattern = r"(?<!\w)" + r"\s+".join(re.escape(p) for p in parts) + r"(?!\w)"
        if re.search(pattern, folded):
            found.append(word)
    return found


def render_voice_stanza(rules: VoiceRules, samples: list[str], *, with_rules: bool = True) -> str:
    """The project's voice for the opening USER turn: its rules (text posts
    only, where the writer enforces them) and its writing samples. Empty when
    there is nothing project-specific to say."""
    parts: list[str] = []
    if with_rules:
        lines = ["## VOICE RULES (this project's own)", ""]
        if rules.banned_words:
            quoted = ", ".join(f'"{w}"' for w in rules.banned_words)
            lines.append(f"- Banned words and phrases (the writer refuses a post that uses one): {quoted}.")
        else:
            lines.append("- No banned words beyond plain good writing.")
        lines.append(
            "- Never name a customer, client or partner unless the brand context or the user says you may."
            if rules.no_client_names
            else "- Customers, clients and partners may be named when the post needs it."
        )
        lines.append(
            "- Protect the edge. Share the lesson and the why, never the exact mechanism that is working "
            "right now: the prompt, the model, the copy variant, the sequence. Directional is fine; "
            "reproducible by a competitor is not. If a post only works by giving the edge away, abstract "
            "it or drop it, and say so."
            if rules.protect_the_edge
            else "- The brand builds in public: the exact mechanism (prompt, model, sequence) may be shared."
        )
        parts.append("\n".join(lines))
    if samples:
        blocks = "\n\n".join(
            f'<writing_sample n="{i}">\n{s}\n</writing_sample>' for i, s in enumerate(samples, start=1)
        )
        parts.append(
            "## WRITING SAMPLES — posts this brand wrote. Match their voice: rhythm, sentence length, "
            "how they open and close. Never reuse their topics, claims or sentences.\n\n" + blocks
        )
    return "\n\n".join(parts)


__all__ = [
    "DEFAULT_BANNED_WORDS",
    "MAX_BANNED_WORDS",
    "MAX_BANNED_WORD_CHARS",
    "MAX_SAMPLES",
    "MAX_SAMPLE_CHARS",
    "RULES_KEY",
    "SAMPLES_KEY",
    "VoiceRules",
    "banned_words_in",
    "render_voice_stanza",
    "voice_problems",
    "voice_rules_of",
    "writing_samples_of",
]
