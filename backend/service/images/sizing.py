"""Aspect ratio + size → each backend's own dimensional vocabulary.

The tools speak ``AspectRatio`` and ``ImageSize`` because that is what a slide
brief is written in ("9:16, 2K"). Gemini takes exactly those. OpenAI wants a
pixel ``WIDTHxHEIGHT`` under a set of arithmetic rules, and xAI wants a ratio
from its own list plus a coarse ``1k``/``2k``. Pure functions, so the mapping
is testable without a client.
"""

from __future__ import annotations

import math

from agents.models import AspectRatio
from service.images.schema import ImageSize

# --- OpenAI -----------------------------------------------------------------
#
# gpt-image-2 accepts arbitrary sizes under four rules (Image API guide):
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


def xai_aspect_ratio(aspect_ratio: AspectRatio) -> str:
    """The closest ratio xAI accepts — exact when it is in their list."""
    wanted = aspect_ratio.value
    if wanted in _XAI_ASPECT_RATIOS:
        return wanted
    target = math.log(_proportion(wanted))
    return min(_XAI_ASPECT_RATIOS, key=lambda r: abs(math.log(_proportion(r)) - target))


def xai_resolution(image_size: ImageSize) -> str:
    return _XAI_RESOLUTION[image_size]
