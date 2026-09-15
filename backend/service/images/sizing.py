"""Aspect ratio + size → each backend's own dimensional vocabulary.

The tools speak ``AspectRatio`` and ``ImageSize`` because that is what a slide
brief is written in ("9:16, 2K"). Gemini takes exactly those. OpenAI wants a
pixel ``WIDTHxHEIGHT`` under a set of arithmetic rules, and xAI and OpenRouter
each want a ratio from a fixed list plus a coarse resolution rung. Pure
functions, so the mapping is testable without a client.

``nearest_aspect_ratio`` is shared rather than written twice. xAI had the only
fixed list until OpenRouter arrived with one *per model*; a second copy of
"pick the closest ratio by log-proportion" is how two backends quietly drift
into answering the same question differently.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from agents.models import AspectRatio
from service.images.schema import ImageSize

# --- OpenAI -----------------------------------------------------------------
#
# Every gpt-image model Duct offers — 2, 2.5-flare, 2.5-sunburst — accepts
# arbitrary sizes under the same four rules (Image API guide):
# both edges multiples of 16, no edge over 3840, total pixels within
# [655,360, 8,294,400], long-to-short ratio at most 3:1. Every AspectRatio in
# the catalogue is within 3:1, so only the grid and the pixel cap need code.
_OPENAI_GRID = 16
_OPENAI_MAX_PIXELS = 8_294_400
# Long edge per size class. 1K is 1536 rather than 1024 because a 9:16 render
# at 1024 long (576x1024) falls under the 655,360-pixel floor; the square
# case keeps the canonical 1024x1024 the docs list.
_OPENAI_LONG_EDGE = {ImageSize.K1: 1536, ImageSize.K2: 2048, ImageSize.K4: 3840}
_OPENAI_SQUARE_1K = "1024x1024"


def _ratio(aspect_ratio: AspectRatio) -> tuple[int, int]:
    width, height = aspect_ratio.value.split(":")
    return int(width), int(height)


def _snap(value: float) -> int:
    return max(_OPENAI_GRID, int(round(value / _OPENAI_GRID)) * _OPENAI_GRID)


def openai_size(aspect_ratio: AspectRatio, image_size: ImageSize) -> str:
    """The ``size`` string for an OpenAI Images call."""
    w_r, h_r = _ratio(aspect_ratio)
    if w_r == h_r and image_size is ImageSize.K1:
        return _OPENAI_SQUARE_1K
    long_edge = _OPENAI_LONG_EDGE[image_size]
    short_edge = _snap(long_edge * min(w_r, h_r) / max(w_r, h_r))
    width, height = (long_edge, short_edge) if w_r >= h_r else (short_edge, long_edge)
    # A 4K square (3840x3840) is nearly twice the pixel cap; scale both edges
    # down by the same factor and re-snap to the grid.
    if width * height > _OPENAI_MAX_PIXELS:
        factor = math.sqrt(_OPENAI_MAX_PIXELS / (width * height))
        width = int(width * factor / _OPENAI_GRID) * _OPENAI_GRID
        height = int(height * factor / _OPENAI_GRID) * _OPENAI_GRID
    return f"{width}x{height}"


# --- xAI --------------------------------------------------------------------
#
# ``aspect_ratio`` is an enumerated list, not free-form; a ratio Duct offers
# that xAI does not (4:5, 5:4, 9:21, 3:5, 5:3) goes to the nearest one by
# proportion. ``resolution`` has two rungs, so 4K rounds down to 2K.
_XAI_ASPECT_RATIOS = (
    "1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "2:1", "1:2",
    "19.5:9", "9:19.5", "20:9", "9:20", "21:9", "5:2",
)
_XAI_RESOLUTION = {ImageSize.K1: "1k", ImageSize.K2: "2k", ImageSize.K4: "2k"}


def _proportion(ratio: str) -> float:
    width, height = ratio.split(":")
    return float(width) / float(height)


def nearest_aspect_ratio(aspect_ratio: AspectRatio, allowed: Sequence[str]) -> str:
    """The closest ratio in ``allowed`` — exact when the wanted one is in it.

    Closest by log-proportion, so 9:16 and 16:9 sit the same distance from 1:1
    and a portrait brief can never be answered with a landscape frame just
    because the arithmetic was linear.
    """
    wanted = aspect_ratio.value
    if wanted in allowed:
        return wanted
    target = math.log(_proportion(wanted))
    return min(allowed, key=lambda r: abs(math.log(_proportion(r)) - target))


def xai_aspect_ratio(aspect_ratio: AspectRatio) -> str:
    """The closest ratio xAI accepts — exact when it is in their list."""
    return nearest_aspect_ratio(aspect_ratio, _XAI_ASPECT_RATIOS)


def xai_resolution(image_size: ImageSize) -> str:
    return _XAI_RESOLUTION[image_size]


# --- OpenRouter -------------------------------------------------------------
#
# ``resolution`` is already Duct's own vocabulary — OpenRouter spells the rungs
# "512", "1K", "2K", "4K" and ``ImageSize`` spells them "1K"/"2K"/"4K", so the
# only work is clamping to what a given model serves. The allowed list is
# per-model (Flux takes no resolution at all, Seedream stops at 2K), which is
# why it arrives as an argument rather than living here.
_OPENROUTER_RUNGS: tuple[str, ...] = ("512", "1K", "2K", "4K")


def openrouter_resolution(image_size: ImageSize, allowed: Sequence[str]) -> str | None:
    """The resolution field for a model, or None when it takes none.

    Clamps **down** to the nearest rung the model serves. Down rather than up
    because the alternative is billing a user for 4K they did not ask for; a
    slide that is softer than requested is the cheaper way to be wrong.
    """
    if not allowed:
        return None
    wanted = image_size.value
    if wanted in allowed:
        return wanted
    ranked = [rung for rung in _OPENROUTER_RUNGS if rung in allowed]
    below = [rung for rung in ranked if _OPENROUTER_RUNGS.index(rung) < _OPENROUTER_RUNGS.index(wanted)]
    return below[-1] if below else ranked[0]
