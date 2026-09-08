"""Which key a content run spends on images.

Images are a *second* provider inside a content run: the conversation is on
whichever provider the user brought a key for, every generated image is on
whichever *image-capable* provider they brought a key for — Gemini, OpenAI or
xAI, in that order of preference. The image tools used to read
``cfg.gemini_api_key`` directly, which on the hosted deployment meant every
image a customer generated was billed to Duct — the one path the provider-key
gate did not cover. Then they read only a Gemini key, which sent a user on an
OpenAI key to Google for something their own key already does.

These pin the replacement: the run resolves an image provider + key once,
stashes both on the session, and the tools spend that or decline. No network
— no client is ever constructed, because a run with no key must not get that
far.
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

import routes.content as content_routes
from agents import engines
from agents.content.schema import make_session
from agents.content.tools import build_content_tools_lc
from agents.models import ImageModel, Provider


async def _noop(_event: dict) -> None:
    return None


def _call(session, tool: str, args: dict) -> str:
    """Invoke one tool as the agent would — through the bound LangChain tool.

    Returns what the model would read — `_err` answers in prose inside its
    JSON envelope, and the prose is the part under test here.
    """
    tools = {t.name: t for t in build_content_tools_lc(session.project_id, _noop, session)}
    return asyncio.run(tools[tool].ainvoke(args))


# --- the tools spend the session's key, never config's ----------------------


@pytest.mark.parametrize(
    "tool,args",
    [
        ("generate_image", {"prompt": "a duct"}),
        ("edit_image", {"prompt": "brighter", "input_asset_id": str(uuid4())}),
    ],
)
def test_an_image_tool_declines_when_the_run_has_no_key(tool, args):
    """And says where to get one — naming every provider that would do,
    not just Google. The old message — "isn't enabled for this workspace
    yet" — described a Duct feature flag, which was never the problem: the
    user needs to add their own key."""
    session = make_session("t", uuid4(), "draft_post")
    assert session.image_provider is None and session.image_api_key == ""

    result = _call(session, tool, args)
    assert "Providers" in result
    for provider_name in ("Gemini", "OpenAI", "xAI"):
        assert provider_name in result


def test_the_tools_module_cannot_reach_config_at_all():
    """The structural half of the same guarantee. A message can be reworded
    back into existence; an import that is not there cannot spend anything.
    `agents/content/tools.py` deliberately holds no route to `get_configs` —
    if this fails, someone re-added the door rather than the bug."""
    import agents.content.tools as tools

    assert not hasattr(tools, "get_configs")


# --- what the run resolves and stashes --------------------------------------


def _patch_resolution(monkeypatch, *, stored=None, raises=False):
    """Stand in for ``resolve_provider_key`` with the real precedence — header,
    then saved, then env — minus the config read, so the order the image
    resolver walks providers in is what is under test."""
    from agents.engines import ProviderKey, ProviderKeyRequired

    monkeypatch.setattr(content_routes, "stored_keys_for", lambda _owner: stored or {})

    def _resolve(provider, user_keys=None, *, stored_keys=None, duct_pays=False):
        supplied = (user_keys or {}).get(provider)
        if supplied:
            return ProviderKey(supplied, provider, "user")
        saved = (stored_keys or {}).get(provider)
        if saved:
            return ProviderKey(saved, provider, "stored")
        if raises:
            raise ProviderKeyRequired(provider)
        return ProviderKey("from-env", provider, "env")

    monkeypatch.setattr(engines, "resolve_provider_key", _resolve)


def _session_under(monkeypatch):
    session = make_session("sid", uuid4(), "draft_post")
    monkeypatch.setattr(
        "agents.core.session.get_session", lambda _sid: session, raising=False
    )
    return session


def test_the_callers_gemini_key_reaches_the_image_tools(monkeypatch):
    session = _session_under(monkeypatch)
    _patch_resolution(monkeypatch, raises=True)

    content_routes._attach_image_run("sid", {Provider.GOOGLE_GENAI: "AIza-mine"})
    assert session.image_provider is Provider.GOOGLE_GENAI
    assert session.image_api_key == "AIza-mine"
    # The Gemini key doubles as the WebSearch key, as it always has.
    assert session.gemini_api_key == "AIza-mine"


def test_an_openai_key_alone_draws_on_openai(monkeypatch):
    """The whole point of the seam. Nothing about the run says Google."""
    session = _session_under(monkeypatch)
    _patch_resolution(monkeypatch, raises=True)

    content_routes._attach_image_run("sid", {Provider.OPENAI: "sk-mine"})
    assert session.image_provider is Provider.OPENAI
    assert session.image_api_key == "sk-mine"
    # And no Gemini-grounded search: there is no Gemini key to run it on.
    assert session.gemini_api_key == ""


def test_an_xai_key_alone_draws_on_xai(monkeypatch):
    session = _session_under(monkeypatch)
    _patch_resolution(monkeypatch, raises=True)

    content_routes._attach_image_run("sid", {Provider.XAI: "xai-mine"})
    assert session.image_provider is Provider.XAI
    assert session.image_api_key == "xai-mine"


def test_gemini_is_preferred_when_more_than_one_key_can_draw(monkeypatch):
    """A preference, not a capability ranking — see IMAGE_PROVIDER_ORDER."""
    session = _session_under(monkeypatch)
    _patch_resolution(monkeypatch, raises=True)

    content_routes._attach_image_run(
        "sid", {Provider.OPENAI: "sk-mine", Provider.GOOGLE_GENAI: "AIza-mine", Provider.XAI: "xai-mine"}
    )
    assert session.image_provider is Provider.GOOGLE_GENAI


def test_a_chat_only_key_does_not_draw(monkeypatch):
    """An Anthropic key drives the conversation and nothing else: Claude has
    no image model, so the run is left without one rather than handed a
    provider that will 404."""
    session = _session_under(monkeypatch)
    _patch_resolution(monkeypatch, raises=True)

    content_routes._attach_image_run("sid", {Provider.ANTHROPIC: "sk-ant-mine"})
    assert session.image_provider is None
    assert session.image_api_key == ""


def test_a_saved_key_serves_a_run_with_no_headers(monkeypatch):
    """A content session started from a resumed conversation carries no
    X-Provider header at all."""
    session = _session_under(monkeypatch)
    _patch_resolution(monkeypatch, stored={Provider.OPENAI: "sk-saved"}, raises=True)

    content_routes._attach_image_run("sid", {})
    assert session.image_provider is Provider.OPENAI
    assert session.image_api_key == "sk-saved"


def test_no_image_key_leaves_the_run_alive(monkeypatch):
    """Fail-soft, deliberately. A content session is worth having without
    images; it is not worth having on Duct's bill, and it is not worth killing
    over an image tool the user may never call."""
    session = _session_under(monkeypatch)
    _patch_resolution(monkeypatch, raises=True)

    content_routes._attach_image_run("sid", {})  # must not raise
    assert session.image_provider is None
    assert session.image_api_key == ""
    assert session.gemini_api_key == ""


# --- the model follows the provider ----------------------------------------


def test_the_tool_schema_default_is_corrected_to_the_runs_provider():
    """The agent's schema defaults to the Gemini model, so on any other
    backend the request arrives naming a model the key cannot reach. The run
    swaps it for the provider's own default rather than refusing — the agent
    asked for an image, not a Google image."""
    from agents.models import image_model_for

    assert image_model_for(Provider.OPENAI, ImageModel.GEMINI_3_1_FLASH_IMAGE) is ImageModel.GPT_IMAGE_2
    assert image_model_for(Provider.XAI, "gemini-3.1-flash-image") is ImageModel.GROK_IMAGINE_IMAGE_2
    # A model the provider does serve is kept as asked.
    assert image_model_for(Provider.GOOGLE_GENAI, ImageModel.GEMINI_3_PRO_IMAGE) is ImageModel.GEMINI_3_PRO_IMAGE
    assert image_model_for(Provider.OPENAI, None) is ImageModel.GPT_IMAGE_2
