"""PostHog AI observability: the LangChain callback for one agent turn.

A binder, like the other LangChain shims here: `service/analytics.py` owns the
client and decides whether analytics is on; this only shapes the callback.
The client runs in privacy mode, so the callback reports model, tokens,
latency, cost and errors, never the prompt or the completion.
"""

from __future__ import annotations

import re
from uuid import uuid4

# PostHog's AI session id accepts this alphabet; anything else becomes "-".
_SESSION_ID_RE = re.compile(r"[^A-Za-z0-9\- _~.@()!'|:]")


def build_callback(client, *, session_id: str, distinct_id: str = ""):
    """One callback per turn: a shared session id, a fresh trace id."""
    from posthog.ai.langchain import CallbackHandler

    kwargs = {
        "client": client,
        "properties": {"$ai_session_id": _SESSION_ID_RE.sub("-", session_id)},
        "trace_id": str(uuid4()),
        "privacy_mode": True,
    }
    if distinct_id:
        kwargs["distinct_id"] = distinct_id
    return CallbackHandler(**kwargs)
