"""GitHub REST API — bearer auth, transport and page-number paging.

Every call here carries a bearer token and nothing else decides which one.
Two kinds arrive:

- a **fine-grained personal access token** the user pasted, limited to the
  repositories they selected, with read-only Contents, Pull requests, Issues
  and Metadata — the path a self-hosted install runs, where no GitHub App's
  private key can ship;
- a **one-hour installation token** the GitHub App minted for exactly one
  repository (``app.py``), swapped in by the fetcher before the first call.

So this module never sees an App grant, only its token, and stays free of
the App's JWT and settings
(docs/engineering/2026-09-28-github-connector-research.md, A2).

A classic token (``ghp_…``) works too, but its ``repo`` scope writes to every
repository its owner can reach, so it is accepted with a warning rather than
refused — the Stripe full-key rule.

Paging is by page number, not the ``Link`` header GitHub documents:
``service/rest.py`` hands back the body only, every endpoint this connector
reads takes ``page``, and a short page is the end of the list. That keeps the
shared transport and its ``FakeWire`` test seam unchanged.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from service.rest import ApiError as BaseApiError
from service.rest import Endpoint, RetryPolicy

API_BASE = "https://api.github.com"

# Pinned the way Stripe's version is, so a GitHub-side default change cannot
# reshape a field we parse. 2022-11-28 is supported until at least 2028-03-10;
# 2026-03-10 drops `merge_commit_sha` from pull requests, so moving means
# reading the breaking-changes page first.
API_VERSION = "2022-11-28"

PAGE_SIZE = 100  # GitHub's maximum per_page on every list read here
# A list still going after this many pages is cut and says so. 1,000 commits,
# pull requests or repositories in one window is past what one FetchData
# response can carry anyway (agents/insights/fetchers.MAX_RESPONSE_CHARS).
MAX_PAGES = 10

CLASSIC_TOKEN_PREFIX = "ghp_"
NEW_TOKEN_URL = "https://github.com/settings/personal-access-tokens/new"

# `owner/name` as GitHub allows it. The value is spliced into a URL path, so
# anything else — a stray slash, `..` — is refused before a request is built.
_REPO_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]*/(?!\.\.?$)[A-Za-z0-9._-]+$")

_PERMISSIONS = "read-only Contents, Pull requests, Issues and Metadata"


class ApiError(BaseApiError):
    """GitHub's envelope is ``{"message": …, "documentation_url": …}``."""

    def parse(self, body: str) -> str:
        try:
            data = json.loads(body)
        except ValueError:
            return ""
        return str(data.get("message") or "") if isinstance(data, dict) else ""

    @property
    def rate_limited(self) -> bool:
        """GitHub sends a spent limit, primary or secondary, as a 403 or a 429
        that says so; a 403 without those words is a permission."""
        return self.status in (403, 429) and "rate limit" in self.summary.lower()

    def hint(self) -> str:
        # Worded for both ways in: a pasted token and the GitHub App. The
        # App's own failures (an uninstall, a repository taken off it) happen
        # while minting, and app.py words those itself.
        message = self.summary.lower()
        if self.status == 401:
            return (
                "GitHub rejected the credentials: the token has expired or been "
                "revoked. Reconnect GitHub on the Connections page."
            )
        if self.status == 301:
            return (
                "The repository was renamed or transferred. Pick it again on the "
                "Connections page."
            )
        if self.rate_limited:
            return (
                "GitHub's rate limit is spent: 5,000 requests an hour for a pasted "
                "token, shared with its owner's other tools, and at least that for "
                "the GitHub App. Wait for it to reset before pulling again."
            )
        if self.status == 403 and "not accessible" in message:
            return f"The credentials lack a permission this read needs: {_PERMISSIONS}."
        if self.status == 403:
            return (
                "GitHub refused access to this repository. An organisation can require "
                "an owner to approve Duct's access, or block it; until then only "
                "public repositories are readable."
            )
        if self.status == 404:
            return (
                "The repository is not among those granted to Duct, or it no longer "
                "exists. Grant it on GitHub, or pick another one."
            )
        return ""


def require_credentials(creds: dict[str, str]) -> str:
    token = (creds.get("token") or "").strip()
    if not token:
        raise ValueError(
            "GitHub credentials incomplete — token missing. Create a fine-grained "
            f"personal access token at {NEW_TOKEN_URL} with \"Only select repositories\" "
            f"and {_PERMISSIONS}."
        )
    return token


def require_repo(creds: dict[str, str]) -> tuple[str, str]:
    """``(owner, name)`` of the picked repository."""
    repo = (creds.get("repo") or "").strip()
    if not _REPO_RE.match(repo):
        raise ValueError(
            "GitHub repository missing or malformed — expected owner/name. Pick the "
            "repository on the Connections page."
        )
    owner, name = repo.split("/", 1)
    return owner, name


def token_warning(token: str) -> str:
    """Non-fatal: a classic token works but violates least privilege."""
    if token.startswith(CLASSIC_TOKEN_PREFIX):
        return (
            "This is a classic token: its repo scope can write to every repository "
            "you can reach. A fine-grained, read-only token limited to the repositories "
            "Duct reads is strongly preferred — Duct only ever reads."
        )
    return ""


# Rate limits are not retried here, unlike the shared default. A secondary
# limit wants a minute and a spent primary one up to an hour — longer than a
# FetchData call should hold a turn — so the hint says so instead.
_ENDPOINT = Endpoint(
    base_url=API_BASE,
    error_cls=ApiError,
    retry=RetryPolicy(attempts=3, statuses={500, 502, 503, 504}, first=1.0, cap=8.0),
    timeout=60,
    success=frozenset({200}),
)


def _headers(creds: dict[str, str]) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {require_credentials(creds)}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": API_VERSION,
    }


def api(path: str, creds: dict[str, str], params: dict | None = None) -> Any:
    """GET one GitHub endpoint. Returns parsed JSON (a list for list reads)."""
    return _ENDPOINT.request(path, headers=_headers(creds), params=params)


def get_pages(
    path: str,
    creds: dict[str, str],
    params: dict | None = None,
    *,
    past_window: Callable[[list], bool] | None = None,
    key: str = "",
) -> tuple[list, bool]:
    """Every row of a list endpoint, and whether the list was cut at ``MAX_PAGES``.

    Stops on a short page, or when ``past_window(page)`` says the newest-first
    list has gone older than the window — the pull requests and releases lists
    take no ``since``, so reading them to the end would page through a
    repository's whole history.

    ``key`` is for the lists GitHub wraps in an object —
    ``{"total_count": n, "installations": [...]}`` — rather than returning
    bare, which is every installation and installation-repository list.
    """
    rows: list = []
    for page in range(1, MAX_PAGES + 1):
        batch = api(path, creds, {**(params or {}), "per_page": PAGE_SIZE, "page": page})
        if key and isinstance(batch, dict):
            batch = batch.get(key)
        if not isinstance(batch, list):
            return rows, False
        rows.extend(batch)
        if len(batch) < PAGE_SIZE or (past_window is not None and past_window(batch)):
            return rows, False
    return rows, True


def list_repositories(creds: dict[str, str]) -> tuple[list[dict], bool]:
    """Repositories this token can read, most recently pushed first.

    For a fine-grained token with "Only select repositories" this is expected
    to be exactly the selection (research memo, A4 — to confirm on the first
    live token). A classic token lists everything its owner can reach.
    """
    return get_pages("user/repos", creds, {"sort": "pushed"})
