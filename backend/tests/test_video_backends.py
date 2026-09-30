"""The video seam: the model table, the fit to each model, and both backends.

Offline throughout except the two ``live`` tests at the end. The Veo client is
driven through a fake of the google-genai async surface it calls (models,
operations, files); the OpenRouter client through ``httpx.MockTransport``, so
each test asserts on the request that would have gone over the wire.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
from types import SimpleNamespace

import httpx
import pytest

from agents.models import (
    DEFAULT_VIDEO_MODELS,
    MODEL_LABELS,
    VIDEO_PRICE_PER_SECOND,
    VIDEO_PROVIDER_ORDER,
    Modality,
    Provider,
    VideoModel,
    model_emits,
    provider_of,
    video_cost_usd,
    video_model_for,
)
from service.videos import (
    VIDEO_CAPS,
    GenerateVideoRequest,
    VideoAPIError,
    VideoAspectRatio,
    VideoErrorCode,
    VideoFrame,
    VideoResolution,
    fit_request,
    video_client_for,
)

CLIP = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def _request(model=VideoModel.VEO_3_1_LITE, **kw) -> GenerateVideoRequest:
    return GenerateVideoRequest(prompt="a kettle boils, slow push-in", model=model, **kw)


async def _no_sleep(_seconds: float) -> None:
    return None


# --- the table ---------------------------------------------------------------


def test_every_video_model_has_a_provider_a_caps_row_and_a_name():
    for model in VideoModel:
        assert provider_of(model) in VIDEO_PROVIDER_ORDER, model
        assert model in VIDEO_CAPS, model
        assert MODEL_LABELS.get(model.value), model
        assert model_emits(model, Modality.VIDEO), model
    assert set(DEFAULT_VIDEO_MODELS) == set(VIDEO_PROVIDER_ORDER)


def test_a_veo_clip_is_priced_at_every_resolution_it_serves_and_seedance_is_not_guessed():
    """Seedance's price is the one OpenRouter reports for each job; a table row
    would be an estimate standing in for an exact figure."""
    for model in (VideoModel.VEO_3_1, VideoModel.VEO_3_1_FAST, VideoModel.VEO_3_1_LITE):
        for resolution in VIDEO_CAPS[model].resolutions:
            assert video_cost_usd(model, resolution.value, 8) is not None, (model, resolution)
    assert video_cost_usd(VideoModel.VEO_3_1_LITE, "720p", 8) == 0.40
    assert VideoModel.OR_SEEDANCE_2_0_MINI not in VIDEO_PRICE_PER_SECOND
    assert video_cost_usd(VideoModel.OR_SEEDANCE_2_0_MINI, "720p", 8) is None


def test_a_model_the_key_cannot_reach_becomes_that_keys_default():
    assert video_model_for(Provider.GOOGLE_GENAI, VideoModel.OR_SEEDANCE_2_5) is VideoModel.VEO_3_1_LITE
    assert video_model_for(Provider.OPENROUTER, VideoModel.OR_SEEDANCE_2_5) is VideoModel.OR_SEEDANCE_2_5
    assert video_model_for(Provider.OPENROUTER) is VideoModel.OR_SEEDANCE_2_0_MINI


def test_only_the_two_video_providers_have_a_backend():
    with pytest.raises(ValueError):
        video_client_for(Provider.ANTHROPIC, "sk-ant")


# --- fitting a request to a model ----------------------------------------------


def test_a_request_the_model_serves_is_sent_as_it_is():
    request = _request(duration_seconds=6)
    assert fit_request(request) == (request, [])


@pytest.mark.parametrize(
    ("asked", "model", "made"),
    [(10, VideoModel.VEO_3_1_LITE, 8), (5, VideoModel.VEO_3_1, 6), (3, VideoModel.VEO_3_1_FAST, 4),
     (20, VideoModel.OR_SEEDANCE_2_0_MINI, 15), (30, VideoModel.OR_SEEDANCE_2_5, 30)],
)
def test_a_length_is_fitted_to_the_nearest_the_model_makes(asked, model, made):
    fitted, notes = fit_request(_request(model, duration_seconds=asked))
    assert fitted.duration_seconds == made
    assert (notes == []) == (asked == made)


def test_veo_keeps_the_orientation_it_was_asked_for():
    portrait, _ = fit_request(_request(aspect_ratio=VideoAspectRatio.SQUARE_1_1))
    landscape, _ = fit_request(_request(aspect_ratio=VideoAspectRatio.LANDSCAPE_4_3))
    assert portrait.aspect_ratio is VideoAspectRatio.PORTRAIT_9_16
    assert landscape.aspect_ratio is VideoAspectRatio.LANDSCAPE_16_9


def test_veo_makes_1080p_only_at_eight_seconds_and_says_so():
    fitted, notes = fit_request(_request(duration_seconds=6, resolution=VideoResolution.P1080))
    assert fitted.resolution is VideoResolution.P720 and fitted.duration_seconds == 6
    assert any("1080p" in note for note in notes)
    kept, _ = fit_request(_request(duration_seconds=8, resolution=VideoResolution.P1080))
    assert kept.resolution is VideoResolution.P1080


def test_a_first_to_last_frame_veo_clip_is_eight_seconds():
    fitted, notes = fit_request(_request(duration_seconds=4), has_last_frame=True)
    assert fitted.duration_seconds == 8 and notes


def test_seedance_stops_at_720p_and_takes_no_negative_prompt():
    fitted, notes = fit_request(_request(
        VideoModel.OR_SEEDANCE_2_0_MINI, resolution=VideoResolution.P1080, negative_prompt="text",
    ))
    assert fitted.resolution is VideoResolution.P720
    assert fitted.negative_prompt is None
    assert len(notes) == 2


# --- the Veo client -----------------------------------------------------------


class _FakeGenai:
    """The google-genai async surface GeminiVeoClient calls, recording each call."""

    def __init__(self, *, polls_until_done=1, response=None, submit_error=None):
        self.calls: list[tuple[str, dict]] = []
        self._polls_left = polls_until_done
        self._response = response if response is not None else SimpleNamespace(
            generated_videos=[SimpleNamespace(video=SimpleNamespace(mime_type="video/mp4", video_bytes=None))],
            rai_media_filtered_reasons=None,
            rai_media_filtered_count=0,
        )
        self._submit_error = submit_error
        fake = self

        class _Models:
            async def generate_videos(self, **kw):
                fake.calls.append(("generate_videos", kw))
                if fake._submit_error is not None:
                    raise fake._submit_error
                return fake._operation(done=fake._polls_left <= 0)

        class _Operations:
            async def get(self, operation):
                fake.calls.append(("operations.get", {}))
                fake._polls_left -= 1
                return fake._operation(done=fake._polls_left <= 0)

        class _Files:
            async def download(self, *, file):
                fake.calls.append(("files.download", {"file": file}))
                return CLIP

        self.aio = SimpleNamespace(models=_Models(), operations=_Operations(), files=_Files())

    def _operation(self, *, done):
        return SimpleNamespace(done=done, error=None, response=self._response if done else None, result=None)


def _veo(fake, **kw):
    from service.google.gemini.veo import GeminiVeoClient

    return GeminiVeoClient("", client=fake, sleep=_no_sleep, **kw)


def test_veo_submits_polls_and_downloads_the_clip():
    fake = _FakeGenai(polls_until_done=2)
    clip = asyncio.run(_veo(fake).generate_video(
        _request(duration_seconds=6), first_frame=VideoFrame(PNG, "image/png"),
    ))

    assert clip.data == CLIP and clip.mime_type == "video/mp4" and clip.cost_usd is None
    assert [name for name, _ in fake.calls] == [
        "generate_videos", "operations.get", "operations.get", "files.download",
    ]
    submit = fake.calls[0][1]
    assert submit["model"] == "veo-3.1-lite-generate-preview"
    assert submit["image"].image_bytes == PNG
    config = submit["config"]
    assert (config.aspect_ratio, config.duration_seconds, config.resolution) == ("9:16", 6, "720p")
    # The flag every Gemini API call refuses: Veo 3.x always has sound there.
    assert config.generate_audio is None


def test_a_filtered_veo_clip_is_a_safety_error_with_the_reasons():
    filtered = SimpleNamespace(
        generated_videos=[], rai_media_filtered_reasons=["The prompt may violate policy."],
        rai_media_filtered_count=1,
    )
    with pytest.raises(VideoAPIError) as excinfo:
        asyncio.run(_veo(_FakeGenai(response=filtered)).generate_video(_request()))
    assert excinfo.value.code is VideoErrorCode.SAFETY
    assert "violate policy" in excinfo.value.detail


def test_a_veo_clip_that_never_finishes_times_out():
    fake = _FakeGenai(polls_until_done=1_000)
    with pytest.raises(VideoAPIError) as excinfo:
        asyncio.run(_veo(fake, poll_seconds=10, deadline_seconds=30).generate_video(_request()))
    assert excinfo.value.code is VideoErrorCode.TIMEOUT
    assert sum(1 for name, _ in fake.calls if name == "operations.get") == 3


def test_a_veo_request_it_rejects_is_an_invalid_request():
    from google.genai import errors

    rejected = errors.ClientError(400, {"error": {"code": 400, "message": "bad duration"}})
    with pytest.raises(VideoAPIError) as excinfo:
        asyncio.run(_veo(_FakeGenai(submit_error=rejected)).generate_video(_request()))
    assert excinfo.value.code is VideoErrorCode.INVALID and excinfo.value.http_status == 400


# --- the OpenRouter client ----------------------------------------------------


class _OpenRouter:
    """A fake of POST /videos → GET /videos/{id} → GET /videos/{id}/content."""

    def __init__(self, statuses=("in_progress", "completed"), *, submit_status=200,
                 submit_body=None, final=None, failure=""):
        self.requests: list[httpx.Request] = []
        self._failure = failure
        self._statuses = list(statuses)
        self._submit_status = submit_status
        self._submit_body = submit_body
        self._final = final or {"usage": {"cost": 0.3024, "is_byok": False}}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if request.method == "POST":
            return httpx.Response(
                self._submit_status,
                json=self._submit_body or {"id": "job-1", "polling_url": "x", "status": "pending"},
            )
        if path.endswith("/content"):
            return httpx.Response(200, content=CLIP, headers={"content-type": "video/mp4"})
        status = self._statuses.pop(0) if self._statuses else "completed"
        body = {"id": "job-1", "status": status}
        if status == "completed":
            body.update(self._final)
        elif status == "failed":
            body["error"] = self._failure
        return httpx.Response(200, json=body)

    @property
    def submitted(self) -> dict:
        return json.loads(self.requests[0].content)


def _openrouter(fake):
    from service.openrouter.videos import OpenRouterVideoClient

    return OpenRouterVideoClient("or-test", transport=httpx.MockTransport(fake), sleep=_no_sleep)


def test_openrouter_submits_polls_downloads_and_reports_the_billed_cost():
    fake = _OpenRouter()
    clip = asyncio.run(_openrouter(fake).generate_video(
        _request(VideoModel.OR_SEEDANCE_2_0_MINI, duration_seconds=10),
        first_frame=VideoFrame(PNG, "image/png"),
    ))

    assert clip.data == CLIP and clip.cost_usd == 0.3024
    assert [(r.method, r.url.path) for r in fake.requests] == [
        ("POST", "/api/v1/videos"),
        ("GET", "/api/v1/videos/job-1"),
        ("GET", "/api/v1/videos/job-1"),
        ("GET", "/api/v1/videos/job-1/content"),
    ]
    assert fake.requests[0].headers["authorization"] == "Bearer or-test"
    body = fake.submitted
    assert {k: body[k] for k in ("model", "duration", "resolution", "aspect_ratio", "generate_audio")} == {
        "model": "bytedance/seedance-2.0-mini", "duration": 10, "resolution": "720p",
        "aspect_ratio": "9:16", "generate_audio": True,
    }
    (frame,) = body["frame_images"]
    assert frame["frame_type"] == "first_frame"
    assert frame["image_url"]["url"] == "data:image/png;base64," + base64.b64encode(PNG).decode()


def test_a_frame_with_a_public_address_is_sent_as_its_address():
    from service.openrouter.videos import OpenRouterVideoClient

    body = OpenRouterVideoClient.body(
        _request(VideoModel.OR_SEEDANCE_2_5),
        first_frame=VideoFrame(PNG, "image/png", url="https://cdn.example/a.png"),
        last_frame=VideoFrame(PNG, "image/png"),
    )
    assert [f["frame_type"] for f in body["frame_images"]] == ["first_frame", "last_frame"]
    assert body["frame_images"][0]["image_url"]["url"] == "https://cdn.example/a.png"


def test_seedance_refusing_a_realistic_face_has_its_own_code():
    """Not "try again": the agent has to change the frame, so the code says so."""
    fake = _OpenRouter(statuses=("failed",), failure="The input image may contain real person.")
    with pytest.raises(VideoAPIError) as excinfo:
        asyncio.run(_openrouter(fake).generate_video(_request(VideoModel.OR_SEEDANCE_2_0_MINI)))
    assert excinfo.value.code is VideoErrorCode.PERSON


@pytest.mark.parametrize(
    ("status", "code"),
    [(402, VideoErrorCode.BILLING), (401, VideoErrorCode.AUTH), (400, VideoErrorCode.INVALID),
     (503, VideoErrorCode.PROVIDER)],
)
def test_an_openrouter_submit_failure_is_classified(status, code):
    fake = _OpenRouter(submit_status=status, submit_body={"error": {"message": "nope"}})
    with pytest.raises(VideoAPIError) as excinfo:
        asyncio.run(_openrouter(fake).generate_video(_request(VideoModel.OR_SEEDANCE_2_5)))
    assert excinfo.value.code is code and excinfo.value.http_status == status
    assert len(fake.requests) == 1


def test_an_openrouter_job_that_never_finishes_times_out():
    from service.openrouter.videos import OpenRouterVideoClient

    fake = _OpenRouter(statuses=["in_progress"] * 100)
    client = OpenRouterVideoClient(
        "or-test", transport=httpx.MockTransport(fake), sleep=_no_sleep,
        poll_seconds=10, deadline_seconds=20,
    )
    with pytest.raises(VideoAPIError) as excinfo:
        asyncio.run(client.generate_video(_request(VideoModel.OR_SEEDANCE_2_0_MINI)))
    assert excinfo.value.code is VideoErrorCode.TIMEOUT


# --- live: one real clip per provider, a few cents each --------------------------


@pytest.mark.live
def test_live_veo_lite_makes_a_four_second_clip():
    """Veo 3.1 Lite, 4 s at 720p: $0.20. Catches an id, parameter or SDK drift."""
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        pytest.skip("GEMINI_API_KEY not set")
    clip = asyncio.run(video_client_for(Provider.GOOGLE_GENAI, key).generate_video(
        _request(duration_seconds=4)
    ))
    assert clip.mime_type.startswith("video/") and len(clip.data) > 10_000


@pytest.mark.live
def test_live_seedance_mini_makes_a_four_second_clip_from_a_data_uri_frame():
    """Seedance 2.0 Mini, 4 s at 480p (~$0.04), opened on a data-URI frame: the
    one path OpenRouter's docs do not show, which a laptop run depends on."""
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        pytest.skip("OPENROUTER_API_KEY not set")
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (720, 1280), (240, 200, 160)).save(buffer, format="PNG")
    clip = asyncio.run(video_client_for(Provider.OPENROUTER, key).generate_video(
        _request(VideoModel.OR_SEEDANCE_2_0_MINI, duration_seconds=4, resolution=VideoResolution.P480),
        first_frame=VideoFrame(buffer.getvalue(), "image/png"),
    ))
    assert clip.mime_type.startswith("video/") and len(clip.data) > 10_000
    assert clip.cost_usd is not None
