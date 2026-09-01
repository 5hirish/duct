"""Which Gemini key a content run spends on images.

Images are a *second* provider inside a content run: the conversation is
Anthropic, every generated image is Google. The image tools used to read
``cfg.gemini_api_key`` directly, which on the hosted deployment meant every
image a customer generated was billed to Duct — the one path the provider-key
gate did not cover.

These pin the replacement: the run resolves an image key once, stashes it on
the session, and the tools spend that or decline. No network — the Gemini
client is never constructed, because a run with no key must not get that far.
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

import routes.content as content_routes
from agents.content.schema import make_session
from agents.content.tools import build_content_mcp_server
from agents.models import Provider


async def _noop(_event: dict) -> None:
    return None


def _call(session, tool: str, args: dict) -> str:
    """Invoke one tool through the MCP server the agent actually talks to.

    Returns the text block the model would see — `_err` answers in prose, not
    JSON, and the prose is the part under test here.
    """
    import mcp.types as mt

    cfg = build_content_mcp_server(session.project_id, _noop, session)
    inst = cfg["instance"]

    async def _run():
        handler = inst.request_handlers[mt.CallToolRequest]
        res = await handler(
            mt.CallToolRequest(
                method="tools/call",
                params=mt.CallToolRequestParams(name=tool, arguments=args),
            )
        )
        return res.root.content[0].text

    return asyncio.run(_run())


# --- the tools spend the session's key, never config's ----------------------


@pytest.mark.parametrize(
    "tool,args",
    [
        ("generate_image", {"prompt": "a duct"}),
        ("edit_image", {"prompt": "brighter", "input_asset_id": str(uuid4())}),
    ],
)
def test_an_image_tool_declines_when_the_run_has_no_key(tool, args):
    """And says where to get one. The old message — "isn't enabled for this
    workspace yet" — described a Duct feature flag, which was never the
    problem: the user needs to add their own key."""
    session = make_session("t", uuid4(), "draft_post")
    assert session.gemini_api_key == ""

    result = _call(session, tool, args)
    assert "Gemini API key" in result
    assert "Providers" in result


def test_the_tools_module_cannot_reach_config_at_all():
    """The structural half of the same guarantee. A message can be reworded
    back into existence; an import that is not there cannot spend anything.
    `agents/content/tools.py` deliberately holds no route to `get_configs` —
    if this fails, someone re-added the door rather than the bug."""
    import agents.content.tools as tools

    assert not hasattr(tools, "get_configs")


# --- what the run resolves and stashes --------------------------------------


def _patch_resolution(monkeypatch, *, stored=None, raises=False):
    from agents.engines import ProviderKey, ProviderKeyRequired

    monkeypatch.setattr(content_routes, "_stored_for", lambda _owner: stored or {})

    def _resolve(provider, user_keys=None, *, stored_keys=None, duct_pays=False):
        assert provider is Provider.GOOGLE_GENAI
        supplied = (user_keys or {}).get(provider) or (stored_keys or {}).get(provider)
        if supplied:
            return ProviderKey(supplied, provider, "user")
        if raises:
            raise ProviderKeyRequired(provider)
        return ProviderKey("from-env", provider, "env")

    monkeypatch.setattr(content_routes, "resolve_provider_key", _resolve)


def test_the_callers_gemini_key_reaches_the_image_tools(monkeypatch):
    session = make_session("sid", uuid4(), "draft_post")
    monkeypatch.setattr(
        "agents.core.session.get_session", lambda _sid: session, raising=False
    )
    _patch_resolution(monkeypatch)

    content_routes._attach_image_key("sid", {Provider.GOOGLE_GENAI: "AIza-mine"})
    assert session.gemini_api_key == "AIza-mine"


def test_a_saved_gemini_key_serves_a_run_with_no_headers(monkeypatch):
    """A content session started from a resumed conversation carries no
    X-Provider header for Google."""
    session = make_session("sid", uuid4(), "draft_post")
    monkeypatch.setattr(
        "agents.core.session.get_session", lambda _sid: session, raising=False
    )
    _patch_resolution(monkeypatch, stored={Provider.GOOGLE_GENAI: "AIza-saved"})

    content_routes._attach_image_key("sid", {})
    assert session.gemini_api_key == "AIza-saved"


def test_no_image_key_leaves_the_run_alive(monkeypatch):
    """Fail-soft, deliberately. A content session is worth having without
    images; it is not worth having on Duct's bill, and it is not worth killing
    over an image tool the user may never call."""
    session = make_session("sid", uuid4(), "draft_post")
    monkeypatch.setattr(
        "agents.core.session.get_session", lambda _sid: session, raising=False
    )
    _patch_resolution(monkeypatch, raises=True)

    content_routes._attach_image_key("sid", {})  # must not raise
    assert session.gemini_api_key == ""
