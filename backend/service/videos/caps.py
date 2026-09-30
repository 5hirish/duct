"""What each video model serves, and the one function that fits a request to it.

The models disagree about everything a clip request carries. Veo makes 4, 6
or 8 seconds, in two ratios, and only makes 1080p at 8 seconds; Seedance 2.0
Mini makes 4 to 15 seconds and stops at 720p; 2.5 runs to 30. So the table
states them and every request is fitted to it before it is sent, the same
rule as the OpenRouter image ``_CAPS``: a clip that came back 8 seconds when
10 were asked for is a deliverable, a 400 is nothing, and the agent cannot
tell a bad request from a bad key.

Unlike the image clamp, each change also comes back as a sentence, because a
clip is seconds of someone's post: the agent has to be able to say "that is
8 seconds, not 10" rather than find out from the player.

Sources: Google's Veo parameter table (ai.google.dev/gemini-api/docs/veo),
OpenRouter's /api/v1/videos/models, both read 2026-09-29, and the Veo MCP
server this workspace already runs for the first/last-frame length rule the
table leaves out.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from agents.models import VideoModel
from service.videos.schema import GenerateVideoRequest, VideoAspectRatio, VideoResolution

logger = logging.getLogger(__name__)

_R = VideoResolution
_A = VideoAspectRatio


@dataclass(frozen=True)
class VideoCaps:
    durations: tuple[int, ...]            # ascending
    resolutions: tuple[VideoResolution, ...]
    aspect_ratios: tuple[VideoAspectRatio, ...]
    #: Veo serves 1080p only on its longest clip…
    full_hd_needs_longest: bool = False
    #: …and interpolates a first and last frame only on it too.
    last_frame_needs_longest: bool = False
    negative_prompt: bool = False
    last_frame: bool = True


_VEO = VideoCaps(
    durations=(4, 6, 8),
    resolutions=(_R.P720, _R.P1080),
    aspect_ratios=(_A.PORTRAIT_9_16, _A.LANDSCAPE_16_9),
    full_hd_needs_longest=True,
    last_frame_needs_longest=True,
    negative_prompt=True,
)

_SEEDANCE_RATIOS = (
    _A.PORTRAIT_9_16, _A.LANDSCAPE_16_9, _A.SQUARE_1_1, _A.PORTRAIT_3_4, _A.LANDSCAPE_4_3, _A.LANDSCAPE_21_9,
)

VIDEO_CAPS: dict[VideoModel, VideoCaps] = {
    VideoModel.VEO_3_1: _VEO,
    VideoModel.VEO_3_1_FAST: _VEO,
    VideoModel.VEO_3_1_LITE: _VEO,
    VideoModel.OR_SEEDANCE_2_5: VideoCaps(
        durations=tuple(range(4, 31)), resolutions=(_R.P480, _R.P720), aspect_ratios=_SEEDANCE_RATIOS,
    ),
    VideoModel.OR_SEEDANCE_2_0_MINI: VideoCaps(
        durations=tuple(range(4, 16)), resolutions=(_R.P480, _R.P720), aspect_ratios=_SEEDANCE_RATIOS,
    ),
}

_RESOLUTION_ORDER = list(VideoResolution)


def caps_for(model: VideoModel) -> VideoCaps:
    return VIDEO_CAPS[model]


def _nearest_duration(asked: int, served: tuple[int, ...]) -> int:
    """The closest length served; a tie goes to the longer one, since a clip
    that runs a second long is trimmed in an editor and one short is not."""
    return min(served, key=lambda d: (abs(d - asked), -d))


def _nearest_ratio(asked: VideoAspectRatio, served: tuple[VideoAspectRatio, ...]) -> VideoAspectRatio:
    """Keep the orientation: portrait and square go to the first portrait ratio
    served, landscape to the first landscape one."""
    width, height = (int(x) for x in asked.value.split(":"))
    want_portrait = width <= height
    for ratio in served:
        w, h = (int(x) for x in ratio.value.split(":"))
        if (w < h) == want_portrait or (w == h and want_portrait):
            return ratio
    return served[0]


def _nearest_resolution(asked: VideoResolution, served: tuple[VideoResolution, ...]) -> VideoResolution:
    """The highest served at or below the ask, else the lowest served."""
    at_or_below = [r for r in served if _RESOLUTION_ORDER.index(r) <= _RESOLUTION_ORDER.index(asked)]
    return at_or_below[-1] if at_or_below else served[0]


def fit_request(
    request: GenerateVideoRequest, *, has_last_frame: bool = False
) -> tuple[GenerateVideoRequest, list[str]]:
    """The request as this model can serve it, and one sentence per change."""
    caps = caps_for(request.model)
    update: dict = {}
    notes: list[str] = []

    duration = request.duration_seconds
    if has_last_frame and caps.last_frame_needs_longest and duration != caps.durations[-1]:
        duration = caps.durations[-1]
        update["duration_seconds"] = duration
        notes.append(
            f"A first-to-last-frame clip is {duration} s on this model, so it is {duration} s "
            f"rather than {request.duration_seconds} s."
        )
    elif duration not in caps.durations:
        duration = _nearest_duration(duration, caps.durations)
        update["duration_seconds"] = duration
        notes.append(
            f"Asked for {request.duration_seconds} s; this model makes "
            f"{caps.durations[0]}-{caps.durations[-1]} s clips, so it is {duration} s."
            if len(caps.durations) > 3 else
            f"Asked for {request.duration_seconds} s; this model makes "
            f"{', '.join(str(d) for d in caps.durations)} s clips, so it is {duration} s."
        )

    if request.aspect_ratio not in caps.aspect_ratios:
        ratio = _nearest_ratio(request.aspect_ratio, caps.aspect_ratios)
        update["aspect_ratio"] = ratio
        notes.append(f"This model does not make {request.aspect_ratio.value}; it is {ratio.value}.")

    resolution = request.resolution
    if resolution not in caps.resolutions:
        resolution = _nearest_resolution(resolution, caps.resolutions)
        update["resolution"] = resolution
        notes.append(f"This model does not make {request.resolution.value}; it is {resolution.value}.")
    if caps.full_hd_needs_longest and resolution is _R.P1080 and duration != caps.durations[-1]:
        update["resolution"] = _R.P720
        notes.append(
            f"1080p needs a {caps.durations[-1]} s clip on this model; the {duration} s clip is 720p."
        )

    if request.negative_prompt and not caps.negative_prompt:
        update["negative_prompt"] = None
        notes.append("This model takes no negative prompt, so it was left out.")

    for note in notes:
        logger.warning("video %s: %s", request.model.value, note)
    return (request.model_copy(update=update) if update else request), notes
