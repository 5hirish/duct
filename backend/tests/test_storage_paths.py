"""Local storage refuses keys that climb out of the uploads directory.

Every caller today composes its key from a project id, a uuid and an
allowlisted extension, so no live path can traverse. That safety lives in the
callers, one refactor from evaporating, and the sink used to join whatever it
was handed. These tests pin the guard to the sink instead.
"""

from __future__ import annotations

import pytest

from service import storage


@pytest.fixture
def uploads(tmp_path, monkeypatch):
    """Point storage at a temp uploads dir on the local backend."""
    monkeypatch.setattr(storage, "storage_backend", lambda: "local")

    class _Cfg:
        uploads_dir = str(tmp_path)

    monkeypatch.setattr(storage, "get_configs", lambda: _Cfg())
    return tmp_path


TRAVERSALS = [
    "../escaped.txt",
    "../../etc/passwd",
    "projects/../../escaped.txt",
    "a/b/../../../escaped.txt",
    "/etc/passwd",              # absolute: os.path.join would honour it whole
]


@pytest.mark.parametrize("key", TRAVERSALS)
def test_writing_outside_uploads_is_refused(uploads, key):
    with pytest.raises(ValueError, match="escapes the uploads directory"):
        storage.put_image(key, b"x", "image/png")
    assert not (uploads.parent / "escaped.txt").exists()


@pytest.mark.parametrize("key", TRAVERSALS)
def test_reading_outside_uploads_is_refused(uploads, key):
    with pytest.raises(ValueError, match="escapes the uploads directory"):
        storage.get_private_bytes(key)


def test_get_bytes_refuses_a_traversing_uploads_url(uploads):
    secret = uploads.parent / "secret.txt"
    secret.write_text("classified")

    with pytest.raises(ValueError, match="escapes the uploads directory"):
        storage.get_bytes("/uploads/../secret.txt")


def test_a_symlink_out_of_uploads_is_refused(uploads):
    """The text of this key is innocent; only resolving it tells the truth."""
    outside = uploads.parent / "outside"
    outside.mkdir()
    (uploads / "link").symlink_to(outside)

    with pytest.raises(ValueError, match="escapes the uploads directory"):
        storage.put_image("link/escaped.txt", b"x", "image/png")


def test_a_sibling_directory_sharing_the_prefix_is_refused(uploads, monkeypatch):
    """/app/uploads-evil starts with /app/uploads; the separator is the check."""
    sibling = uploads.parent / f"{uploads.name}-evil"
    sibling.mkdir()

    with pytest.raises(ValueError, match="escapes the uploads directory"):
        storage.get_private_bytes(f"../{sibling.name}/secret.txt")


def test_delete_never_raises_even_on_a_bad_key(uploads):
    """delete_private promises it never raises; the guard must not break that."""
    storage.delete_private("../../escaped.txt")


def test_an_ordinary_key_still_round_trips(uploads):
    key = "projects/abc/generated/img.png"

    url = storage.put_image(key, b"hello", "image/png")

    assert url == f"/uploads/{key}"
    assert (uploads / key).read_bytes() == b"hello"
    assert storage.get_bytes(url) == b"hello"
    assert storage.get_private_bytes(key) == b"hello"
