"""PostHog AI Observability callback construction for LangChain turns."""

from __future__ import annotations

import re
from uuid import uuid4

_SESSION_ID_RE = re.compile(r"[^A-Za-z0-9\- _~.@()!'|:]")


def langchain_callback(*, session_id: str, distinct_id: str = ""):
    """Return one callback for a LangChain turn when server analytics is configured."""
    if not session_id:
        return None

    # Import lazily: server owns the singleton and imports agent modules while
    # it builds the application.
    from server import posthog_client

    if posthog_client is None:
        return None

    from posthog.ai.langchain import CallbackHandler

    kwargs = {
        "client": posthog_client,
        "properties": {"$ai_session_id": _SESSION_ID_RE.sub("-", session_id)},
        "trace_id": str(uuid4()),
    }
    if distinct_id:
        kwargs["distinct_id"] = distinct_id
    return CallbackHandler(**kwargs)
