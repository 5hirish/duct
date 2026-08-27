"""Tests for service.google.gemini.

Mocked tests cover the two pieces that have real logic worth defending:
  - persist_generated_image: writes bytes to disk + inserts the right
    ContentAsset row (catches: wrong filename extension, missing dirs,
    wrong source/asset_type, URL not under /uploads/).
  - per-model option pruning (Imagen-fast drops image_size; Gemini-3.1
    collapses LOW/MEDIUM thinking levels) — actual gating logic.

Live coverage (real Gemini call) lives in tests/test_content_e2e.py
behind GEMINI_API_KEY — that's where contract correctness is verified.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from agents.models import ImageModel
from service.google.gemini.schema import GeneratedImage, ThinkingLevel


# ---------------------------------------------------------------------------
# Per-model option pruning — actual conditional logic
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("model", "level", "expected"),
    [
        (ImageModel.GEMINI_3_1_FLASH_IMAGE, ThinkingLevel.LOW,    ThinkingLevel.MINIMAL),
        (ImageModel.GEMINI_3_1_FLASH_IMAGE, ThinkingLevel.MEDIUM, ThinkingLevel.HIGH),
        (ImageModel.GEMINI_3_1_FLASH_IMAGE, ThinkingLevel.HIGH,   ThinkingLevel.HIGH),
        (ImageModel.GEMINI_3_PRO_IMAGE,     ThinkingLevel.LOW,    ThinkingLevel.LOW),
        (ImageModel.GEMINI_3_PRO_IMAGE,     ThinkingLevel.MEDIUM, ThinkingLevel.MEDIUM),
    ],
)
def test_thinking_level_collapse_per_model(model, level, expected):
    """gemini-3.1-flash-image only supports MINIMAL/HIGH; other Gemini
    models accept the full set unchanged."""
    from service.google.gemini.client import _collapse_thinking_for_gemini_3_1
    assert _collapse_thinking_for_gemini_3_1(model, level) == expected


# ---------------------------------------------------------------------------
# Disk + DB persistence — real behavior, not Pydantic round-tripping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("mime_type", "expected_ext"),
    [
        ("image/png",  ".png"),
        ("image/jpeg", ".jpg"),
        ("image/webp", ".webp"),
    ],
)
def test_persist_generated_image_writes_file_and_inserts_row(mime_type, expected_ext):
    """Catches: wrong file extension for mime type, missing intermediate
    dirs, wrong URL prefix, missing ContentAsset fields. These are the
    actual ways persist_generated_image can break."""
    from service.google.gemini.storage import persist_generated_image

    with tempfile.TemporaryDirectory() as tmpdir:
        # Persistence now flows through service.storage (local backend → disk).
        with patch("service.storage.get_configs") as mock_cfg:
            mock_cfg.return_value.uploads_dir = tmpdir
            mock_cfg.return_value.storage_backend = "local"
            db = MagicMock()
            project_id = uuid4()
            img = GeneratedImage(data=b"\x89PNG-fake-bytes", mime_type=mime_type)

            asset = persist_generated_image(
                project_id, img,
                db=db,
                prompt="a young woman, soft window light",
                model="imagen-4.0-generate-001",
                params={"aspect_ratio": "9:16"},
                source="imagen",
            )

        # File on disk under the project's generated/ subdirectory.
        files = list((Path(tmpdir) / "projects" / str(project_id) / "generated").iterdir())
        assert len(files) == 1
        assert files[0].suffix == expected_ext
        assert files[0].read_bytes() == img.data

        # ContentAsset row inserted with the right shape.
        db.add.assert_called_once()
        row = db.add.call_args[0][0]
        assert row.project_id == project_id
        assert row.source     == "imagen"
        assert row.asset_type == "generated"
        assert row.mime_type  == mime_type
        assert row.url.startswith(f"/uploads/projects/{project_id}/generated/")

        # Returned ImageAsset mirrors the row.
        assert asset.url == row.url
        assert asset.model == "imagen-4.0-generate-001"


# ---------------------------------------------------------------------------
# Multi-reference prefix — the role-explanation text the @tool prepends
# when 2+ references are passed. Without it the model treats both images
# as equal context and may drift on character identity or framing.
# ---------------------------------------------------------------------------


def test_multi_reference_prefix_returns_empty_for_zero_or_one_ref():
    """Single-reference and no-reference cases must not get a multi-ref
    prefix — otherwise the prompt lies to the model about what's
    available, and the result drifts. Cheap regression guard."""
    from service.google.gemini.client import build_multi_reference_prefix
    assert build_multi_reference_prefix(0) == ""
    assert build_multi_reference_prefix(1) == ""


def test_multi_reference_prefix_describes_roles_for_two_or_three_refs():
    """The whole value-add of the multi-ref pattern is that the model
    knows which image is character vs camera vs supplementary. If the
    prefix ever stops naming both roles, character drift returns on
    slides 2-5."""
    from service.google.gemini.client import build_multi_reference_prefix
    two_ref = build_multi_reference_prefix(2)
    assert "character reference" in two_ref
    assert "framing/style reference" in two_ref or "framing/style" in two_ref

    three_ref = build_multi_reference_prefix(3)
    assert "character reference"     in three_ref
    assert "framing/style reference" in three_ref
    assert "third image" in three_ref.lower() or "supplementary" in three_ref.lower()


def test_gemini_image_config_carries_aspect_ratio_and_size():
    """Gemini image models read aspect_ratio + image_size from
    config.image_config (not top-level kwargs, and not a negative_prompt — those
    aren't a concept for Gemini). _gemini_image_config builds that, and returns
    None when nothing is set (an edit that should keep the source dimensions)."""
    from types import SimpleNamespace

    from service.google.gemini.client import _gemini_image_config

    cfg = _gemini_image_config(SimpleNamespace(
        aspect_ratio=SimpleNamespace(value="9:16"),
        image_size=SimpleNamespace(value="2K"),
    ))
    assert cfg is not None
    assert cfg.aspect_ratio == "9:16"
    assert cfg.image_size == "2K"

    assert _gemini_image_config(SimpleNamespace(aspect_ratio=None, image_size=None)) is None
