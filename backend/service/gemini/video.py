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
# director/cinematographer/editor AND a viral-growth strategist would —
# frame-accurate and per-beat, but also DECODING why it stops the scroll and holds:
# the hook taxonomy, the algorithm's real decision gates (≈1.5s distribute / 3s
# resolve), the canonical hook→body→payoff→loop structure as % of runtime, the
# loop/rewatch seam (a 4× reach multiplier), audio-as-distribution + a beat map,
# and the searchable keywords that feed FYP/search. It still forces the two signals
# a vibe-level analyser drops — the TRANSFORMATION arc and the ON-SCREEN TEXT (often
# the real hook). This is the Phase-A "blind craft read" (metrics-free, so the
# predicted lever isn't biased by hindsight); build_deconstruction_prompt() appends
# a Phase-B "why it worked" decode once the real performance data is known. Markers
# are grounded in 2025-26 top-creator practice (see the discovery flow's notes).
VIDEO_DECONSTRUCTION_PROMPT = """\
You are an elite short-form director, cinematographer, editor AND viral-growth \
strategist reverse-engineering a TikTok/Reel so another creator can rebuild it as \
an original. Watch it like a craftsperson AND a growth hacker: read the frame, the \
cut, the sound, the subtext — then decode WHY it stops the scroll and holds. Be \
precise, literal and timestamped — never generalise, never invent, never assume. \
If you are inferring, say so. Capture EVERY detail that makes it connect, hook, and \
retain. Output these sections:

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
   - CASTING BRIEF (state ONCE, for a cloner): describe the creator as a CASTABLE \
person — their KIND of attractiveness + energy + styling vibe (e.g. "striking, warm, \
confident it-girl; glossy lips, polished statement earrings, magnetic direct-to-camera \
gaze, healthy glow"), so a clone can recreate the SAME KIND of magnetic, attractive \
person. Record any literal skin texture / acne / tired or heavy eyes / matte styling / \
an unflattering frame SEPARATELY and label it "literal capture — do NOT copy into a \
clone": those describe THIS recording, not the attractiveness floor to mirror. The \
casting brief is the VIBE to clone; the literal notes are not styling instructions.
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

3. STRUCTURE MAP — give the TOTAL duration in seconds, then map the clip onto the \
canonical short-form skeleton as BOTH a % of runtime AND timestamps: HOOK (0–~3s) \
· BODY/ESCALATION · PAYOFF · CTA/LOOP tail. State the EXACT moment the PAYOFF lands \
(MM:SS) and whether it is CONCRETE (a number, result, or visible transformation) or \
vague. List any mini open-loops inside the body and how each one blocks a clean \
exit (so the viewer can't leave mid-clip).

4. HOOK DECODE — the scroll-stopper, analysed at the algorithm's real decision \
gates:
   - FRAME 0 (the ~150ms thumb-stop): is there a human FACE? high colour CONTRAST \
or a complementary palette? what MOTION type (fast cut = energy / slow push = \
intimacy / snap-zoom = surprise)? does the first frame ITSELF promise value?
   - BY ~1.5s (where the algorithm decides distribution) and BY ~3s (where the hook \
must fully resolve): what has the viewer seen and understood at each gate?
   - HOOK TYPE — classify as one or more of: Product/Outcome-Showcase · \
Authority/Expert-Setup · Contrarian · Specific-Number · Imperative-Command · \
Question/Open-Loop · Confession/Relatable.
   - TRIGGER STACK — which of the four it stacks (strong hooks stack ≥2): \
curiosity · pattern-interrupt · self-relevance · emotional-arousal.
   - the open loop it opens, and when/where it closes.

5. ON-SCREEN TEXT (consolidated) — every overlay transcribed EXACTLY with \
timestamps and its caption STYLE (font/case/colour/placement/animation). This is \
frequently the real hook (e.g. "me without bangs" → "me with bangs"). ALSO extract \
SEARCHABLE KEYWORDS — the niche/topic words in the text (and any spoken words) that \
feed TikTok search + FYP relevance via the auto-transcript. If none, say "none".

6. AUDIO — music genre / energy / tempo / mood and whether vocals are present; the \
track or sound name if identifiable or shown, and whether it reads as a TRENDING / \
borrowed sound vs ORIGINAL audio (trending audio is a distribution lever — flag the \
action: "ride this sound" vs "find the trending equivalent"). Give a BEAT MAP: the \
timestamps the EDIT's cuts/hits land on, so a clone can re-sync to an equivalent \
track. Transcribe any SPOKEN dialogue or voiceover verbatim with timestamps. Do NOT \
transcribe song LYRICS — for music, describe the vibe and the drop/beat moments the \
edit syncs to. Note SFX and ambient/room tone.

7. RETENTION & LOOP — the retention structure (open loop, A/B reveal, pattern \
interrupts, numbered progress), the payoff and its timing, AND the LOOP/REWATCH \
design: does the LAST frame seam back to the FIRST (a seamless loop), and is the \
clip built to reward a rewatch? (Loop/rewatch is a major reach multiplier.) Then \
name the single engagement lever the CRAFT alone predicts it wins on (saves / \
shares / comments / completion) with your reasoning — this is your BLIND prediction \
from structure, BEFORE seeing any metrics.

8. AESTHETIC / VIBE / THEME — the overall style label (e.g. alt e-girl, clean \
girl, gorpcore), the theme and subculture it signals, the texture (grain, \
handheld shake, film look), the cut cadence/pacing, the subtle taste signals \
(the sound choice, the framing imperfections) that make it feel authentic rather \
than an ad — AND what it deliberately OMITS (no intro ramp, no "hey guys", value \
in frame 1) that a cloner should also omit.

9. CLONE BRIEF + TRANSFERABLE TEMPLATE — what to KEEP (format / hook / beat \
structure / on-screen-text logic / cut-on-the-beat / pacing / loop) vs CHANGE \
(subject, substance, claims, footage). Crystallise the reusable skeleton as a \
one-line TEMPLATE — e.g. "[intriguing yes/no question + credibility prop, CU] → \
[hard cut on the beat] → [payoff that answers it, WS] → [repeat the question as \
CTA]". State exactly where a "native product moment" slots into the beats without \
breaking the vibe."""


# 2025-26 algorithm benchmarks the Phase-B decode reasons against. Public counts
# expose none of the #1 signal (watch-time per impression / completion), so the
# model must judge completion STRUCTURALLY from the hook→payoff→loop design.
_GROWTH_BENCHMARKS_2026 = (
    "viral completion bar ≈ 70% of runtime watched; share-rate 2–5% (shares÷views) "
    "= viral-grade; loop/rewatch-rate >15% ≈ 4× the reach; comments now outrank "
    "likes; watch-time-per-impression is the #1 signal but is INVISIBLE in public "
    "counts — judge it STRUCTURALLY from the hook→payoff→loop design, not the ratios."
)


def _author_line(author: dict | None) -> str:
    """One-line creator context for the Phase-B decode. A small account with big
    views is the loudest 'the format itself is the engine' signal, so surface
    follower count + verified prominently."""
    a = author or {}
    handle = a.get("nick_name") or a.get("name") or a.get("unique_id") or "unknown"
    fans = a.get("fans")
    verified = " · verified" if a.get("verified") else ""
    fans_txt = f"{fans:,} followers" if isinstance(fans, int) and fans > 0 else "follower count unknown"
    bio = (a.get("signature") or "").strip().replace("\n", " ")
    bio_txt = f' · bio: "{bio[:120]}"' if bio else ""
    return f"@{handle} — {fans_txt}{verified}{bio_txt}"


def build_deconstruction_prompt(
    *,
    diagnostic: dict | None = None,
    author: dict | None = None,
    niche: str | None = None,
) -> str:
    """The full deconstruction prompt: the Phase-A blind craft read (above) plus,
    when the real performance data is known, a Phase-B "why it worked" growth decode
    that grounds the reasoning in the actual metrics, creator size, niche and the
    2026 benchmarks — and forces a reconciliation against the blind prediction.

    Passing no diagnostic returns the metrics-free Phase-A prompt unchanged (what
    the ad-hoc understand_video tool and the generated-clip review use)."""
    if not diagnostic:
        return VIDEO_DECONSTRUCTION_PROMPT

    d = diagnostic
    metrics_line = (
        f"views={d.get('views')} · likes={d.get('likes')} · comments={d.get('comments')} · "
        f"shares={d.get('shares')} · saves={d.get('saves')} "
        f"(save_rate={d.get('save_rate')}, share_rate={d.get('share_rate')}, "
        f"comment_rate={d.get('comment_rate')})"
    )
    niche_line = f"\n- BRAND NICHE the clone targets: {niche}" if niche else ""
    phase_b = f"""

────────────────────────────────────────
WHY IT WORKED — GROWTH DECODE (do this LAST, AFTER the craft read above)
You now get the REAL performance data. Put on your viral-growth-strategist hat.

- ACTUAL PERFORMANCE: {metrics_line}
- CREATOR: {_author_line(author)}
- DETERMINISTIC LEVER PRIOR (from public counts only): \
{(d.get('lever') or 'unknown').upper()} ({d.get('confidence')} confidence). This is \
a crude ratio prior — TRUST YOUR READ OF THE VIDEO over it if they conflict.{niche_line}
- 2026 BENCHMARKS to judge against: {_GROWTH_BENCHMARKS_2026}

Write a section headed exactly "## WHY IT WORKED" that:
- RECONCILES your blind craft prediction (section 7) with the actual lever — if \
they differ, say what the metrics reveal that the craft read alone didn't.
- names the ONE dominant mechanism that drove the result, tied to SPECIFIC on-screen \
evidence (a named beat / the exact on-screen text / a gesture) — never a platitude.
- judges whether the structure likely CLEARED the ~70% completion bar, and why.
- flags creator-size context (a small account hitting big views = the format itself \
is the engine, so clone it CLOSE).
- gives COPY THIS (the single element to keep) and BEAT THIS (the single weakness \
to fix in the clone — e.g. "no save-worthy asset; add one").

Then, on the final line, output ONLY a fenced ```json block with these keys (no \
prose inside it), inferring each from the video — use null when genuinely unknown:
```json
{{"hook_type": ["..."], "trigger_stack": ["..."], "total_seconds": 0,
 "structure_pct": {{"hook": 0, "body": 0, "payoff": 0, "cta": 0}},
 "payoff_ts": "MM:SS", "payoff_concrete": true, "loops": true,
 "beat_map": ["MM:SS"], "search_keywords": ["..."], "trending_audio": false,
 "predicted_lever": "...", "actual_lever": "...",
 "why_it_worked": "one sentence", "copy_this": "...", "beat_this": "..."}}
```"""
    return VIDEO_DECONSTRUCTION_PROMPT + phase_b


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
