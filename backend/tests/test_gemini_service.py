"""Unit tests for service.gemini.

Covers schema validation, the storage helper (real disk + mocked DB
session), and the per-model option-pruning logic. Real Gemini API calls
are not exercised here — that needs a live key and lives in Phase 6.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from agents.models import AspectRatio, ImageModel
from service.gemini.schema import (
    EditImageRequest,
    EditMode,
    GenerateImageRequest,
    GeneratedImage,
    ImageSize,
    MaskMode,
    PersonGeneration,
    SubjectType,
    ThinkingLevel,
)


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


def test_generate_image_request_defaults():
    req = GenerateImageRequest(prompt="a cat")
    assert req.model == ImageModel.GEMINI_3_1_FLASH_IMAGE_PREVIEW  # DEFAULT_IMAGE_MODEL
    assert req.aspect_ratio == AspectRatio.PORTRAIT_9_16
    assert req.image_size == ImageSize.K1
    assert req.number_of_images == 1
    assert req.output_mime_type == "image/png"


def test_generate_image_request_caps_number_of_images():
    with pytest.raises(Exception):
        GenerateImageRequest(prompt="x", number_of_images=99)


def test_generate_image_request_rejects_empty_prompt():
    with pytest.raises(Exception):
        GenerateImageRequest(prompt="")


def test_edit_image_request_requires_input_asset_id():
    with pytest.raises(Exception):
        EditImageRequest(prompt="add a hat")


def test_edit_image_request_with_all_refs():
    """All reference fields are optional and accept enum values."""
    req = EditImageRequest(
        prompt="swap background",
        input_asset_id=uuid4(),
        model=ImageModel.IMAGEN_4_GENERATE_001,
        edit_mode=EditMode.BGSWAP,
        mask_asset_id=uuid4(),
        mask_mode=MaskMode.BACKGROUND,
        subject_asset_id=uuid4(),
        subject_type=SubjectType.PERSON,
    )
    assert req.edit_mode == EditMode.BGSWAP
    assert req.mask_mode == MaskMode.BACKGROUND
    assert req.subject_type == SubjectType.PERSON


# ---------------------------------------------------------------------------
# Per-model option pruning
# ---------------------------------------------------------------------------


def test_thinking_level_collapse_for_gemini_3_1():
    """Gemini-3.1-flash-image only supports MINIMAL or HIGH; LOW→MINIMAL, MEDIUM→HIGH."""
    from service.gemini.client import _collapse_thinking_for_gemini_3_1

    assert _collapse_thinking_for_gemini_3_1(
        ImageModel.GEMINI_3_1_FLASH_IMAGE_PREVIEW, ThinkingLevel.LOW
    ) == ThinkingLevel.MINIMAL
    assert _collapse_thinking_for_gemini_3_1(
        ImageModel.GEMINI_3_1_FLASH_IMAGE_PREVIEW, ThinkingLevel.MEDIUM
    ) == ThinkingLevel.HIGH
    assert _collapse_thinking_for_gemini_3_1(
        ImageModel.GEMINI_3_1_FLASH_IMAGE_PREVIEW, ThinkingLevel.HIGH
    ) == ThinkingLevel.HIGH
    # Other models pass through unchanged
    assert _collapse_thinking_for_gemini_3_1(
        ImageModel.GEMINI_3_PRO_IMAGE_PREVIEW, ThinkingLevel.LOW
    ) == ThinkingLevel.LOW


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------


def test_persist_generated_image_writes_disk_and_row():
    from service.gemini.storage import persist_generated_image

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("service.gemini.storage.get_configs") as mock_cfg:
            mock_cfg.return_value.uploads_dir = tmpdir

            db = MagicMock()
            db.add = MagicMock()
            db.commit = MagicMock()
            db.refresh = MagicMock()

            project_id = uuid4()
            img = GeneratedImage(data=b"\x89PNG\r\n\x1a\nfake-bytes", mime_type="image/png")
            asset = persist_generated_image(
                project_id, img,
                db=db,
                prompt="a young woman, oval face, soft light",
                model="gemini-3.1-flash-image-preview",
                params={"aspect_ratio": "9:16"},
            )

            # File written
            expected_dir = Path(tmpdir) / "projects" / str(project_id) / "generated"
            files = list(expected_dir.iterdir())
            assert len(files) == 1
            assert files[0].read_bytes() == img.data
            assert files[0].suffix == ".png"

            # URL points at the public path
            assert asset.url.startswith(f"/uploads/projects/{project_id}/generated/")
            assert asset.url.endswith(".png")
            assert asset.mime_type == "image/png"
            assert asset.prompt.startswith("a young woman")
            assert asset.model == "gemini-3.1-flash-image-preview"

            # DB row persisted
            db.add.assert_called_once()
            db.commit.assert_called_once()
            row = db.add.call_args[0][0]
            assert row.project_id == project_id
            assert row.source == "gemini"
            assert row.asset_type == "generated"


def test_persist_generated_image_jpeg_extension():
    from service.gemini.storage import persist_generated_image

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("service.gemini.storage.get_configs") as mock_cfg:
            mock_cfg.return_value.uploads_dir = tmpdir
            db = MagicMock()
            project_id = uuid4()
            img = GeneratedImage(data=b"\xff\xd8\xff", mime_type="image/jpeg")
            asset = persist_generated_image(
                project_id, img,
                db=db,
                prompt="x", model="imagen-4.0-generate-001",
                params={}, source="imagen",
            )
            assert asset.url.endswith(".jpg")
            row = db.add.call_args[0][0]
            assert row.source == "imagen"


# ---------------------------------------------------------------------------
# Client construction
# ---------------------------------------------------------------------------


def test_gemini_client_requires_api_key():
    from service.gemini.client import GeminiImageClient
    with pytest.raises(ValueError):
        GeminiImageClient("")


def test_extract_imagen_images_raises_when_empty():
    from service.gemini.client import GeminiAPIError, _extract_imagen_images

    fake = MagicMock()
    fake.generated_images = []
    with pytest.raises(GeminiAPIError, match="No images returned"):
        _extract_imagen_images(fake, "imagen-4.0-generate-001")


def test_extract_gemini_images_handles_inline_data():
    from service.gemini.client import _extract_gemini_images

    inline = MagicMock()
    inline.data = b"FAKE"
    inline.mime_type = "image/png"
    part = MagicMock()
    part.inline_data = inline
    content = MagicMock()
    content.parts = [part]
    cand = MagicMock()
    cand.content = content
    fake = MagicMock()
    fake.candidates = [cand]

    images = _extract_gemini_images(fake, "gemini-3.1-flash-image-preview")
    assert len(images) == 1
    assert images[0].data == b"FAKE"
    assert images[0].mime_type == "image/png"


def test_extract_gemini_images_skips_text_parts():
    """Gemini may return text+image parts; only image parts become GeneratedImage."""
    from service.gemini.client import _extract_gemini_images

    text_part = MagicMock()
    text_part.inline_data = None
    inline = MagicMock()
    inline.data = b"IMG"
    inline.mime_type = "image/png"
    img_part = MagicMock()
    img_part.inline_data = inline
    content = MagicMock()
    content.parts = [text_part, img_part]
    cand = MagicMock()
    cand.content = content
    fake = MagicMock()
    fake.candidates = [cand]
    images = _extract_gemini_images(fake, "gemini-3.1-flash-image-preview")
    assert len(images) == 1
    assert images[0].data == b"IMG"


def test_person_generation_enum():
    """Sanity: enum values match what the Gemini SDK expects."""
    assert PersonGeneration.ALLOW_ADULT.value == "allow_adult"
    assert PersonGeneration.DONT_ALLOW.value  == "dont_allow"
