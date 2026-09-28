"""GitHub read pull + connector registration — what shipped, and when.

The question this answers for the insights agent is "did the drop start with
a change we made?", and later, for Content Studio's daily reflection (#270),
"what did we ship today?". Both read one list of work events in one row shape
— commits, merged pull requests, closed issues, releases and changed
documentation — each with when it happened, a reference to cite, and who.

Rules encoded here, each one a way the naive reading goes wrong:

- **A pull request row is a merge**, inside the window by ``merged_at``. A PR
  closed without merging shipped nothing and is dropped, and so is every PR
  the issues endpoint returns among real issues.
- **The window is the caller's, to the day.** ``date_from`` / ``date_to``
  become ``since`` / ``until`` at the day's edges in UTC. There is no
  watermark: nothing schedules this pull, FetchData asks for a window and
  gets exactly that one.
- **File stats cost one call per commit**, so only the newest
  ``MAX_COMMIT_DETAILS`` carry them (every commit when the window is
  ``FULL_DETAIL_WINDOW_DAYS`` or shorter). A 30-day pull of a busy repository
  is then about 45 calls instead of 700, and its additions and deletions are
  a floor, which ``truncated`` says.
- **Documentation text is one compare call** for the whole window: the net
  change from the last commit before it to the newest inside it, kept for
  ``docs/`` markdown and the root README, CHANGELOG, DECISIONS and ROADMAP,
  each patch capped at ``MAX_PATCH_CHARS``. Source files are never read.
- **One failed section does not sink the others** (the Stripe rule), except
  a rejected token, a moved repository, one the token cannot see, or a spent
  rate limit: every section would fail the same way, so the pull fails once,
  with the fix.
- **A GitHub App grant becomes a token before the first call.** The row holds
  an installation id; ``_read_credentials`` mints a one-hour token narrowed
  to this one repository, so a refused mint fails the pull once, and every
  section below reads with a plain bearer token either way.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from datetime import date, datetime, time, timezone
from typing import Any

from service.connectors import (
    CAP_ACCOUNTS,
    ConnectorAuthContext,
    ConnectorMeta,
    entity_facts,
    register_connector,
)
from service.github import GITHUB_CONNECTOR_ID, WorkEventKind
from service.github import app as gh_app
from service.github import client as gh
from utils.dates import parse_iso

logger = logging.getLogger(__name__)

MAX_COMMIT_DETAILS = 30
FULL_DETAIL_WINDOW_DAYS = 2
# Per documentation file. A rewritten guide is thousands of lines; the first
# two thousand characters say what changed, and a pull has one 60,000-character
# response to share across every row.
MAX_PATCH_CHARS = 2_000
# Commit, pull request, issue and release bodies. This repository's commit
# bodies alone would fill a response; the subject line carries the event.
MAX_BODY_CHARS = 500
MAX_DESCRIPTION_CHARS = 140
SHORT_SHA = 7

DOCS_DIR = "docs/"
DOCS_EXTENSIONS = (".md", ".mdx", ".markdown")
ROOT_DOCS = frozenset({"README", "CHANGELOG", "DECISIONS", "ROADMAP"})

# Statuses that describe the token or the repository rather than one section:
# rejected, moved, not granted. A spent rate limit is the fourth such answer.
_WHOLE_PULL_STATUSES = frozenset({301, 401, 404})

# A git trailer line: `Token: value`, token letters, digits and hyphens.
_TRAILER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9-]*:\s+\S")
_PARAGRAPH_BREAK_RE = re.compile(r"\n\s*\n")


# ---------------------------------------------------------------- shaping

def window_bounds(date_from: str, date_to: str) -> tuple[datetime, datetime]:
    """The window's first and last second, in UTC. Raises ValueError on a bad date."""
    start = datetime.combine(date.fromisoformat(date_from), time.min, tzinfo=timezone.utc)
    end = datetime.combine(date.fromisoformat(date_to), time(23, 59, 59), tzinfo=timezone.utc)
    return start, end


def _iso(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _inside(timestamp: Any, start: datetime, end: datetime) -> bool:
    moment = parse_iso(timestamp)
    return moment is not None and start <= moment <= end


def _older_than(start: datetime, field: str) -> Callable[[list], bool]:
    """For a newest-first list with no ``since``: has this page gone past the window?"""

    def past(page: list) -> bool:
        moment = parse_iso((page[-1] or {}).get(field)) if page else None
        return moment is not None and moment < start

    return past


def _clip(text: Any, limit: int) -> str:
    text = str(text or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}… [{len(text) - limit:,} more characters cut]"


def _login(user: Any) -> str | None:
    return (user or {}).get("login") if isinstance(user, dict) else None


def split_message(message: Any) -> tuple[str, str, str]:
    """``(subject, body, trailers)`` of a commit message.

    Trailers are the last paragraph when every line in it is ``Token: value``
    (``Co-authored-by``, ``Refs``, ``Signed-off-by``), joined with "; " so a
    row stays one flat record. ``Closes #12`` without a colon is prose to git
    and stays in the body.
    """
    lines = str(message or "").strip().splitlines()
    if not lines:
        return "", "", ""
    subject = lines[0].strip()
    rest = "\n".join(lines[1:]).strip()
    paragraphs = _PARAGRAPH_BREAK_RE.split(rest) if rest else []
    trailers = ""
    if paragraphs:
        last = [line.strip() for line in paragraphs[-1].splitlines() if line.strip()]
        if last and all(_TRAILER_RE.match(line) for line in last):
            trailers = "; ".join(last)
            paragraphs = paragraphs[:-1]
    body = "\n\n".join(p.strip() for p in paragraphs)
    return subject, body, trailers


def is_docs_path(path: str) -> bool:
    """Markdown under ``docs/``, or a root README / CHANGELOG / DECISIONS / ROADMAP."""
    if path.startswith(DOCS_DIR):
        return path.lower().endswith(DOCS_EXTENSIONS)
    return "/" not in path and path.split(".", 1)[0].upper() in ROOT_DOCS


def _event(
    kind: WorkEventKind,
    *,
    at: Any,
    ref: Any,
    title: str,
    body: str = "",
    author: str | None = None,
    url: str | None = None,
    state: str | None = None,
    trailers: str = "",
) -> dict[str, Any]:
    """One work event. Every kind carries every key, so the rows fold to one
    table (agents/core/compaction.py) and the catalog can name each field."""
    return {
        "kind": kind.value,
        "at": at,
        "ref": ref,
        "title": title,
        "body": body,
        "author": author,
        "url": url,
        "state": state,
        # Only a commit with a detail call has these; None is "not fetched",
        # never zero lines.
        "files_changed": None,
        "additions": None,
        "deletions": None,
        "trailers": trailers,
    }


def commit_event(raw: dict) -> dict[str, Any]:
    commit = raw.get("commit") or {}
    subject, body, trailers = split_message(commit.get("message"))
    return _event(
        WorkEventKind.COMMIT,
        # The committer date is the one `since`/`until` filter on, and the one
        # a GitHub squash merge sets to the moment it landed.
        at=(commit.get("committer") or {}).get("date"),
        ref=str(raw.get("sha") or "")[:SHORT_SHA],
        title=subject,
        body=_clip(body, MAX_BODY_CHARS),
        author=_login(raw.get("author")) or (commit.get("author") or {}).get("name"),
        url=raw.get("html_url"),
        trailers=trailers,
    )


def add_file_stats(event: dict[str, Any], detail: dict) -> None:
    """Stats from one commit's detail call. ``files`` pages at 300 on GitHub's
    side, so a larger commit counts 300 files; its line stats are whole."""
    stats = detail.get("stats") or {}
    event["files_changed"] = len(detail.get("files") or [])
    event["additions"] = int(stats.get("additions") or 0)
    event["deletions"] = int(stats.get("deletions") or 0)


def pull_request_event(raw: dict) -> dict[str, Any]:
    return _event(
        WorkEventKind.PULL_REQUEST,
        at=raw.get("merged_at"),
        ref=f"#{raw.get('number')}",
        title=str(raw.get("title") or ""),
        body=_clip(raw.get("body"), MAX_BODY_CHARS),
        author=_login(raw.get("user")),
        url=raw.get("html_url"),
        state="merged",
    )


def issue_event(raw: dict) -> dict[str, Any]:
    return _event(
        WorkEventKind.ISSUE,
        at=raw.get("closed_at"),
        ref=f"#{raw.get('number')}",
        title=str(raw.get("title") or ""),
        body=_clip(raw.get("body"), MAX_BODY_CHARS),
        author=_login(raw.get("user")),
        url=raw.get("html_url"),
        # completed, not_planned, duplicate — "closed" for issues from before
        # GitHub recorded a reason.
        state=raw.get("state_reason") or "closed",
    )


def release_event(raw: dict) -> dict[str, Any]:
    return _event(
        WorkEventKind.RELEASE,
        at=raw.get("published_at"),
        ref=raw.get("tag_name"),
        title=str(raw.get("name") or raw.get("tag_name") or ""),
        body=_clip(raw.get("body"), MAX_BODY_CHARS),
        author=_login(raw.get("author")),
        url=raw.get("html_url"),
        state="prerelease" if raw.get("prerelease") else "release",
    )


def docs_event(raw: dict) -> dict[str, Any]:
    path = str(raw.get("filename") or "")
    previous = raw.get("previous_filename")
    name = f"{previous} → {path}" if previous else path
    return _event(
        WorkEventKind.DOCS_CHANGE,
        # The net change across the window, not one moment in it.
        at=None,
        ref=path,
        title=f"{name} (+{raw.get('additions') or 0} −{raw.get('deletions') or 0})",
        body=_clip(raw.get("patch"), MAX_PATCH_CHARS),
        url=raw.get("blob_url"),
        state=raw.get("status"),
    )


def _newest_first(events: list[dict]) -> list[dict]:
    # GitHub writes every timestamp as `YYYY-MM-DDTHH:MM:SSZ`, so the strings sort.
    return sorted(events, key=lambda e: e["at"] or "", reverse=True)


# ------------------------------------------------------------------ pull

def _section(errors: dict[str, str], key: str, fn: Callable[[], Any], default: Any) -> Any:
    try:
        return fn()
    except gh.ApiError as exc:
        hint = exc.hint()
        if exc.status in _WHOLE_PULL_STATUSES or exc.rate_limited:
            raise ValueError(f"GitHub {exc}. {hint}".strip()) from exc
        errors[key] = (f"{exc} → {hint}" if hint else str(exc))[:500]
        logger.warning("github pull section %s failed: %s", key, exc.summary)
        return default


def _add_details(repo_path: str, creds: dict[str, str], raw: list[dict], events: list[dict], cap: int) -> None:
    for commit, event in list(zip(raw, events))[:cap]:
        add_file_stats(event, gh.api(f"{repo_path}/commits/{commit.get('sha')}", creds))


def _docs_changes(repo_path: str, creds: dict[str, str], since: str, head: str) -> tuple[list[dict], str | None]:
    before = gh.api(f"{repo_path}/commits", creds, {"until": since, "per_page": 1})
    if not isinstance(before, list) or not before:
        return [], None  # the history starts inside the window; nothing to compare from
    base = str(before[0].get("sha") or "")
    compared = gh.api(f"{repo_path}/compare/{base}...{head}", creds)
    files = (compared.get("files") or []) if isinstance(compared, dict) else []
    events = [docs_event(f) for f in files if is_docs_path(str(f.get("filename") or ""))]
    return events, f"{base[:SHORT_SHA]}...{head[:SHORT_SHA]}"


def _read_credentials(creds: dict[str, str]) -> dict[str, str]:
    """A pasted token as it is; an App grant swapped for a token reading this repository only.

    The installation id comes from a stored row, never a request: only the
    claim route writes one (service/github/app.py).
    """
    installation_id = str(creds.get(gh_app.INSTALLATION_ID_KEY) or "").strip()
    if not installation_id:
        gh.require_credentials(creds)
        return creds
    _owner, name = gh.require_repo(creds)
    return {**creds, "token": gh_app.installation_token(installation_id, name)}


def fetch_github(creds: dict[str, str], date_from: str, date_to: str) -> dict[str, Any]:
    """The work events of one repository inside ``[date_from, date_to]``, inclusive."""
    creds = _read_credentials(creds)  # ValueError, with the fix, when GitHub refuses
    owner, name = gh.require_repo(creds)
    start, end = window_bounds(date_from, date_to)
    since, until = _iso(start), _iso(end)
    repo_path = f"repos/{owner}/{name}"
    errors: dict[str, str] = {}

    raw_commits, commits_cut = _section(
        errors, "commits",
        lambda: gh.get_pages(f"{repo_path}/commits", creds, {"since": since, "until": until}),
        ([], False),
    )
    commits = [commit_event(c) for c in raw_commits]
    window_days = (end.date() - start.date()).days + 1
    cap = len(commits) if window_days <= FULL_DETAIL_WINDOW_DAYS else MAX_COMMIT_DETAILS
    _section(errors, "commit_details", lambda: _add_details(repo_path, creds, raw_commits, commits, cap), None)
    detailed = sum(1 for e in commits if e["files_changed"] is not None)

    docs: list[dict] = []
    compared: str | None = None
    if raw_commits:
        docs, compared = _section(
            errors, "docs",
            lambda: _docs_changes(repo_path, creds, since, head=str(raw_commits[0].get("sha") or "")),
            ([], None),
        )

    raw_pulls, pulls_cut = _section(
        errors, "pull_requests",
        lambda: gh.get_pages(
            f"{repo_path}/pulls", creds,
            {"state": "closed", "sort": "updated", "direction": "desc"},
            # Merging updates a PR, so one merged inside the window was updated
            # inside it too; past that point the list is older history.
            past_window=_older_than(start, "updated_at"),
        ),
        ([], False),
    )
    pulls = [pull_request_event(p) for p in raw_pulls if _inside(p.get("merged_at"), start, end)]

    raw_issues, issues_cut = _section(
        errors, "issues",
        lambda: gh.get_pages(f"{repo_path}/issues", creds, {"state": "closed", "since": since}),
        ([], False),
    )
    issues = [
        issue_event(i) for i in raw_issues
        if "pull_request" not in i and _inside(i.get("closed_at"), start, end)
    ]

    raw_releases, releases_cut = _section(
        errors, "releases",
        lambda: gh.get_pages(f"{repo_path}/releases", creds, past_window=_older_than(start, "created_at")),
        ([], False),
    )
    # A read-only token never sees drafts; the check is for a token that can.
    releases = [
        release_event(r) for r in raw_releases
        if not r.get("draft") and _inside(r.get("published_at"), start, end)
    ]

    summary: dict[str, Any] = {
        "commits": len(commits),
        "commits_with_file_stats": detailed,
        "pull_requests_merged": len(pulls),
        "issues_closed": len(issues),
        "releases": len(releases),
        "docs_changed": len(docs),
        "docs_compared": compared,
    }
    if detailed < len(commits):
        summary["note"] = (
            f"File stats cover the newest {detailed} of {len(commits)} commits, so "
            "files_changed, additions and deletions totals are a floor."
        )

    # Most telling first: an oversized response is cut from the end
    # (agents/insights/data_tools._truncate), and commits are the long tail.
    rows = (
        _newest_first(releases) + _newest_first(pulls) + _newest_first(issues)
        + docs + _newest_first(commits)
    )
    return {
        "api": f"github-rest-{gh.API_VERSION}",
        "repo": f"{owner}/{name}",
        "window": {"from": date_from, "to": date_to, "since": since, "until": until},
        "summary": summary,
        # Top level, where agents/insights/totals.py sums the catalog's metrics.
        "rows": rows,
        "truncated": bool(commits_cut or pulls_cut or issues_cut or releases_cut or detailed < len(commits)),
        "errors": errors,
    }


# ------------------------------------------------------------ connector

class GitHubConnector:
    """A pasted token or a GitHub App grant; the account a project picks is a repository."""

    def list_accounts(self, auth: ConnectorAuthContext) -> list[dict[str, Any]]:
        creds = dict(auth.extras)
        if creds.get(gh_app.INSTALLATION_ID_KEY):
            # An App row already is one repository — GitHub named it at connect
            # time. Echoed rather than looked up: this method is also reachable
            # with request-supplied credentials, and nothing here may mint a
            # token for an installation id a request named.
            owner, name = gh.require_repo(creds)
            return [{"account_id": f"{owner}/{name}", "account_name": f"{owner}/{name}"}]
        token = gh.require_credentials(creds)  # ValueError → 422 upstream
        try:
            repos, _cut = gh.list_repositories(creds)
        except gh.ApiError as exc:
            if exc.status in (401, 403):
                raise ValueError(exc.hint() or str(exc)) from exc
            raise RuntimeError(str(exc)) from exc
        warning = gh.token_warning(token)
        rows: list[dict[str, Any]] = []
        for repo in repos:
            full_name = str(repo.get("full_name") or "")
            if not full_name:
                continue
            visibility = repo.get("visibility") or ("private" if repo.get("private") else "public")
            row: dict[str, Any] = {
                "account_id": full_name,
                "account_name": full_name,
                "entity_detail": _clip(repo.get("description"), MAX_DESCRIPTION_CHARS),
                "entity_meta": entity_facts(
                    ("Visibility", visibility),
                    ("Last push", str(repo.get("pushed_at") or "")[:10]),
                ),
                "default_branch": repo.get("default_branch"),
            }
            if warning:
                row["warning"] = warning
            rows.append(row)
        if not rows:
            raise ValueError(
                "This token can read no repositories. Edit it on GitHub and add the "
                "repository under \"Only select repositories\"."
            )
        return rows


GITHUB_META = ConnectorMeta(
    id=GITHUB_CONNECTOR_ID,
    label="GitHub",
    # No scope strings: a GitHub App declares permissions, not scopes, and a
    # pasted token carries its own. Both are read-only (`access`).
    oauth_scope=None,
    capabilities=frozenset({CAP_ACCOUNTS}),
    entity_noun="repository",
    entity_noun_plural="repositories",
    server_only_keys=frozenset({gh_app.INSTALLATION_ID_KEY}),
)

register_connector(GITHUB_META, GitHubConnector())
