"""The image backends behind ``service/images``: what each one puts on the wire.

The Gemini client's own logic is covered in test_gemini_service.py. These
pin the two newer backends and the pieces they share — the size translation
(pure functions), the factory, the resolver's preference order, and the
shape of the requests each client sends. No network: OpenAI's SDK is faked
at the ``images`` resource and xAI's HTTP goes through an httpx mock
transport, so the assertions are on exactly the bytes a provider would see.
"""

from __future__ import annotations

import asyncio
import base64
import json
from types import SimpleNamespace

import httpx
import pytest

from agents.models import DEFAULT_IMAGE_MODELS, IMAGE_PROVIDER_ORDER, AspectRatio, ImageModel, Provider, provider_of
from service.images import GenerateImageRequest, EditImageRequest, ImageAPIError, ImageSize, image_client_for
from service.images.sizing import openai_size, xai_aspect_ratio, xai_resolution

PNG = b"\x89PNG-not-really"
B64 = base64.b64encode(b"generated").decode()


# --- the registry -----------------------------------------------------------


def test_every_image_model_has_a_provider_and_every_image_provider_a_default():
    for model in ImageModel:
        assert provider_of(model) is not None, model
    assert set(DEFAULT_IMAGE_MODELS) == set(IMAGE_PROVIDER_ORDER)
    for provider, model in DEFAULT_IMAGE_MODELS.items():
        assert provider_of(model) is provider


def test_xai_chat_models_resolve_to_xai():
    """Had returned None, so the catalogue silently listed no xAI models."""
    from agents.models import ModelName

    assert provider_of(ModelName.GROK_4_6) is Provider.XAI


def test_the_factory_refuses_a_provider_with_no_image_model():
    with pytest.raises(ValueError):
        image_client_for(Provider.ANTHROPIC, "sk-ant-x")


# --- sizing: OpenAI ---------------------------------------------------------


@pytest.mark.parametrize("aspect_ratio", list(AspectRatio))
@pytest.mark.parametrize("image_size", list(ImageSize))
def test_openai_sizes_obey_the_image_api_rules(aspect_ratio, image_size):
    """Both edges multiples of 16, none over 3840, pixels within the
    documented band, and the ratio at most 3:1 — for every combination the
    tools can ask for, not just the ones on the docs' popular list."""
    width, height = (int(v) for v in openai_size(aspect_ratio, image_size).split("x"))
    assert width % 16 == 0 and height % 16 == 0
    assert max(width, height) <= 3840
    assert 655_360 <= width * height <= 8_294_400
    assert max(width, height) / min(width, height) <= 3


def test_openai_size_keeps_orientation_and_the_canonical_square():
    assert openai_size(AspectRatio.SQUARE_1_1, ImageSize.K1) == "1024x1024"
    w, h = (int(v) for v in openai_size(AspectRatio.PORTRAIT_9_16, ImageSize.K2).split("x"))
    assert h == 2048 and w < h
    w, h = (int(v) for v in openai_size(AspectRatio.LANDSCAPE_16_9, ImageSize.K4).split("x"))
    assert w == 3840 and h == 2160


# --- sizing: xAI ------------------------------------------------------------


@pytest.mark.parametrize("aspect_ratio", list(AspectRatio))
def test_every_duct_ratio_maps_onto_one_xai_accepts(aspect_ratio):
    from service.images.sizing import _XAI_ASPECT_RATIOS

    assert xai_aspect_ratio(aspect_ratio) in _XAI_ASPECT_RATIOS


def test_xai_ratio_is_exact_when_shared_and_nearest_otherwise():
    assert xai_aspect_ratio(AspectRatio.PORTRAIT_9_16) == "9:16"
    assert xai_aspect_ratio(AspectRatio.PORTRAIT_4_5) == "3:4"
    assert xai_aspect_ratio(AspectRatio.LANDSCAPE_5_4) == "4:3"
    assert xai_resolution(ImageSize.K1) == "1k"
    assert xai_resolution(ImageSize.K4) == "2k"


# --- the OpenAI client ------------------------------------------------------


class _FakeImages:
    """The ``images`` resource of the OpenAI SDK, recording what it was sent."""

    def __init__(self, *, fail: Exception | None = None):
        self.calls: list[tuple[str, dict]] = []
        self._fail = fail

    async def generate(self, **kwargs):
        self.calls.append(("generate", kwargs))
        if self._fail:
            raise self._fail
        return SimpleNamespace(data=[SimpleNamespace(b64_json=B64)])

    async def edit(self, **kwargs):
        self.calls.append(("edit", kwargs))
        if self._fail:
            raise self._fail
        return SimpleNamespace(data=[SimpleNamespace(b64_json=B64)])


def _openai_client(**kw):
    from service.openai.images import OpenAIImageClient

    client = OpenAIImageClient("sk-test")
    fake = _FakeImages(**kw)
    client._client = SimpleNamespace(images=fake)
    return client, fake


def test_openai_generate_sends_a_pixel_size_and_asks_for_png():
    client, fake = _openai_client()
    request = GenerateImageRequest(prompt="a duct", model=ImageModel.GPT_IMAGE_2)

    images = asyncio.run(client.generate_image(request))

    (verb, sent), = fake.calls
    assert verb == "generate"
    assert sent["model"] == "gpt-image-2"
    assert sent["size"] == openai_size(AspectRatio.PORTRAIT_9_16, ImageSize.K2)
    assert sent["output_format"] == "png"
    assert "input_fidelity" not in sent and "aspect_ratio" not in sent
    assert images[0].data == b"generated" and images[0].mime_type == "image/png"


def test_openai_generate_with_references_is_an_edit():
    """OpenAI has no generate-with-references call; an edit with several
    inputs is that call, and the references keep their role order."""
    client, fake = _openai_client()
    request = GenerateImageRequest(prompt="same face", model=ImageModel.GPT_IMAGE_2)

    asyncio.run(client.generate_image(request, input_bytes_list=[b"face", b"camera"]))

    (verb, sent), = fake.calls
    assert verb == "edit"
    assert [name for name, _, _ in sent["image"]] == ["ref-0.png", "ref-1.png"]
    assert [data for _, data, _ in sent["image"]] == [b"face", b"camera"]


def test_openai_edit_leads_with_the_base_and_keeps_its_dimensions():
    from uuid import uuid4

    client, fake = _openai_client()
    request = EditImageRequest(prompt="brighter", input_asset_id=uuid4(), model=ImageModel.GPT_IMAGE_2)

    asyncio.run(client.edit_image(request, base_bytes=b"base", mask_bytes=b"mask", style_bytes=b"style"))

    (verb, sent), = fake.calls
    assert verb == "edit"
    assert [data for _, data, _ in sent["image"]] == [b"base", b"style"]
    assert sent["mask"][1] == b"mask"
    assert sent["size"] == "auto"


def test_openai_failures_surface_as_the_shared_error_with_the_status():
    client, _ = _openai_client(fail=type("APIStatusError", (Exception,), {"status_code": 403})("verify your org"))
    request = GenerateImageRequest(prompt="x", model=ImageModel.GPT_IMAGE_2)

    with pytest.raises(ImageAPIError) as excinfo:
        asyncio.run(client.generate_image(request))
    assert excinfo.value.http_status == 403
    assert "OpenAI (gpt-image-2)" in str(excinfo.value)


# --- the xAI client ---------------------------------------------------------


def _xai_client(handler):
    from service.xai.images import XAIImageClient

    return XAIImageClient("xai-test", transport=httpx.MockTransport(handler))


def _ok(payload: dict) -> httpx.Response:
    return httpx.Response(200, json=payload)


def test_xai_generate_speaks_aspect_ratio_and_resolution_not_size():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return _ok({"data": [{"b64_json": B64}]})

    client = _xai_client(handler)
    request = GenerateImageRequest(
        prompt="a duct", model=ImageModel.GROK_IMAGINE_IMAGE_2,
        aspect_ratio=AspectRatio.PORTRAIT_4_5, image_size=ImageSize.K1, number_of_images=2,
    )
    images = asyncio.run(client.generate_image(request))

    assert seen["path"].endswith("/images/generations")
    assert seen["auth"] == "Bearer xai-test"
    body = seen["body"]
    assert body["model"] == "grok-imagine-image-2.0"
    assert body["n"] == 2
    assert body["aspect_ratio"] == "3:4" and body["resolution"] == "1k"
    assert "size" not in body
    assert images[0].data == b"generated"


def test_xai_references_go_to_the_edits_endpoint_as_a_data_url():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return _ok({"data": [{"b64_json": B64}]})

    client = _xai_client(handler)
    request = GenerateImageRequest(prompt="same face", model=ImageModel.GROK_IMAGINE_IMAGE_2)
    asyncio.run(client.generate_image(request, input_bytes_list=[PNG, b"camera"]))

    assert seen["path"].endswith("/images/edits")
    image = seen["body"]["image"]
    assert image["type"] == "image_url"
    assert image["url"] == "data:image/png;base64," + base64.b64encode(PNG).decode()


def test_xai_honours_a_url_answer_by_fetching_it_without_the_key():
    """The edits endpoint is documented against ``url``; asking for base64
    is a preference, not something to fail on. But the download must not
    carry the bearer token: it is for api.x.ai, and the URL came from a
    response body."""
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/images/generations"):
            return _ok({"data": [{"url": "https://imgen.x.ai/out.png"}]})
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, content=b"fetched", headers={"content-type": "image/jpeg"})

    client = _xai_client(handler)
    images = asyncio.run(client.generate_image(
        GenerateImageRequest(prompt="x", model=ImageModel.GROK_IMAGINE_IMAGE_2)
    ))
    assert images[0].data == b"fetched" and images[0].mime_type == "image/jpeg"
    assert seen["auth"] is None


@pytest.mark.parametrize("url", [
    "https://evil.example/out.png",        # another host
    "https://x.ai.evil.example/out.png",   # a lookalike
    "http://imgen.x.ai/out.png",           # xAI, but off TLS
    "https://127.0.0.1/out.png",           # loopback
])
def test_xai_refuses_a_result_url_off_its_domain(url):
    fetched: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/images/generations"):
            return _ok({"data": [{"url": url}]})
        fetched.append(str(request.url))
        return httpx.Response(200, content=b"should not be reached")

    client = _xai_client(handler)
    with pytest.raises(ImageAPIError):
        asyncio.run(client.generate_image(
            GenerateImageRequest(prompt="x", model=ImageModel.GROK_IMAGINE_IMAGE_2)
        ))
    assert fetched == []


def test_xai_failures_surface_as_the_shared_error_with_the_status():
    client = _xai_client(lambda _r: httpx.Response(429, text="slow down"))

    with pytest.raises(ImageAPIError) as excinfo:
        asyncio.run(client.generate_image(
            GenerateImageRequest(prompt="x", model=ImageModel.GROK_IMAGINE_IMAGE_2)
        ))
    assert excinfo.value.http_status == 429
    assert "xAI (grok-imagine-image-2.0)" in str(excinfo.value)


# --- what the settings page is told ----------------------------------------


def test_provider_status_names_the_same_pick_the_run_would_make(monkeypatch):
    """Header keys only — a Gemini key in the developer's own env would
    otherwise win, which is the preference order working, not the test."""
    from routes import providers as providers_route

    monkeypatch.setattr(providers_route, "allow_server_provider_keys", lambda: False)
    out = providers_route.providers_status(
        user_keys={Provider.OPENAI: "sk-test", Provider.XAI: "xai-test"}, user=None, db=None
    )
    assert out["images"] == {"provider": "openai", "model": "gpt-image-2", "source": "user"}


def test_provider_status_says_none_when_only_a_chat_provider_is_reachable(monkeypatch):
    from routes import providers as providers_route

    monkeypatch.setattr(providers_route, "allow_server_provider_keys", lambda: False)
    out = providers_route.providers_status(
        user_keys={Provider.ANTHROPIC: "sk-ant-test"}, user=None, db=None
    )
    assert out["images"] == {"provider": None, "model": None, "source": "none"}


def test_the_catalogue_lists_an_image_model_per_drawing_provider():
    from routes import providers as providers_route

    out = providers_route.models_catalogue()
    by_provider = {row["provider"] for row in out["image_models"]}
    assert by_provider == {"google_genai", "openai", "xai"}
    defaults = {row["provider"]: row["id"] for row in out["image_models"] if row["default"]}
    assert defaults == {p.value: m.value for p, m in DEFAULT_IMAGE_MODELS.items()}
    assert out["image_provider_order"] == ["google_genai", "openai", "xai"]
