"""The route authorization gate.

``validate_api_key`` is not an authorization boundary. ``DUCT_API_KEY`` ships to
the browser as ``NEXT_PUBLIC_DUCT_API_KEY``, so it proves "this request came
from the Duct app" and never "this caller owns that row". A router mounted
behind it alone *looks* protected and is not — which is exactly the mistake
that is easy to make when adding an endpoint quickly, and the one an outside
contributor (or a coding agent) is most likely to make, because the surrounding
code reads as though it is already guarded.

``routes/namespace.py`` explains the two gates in prose. This test makes them a
property of the running app, by walking FastAPI's resolved dependency tree for
every mounted route rather than reading source.

It fails in two directions:

  * a project-scoped route appears without ``get_current_user`` anywhere in its
    dependency chain, or
  * an ungated ``/api`` route appears that is not on ``UNGATED`` — or an entry
    on ``UNGATED`` has become gated and the allowlist is now blessing nothing.

Adding an entry to ``UNGATED`` is a deliberate act, not the fix for a failing
test. The usual fix is to mount the router with ``APP_AND_USER``. If a route
genuinely must be reachable without a signed-in user, say why in the comment
beside its entry — the reason is the part that is worth reviewing.

Note what this does *not* check: that a route with ``get_current_user`` also
runs the right membership check. No structural test can see that. The
per-router suites (``test_content_access.py``, ``test_connector_access.py``,
``test_agent_session_project_access.py``) assert the actual 404-for-a-stranger
behaviour, and remain the real guarantee. This test only closes the cheaper
hole: forgetting the user entirely.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("DUCT_API_KEY", "test-api-key")

from server import app  # noqa: E402  — import after the env default above

# ---------------------------------------------------------------------------
# Routes that resolve no signed-in user, and why each one is allowed to.
#
# Keyed by "METHOD path". Anything not listed here must carry
# `get_current_user`, so a new router lands as a failing test until its author
# has made the call consciously.
# ---------------------------------------------------------------------------
UNGATED: dict[str, str] = {
    # Public catalogue reads. These describe what Duct *can* do, not what any
    # account has done, so they leak nothing about a user. All are behind
    # validate_api_key, which keeps them off the open internet.
    "GET /api/engines/status": "capability catalogue; reports presence, never a key",
    "GET /api/engines/thinking": "static catalogue of thinking levels per model",
    "GET /api/insights/modes": "static list of insight modes",
    "GET /api/models/catalogue": "static model catalogue",
    "POST /api/models/preview": "resolves a tier map to model names; no stored data",
    "GET /api/projects/config": "static project-shape options (industries, models)",
    "GET /api/providers/status": "reads the caller's own X-Provider-* headers, reports presence only",
    "GET /api/execute/ops": "static registry of executor operations",
    # Agent sessions authenticate with `get_current_user_optional` and then
    # perform their own ownership check downstream — a session created before
    # sign-in has no user to match, so the dependency cannot be mandatory. The
    # downstream check is asserted by test_agent_session_project_access.py.
    "GET /api/agents": "agent-type catalogue",
    "GET /api/agents/{agent_type}": "agent-type descriptor",
    "POST /api/agents/{agent_type}/sessions": "optional user; session records user_id when present",
    "GET /api/agents/{agent_type}/sessions/{session_id}": "optional user; ownership checked downstream",
    "DELETE /api/agents/{agent_type}/sessions/{session_id}": "optional user; ownership checked downstream",
    "POST /api/agents/{agent_type}/sessions/{session_id}/messages": "optional user; ownership checked downstream",
    "GET /api/agents/{agent_type}/sessions/{session_id}/stream": "optional user; ownership checked downstream",
    # Invitation preview. The recipient has not signed in yet, and the token in
    # the URL is the secret. Accepting an invitation (POST) does require a JWT.
    "GET /api/invitations/{token}": "pre-sign-in preview; the token is the credential",
    # Lead magnet capture. Deliberately public and Turnstile-gated rather than
    # API-key gated: these are hit from the marketing site by people with no
    # account at all.
    "GET /api/lead-magnet/check-url": "public; Turnstile-gated",
    "POST /api/lead-magnet/execution-interest": "public; Turnstile-gated",
    "POST /api/lead-magnet/report": "public; Turnstile-gated",
    "POST /api/lead-magnet/submit": "public; Turnstile-gated",
    "POST /api/lead-magnet/validate": "public; Turnstile-gated",
}


def _dependency_names(dependant) -> set[str]:
    """Every callable FastAPI will resolve for a route, flattened."""
    names: set[str] = set()
    stack = [dependant]
    while stack:
        node = stack.pop()
        if node.call is not None:
            names.add(getattr(node.call, "__name__", repr(node.call)))
        stack.extend(node.dependencies)
    return names


def _routes():
    """(method, path, dependency names, is_project_scoped) for every API route."""
    for route in app.routes:
        dependant = getattr(route, "dependant", None)
        if dependant is None:  # mounts, static files
            continue
        methods = sorted(route.methods - {"HEAD", "OPTIONS"}) or sorted(route.methods)
        params = {
            p.name
            for p in dependant.path_params + dependant.query_params + dependant.body_params
        }
        scoped = "project_id" in route.path or "project_id" in params
        for method in methods:
            yield method, route.path, _dependency_names(dependant), scoped


def test_every_project_scoped_route_resolves_a_user():
    """A route that names a project must know who is asking.

    This is the cheap half of the membership rule and the half a structural
    test can enforce. An endpoint that takes a `project_id` and never resolves
    a user is letting the caller vouch for themselves.
    """
    offenders = [
        f"{method} {path}"
        for method, path, deps, scoped in _routes()
        if scoped and "get_current_user" not in deps
    ]
    assert not offenders, (
        "These routes are project-scoped but resolve no signed-in user:\n  "
        + "\n  ".join(sorted(offenders))
        + "\n\nAdd `get_current_user` and a membership check "
        "(`get_project_for_user` for a project named in the request, "
        "`get_project_row_for_user` for a row addressed by its own id). "
        "Return 404, not 403, for a non-member."
    )


def test_ungated_api_routes_are_all_declared():
    """Adding a router without deciding about auth fails here.

    The allowlist is the decision record. If this fails on a route you just
    added, the question to answer is not "how do I silence it" but "should an
    anonymous caller be able to do this".
    """
    undeclared = [
        f"{method} {path}"
        for method, path, deps, _ in _routes()
        if path.startswith("/api") and "get_current_user" not in deps
        and f"{method} {path}" not in UNGATED
    ]
    assert not undeclared, (
        "Ungated /api routes that are not declared in UNGATED:\n  "
        + "\n  ".join(sorted(undeclared))
        + "\n\nMount the router with APP_AND_USER in routes/namespace.py, or add "
        "an entry to UNGATED in this file explaining why anonymous access is correct."
    )


def test_the_allowlist_has_not_gone_stale():
    """An entry that is now gated is blessing nothing and should be deleted."""
    live = {
        f"{method} {path}"
        for method, path, deps, _ in _routes()
        if "get_current_user" not in deps
    }
    stale = sorted(set(UNGATED) - live)
    assert not stale, (
        "These UNGATED entries no longer match an ungated route — they are "
        "either now authenticated (delete the entry) or renamed (update it):\n  "
        + "\n  ".join(stale)
    )


@pytest.mark.parametrize("reason", UNGATED.values())
def test_every_allowlist_entry_carries_a_reason(reason):
    """A bare exemption is a hole in the check, not an exemption."""
    assert reason.strip(), "UNGATED entries must explain why anonymous access is correct"
