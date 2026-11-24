"""What a pull request, release or issue body says, without its template.

A merged pull request is the best first draft of a story about what shipped,
but only its opening carries the why. The rest is a repository's template
(the area checkboxes, the verification log, the AI-assistance note) and, in
this repository and many others, one line that matters more than all of it:
``Launch:``, the maintainer's own decision on whether the change earns a post.
A plan from shipped work (#561) read the first 240 characters of the raw body
and so never saw that line; on 2026-11-24 it offered a feature whose own pull
request said "changelog only for now … a post before there's evidence would be
a claim".

Pure functions, no network: the fetcher and the feed both call them.
"""

from __future__ import annotations

import re

# Sections a reader of shipped work never needs: how the change was checked
# and filed, not what it did. Matched on the heading's first words.
_SKIP_SECTIONS = re.compile(
    r"^(area|verification|testing|test plan|tests|checklist|screenshots?|ai assistance|"
    r"things that need|how (?:to|it was) test|reviewer notes)\b",
    re.IGNORECASE,
)
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$")
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_CHECKBOX = re.compile(r"^\s*[-*+]\s+\[[ xX]\]")
_FENCE = re.compile(r"^\s*(```|~~~)")
# "Launch: changelog only …", "**Launch:** a blog post", "- Launch: none".
_LAUNCH_LINE = re.compile(r"^\s*(?:[-*+]\s+)?\**launch\**\s*:\**\s*(.+?)\s*$", re.IGNORECASE)
_LAUNCH_INLINE = re.compile(r"(?:^|\s)Launch:\s*(.+)$")
_CLOSES = re.compile(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)\b", re.IGNORECASE)
# The maintainer said "not yet": a story to leave out, not to tell early.
# Each phrase is a decision, not a word that can turn up in passing: a bare
# "until" held "blog post: people waited until now for Windows builds".
_HELD = re.compile(
    r"\b(only for now|for now only|(?:changelog|nothing) [\w ]{0,20}for now|not yet|"
    r"(?:hold|wait|not) until|hold(?:ing)? (?:it|the|off)|wait(?:s|ing)? (?:for|on)|no post|"
    r"before (?:there(?:'|’)s |any )?evidence|would be a claim)\b",
    re.IGNORECASE,
)
# An outlet the maintainer named, so the story was meant to be told.
_OUTLET = re.compile(r"\b(blog|post|thread|announce\w*|landing page|video|newsletter)\b", re.IGNORECASE)
# ...unless the line turns it down ("changelog only, not a blog post").
_OUTLET_REFUSED = re.compile(
    r"\b(?:no|not|nothing|never|without|none)\b[^.;|]{0,30}?\b(?:blog|post|thread|announce\w*|video|newsletter)\b",
    re.IGNORECASE,
)
# The pull request template's own line, left unfilled: a menu, not a choice.
_TEMPLATE_LAUNCH = re.compile(r"\|.*\||<n>|…$")

LAUNCH_CHARS = 300


def _lines_without_noise(text: str, *, skip_sections: bool, drop_launch: bool) -> list[str]:
    lines: list[str] = []
    skipping = False
    fenced = False
    in_launch = False
    for line in _COMMENT.sub("", text or "").splitlines():
        if _FENCE.match(line):
            fenced = not fenced
            if skip_sections:
                continue
        if fenced and skip_sections:
            continue
        heading = _HEADING.match(line)
        if heading:
            title = heading.group(1).strip()
            skipping = skip_sections and bool(_SKIP_SECTIONS.match(title))
            in_launch = drop_launch and title.lower().startswith("launch")
            if not skip_sections:
                lines.append(line)  # a whole read keeps its structure
            continue
        if skipping or in_launch:
            continue
        if _CHECKBOX.match(line):
            continue
        if drop_launch and _LAUNCH_LINE.match(line):
            continue
        lines.append(line)
    return lines


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def brief_body(text: str, limit: int) -> str:
    """The body's own words, one flat line: no template sections, checklists,
    code blocks, comments or headings, and no Launch line (see ``launch_line``)."""
    lines = _lines_without_noise(text, skip_sections=True, drop_launch=True)
    return _clip(" ".join(" ".join(lines).split()), limit)


def full_body(text: str, limit: int) -> str:
    """The whole body for a reader who asked for it: comments and checklists
    out, everything else in, line breaks kept."""
    lines = _lines_without_noise(text, skip_sections=False, drop_launch=False)
    kept = "\n".join(lines).strip()
    return _clip(re.sub(r"\n{3,}", "\n\n", kept), limit)


def launch_line(text: str) -> str:
    """The maintainer's launch decision: a ``Launch:`` line, or the first line
    under a ``## Launch`` heading. Empty when the body has neither."""
    under_heading = False
    for line in _COMMENT.sub("", text or "").splitlines():
        match = _LAUNCH_LINE.match(line)
        if match:
            return _clip(match.group(1).strip(" *"), LAUNCH_CHARS)
        heading = _HEADING.match(line)
        if heading:
            under_heading = heading.group(1).strip().lower().startswith("launch")
            continue
        if under_heading and line.strip() and not _CHECKBOX.match(line):
            return _clip(line.strip(" -*"), LAUNCH_CHARS)
    inline = _LAUNCH_INLINE.search(" ".join((text or "").split()))
    return _clip(inline.group(1).strip(), LAUNCH_CHARS) if inline else ""


def launch_held(launch: str) -> bool:
    """The Launch line says to wait: tell it later, or never in public."""
    return bool(_HELD.search(launch or ""))


def launch_names_outlet(launch: str) -> bool:
    """The Launch line names somewhere to tell it, and does not say to wait."""
    if not launch or launch_held(launch) or _TEMPLATE_LAUNCH.search(launch):
        return False
    return bool(_OUTLET.search(launch)) and not _OUTLET_REFUSED.search(launch)


def closes(text: str) -> list[int]:
    """The issues a body closes (``Closes #12``, ``fixes #3``), in order, once each."""
    seen: list[int] = []
    for number in (int(n) for n in _CLOSES.findall(text or "")):
        if number not in seen:
            seen.append(number)
    return seen


def added_lines(patch: str, limit: int) -> str:
    """What a diff added, as one line: the new entries of a changelog."""
    added = [
        line[1:].strip() for line in (patch or "").splitlines()
        if line.startswith("+") and not line.startswith("+++")
    ]
    return _clip(" · ".join(a.lstrip("#").strip() for a in added if a.lstrip("#").strip()), limit)


def dated_notes(text: str, *, limit: int = 15, width: int = 240) -> list[str]:
    """Lines that carry a date (``2026-11-08``): in a codebase that writes its
    reasons into comments, the dated ones are where a failure, its number and
    what changed after it were recorded, which is the story a post needs."""
    notes: list[str] = []
    for line in (text or "").splitlines():
        if re.search(r"\b20\d\d-\d\d-\d\d\b", line):
            notes.append(_clip(" ".join(line.split()), width))
            if len(notes) >= limit:
                break
    return notes


__all__ = [
    "LAUNCH_CHARS",
    "added_lines",
    "brief_body",
    "closes",
    "dated_notes",
    "full_body",
    "launch_held",
    "launch_line",
    "launch_names_outlet",
]
