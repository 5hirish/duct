"""What each OAuth scope buys, and what a credential was actually granted.

Two different facts, deliberately kept apart:

* **Declared** — the scopes a connector asks for. A catalog constant, the same
  for every user, living on ``ConnectorMeta.oauth_scope``.
* **Granted** — what the provider actually handed back for one credential.
  A per-row runtime fact that can differ per user and per reconnect, because
  Google's consent screen lets people untick individual boxes.

Nothing here infers one from the other. Code that assumes the grant matches the
request is how a connector reports "connected" in green while every call it
plans is going to 403.

The justifications are prose about a constant, so they belong in code rather
than in a table: they change when we change what we do with a permission, which
is a deploy, not a user action. The database stores one thing — the granted
scope string — and everything the UI shows is joined onto it from here.
"""

from __future__ import annotations

from dataclasses import dataclass

READ = "read"
WRITE = "write"

# Scope state as the UI shows it.
SCOPE_COMPLETE = "complete"      # everything asked for was granted
SCOPE_PARTIAL = "partial"        # authorized, but something was declined
SCOPE_UNKNOWN = "unknown"        # OAuth connector stored before we recorded grants
SCOPE_NA = "n/a"                 # manual-credential connector; no scopes exist


@dataclass(frozen=True)
class ScopeInfo:
    """One OAuth scope, in the terms a user deciding whether to grant it needs."""

    #: Names the *thing*, never the access level — ``access`` below is that,
    #: and the dialog groups the list by it. Labels used to end in "— read" /
    #: "— edit", which put the same word on screen three times in one row.
    #: Front-loaded, because a list item is judged by its first two words.
    label: str
    #: One or two sentences: what Duct does with this permission. Shown beside
    #: the scope in the connector dialog, so it is written for the person
    #: deciding, not for us.
    why: str
    access: str
    #: False when the connector still does something useful without it. Drives
    #: whether a partial grant is a warning or merely a note.
    required: bool = True


SCOPE_CATALOG: dict[str, ScopeInfo] = {
    "https://www.googleapis.com/auth/adwords": ScopeInfo(
        label="Google Ads",
        why=(
            "Reads campaign, ad group, search term and geo performance. Also the "
            "permission behind proposed changes — pausing a campaign, adding a "
            "negative keyword — which never apply without your approval."
        ),
        access=WRITE,
    ),
    "https://www.googleapis.com/auth/webmasters.readonly": ScopeInfo(
        label="Search Console",
        why=(
            "Reads queries, pages, clicks, impressions and average position. "
            "Read-only: Duct cannot change anything in Search Console."
        ),
        access=READ,
    ),
    "https://www.googleapis.com/auth/analytics.readonly": ScopeInfo(
        label="Analytics",
        why=(
            "Reads sessions, landing pages, conversions and channel data, so "
            "organic numbers can be checked against what visitors actually did."
        ),
        access=READ,
    ),
    "https://www.googleapis.com/auth/analytics.edit": ScopeInfo(
        label="Analytics key events",
        why=(
            "Only used to mark a GA4 event as a key event when you approve that "
            "change. Decline it and every report still works — Duct will just "
            "hand you the change to make yourself."
        ),
        access=WRITE,
        required=False,
    ),
    "https://www.googleapis.com/auth/tagmanager.readonly": ScopeInfo(
        label="Tag Manager",
        why="Reads containers, tags, triggers and variables to see how measurement is wired.",
        access=READ,
    ),
    "https://www.googleapis.com/auth/tagmanager.edit.containers": ScopeInfo(
        label="Tag Manager drafts",
        why=(
            "Stages measurement fixes in a container version. Staged only — "
            "nothing reaches your site until it is published."
        ),
        access=WRITE,
        required=False,
    ),
    "https://www.googleapis.com/auth/tagmanager.publish": ScopeInfo(
        label="Tag Manager publishing",
        why=(
            "Publishes a staged container version once you approve it, and is "
            "what makes a one-click rollback possible. Decline it and Duct "
            "stages the change for you to publish yourself."
        ),
        access=WRITE,
        required=False,
    ),
}


def parse_scopes(raw: str | list[str] | tuple[str, ...] | None) -> list[str]:
    """Scopes from either storage form — space-separated string or a list."""
    if not raw:
        return []
    if isinstance(raw, str):
        return [s for s in raw.split() if s]
    return [str(s) for s in raw if str(s).strip()]


def join_scopes(scopes: list[str] | tuple[str, ...] | None) -> str:
    """The storage form: space-separated, the same shape OAuth itself uses."""
    return " ".join(dict.fromkeys(parse_scopes(list(scopes or []))))


def access_for(granted: list[str]) -> list[str]:
    """What a credential can do, derived from the grant rather than declared.

    An unknown scope counts as read: it was asked for and granted, so treating
    it as nothing would understate what the connector can reach. Only a scope
    the catalog knows to be a write scope earns ``write``.
    """
    if not granted:
        return []
    levels = {READ}
    for scope in granted:
        info = SCOPE_CATALOG.get(scope)
        if info is not None and info.access == WRITE:
            levels.add(WRITE)
    return sorted(levels)


def scope_rows(declared: list[str], granted: list[str]) -> list[dict]:
    """Every scope this connector asks for, with whether it was granted.

    Ordered as declared, so the dialog reads in the same order as Google's
    consent screen. A granted scope that was never declared is appended rather
    than dropped — it is real access, and hiding it would be the more
    surprising of the two options.
    """
    seen = set(granted)
    rows: list[dict] = []
    for scope in declared:
        info = SCOPE_CATALOG.get(scope)
        rows.append({
            "scope": scope,
            "label": info.label if info else scope.rsplit("/", 1)[-1],
            "why": info.why if info else "",
            "access": info.access if info else READ,
            "required": info.required if info else True,
            "granted": scope in seen,
        })
    for scope in granted:
        if scope in declared:
            continue
        info = SCOPE_CATALOG.get(scope)
        rows.append({
            "scope": scope,
            "label": info.label if info else scope.rsplit("/", 1)[-1],
            "why": info.why if info else "",
            "access": info.access if info else READ,
            "required": False,
            "granted": True,
        })
    return rows


def missing_scopes(declared: list[str], granted: list[str]) -> list[str]:
    """Declared minus granted. Empty when nothing was declined."""
    seen = set(granted)
    return [s for s in declared if s not in seen]


def scope_status(*, is_oauth: bool, declared: list[str], granted: list[str]) -> str:
    """How the card should read: complete, partial, unknown, or not applicable.

    ``unknown`` is its own answer rather than an optimistic ``complete``: a row
    stored before grants were recorded genuinely tells us nothing, and the whole
    point of this module is to stop guessing in that situation.
    """
    if not is_oauth:
        return SCOPE_NA
    if not granted:
        return SCOPE_UNKNOWN
    return SCOPE_PARTIAL if missing_scopes(declared, granted) else SCOPE_COMPLETE
