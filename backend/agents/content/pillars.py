"""The content pillars a project plans and drafts from.

Two places hold pillars. The Brand tab writes Content Studio's own list
(``projects.content_pillars["items"]``: id, name, description). The audit's
crawl and an outside agent's ``draft_project`` write the project profile's
(``brand_channels["content_pillars"]``: names only), under the draft rules in
``service/project_draft.py``. The content agent read only the first, so a
project set up through the audit or from Claude Code planned with no pillars
while its profile listed four.

Every reader goes through ``pillars_of``: the Studio's own list wins once it
names a pillar, and until then the profile's names stand in, shaped as
pillars. The Brand tab shows the same list, so saving it is the person
taking those pillars as their own.
"""

from __future__ import annotations

from typing import Any

from utils.strings import slugify

# The Brand tab keys pillars by underscore slugs (BrandContextForm's
# pillarSlug), and research_pillar sub-agents are dispatched by that id.
_ID_SEP = "_"


def pillars_of(project: Any) -> list[dict]:
    """The project's pillars as ``{id, name, description}`` rows."""
    blob = project.content_pillars or {}
    items = blob.get("items") if isinstance(blob, dict) else blob
    own = [p for p in (items or []) if isinstance(p, dict)]
    if any(str(p.get("name") or "").strip() for p in own):
        return own
    drafted = (project.brand_channels or {}).get("content_pillars") or []
    out: list[dict] = []
    seen: set[str] = set()
    for name in drafted:
        if not isinstance(name, str):
            continue
        pillar_id = slugify(name, sep=_ID_SEP)
        if pillar_id and pillar_id not in seen:
            seen.add(pillar_id)
            out.append({"id": pillar_id, "name": name.strip(), "description": ""})
    return out
