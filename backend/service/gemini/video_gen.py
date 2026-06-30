"""Veo video generation — the backend counterpart to the Claude Code
``gemini-video-generation`` MCP server (~/.claude/mcp-servers), so the content
pipeline can generate clips IN-HOUSE via Veo instead of (or alongside)
Higgsfield. Mirrors service/gemini/video.py (understanding): a pure SDK client
that takes bytes in and returns bytes out — no DB / filesystem coupling.

Flow (per ai.google.dev/gemini-api/docs/video): generate_videos() returns a
long-running operation → poll operations.get() until done → download the mp4
bytes. Supports text-to-video, image-to-video (first frame), first+last-frame
interpolation (before→after), and up to 3 reference images for subject
consistency (Veo 3.1).
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from agents.models import DEFAULT_VIDEO_GEN_MODEL, VideoModel
from service.gemini.client import GeminiAPIError

logger = logging.getLogger(__name__)

# Model IDs are centralised as the VideoModel enum in agents/models.py (mirrors
# ImageModel). The client accepts the model id as a string; the agent tool input
# constrains it to the enum.
DEFAULT_VEO_MODEL = DEFAULT_VIDEO_GEN_MODEL.value

# Veo is a long-running op — minutes, not seconds.
_POLL_INTERVAL_SECS = 10.0
_MAX_WAIT_SECS = 10 * 60.0

# Video extension (ai.google.dev/gemini-api/docs/video#extending_veo_videos):
# continue a PRIOR generation by passing its Video as `video=`; the output is the
# FULL cumulative clip (no stitching). +7s each, ≤20 extensions (≤148s total),
# 720p during extension, Veo 3.1 / 3.1-Fast only (not Lite / 3.0).
_EXTENSION_MODELS = {VideoModel.VEO_3_1.value, VideoModel.VEO_3_1_FAST.value}
_MAX_EXTENSIONS = 20
_EXTENSION_SECS = 7

# Veo's weakest facial signal is the EYES — wandering / divergent pupils and a
# glassy stare are the clearest "AI video" tell. Veo honours a negative_prompt on
# the Gemini Developer API, so we ALWAYS steer it away from the eye + face-stability
# artifacts (merged with any caller-supplied negatives, on both the base and every
# extension). This pairs with the positive EYES & GAZE direction in the motion prompt.
_DEFAULT_NEGATIVE_PROMPT = (
    "wandering eyes, darting pupils, jittering or twitching eyes, cross-eyed, "
    "divergent or misaligned gaze, walleyed, rolling eyes, glassy lifeless eyes, "
    "distorted or asymmetric eyes, warped or morphing face, flickering facial features"
)


def _merge_negatives(caller: str | None) -> str:
    """Always include the eye/face-artifact negatives; append the caller's, if any."""
    caller = (caller or "").strip()
    return f"{_DEFAULT_NEGATIVE_PROMPT}, {caller}" if caller else _DEFAULT_NEGATIVE_PROMPT


class GeminiVeoClient:
    """Wraps google-genai Veo generation. One instance per request is fine
    (mirrors GeminiImageClient / GeminiVideoClient)."""

    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise ValueError("GeminiVeoClient: api_key is required")
        from google import genai  # late import — heavy module

        self._client = genai.Client(api_key=api_key)

    async def generate_video(
        self,
        *,
        prompt: str,
        first_frame: bytes | None = None,
        first_frame_mime: str = "image/png",
        last_frame: bytes | None = None,
        reference_images: list[bytes] | None = None,
        model: str = DEFAULT_VEO_MODEL,
        aspect_ratio: str = "9:16",
        resolution: str | None = None,
        duration_seconds: int | None = None,
        person_generation: str | None = None,
        negative_prompt: str | None = None,
        generate_audio: bool = True,
        extension_prompts: list[str] | None = None,
    ) -> tuple[bytes, int]:
        """Generate a clip and return ``(mp4 bytes, extension segments actually
        applied)``. Raises GeminiAPIError when the BASE generation fails (SDK error,
        timeout, empty result); a failed EXTENSION never raises — it degrades to the
        clip generated so far (see _run_generate), so the count tells the caller the
        real duration.

          - first_frame        — image-to-video opening frame (omit for text-to-video)
          - last_frame         — first+last interpolation (before→after); needs first_frame
          - reference_images   — up to 3 stills of one person/product (Veo 3.1)
          - generate_audio     — Veo generates synced audio by default; set False for a
            SILENT clip (e.g. a pure-vibe montage where the user adds their own sound)
          - extension_prompts  — CONTINUE the clip with N continuation segments (+7s each,
            ≤20), each directed by its prompt; the output is the FULL cumulative clip.
            For LONGER continuous shots, not hard cuts. Veo 3.1 / 3.1-Fast only, 720p.
          - aspect_ratio/resolution/duration_seconds/person_generation/negative_prompt
            map 1:1 to GenerateVideosConfig; only set knobs are passed.
        """
        exts = [p for p in (extension_prompts or []) if isinstance(p, str)]
        if exts and model not in _EXTENSION_MODELS:
            raise GeminiAPIError(
                f"model {model} doesn't support extension — use "
                f"{VideoModel.VEO_3_1.value} or {VideoModel.VEO_3_1_FAST.value}.",
                model=model,
            )
        # Veo can't EXTEND a first+last interpolation clip — the base has a fixed end
        # frame, so the API rejects it as input with "Input video must be a video that
        # was generated by VEO that has been processed". A transformation (last_frame)
        # and a continuation (extension) are different intents; the transformation is
        # the creative ask, so it wins — drop the extensions rather than 400 the whole
        # clip. (For a longer transformation, animate the beats as separate clips.)
        if last_frame is not None and exts:
            logger.info(
                "veo: last_frame (first→last interpolation) can't be extended — dropping "
                "%d extension prompt(s); returning the transformation clip.", len(exts),
            )
            exts = []
        # Veo can't COMBINE a literal first frame (image-to-video) with
        # reference_images (subject-reference mode) — sending both is a 400
        # "Unsupported video generation request". The approved keyframe IS the
        # first frame and already carries the character, so it wins; drop the
        # references. (Reference images still work on their own — text+refs → video.)
        if first_frame is not None and reference_images:
            logger.info(
                "veo: first frame present — dropping %d reference image(s) (Veo can't "
                "combine image-to-video with reference images)", len(reference_images),
            )
            reference_images = None
        return await asyncio.to_thread(
            self._run_generate,
            prompt, first_frame, first_frame_mime, last_frame,
            reference_images, model, aspect_ratio, resolution,
            duration_seconds, person_generation, negative_prompt, generate_audio,
            exts[:_MAX_EXTENSIONS],
        )

    # ------------------------------------------------------------------

    def _run_generate(
        self,
        prompt: str,
        first_frame: bytes | None,
        first_frame_mime: str,
        last_frame: bytes | None,
        reference_images: list[bytes] | None,
        model: str,
        aspect_ratio: str,
        resolution: str | None,
        duration_seconds: int | None,
        person_generation: str | None,
        negative_prompt: str | None,
        generate_audio: bool,
        extension_prompts: list[str],
    ) -> tuple[bytes, int]:
        from google.genai import types

        # Extension only accepts a 720p Veo base as input (the input video must be
        # 720p). If the base is generated at a higher/unset resolution, the first
        # extension 400s "Input video must be a video that was generated by VEO that
        # has been processed". So when we're going to extend, pin the BASE to 720p.
        if extension_prompts and not resolution:
            resolution = "720p"

        # `generate_audio` is ONLY accepted in Vertex / Enterprise mode — on the
        # Gemini Developer API it raises "generate_audio parameter is only supported
        # in Gemini Enterprise Agent Platform mode" and fails EVERY Veo call (any
        # value). Only pass it where supported; on the Developer API omit it so the
        # clip generates with Veo's default instead of crashing.
        audio_supported = bool(getattr(self._client, "vertexai", False))
        if generate_audio and not audio_supported:
            logger.info(
                "veo: generate_audio is unsupported on the Gemini Developer API — "
                "generating without the audio toggle (model %s)", model,
            )

        cfg: dict[str, Any] = {}
        if audio_supported:
            cfg["generate_audio"] = generate_audio
        if aspect_ratio:
            cfg["aspect_ratio"] = aspect_ratio
        if resolution:
            cfg["resolution"] = resolution
        if duration_seconds is not None:
            cfg["duration_seconds"] = int(duration_seconds)
        if person_generation:
            cfg["person_generation"] = person_generation
        # Always steer Veo off the eye/face artifacts (the #1 AI-video tell), merged
        # with any caller negatives. Reused on every extension segment below.
        merged_negative = _merge_negatives(negative_prompt)
        cfg["negative_prompt"] = merged_negative
        if last_frame is not None:
            cfg["last_frame"] = types.Image(image_bytes=last_frame, mime_type="image/png")
        if reference_images:
            cfg["reference_images"] = [
                types.VideoGenerationReferenceImage(
                    image=types.Image(image_bytes=b, mime_type="image/png"),
                    reference_type="asset",
                )
                for b in reference_images[:3]
            ]

        kwargs: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "config": types.GenerateVideosConfig(**cfg),
        }
        if first_frame is not None:
            kwargs["image"] = types.Image(image_bytes=first_frame, mime_type=first_frame_mime)

        # BASE generation — a failure here is fatal (the clip never existed).
        try:
            op = self._client.models.generate_videos(**kwargs)
            op = self._poll(op)
        except GeminiAPIError:
            raise
        except Exception as exc:
            raise GeminiAPIError(str(exc), model=model) from exc

        # Extend: each pass continues the PRIOR generation (video=) and returns the
        # FULL cumulative clip — so we just chain, then download the final. Extension
        # is fixed to 720p / duration 8 per the docs. It's FINICKY (Veo only extends a
        # 720p Veo-generated base), so a failed segment must NOT throw away the good
        # base clip we already have — degrade to the furthest segment that succeeded
        # and report how many applied so the caller can set the real duration.
        applied = 0
        last_good_op = op
        for ext_prompt in extension_prompts:
            try:
                prev_video = self._video_from_op(op, model)
                ext_kwargs: dict[str, Any] = dict(
                    number_of_videos=1,
                    resolution="720p",
                    duration_seconds=8,
                    aspect_ratio=aspect_ratio,
                    negative_prompt=merged_negative,  # keep eyes steady across segments too
                )
                if audio_supported:
                    ext_kwargs["generate_audio"] = generate_audio
                ext_cfg = types.GenerateVideosConfig(**ext_kwargs)
                op = self._client.models.generate_videos(
                    model=model, video=prev_video,
                    prompt=(ext_prompt.strip() or prompt), config=ext_cfg,
                )
                op = self._poll(op)
                last_good_op, applied = op, applied + 1
            except Exception as exc:
                logger.warning(
                    "veo: extension %d/%d failed (%s) — returning the clip generated so "
                    "far (%d extension(s) applied). Veo only extends a 720p Veo-generated "
                    "base and rejects interpolation/image-to-video bases.",
                    applied + 1, len(extension_prompts), exc, applied,
                )
                op = last_good_op
                break

        video = self._video_from_op(op, model)
        try:
            downloaded = self._client.files.download(file=video)
        except Exception as exc:
            raise GeminiAPIError(f"clip download failed: {exc}", model=model) from exc
        data = downloaded if isinstance(downloaded, (bytes, bytearray)) else getattr(video, "video_bytes", None)
        if not data:
            raise GeminiAPIError("clip downloaded empty.", model=model)
        return bytes(data), applied

    def _video_from_op(self, op: Any, model: str) -> Any:
        """Extract the generated Video from a completed operation, or raise."""
        vids = getattr(getattr(op, "response", None), "generated_videos", None) or []
        if not vids:
            err = getattr(op, "error", None)
            raise GeminiAPIError(
                f"No video returned ({err or 'safety filter / unsupported input'}).", model=model
            )
        return vids[0].video

    def _poll(self, op: Any) -> Any:
        """Poll the long-running operation until done (or timeout)."""
        deadline = time.monotonic() + _MAX_WAIT_SECS
        while not getattr(op, "done", False):
            if time.monotonic() > deadline:
                raise GeminiAPIError("Veo generation timed out after 10 minutes.", model="veo")
            time.sleep(_POLL_INTERVAL_SECS)
            op = self._client.operations.get(op)
        return op
