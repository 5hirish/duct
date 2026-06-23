"""Gemini video understanding — ported from the Claude Code
``gemini-video-understanding`` MCP server (~/.claude/mcp-servers) so the content
backend can deconstruct a reference clip itself instead of relying on
Higgsfield's Video Analyzer (which missed the before→after transformation and
the on-screen text — the two things that drive a clone).

Same contract as the Node server: a local-or-fetched video is sent INLINE when
it's under ~20MB, else uploaded via the Files API and polled until ACTIVE, then
``generate_content([video_part, prompt])`` is called. We hand in the bytes (the
discovery layer fetches them from the Apify CDN) so this stays pure — no DB,
filesystem, or network coupling beyond the Gemini SDK + Files API.
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
from typing import Any

from agents.models import DEFAULT_VIDEO_UNDERSTANDING_MODEL
from service.gemini.client import GeminiAPIError

logger = logging.getLogger(__name__)

# Inline requests must keep the whole payload under ~20MB (Gemini limit). Above
# that we upload via the Files API. Mirrors the MCP server's INLINE_MAX_BYTES.
INLINE_MAX_BYTES = 20 * 1024 * 1024

# Model IDs are centralised as the VideoUnderstandingModel enum in agents/models.py.
# pro is the default — cached per clone (paid once), so quality (catching the
# transformation + on-screen text that flash-tier analysers miss) wins.
DEFAULT_VIDEO_MODEL = DEFAULT_VIDEO_UNDERSTANDING_MODEL.value

# Short UGC clips have fast hard cuts; 3 fps reliably catches the before/after
# reveal that 1 fps (the Gemini default) can skip between. Cheap on ≤60s clips.
DEFAULT_FPS = 3.0

_FILE_PROCESS_TIMEOUT_SECS = 5 * 60.0
_FILE_POLL_INTERVAL_SECS = 3.0


# The canonical clone-deconstruction prompt. Written to read the clip like a
# director/cinematographer/editor would — frame-accurate, per-beat, capturing the
# subtle craft (aesthetic, caption style, character/outfit/mood/lighting changes,
# audio, story beats) that make a clip *connect*, not just a surface summary. It
# explicitly forces the two signals a vibe-level analyser drops — the
# TRANSFORMATION arc (what changes start→end) and the ON-SCREEN TEXT (often the
# real hook) — the exact things Higgsfield's analyser missed on the alt-baddie
# bangs reference (it read a before/after transformation as a static "vibe
# montage"). Be exhaustive: capture everything that drives the result.
VIDEO_DECONSTRUCTION_PROMPT = """\
You are an elite short-form director, cinematographer and editor reverse-\
engineering a TikTok/Reel so another creator can rebuild it as an original. \
Watch it like a craftsperson: read the frame, the cut, the sound, the subtext. \
Be precise, literal and timestamped — never generalise, never invent, never \
assume. If you are inferring, say so. Capture EVERY detail that makes it connect, \
hook, and retain. Output these sections:

1. BEAT-BY-BEAT TIMELINE — every distinct shot/cut as a row, with MM:SS start–end. \
For each beat give ALL of:
   - location / setting / environment (and what's in the background)
   - camera: POV (selfie / handheld / tripod / locked-off), framing (ECU/CU/MS/WS), \
angle, movement (push-in, whip, static), lens feel, any speed-ramp or freeze
   - lighting (source, direction, hard/soft, warm/cool, natural/ring-light) and \
colour palette / grade
   - the subject(s): who is on screen, exact action and body language, gaze, hands
   - CHARACTER STATE and any CHANGE vs the previous beat — hair (length, cut, \
styling, colour), outfit, makeup, accessories, props. Call out every change \
explicitly (e.g. "straight centre-part, no bangs" → "blunt micro-bangs").
   - mood / emotion / facial expression and the micro-shift in it
   - on-screen text in THIS beat (verbatim, with its style — font, weight, case, \
colour, position, animation) and any stickers/emoji/effects
   - editing: the transition INTO this beat and whether the cut lands on a beat of \
the music

2. TRANSFORMATION / NARRATIVE ARC — state explicitly what changes from first shot \
to last (appearance, place, emotion, status). If it's a before→after (e.g. \
straight hair → bangs, long → bob, messy → done), describe the exact progression \
and the precise reveal moment. If there is genuinely no transformation, say so \
plainly — do NOT default to "static vibe montage" just because there's no talking \
head.

3. ON-SCREEN TEXT (consolidated) — every overlay transcribed EXACTLY with \
timestamps and its caption STYLE (font/case/colour/placement/animation). This is \
frequently the real hook (e.g. "me without bangs" → "me with bangs"). If none, \
say "none".

4. AUDIO — the sound design beat by beat: music genre / energy / tempo / mood and \
whether vocals are present; the track or sound name if identifiable or shown. \
Transcribe any SPOKEN dialogue or voiceover verbatim with timestamps. Do NOT \
transcribe song LYRICS — for music, describe the vibe and the drop/beat moments \
the edit syncs to. Note SFX and ambient/room tone.

5. HOOK & RETENTION — the first ~1.5s hook mechanism (what stops the scroll), the \
retention structure (open loop, A/B reveal, pattern interrupts, the payoff and \
its timing), the emotional/identity driver, and the single engagement lever it \
most likely wins on (saves / shares / comments / completion) with your reasoning.

6. AESTHETIC / VIBE / THEME — the overall style label (e.g. alt e-girl, clean \
girl, gorpcore), the theme and subculture it signals, the texture (grain, \
handheld shake, film look), the cut cadence/pacing, and the subtle taste signals \
(the sound choice, the framing imperfections) that make it feel authentic rather \
than an ad.

7. CLONE BRIEF — what to KEEP (format / hook / beat structure / on-screen-text \
logic / cut-on-the-beat / pacing) vs CHANGE (subject, substance, claims, \
footage), and exactly where a "native product moment" should slot into the beats \
without breaking the vibe."""


class GeminiVideoClient:
    """Wraps google-genai for video understanding. One instance per request is
    fine (mirrors GeminiImageClient)."""

    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise ValueError("GeminiVideoClient: api_key is required")
        from google import genai  # late import — heavy module

        self._client = genai.Client(api_key=api_key)

    async def understand_video(
        self,
        *,
        data: bytes | None = None,
        youtube_url: str | None = None,
        mime_type: str = "video/mp4",
        prompt: str = VIDEO_DECONSTRUCTION_PROMPT,
        model: str = DEFAULT_VIDEO_MODEL,
        fps: float | None = DEFAULT_FPS,
        start_offset: str | None = None,
        end_offset: str | None = None,
        media_resolution: str | None = None,
    ) -> str:
        """Return Gemini's text deconstruction of a clip — exposing the documented
        video-understanding knobs (ai.google.dev/gemini-api/docs/video-understanding):

          - data | youtube_url — inline/Files-API bytes, OR a public YouTube URL
            (passed as fileData; Gemini fetches it). Exactly one is required.
          - fps                — sampling frame rate via videoMetadata (default 3;
            lower for long videos to save tokens, higher for very fast motion).
          - start_offset/end_offset — clip the analysed window, e.g. "30s", "1m15s".
          - media_resolution   — "low" (~66 tok/frame) | "medium" | "high"; omit for
            the API default (~258 tok/frame). The main token/cost lever.
          - model              — any video-capable Gemini model.

        Raises GeminiAPIError on SDK failure or an empty response (callers fail soft)."""
        if not data and not youtube_url:
            raise ValueError("understand_video: pass either data or youtube_url")
        return await asyncio.to_thread(
            self._run_understand, data, youtube_url, mime_type, prompt, model,
            fps, start_offset, end_offset, media_resolution,
        )

    # ------------------------------------------------------------------

    def _run_understand(
        self,
        data: bytes | None,
        youtube_url: str | None,
        mime_type: str,
        prompt: str,
        model: str,
        fps: float | None,
        start_offset: str | None,
        end_offset: str | None,
        media_resolution: str | None,
    ) -> str:
        from google.genai import types

        vm = _video_metadata(types, fps, start_offset, end_offset)

        if youtube_url:
            video_part = types.Part(
                file_data=types.FileData(file_uri=youtube_url, mime_type="video/*"),
                video_metadata=vm,
            )
        elif data is not None and len(data) <= INLINE_MAX_BYTES:
            video_part = types.Part(
                inline_data=types.Blob(mime_type=mime_type, data=data),
                video_metadata=vm,
            )
        else:
            file_uri, file_mime = self._upload_and_wait(data or b"", mime_type)
            video_part = types.Part(
                file_data=types.FileData(file_uri=file_uri, mime_type=file_mime),
                video_metadata=vm,
            )

        parts: list[Any] = [video_part, types.Part.from_text(text=prompt)]
        cfg = _gen_config(types, media_resolution)
        try:
            resp = self._client.models.generate_content(
                model=model,
                contents=[types.Content(role="user", parts=parts)],
                config=cfg,
            )
        except Exception as exc:
            raise GeminiAPIError(str(exc), model=model) from exc

        text = (getattr(resp, "text", "") or "").strip()
        if not text:
            raise GeminiAPIError(
                "Empty response (safety filter or unsupported video).", model=model
            )
        return text

    def _upload_and_wait(self, data: bytes, mime_type: str) -> tuple[str, str]:
        """Upload via the Files API and poll until ACTIVE. Used only for clips
        over the inline ceiling (rare — TikToks are usually a few MB)."""
        import time

        # The SDK uploads from a path most reliably across versions; the inline
        # path handles the common small-clip case, so the temp file is rare.
        ext = {"video/mp4": ".mp4", "video/webm": ".webm", "video/quicktime": ".mov"}.get(
            mime_type, ".mp4"
        )
        with tempfile.NamedTemporaryFile(suffix=ext) as tmp:
            tmp.write(data)
            tmp.flush()
            file = self._client.files.upload(
                file=tmp.name, config={"mime_type": mime_type}
            )
            deadline = time.monotonic() + _FILE_PROCESS_TIMEOUT_SECS
            while _state_name(file) == "PROCESSING":
                if time.monotonic() > deadline:
                    raise GeminiAPIError(
                        "File processing timed out after 5 minutes.", model="files"
                    )
                time.sleep(_FILE_POLL_INTERVAL_SECS)
                file = self._client.files.get(name=file.name)
            if _state_name(file) == "FAILED":
                raise GeminiAPIError("Files API processing failed.", model="files")
            return file.uri, (getattr(file, "mime_type", None) or mime_type)


def _state_name(file: Any) -> str:
    """File.state is a FileState enum (``.name``) on recent SDKs, a bare string
    on older ones — normalise to the uppercase name."""
    state = getattr(file, "state", None)
    return getattr(state, "name", str(state or "")).upper()


def _video_metadata(types: Any, fps: float | None, start_offset: str | None, end_offset: str | None):
    """Build types.VideoMetadata from the set knobs, or None when none are set.
    start/end offsets are duration strings the SDK accepts (e.g. "30s", "1m15s")."""
    kw: dict[str, Any] = {}
    if fps is not None:
        kw["fps"] = fps
    if start_offset:
        kw["start_offset"] = start_offset
    if end_offset:
        kw["end_offset"] = end_offset
    return types.VideoMetadata(**kw) if kw else None


# Friendly name → SDK MediaResolution member. "default"/unknown ⇒ omit (API default).
_MEDIA_RESOLUTIONS = {
    "low":    "MEDIA_RESOLUTION_LOW",
    "medium": "MEDIA_RESOLUTION_MEDIUM",
    "high":   "MEDIA_RESOLUTION_HIGH",
}


def _gen_config(types: Any, media_resolution: str | None):
    """GenerateContentConfig carrying media_resolution (the per-frame token lever),
    or None when not set / unrecognised (so the API default applies). Guarded with
    getattr so a member absent on an older SDK degrades to the default."""
    if not media_resolution:
        return None
    member = _MEDIA_RESOLUTIONS.get(media_resolution.strip().lower())
    enum_val = getattr(types.MediaResolution, member, None) if member else None
    if enum_val is None:
        return None
    return types.GenerateContentConfig(media_resolution=enum_val)
