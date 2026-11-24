"""Reads of one repository beyond the window's events, for a plan from
shipped work (#561): whether the repository is public, which open issues ask
for help, and one pull request, release, issue, commit or file read whole.

``fetch_github`` answers "what happened in this window" for FetchData, in one
row shape both agents share. These answer the questions a story needs after
that, and only Content Studio's plan from shipped work asks them, so they
cost FetchData nothing.

Two rules, each a way a careless read leaks or misleads:

- **A private repository's code never reaches a model.** Visibility comes from
  GitHub, never from a request, and an unknown visibility is private. On a
  private repository a pull request reads as its words and counts; file
  names, file text and dated notes are public-only.
- **Every read is bounded**, by characters and by count, because a body or a
  file is the repository's text in the model's context: information to cite,
  never instructions.

Every call is a GET on the narrowed read token ``fetch.read_credentials``
mints, with the App's four read permissions (contents, pull requests, issues,
metadata): nothing here needs more.
"""

from __future__ import annotations

import base64
import binascii
import logging
from typing import Any
from urllib.parse import quote

from service.github import client as gh
from service.github.fetch import read_credentials
from service.github.prose import brief_body, dated_notes, full_body, launch_line

logger = logging.getLogger(__name__)

PUBLIC = "public"
# The labels a repository uses to ask outsiders in. GitHub's own defaults.
ASK_LABELS = ("help wanted", "good first issue")
MAX_ASKS = 10
ASK_BODY_CHARS = 240
BODY_CHARS = 6_000
ISSUE_CHARS = 4_000
FILE_CHARS = 8_000
MAX_FILES_LISTED = 100
# A file larger than this is generated or vendored, never a story.
MAX_FILE_BYTES = 400_000


def _visibility(repo: Any) -> str:
    if not isinstance(repo, dict):
        return "private"
    return str(repo.get("visibility") or ("private" if repo.get("private", True) else PUBLIC))


def repository_visibility(creds: dict[str, str]) -> str:
    """``public`` or anything else, which reads as private. One call."""
    creds = read_credentials(creds)
    owner, name = gh.require_repo(creds)
    return _visibility(gh.api(f"repos/{owner}/{name}", creds))


def repository_facts(creds: dict[str, str]) -> dict[str, Any]:
    """``{"visibility": …, "asks": [...]}``: whether the repository is public,
    and, when it is, the open issues labelled for outside help. A private
    repository's open issues are its team's backlog, never a post."""
    creds = read_credentials(creds)
    owner, name = gh.require_repo(creds)
    visibility = _visibility(gh.api(f"repos/{owner}/{name}", creds))
    asks: list[dict[str, Any]] = []
    if visibility == PUBLIC:
        seen: set[int] = set()
        for label in ASK_LABELS:
            rows = gh.api(f"repos/{owner}/{name}/issues", creds,
                          {"state": "open", "labels": label, "sort": "updated", "per_page": MAX_ASKS})
            for raw in rows if isinstance(rows, list) else []:
                number = raw.get("number")
                if "pull_request" in raw or not isinstance(number, int) or number in seen:
                    continue
                seen.add(number)
                asks.append({
                    "ref": f"#{number}",
                    "title": str(raw.get("title") or ""),
                    "body": brief_body(str(raw.get("body") or ""), ASK_BODY_CHARS),
                    "labels": [str(lb.get("name")) for lb in raw.get("labels") or [] if isinstance(lb, dict)],
                    "url": raw.get("html_url"),
                    "at": raw.get("updated_at"),
                    "assigned": bool(raw.get("assignees")),
                })
    return {"visibility": visibility, "asks": asks[:MAX_ASKS]}


def _file_text(owner: str, name: str, path: str, creds: dict[str, str], ref: str = "") -> dict[str, Any]:
    params = {"ref": ref} if ref else None
    raw = gh.api(f"repos/{owner}/{name}/contents/{quote(path, safe='/')}", creds, params)
    if not isinstance(raw, dict) or raw.get("type") != "file":
        return {"status": "not_a_file", "path": path}
    if int(raw.get("size") or 0) > MAX_FILE_BYTES or raw.get("encoding") != "base64":
        return {"status": "too_large", "path": path}
    try:
        text = base64.b64decode(str(raw.get("content") or "")).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        return {"status": "not_text", "path": path}
    return {
        "status": "ok",
        "path": path,
        # The dated lines first: they are where a codebase that writes its
        # reasons down recorded what broke, when, and by how much.
        "dated_notes": dated_notes(text),
        "text": text if len(text) <= FILE_CHARS else text[:FILE_CHARS].rstrip() + "\n… [cut]",
    }


def read_pull_request(creds: dict[str, str], number: int, *, public: bool, path: str = "") -> dict[str, Any]:
    creds = read_credentials(creds)
    owner, name = gh.require_repo(creds)
    pr = gh.api(f"repos/{owner}/{name}/pulls/{number}", creds)
    if not isinstance(pr, dict):
        return {"status": "not_found"}
    body = str(pr.get("body") or "")
    out: dict[str, Any] = {
        "status": "ok",
        "title": pr.get("title"),
        "merged_at": pr.get("merged_at"),
        "url": pr.get("html_url"),
        "labels": [str(lb.get("name")) for lb in pr.get("labels") or [] if isinstance(lb, dict)],
        "launch": launch_line(body),
        "changed_files": pr.get("changed_files"),
        "additions": pr.get("additions"),
        "deletions": pr.get("deletions"),
        "body": full_body(body, BODY_CHARS),
    }
    if not public:
        # Its words and counts are what the feed already showed; its paths are not.
        out["note"] = "Private repository: file names and file text are not read."
        return out
    files = gh.api(f"repos/{owner}/{name}/pulls/{number}/files", creds, {"per_page": MAX_FILES_LISTED})
    names = [str(f.get("filename")) for f in files if isinstance(f, dict)] if isinstance(files, list) else []
    out["files"] = names
    if path:
        if path not in names:
            out["file"] = {"status": "not_in_pull_request", "path": path}
        else:
            out["file"] = _file_text(owner, name, path, creds, str(pr.get("merge_commit_sha") or ""))
    return out


def read_release(creds: dict[str, str], tag: str) -> dict[str, Any]:
    creds = read_credentials(creds)
    owner, name = gh.require_repo(creds)
    rel = gh.api(f"repos/{owner}/{name}/releases/tags/{quote(tag, safe='')}", creds)
    if not isinstance(rel, dict):
        return {"status": "not_found"}
    return {
        "status": "ok",
        "title": rel.get("name") or rel.get("tag_name"),
        "published_at": rel.get("published_at"),
        "url": rel.get("html_url"),
        "body": full_body(str(rel.get("body") or ""), BODY_CHARS),
    }


def read_issue(creds: dict[str, str], number: int) -> dict[str, Any]:
    creds = read_credentials(creds)
    owner, name = gh.require_repo(creds)
    issue = gh.api(f"repos/{owner}/{name}/issues/{number}", creds)
    if not isinstance(issue, dict):
        return {"status": "not_found"}
    return {
        "status": "ok",
        "title": issue.get("title"),
        "state": issue.get("state"),
        "url": issue.get("html_url"),
        "labels": [str(lb.get("name")) for lb in issue.get("labels") or [] if isinstance(lb, dict)],
        "body": full_body(str(issue.get("body") or ""), ISSUE_CHARS),
    }


def read_commit(creds: dict[str, str], sha: str, *, public: bool) -> dict[str, Any]:
    creds = read_credentials(creds)
    owner, name = gh.require_repo(creds)
    commit = gh.api(f"repos/{owner}/{name}/commits/{quote(sha, safe='')}", creds)
    if not isinstance(commit, dict):
        return {"status": "not_found"}
    out: dict[str, Any] = {
        "status": "ok",
        "message": full_body(str((commit.get("commit") or {}).get("message") or ""), ISSUE_CHARS),
        "url": commit.get("html_url"),
    }
    if public:
        out["files"] = [str(f.get("filename")) for f in commit.get("files") or [] if isinstance(f, dict)]
    return out


def read_file(creds: dict[str, str], path: str) -> dict[str, Any]:
    """A file on the default branch. Public repositories only; the caller checks."""
    creds = read_credentials(creds)
    owner, name = gh.require_repo(creds)
    return _file_text(owner, name, path, creds)


__all__ = [
    "ASK_LABELS",
    "PUBLIC",
    "read_commit",
    "read_file",
    "read_issue",
    "read_pull_request",
    "read_release",
    "repository_facts",
    "repository_visibility",
]
