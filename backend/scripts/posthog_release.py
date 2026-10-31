#!/usr/bin/env python
"""Tie this deploy to a PostHog release, so an error names the deploy it came from.

PostHog's documented route for a Python backend is a ``resolve-release`` step
in the deploy workflow, whose id the app then reads as ``POSTHOG_RELEASE_ID``.
Railway deploys from its own GitHub hook, so there is no deploy workflow to
put that step in; Railway's build is the one deploy step we own, and this
runs there (``railpack.json``). It finds or creates the release for the commit
being built and writes its id to ``RELEASE_ID_FILE``, which
``service/analytics.py`` reads when it builds the client.

The calls are the two ``posthog-cli release resolve`` makes, against PostHog's
published API: look the release up by ``hash_id``, create it when missing.
``hash_id`` is the CLI's own (SHA-512 of name then version), so a release the
CLI made for the same name and version is found, not duplicated.

Off unless ``POSTHOG_CLI_API_KEY`` is set (a personal API key with
``error_tracking:write``), so staging and self-hosted builds skip it. It never
fails the build: a deploy without a release id costs a less useful stack trace,
and a failed deploy costs the deploy.
"""

from __future__ import annotations

import hashlib
import os
import sys
from collections.abc import Mapping
from pathlib import Path

import httpx

BACKEND_DIR = Path(__file__).resolve().parents[1]
RELEASE_ID_FILE = BACKEND_DIR / ".posthog-release-id"

# The app's source maps upload as "duct-app" (app/next.config.mjs). A distinct
# name keeps a backend deploy and an app deploy of the same commit apart.
RELEASE_NAME = "duct-backend"
DEFAULT_HOST = "https://us.posthog.com"
# The build waits on this; PostHog being slow must not make the deploy slow.
TIMEOUT_SECONDS = 15.0
_HASH_IN_USE = "release_hash_in_use"


def release_hash(name: str, version: str) -> str:
    return hashlib.sha512((name + version).encode()).hexdigest()


def _git_metadata(env: Mapping[str, str]) -> dict:
    """The CLI's ``git`` block, from what Railway tells a build about its commit."""
    git = {"commit_id": env["RAILWAY_GIT_COMMIT_SHA"], "branch": env.get("RAILWAY_GIT_BRANCH", "")}
    owner, repo = env.get("RAILWAY_GIT_REPO_OWNER", ""), env.get("RAILWAY_GIT_REPO_NAME", "")
    if repo:
        git["repo_name"] = repo
        if owner:
            git["remote_url"] = f"https://github.com/{owner}/{repo}.git"
    return {"git": git}


def resolve(env: Mapping[str, str], http: httpx.Client) -> str | None:
    """The release id for this build's commit, or None when there is nothing to do."""
    key = env.get("POSTHOG_CLI_API_KEY", "").strip()
    project = env.get("POSTHOG_CLI_PROJECT_ID", "").strip()
    version = env.get("RAILWAY_GIT_COMMIT_SHA", "").strip()
    if not (key and project and version):
        return None

    host = (env.get("POSTHOG_CLI_HOST") or DEFAULT_HOST).rstrip("/")
    releases = f"{host}/api/projects/{project}/error_tracking/releases/"
    digest = release_hash(RELEASE_NAME, version)
    headers = {"Authorization": f"Bearer {key}"}

    def lookup() -> str | None:
        found = http.get(f"{releases}hash/{digest}/", headers=headers)
        if found.status_code == 404:
            return None
        found.raise_for_status()
        return found.json()["id"]

    if (existing := lookup()) is not None:
        return existing
    created = http.post(
        releases,
        headers=headers,
        json={"project": RELEASE_NAME, "version": version, "hash_id": digest, "metadata": _git_metadata(env)},
    )
    # Two builds of one commit can race to create it; the loser takes the winner's.
    if created.status_code == 400 and _HASH_IN_USE in created.text and (winner := lookup()):
        return winner
    created.raise_for_status()
    return created.json()["id"]


def main(env: Mapping[str, str] | None = None, http: httpx.Client | None = None) -> int:
    env = os.environ if env is None else env
    if not env.get("POSTHOG_CLI_API_KEY", "").strip():
        print("posthog release: off (POSTHOG_CLI_API_KEY is not set)")
        return 0
    try:
        with http or httpx.Client(timeout=TIMEOUT_SECONDS) as client:
            release_id = resolve(env, client)
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        # The type and status only: an httpx error's text carries the request,
        # and the request carries the key.
        status = getattr(getattr(exc, "response", None), "status_code", "")
        reason = f"{type(exc).__name__} {status}".strip()
        print(f"posthog release: skipped ({reason})")
        return 0
    if release_id is None:
        print("posthog release: skipped (no POSTHOG_CLI_PROJECT_ID or RAILWAY_GIT_COMMIT_SHA)")
        return 0
    RELEASE_ID_FILE.write_text(release_id + "\n")
    print(f"posthog release: {RELEASE_NAME}@{env['RAILWAY_GIT_COMMIT_SHA'][:12]} is {release_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
