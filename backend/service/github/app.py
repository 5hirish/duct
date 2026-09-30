"""GitHub App — the one-click GitHub connection, and the tokens it reads with.

Why an App rather than OAuth: a classic OAuth App's only scope that reads a
private repository, ``repo``, also writes to every repository its user can
reach. An App asks for exactly the four read permissions below, on exactly
the repositories the user ticks on GitHub's own install screen, and Duct
keeps no long-lived GitHub secret: a credential row holds an installation id,
and each pull mints a one-hour token from the App's private key, narrowed to
the one repository it reads.

The pasted fine-grained token (``client.py``) stays for self-hosted installs,
which cannot use this: the private key belongs to whoever registered the App,
and a public binary cannot carry it.

The connect, driven by ``routes/auth.py``:

1. The signed-in app mints a single-use link code for its user
   (``POST /api/user/connectors/github/connect``) and opens the authorize
   route with it — a bare navigation, which carries no bearer token.
2. GitHub's OAuth screen, with state and PKCE.
3. The callback trades the code for a user token and asks GitHub which
   installations of this App that user can reach, and which repositories in
   each (``granted_repositories``). None yet: on to GitHub's install screen,
   whose return through the setup URL restarts step 2.
4. The grant is parked behind a single-use code bound to the user from step
   1, and only that user's signed-in session can redeem it
   (``POST /api/user/connectors/github/claim``).

Step 4 is the security property. GitHub warns that the ``installation_id``
on its setup URL can be spoofed, and the general case is worse: anything a
browser could submit as a credential could name someone else's installation,
and this module's private key would mint a token for it without complaint.
So an installation id is never read from a request. The claim is its only
writer (``ConnectorMeta.server_only_keys`` refuses it everywhere else), and
what the claim writes came from GitHub, for that user's own token. Binding the
claim to the user who started the connect also closes the forged-link case,
where someone sends a victim an authorize link minted for their own account.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import threading
import time
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import urlencode

import jwt

from config import get_configs
from service.github import client as gh
from service.rest import Endpoint, RetryPolicy
from utils.dates import parse_iso

GITHUB_WEB = "https://github.com"

# Registered on the App as its callback and setup URLs, under api_public_url.
# The callback is the generic connector route in routes/auth.py.
CALLBACK_PATH = "/auth/connectors/github/oauth/callback"
SETUP_PATH = "/auth/connectors/github/setup"

#: Where an App grant is stored in a credential blob, and the one key a
#: browser may never write (module docstring, step 4).
INSTALLATION_ID_KEY = "installation_id"

#: Read-only, the same four the pasted token is told to grant. Sent on every
#: mint, so a later widening of the App's registration cannot widen what a
#: Duct token can do.
APP_PERMISSIONS = {
    "contents": "read",
    "issues": "read",
    "metadata": "read",
    "pull_requests": "read",
}

# GitHub refuses a JWT whose `exp` is more than ten minutes out, and advises
# backdating `iat` a minute against clock drift.
JWT_BACKDATE_SECONDS = 60
JWT_LIFETIME_SECONDS = 540
# An installation token lives an hour. Mint afresh once less than this is
# left, so a pull that starts on a nearly spent token does not die midway.
TOKEN_REFRESH_MARGIN_SECONDS = 300

#: Repositories one connect writes as rows, most recently pushed first. An
#: App installed on "All repositories" of a large organisation would otherwise
#: fill the picker with hundreds; "Only select repositories" reaches the rest.
MAX_GRANTED_REPOS = 50

# The code exchange is not retried: GitHub may have spent the code on the
# attempt that timed out, and the retry would only report it as bad.
_WEB = Endpoint(
    base_url=GITHUB_WEB,
    error_cls=gh.ApiError,
    retry=RetryPolicy(attempts=1),
    timeout=30,
    success=frozenset({200}),
)
# Minting is safe to repeat; a second token for the same repository is harmless.
_APP = Endpoint(
    base_url=gh.API_BASE,
    error_cls=gh.ApiError,
    retry=RetryPolicy(attempts=3, statuses={500, 502, 503, 504}, first=1.0, cap=8.0),
    timeout=30,
    success=frozenset({201}),
)


@dataclass(frozen=True)
class AppSettings:
    slug: str
    client_id: str
    client_secret: str
    private_key: str


@dataclass(frozen=True)
class GrantedRepo:
    """One repository a connect may write a row for."""

    installation_id: str
    full_name: str
    description: str
    private: bool
    pushed_at: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def settings() -> AppSettings | None:
    """The App's registration, or None when this server has none (all four or nothing)."""
    cfg = get_configs()
    values = AppSettings(
        slug=cfg.github_app_slug,
        client_id=cfg.github_app_client_id,
        client_secret=cfg.github_app_client_secret,
        private_key=cfg.github_app_private_key.replace("\\n", "\n"),
    )
    return values if all(asdict(values).values()) else None


def is_configured() -> bool:
    return settings() is not None


def _require() -> AppSettings:
    values = settings()
    if values is None:
        raise ValueError(
            "The GitHub App is not configured on this server. Connect GitHub with a "
            "fine-grained personal access token instead."
        )
    return values


def callback_url() -> str:
    return f"{get_configs().api_public_url}{CALLBACK_PATH}"


def pkce_pair() -> tuple[str, str]:
    """``(verifier, S256 challenge)`` — RFC 7636, which GitHub strongly recommends."""
    verifier = secrets.token_urlsafe(64)  # 86 characters; the RFC allows 43-128
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return verifier, base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def authorize_url(*, state: str, code_challenge: str) -> str:
    query = urlencode({
        "client_id": _require().client_id,
        "redirect_uri": callback_url(),
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    })
    return f"{GITHUB_WEB}/login/oauth/authorize?{query}"


def install_url(state: str) -> str:
    # `select_target` rather than `installations/new`: GitHub reliably carries
    # `state` from the former through to the setup URL, and the setup route
    # copes when it does not.
    slug = _require().slug
    return f"{GITHUB_WEB}/apps/{slug}/installations/select_target?{urlencode({'state': state})}"


def manage_url() -> str:
    """GitHub's page for adding or removing the repositories Duct can read."""
    return f"{GITHUB_WEB}/apps/{_require().slug}/installations/select_target"


# ------------------------------------------------------------ user side

def exchange_code(code: str, code_verifier: str) -> str:
    """The GitHub user token for an OAuth code. Raises ValueError when GitHub says no."""
    app = _require()
    body = _WEB.request(
        "login/oauth/access_token",
        method="POST",
        headers={"Accept": "application/json"},
        data={
            "client_id": app.client_id,
            "client_secret": app.client_secret,
            "code": code,
            "redirect_uri": callback_url(),
            "code_verifier": code_verifier,
        },
    )
    token = str(body.get("access_token") or "") if isinstance(body, dict) else ""
    if not token:
        # A bad, spent or expired code is a 200 with an `error` field, not a 4xx.
        reason = body.get("error_description") or body.get("error") if isinstance(body, dict) else ""
        raise ValueError(str(reason or "GitHub returned no user token."))
    return token


def granted_repositories(user_token: str) -> tuple[list[GrantedRepo], int]:
    """What this connect may write rows for, and how many were left past the cap.

    The repositories the App is installed on AND this GitHub user can see —
    the ``/user/installations`` endpoints answer that intersection. Reading
    the installation's own list instead would hand an organisation member
    every repository an admin installed the App on, including ones they
    cannot open on GitHub themselves.
    """
    creds = {"token": user_token}
    installations, _ = gh.get_pages("user/installations", creds, key="installations")
    repos: list[GrantedRepo] = []
    for installation in installations:
        installation_id = str(installation.get("id") or "")
        if not installation_id.isdigit():
            continue
        rows, _ = gh.get_pages(
            f"user/installations/{installation_id}/repositories", creds, key="repositories"
        )
        for row in rows:
            full_name = str(row.get("full_name") or "")
            if not full_name:
                continue
            repos.append(GrantedRepo(
                installation_id=installation_id,
                full_name=full_name,
                description=str(row.get("description") or ""),
                private=bool(row.get("private")),
                pushed_at=str(row.get("pushed_at") or ""),
            ))
    # ISO timestamps sort as strings; a repository never pushed sorts last.
    repos.sort(key=lambda r: r.pushed_at, reverse=True)
    return repos[:MAX_GRANTED_REPOS], max(0, len(repos) - MAX_GRANTED_REPOS)


# ------------------------------------------------------------- app side

def app_jwt(now: float | None = None) -> str:
    """The App's own identity, for minting installation tokens. RS256, ≤10 minutes."""
    app = _require()
    issued = int(now if now is not None else time.time()) - JWT_BACKDATE_SECONDS
    claims = {
        "iat": issued,
        "exp": issued + JWT_BACKDATE_SECONDS + JWT_LIFETIME_SECONDS,
        # The client ID rather than the numeric app ID: GitHub recommends it,
        # and it saves a fifth setting.
        "iss": app.client_id,
    }
    return jwt.encode(claims, app.private_key, algorithm="RS256")


_tokens: dict[tuple[str, str], tuple[str, float]] = {}
_tokens_lock = threading.Lock()


def installation_token(installation_id: str, repo_name: str) -> str:
    """A token reading ``repo_name`` alone, read-only, cached until near expiry.

    Raises ValueError with the fix when GitHub refuses: an App uninstalled,
    suspended, or no longer covering the repository is a reconnect, and a
    rejected JWT is this server's configuration, which no reconnect fixes.
    """
    installation_id = str(installation_id).strip()
    if not installation_id.isdigit():
        raise ValueError("GitHub App grant is malformed. Reconnect GitHub on the Connections page.")
    key = (installation_id, repo_name)
    with _tokens_lock:
        cached = _tokens.get(key)
    if cached and cached[1] - time.time() > TOKEN_REFRESH_MARGIN_SECONDS:
        return cached[0]

    try:
        body = _APP.request(
            f"app/installations/{installation_id}/access_tokens",
            method="POST",
            headers={
                "Authorization": f"Bearer {app_jwt()}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": gh.API_VERSION,
            },
            json={"repositories": [repo_name], "permissions": APP_PERMISSIONS},
        )
    except gh.ApiError as exc:
        raise ValueError(_mint_failure(exc)) from exc

    token = str(body.get("token") or "") if isinstance(body, dict) else ""
    expires = parse_iso(body.get("expires_at")) if isinstance(body, dict) else None
    if not token:
        raise ValueError("GitHub minted no installation token. Try again shortly.")
    expires_at = expires.timestamp() if expires else time.time() + 3600
    with _tokens_lock:
        _tokens[key] = (token, expires_at)
    return token


def _mint_failure(exc: gh.ApiError) -> str:
    if exc.status == 401:
        return (
            "GitHub rejected Duct's App credentials. This server's GitHub App settings "
            "(GITHUB_APP_CLIENT_ID, GITHUB_APP_PRIVATE_KEY) are wrong; reconnecting will not help."
        )
    if exc.status == 403:
        return (
            "GitHub has suspended the Duct app for this account or organisation. An owner "
            "can lift it in the account's GitHub App settings."
        )
    if exc.status == 404:
        return (
            "The Duct app is no longer installed where this repository lives. Reconnect "
            "GitHub on the Connections page."
        )
    if exc.status == 422:
        return (
            "The Duct app no longer has access to this repository. Add it to the "
            "installation on GitHub, or pick another repository."
        )
    return f"GitHub could not mint a token: {exc}"


def clear_token_cache() -> None:
    """For tests, and for nothing else: the cache is keyed by grant, not by user."""
    with _tokens_lock:
        _tokens.clear()
