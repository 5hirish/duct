"""GitHub connector — read-only work events (commits, merged PRs, closed issues, releases, docs).

The vocabulary lives here, apart from ``fetch.py``, so the insights catalog
can name it without importing the module whose import registers the
connector.
"""

from __future__ import annotations

from enum import StrEnum

#: The registry key, the credential's ``connector_type``, and the catalog and
#: knowledge-pack name. Named rather than spelled, because connector ids as
#: literals in parallel places is the first gap STYLE.md lists.
GITHUB_CONNECTOR_ID = "github"


class WorkEventKind(StrEnum):
    """What one work-event row is. The values reach the agent through its
    catalog, so never rename one; only add."""

    COMMIT = "commit"
    PULL_REQUEST = "pull_request"
    ISSUE = "issue"
    RELEASE = "release"
    DOCS_CHANGE = "docs_change"
