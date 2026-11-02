"""The Ollama server this instance points at: which models it holds, and what
each one can do.

Ollama is the one chat provider Duct holds no key for. The operator sets
``OLLAMA_BASE_URL`` (a local install defaults to this machine's) and every
user of the instance may run on that server, so the questions a key answers
for the other providers — is it there, which models, can this one call tools —
are asked of the server itself, here.

Two reads of Ollama's own REST API, ``GET /api/tags`` and ``POST /api/show``,
through ``httpx.request`` rather than the ``ollama`` package's client: the
answers are small, and one call shape keeps the tests on the same fake as
every other REST connector (``tests/fakes.FakeWire``).

Cached for a minute per server: the catalogue route, the run resolver and
the transport all ask, and a model pulled or removed shows up on the next
minute without anyone restarting Duct.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import httpx

import config
from config import Configs

logger = logging.getLogger(__name__)

# Short: every caller is a page load or the start of a run, and a server that
# takes longer than this to list its models is not one a run should wait on.
_TIMEOUT_SECONDS = 3.0
_CACHE_SECONDS = 60.0

# What /api/show lists under `capabilities`. A model without TOOLS cannot drive
# an agent — every Duct agent works by calling tools — so the pickers leave it
# out rather than let a run fail on its first step.
CAPABILITY_TOOLS = "tools"
CAPABILITY_THINKING = "thinking"


class OllamaUnreachable(RuntimeError):
    """The configured server did not answer, or answered something else."""


@dataclass(frozen=True)
class OllamaModel:
    tag: str
    #: As Ollama reports it, e.g. "8.2B"; empty when it does not say.
    parameter_size: str
    capabilities: frozenset[str]
    #: The length the model was trained to; 0 when Ollama does not say.
    context_length: int

    @property
    def calls_tools(self) -> bool:
        return CAPABILITY_TOOLS in self.capabilities

    @property
    def thinks(self) -> bool:
        return CAPABILITY_THINKING in self.capabilities


def server_url(cfg: Configs | None = None) -> str:
    """The configured server, without a trailing slash; empty when none is."""
    # getattr: asked on every run's resolution, so a settings object without
    # the field (an older stand-in, a test's namespace) means "none", not a 500.
    settings = cfg or config.get_configs()
    return (getattr(settings, "ollama_base_url", "") or "").strip().rstrip("/")


_cache: dict[tuple[str, str], tuple[float, object]] = {}


def _cached(key: tuple[str, str], load):
    now = time.monotonic()
    hit = _cache.get(key)
    if hit is not None and now - hit[0] < _CACHE_SECONDS:
        return hit[1]
    value = load()
    _cache[key] = (now, value)
    return value


def clear_cache() -> None:
    _cache.clear()


def _call(method: str, url: str, **kwargs) -> dict:
    try:
        response = httpx.request(method, url, timeout=_TIMEOUT_SECONDS, **kwargs)
        response.raise_for_status()
        body = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise OllamaUnreachable(f"{method} {url}: {exc}") from exc
    if not isinstance(body, dict):
        raise OllamaUnreachable(f"{method} {url}: not a JSON object")
    return body


def _context_length(model_info: dict) -> int:
    # Keyed by architecture ("llama.context_length", "qwen3.context_length"),
    # so matched by suffix rather than by a table of architectures.
    for key, value in (model_info or {}).items():
        if key.endswith(".context_length") and isinstance(value, int):
            return value
    return 0


def describe(tag: str, *, url: str) -> OllamaModel:
    """One model's size, capabilities and trained length. Raises
    ``OllamaUnreachable``."""

    def load() -> OllamaModel:
        body = _call("POST", f"{url}/api/show", json={"model": tag})
        details = body.get("details") or {}
        return OllamaModel(
            tag=tag,
            parameter_size=str(details.get("parameter_size") or ""),
            capabilities=frozenset(body.get("capabilities") or ()),
            context_length=_context_length(body.get("model_info") or {}),
        )

    return _cached((url, f"show:{tag}"), load)


def installed_models(url: str) -> list[OllamaModel]:
    """Every model the server holds, most recently pulled first. Raises
    ``OllamaUnreachable``."""

    def load() -> list[OllamaModel]:
        tags = [m.get("name") or m.get("model") for m in _call("GET", f"{url}/api/tags").get("models") or []]
        return [describe(tag, url=url) for tag in tags if tag]

    return _cached((url, "tags"), load)


def tool_models(cfg: Configs | None = None) -> list[OllamaModel]:
    """The models a Duct agent can run on; empty when there is no server, it
    is down, or it holds nothing that calls tools. Never raises."""
    url = server_url(cfg)
    if not url:
        return []
    try:
        return [m for m in installed_models(url) if m.calls_tools]
    except OllamaUnreachable as exc:
        logger.info("ollama: %s", exc)
        return []


def model_or_none(tag: str, cfg: Configs | None = None) -> OllamaModel | None:
    """What the server says about one tag, or None when it cannot say."""
    url = server_url(cfg)
    if not url:
        return None
    try:
        return describe(tag, url=url)
    except OllamaUnreachable as exc:
        logger.info("ollama: %s", exc)
        return None
