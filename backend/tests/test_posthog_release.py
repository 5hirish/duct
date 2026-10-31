"""scripts/posthog_release.py — the Railway build step that makes each deploy a
PostHog release, and the analytics seam reading what it wrote.

The requests are faked at httpx's transport, so the URL, the hash and the body
are the ones that would go over the wire."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import httpx
import pytest

from service import analytics

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "posthog_release.py"
spec = importlib.util.spec_from_file_location("posthog_release", SCRIPT)
posthog_release = importlib.util.module_from_spec(spec)
sys.modules["posthog_release"] = posthog_release
spec.loader.exec_module(posthog_release)

SHA = "3c5c4c2fc010dce57cacfb5a233571ead6477b6b"
ENV = {
    "POSTHOG_CLI_API_KEY": "phx_test",
    "POSTHOG_CLI_PROJECT_ID": "694957",
    "RAILWAY_GIT_COMMIT_SHA": SHA,
    "RAILWAY_GIT_BRANCH": "main",
    "RAILWAY_GIT_REPO_OWNER": "5hirish",
    "RAILWAY_GIT_REPO_NAME": "duct",
}
RELEASES = "https://us.posthog.com/api/projects/694957/error_tracking/releases/"


class Server:
    """PostHog's two release routes, holding what has been created."""

    def __init__(self, *, existing: dict | None = None, create_status: int = 201):
        self.by_hash = dict(existing or {})
        self.create_status = create_status
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        url = str(request.url)
        if request.method == "GET" and url.startswith(f"{RELEASES}hash/"):
            digest = url.removeprefix(f"{RELEASES}hash/").rstrip("/")
            found = self.by_hash.get(digest)
            return httpx.Response(200, json=found) if found else httpx.Response(404)
        if request.method == "POST" and url == RELEASES:
            if self.create_status != 201:
                return httpx.Response(self.create_status, json={"detail": "nope"})
            body = json.loads(request.content)
            release = {"id": "rel-new", **body}
            self.by_hash[body["hash_id"]] = release
            return httpx.Response(201, json=release)
        return httpx.Response(418)

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self))


@pytest.fixture
def id_file(monkeypatch, tmp_path):
    path = tmp_path / ".posthog-release-id"
    monkeypatch.setattr(posthog_release, "RELEASE_ID_FILE", path)
    return path


def test_the_hash_is_the_clis_so_its_releases_are_found_not_duplicated():
    assert posthog_release.release_hash("duct-backend", SHA) == hashlib.sha512(
        f"duct-backend{SHA}".encode()
    ).hexdigest()


def test_a_new_commit_is_created_with_its_git_block(id_file):
    server = Server()
    assert posthog_release.main(ENV, server.client()) == 0

    lookup, create = server.requests
    assert lookup.headers["authorization"] == "Bearer phx_test"
    body = json.loads(create.content)
    assert body["project"] == "duct-backend" and body["version"] == SHA
    assert body["hash_id"] == posthog_release.release_hash("duct-backend", SHA)
    assert body["metadata"]["git"] == {
        "commit_id": SHA,
        "branch": "main",
        "repo_name": "duct",
        "remote_url": "https://github.com/5hirish/duct.git",
    }
    assert id_file.read_text().strip() == "rel-new"


def test_a_commit_built_twice_reuses_its_release(id_file):
    digest = posthog_release.release_hash("duct-backend", SHA)
    server = Server(existing={digest: {"id": "rel-old", "hash_id": digest}})
    posthog_release.main(ENV, server.client())
    assert [r.method for r in server.requests] == ["GET"]
    assert id_file.read_text().strip() == "rel-old"


@pytest.mark.parametrize("missing", ["POSTHOG_CLI_API_KEY", "POSTHOG_CLI_PROJECT_ID", "RAILWAY_GIT_COMMIT_SHA"])
def test_a_build_without_the_settings_asks_nothing(id_file, missing):
    server = Server()
    env = {k: v for k, v in ENV.items() if k != missing}
    assert posthog_release.main(env, server.client()) == 0
    assert server.requests == []
    assert not id_file.exists()


def test_posthog_failing_never_fails_the_build_or_prints_the_key(id_file, capsys):
    server = Server(create_status=500)
    assert posthog_release.main(ENV, server.client()) == 0
    assert not id_file.exists()
    out = capsys.readouterr().out
    assert "500" in out and "phx_test" not in out


def test_the_client_tags_events_with_the_builds_release(monkeypatch, tmp_path):
    path = tmp_path / ".posthog-release-id"
    path.write_text("rel-new\n")
    monkeypatch.setattr(analytics, "_RELEASE_ID_FILE", path)
    monkeypatch.delenv("POSTHOG_RELEASE_ID", raising=False)
    assert analytics._release_properties() == {"$release_id": "rel-new"}

    # Set by hand, the variable wins, and the SDK applies it itself.
    monkeypatch.setenv("POSTHOG_RELEASE_ID", "rel-manual")
    assert analytics._release_properties() == {}


def test_no_build_file_means_no_release_property(monkeypatch, tmp_path):
    monkeypatch.setattr(analytics, "_RELEASE_ID_FILE", tmp_path / "absent")
    monkeypatch.delenv("POSTHOG_RELEASE_ID", raising=False)
    assert analytics._release_properties() == {}
