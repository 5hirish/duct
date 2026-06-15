"""Tests for service.content_references — disk enumeration of the
repo-bundled global reference library.

These tests stub the disk root to a tempdir so they don't depend on
the actual shipped references; the enumeration logic is what we're
defending here, not specific file contents.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch


def _seed_refs(root: Path) -> None:
    """Build a representative subset of the on-disk layout."""
    (root / "camera" / "selfie-talking").mkdir(parents=True, exist_ok=True)
    (root / "camera" / "selfie-talking" / "IMG_5885.jpeg").write_bytes(b"fake")
    (root / "camera" / "selfie-talking" / ".gitkeep").write_bytes(b"")
    (root / "camera" / "selfie-talking" / "Thumbs.db").write_bytes(b"")  # non-image
    (root / "camera" / "closeup").mkdir(parents=True, exist_ok=True)
    (root / "camera" / "closeup" / "IMG_5901.png").write_bytes(b"fake")
    (root / "layouts" / "collage").mkdir(parents=True, exist_ok=True)
    (root / "layouts" / "collage" / "shopping-season.jpeg").write_bytes(b"fake")
    (root / "captions" / "pill-bubble").mkdir(parents=True, exist_ok=True)
    (root / "captions" / "pill-bubble" / "puntoymoda-self-test.jpeg").write_bytes(b"fake")


def test_iter_global_references_walks_full_tree_and_skips_non_images(tmp_path):
    """Catches the regression class: someone adds a .gitkeep or DS_Store
    and the picker presents it to the model as a 'reference'. Also
    confirms the tree-walk hits all three axes."""
    _seed_refs(tmp_path)
    with patch("service.content_references._DISK_ROOT", tmp_path):
        from service.content_references import iter_global_references
        refs = list(iter_global_references())

    slugs = {r.slug for r in refs}
    assert slugs == {
        "camera/selfie-talking/IMG_5885",
        "camera/closeup/IMG_5901",
        "layouts/collage/shopping-season",
        "captions/pill-bubble/puntoymoda-self-test",
    }
    # .gitkeep + Thumbs.db dropped silently
    assert not any("gitkeep" in r.filename.lower() for r in refs)
    assert not any("thumbs" in r.filename.lower() for r in refs)


def test_iter_global_references_filters_by_axis_and_subtype(tmp_path):
    """The picker tool will filter by axis + subtype when the orchestrator
    has decided on a layout/camera/caption family. Catches typos in the
    axis/subtype membership lists."""
    _seed_refs(tmp_path)
    with patch("service.content_references._DISK_ROOT", tmp_path):
        from service.content_references import iter_global_references

        only_camera = list(iter_global_references(axis="camera"))
        assert {r.subtype for r in only_camera} == {"selfie-talking", "closeup"}

        only_selfie = list(iter_global_references(axis="camera", subtype="selfie-talking"))
        assert [r.filename for r in only_selfie] == ["IMG_5885.jpeg"]


def test_iter_global_references_rejects_unknown_axis(tmp_path):
    """Defensive — the picker might pass a typo. Yield nothing rather
    than blowing up the agent loop."""
    _seed_refs(tmp_path)
    with patch("service.content_references._DISK_ROOT", tmp_path):
        from service.content_references import iter_global_references
        assert list(iter_global_references(axis="bogus")) == []


def test_disk_path_for_public_url_resolves_under_root(tmp_path):
    """The @tool layer uses this to convert an asset's `url` back to a
    disk path it can read bytes from. Critical security note: the
    resolver must reject path traversal (`..`)."""
    _seed_refs(tmp_path)
    with patch("service.content_references._DISK_ROOT", tmp_path):
        from service.content_references import disk_path_for_public_url

        # Happy path
        p = disk_path_for_public_url("/static/references/camera/selfie-talking/IMG_5885.jpeg")
        assert p is not None
        assert p.exists()
        assert p.read_bytes() == b"fake"

        # Wrong prefix → None
        assert disk_path_for_public_url("/uploads/foo.jpeg") is None
        assert disk_path_for_public_url("not-a-url") is None

        # Path traversal is dropped — the resolved path stays under the root
        traversal = disk_path_for_public_url("/static/references/../../etc/passwd")
        # Either None or a path still under tmp_path — both are safe
        if traversal is not None:
            assert str(traversal).startswith(str(tmp_path))


def test_public_url_matches_disk_layout(tmp_path):
    """Sanity: the public URL the agent stores in ContentAsset.url must
    resolve back to the same file via disk_path_for_public_url. Catches
    silent layout drift between the URL builder + the path resolver."""
    _seed_refs(tmp_path)
    with patch("service.content_references._DISK_ROOT", tmp_path):
        from service.content_references import (
            disk_path_for_public_url,
            iter_global_references,
        )
        for ref in iter_global_references():
            resolved = disk_path_for_public_url(ref.public_url)
            assert resolved is not None
            assert resolved.resolve() == ref.disk_path


def test_global_reference_asset_dicts_shape_and_filter(tmp_path):
    """fetch_content_assets surfaces globals via this shaper. The agent
    treats globals like DB assets, so the dict must carry the asset keys —
    and crucially `id` MUST be the /static/references URL (NOT a UUID),
    because that's exactly what the agent passes back into generate_image."""
    _seed_refs(tmp_path)
    with patch("service.content_references._DISK_ROOT", tmp_path):
        from service.content_references import global_reference_asset_dicts

        cam = global_reference_asset_dicts(axis="camera", subtype="selfie-talking")
        assert len(cam) == 1
        a = cam[0]
        assert a["id"] == "/static/references/camera/selfie-talking/IMG_5885.jpeg"
        assert a["id"] == a["url"]
        assert a["asset_type"] == "reference"
        assert a["source"] == "global"
        assert a["mime_type"] == "image/jpeg"
        assert a["axis"] == "camera"
        assert a["subtype"] == "selfie-talking"

        # .png subtype carries the right mime
        closeup = global_reference_asset_dicts(axis="camera", subtype="closeup")
        assert closeup[0]["mime_type"] == "image/png"

        # No filter → every axis is represented
        axes = {a["axis"] for a in global_reference_asset_dicts()}
        assert axes == {"camera", "layouts", "captions"}
