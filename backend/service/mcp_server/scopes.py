"""What an outside agent may do in Duct, in two tiers the person chooses between.

**Set up your project** (``projects``) is what every connection gets: list,
read, draft and edit project profiles. **Work on your behalf** is opt-in, one
capability at a time, and each one is an OAuth scope so the token says what
it carries:

| Scope      | Lets the agent                                              | Ticked |
|------------|-------------------------------------------------------------|--------|
| ``data``   | read the connected sources, with totals computed by Duct    | yes    |
| ``memory`` | search what Duct remembers and save new facts               | yes    |
| ``reports``| read briefs, start one from Duct's playbook, save it        | yes    |
| ``changes``| propose a change to an ad or tag account, for you to approve | no     |
| ``content``| read the brand, plans and posts, and save post drafts       | no     |
| ``media``  | generate images on your saved provider keys (it costs you)  | no     |

None of them approves, applies, publishes, connects a tool or touches a
credential: those stay buttons in Duct whatever was granted.

Per-project grants sit beside the scopes on the token (``project_ids``), so a
connection can be "this client's project, read-only" rather than everything
the person can reach.

The app's consent page and token form show the same table from
``app/src/components/settings/AgentAbilities.jsx``; change both together.
"""

from __future__ import annotations

from collections.abc import Iterable

PROJECTS = "projects"
DATA = "data"
MEMORY = "memory"
REPORTS = "reports"
CHANGES = "changes"
CONTENT = "content"
MEDIA = "media"

SETUP_SCOPES = (PROJECTS,)
WORK_SCOPES = (DATA, MEMORY, REPORTS, CHANGES, CONTENT, MEDIA)
ALL_SCOPES = SETUP_SCOPES + WORK_SCOPES
# What the consent page ticks when the person opens the second tier: reading
# and saving inside Duct. Proposing changes, writing content and spending
# their keys each need a deliberate tick.
DEFAULT_WORK_SCOPES = (DATA, MEMORY, REPORTS)

# The one scope before tiers existed. A client that cached it, or a row made
# then, means project setup.
LEGACY_SCOPE = "mcp"


def parse(value: str | Iterable[str] | None) -> frozenset[str]:
    """The known scopes in ``value``. Unknown words are dropped rather than
    refused, so a client asking for a scope this server has never had still
    gets the ones it has. Project setup is always in: it is the floor every
    connection was allowed."""
    if value is None:
        words: Iterable[str] = ()
    elif isinstance(value, str):
        words = value.split()
    else:
        words = value
    granted = {PROJECTS if w == LEGACY_SCOPE else w for w in words}
    return frozenset((granted & set(ALL_SCOPES)) | {PROJECTS})


def serialize(scopes: Iterable[str]) -> str:
    """Space-separated, in table order, for a token response and the row."""
    chosen = set(scopes)
    return " ".join(s for s in ALL_SCOPES if s in chosen)


def has_work_tier(scopes: Iterable[str]) -> bool:
    return bool(set(scopes) & set(WORK_SCOPES))
