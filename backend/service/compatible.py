"""An OpenAI-compatible endpoint a user brings: the address, its key, and
which of its models they chose.

Nearly every way to run an open model speaks OpenAI's chat-completions API:
vLLM, llama.cpp's server, LM Studio, SGLang, LiteLLM, and the hosts of
open-weight models (Together, Fireworks, Groq, DeepInfra). One provider covers
all of them, ``Provider.OPENAI_COMPATIBLE``, and this module is what it knows
that a plain API key does not.

**The credential is one string.** Address, optional key and the chosen models
(with the context length the server reported for each) are packed into a
single opaque value (``pack`` / ``unpack``). That is what lets it be a key
everywhere a key already goes: the browser's session storage or the desktop
keychain, the ``X-Provider-Compatible`` header, a remembered key encrypted at
rest, a key lent to the memory sweep. Nothing between the settings page and
``resolve_chat_model`` has to know it holds three things, the way nothing
between them knows a ChatGPT plan holds two (``agents/core/codex.py``).
Packing the models in means a run never asks the server what it serves: the
answer it got when the user connected is the one they chose from.

**The address is user input, so it is a request someone else aims.** On a
hosted instance it must be a public https address, judged on the name when it
is entered and on the resolved address on every request after
(``service/crawl/fetcher``'s check, the one every other user-aimed fetch in
Duct goes through). A private address (LM Studio on localhost, vLLM on the
LAN) is allowed only where the network is the user's own: a desktop sidecar,
local dev, or a self-hosted server that set ``PRIVATE_MODEL_ENDPOINTS``.

Framework-free: the tool-call check that proves a model can run an agent is
LangChain's, and lives in ``routes/providers.py``.
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
import re
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

import httpx

import config
from config import Configs
from service.crawl.fetcher import SSRFError, assert_public_url, assert_public_url_sync, validate_public_url

logger = logging.getLogger(__name__)

# Versioned, so the shape can change without a stored credential becoming a
# string nobody can read.
CREDENTIAL_PREFIX = "oaic1."

# A server that does not say how long a model's context is gets this. Low on
# purpose: budgeting a thread in less than the model has costs an early
# summary, and budgeting in more than it has is a request it refuses.
DEFAULT_CONTEXT_LENGTH = 32_768

_LIST_TIMEOUT_SECONDS = 10.0

# Where servers put a model's context length in their /models listing, which
# the OpenAI shape itself does not carry: vLLM says `max_model_len`, Together,
# DeepInfra and OpenRouter `context_length`, Groq `context_window`.
_CONTEXT_FIELDS = ("max_model_len", "context_length", "context_window", "max_context_length")

# A listing mixes chat models with ones that cannot hold a conversation. Some
# servers type their entries (Together does); the rest are judged by name.
_CHAT_TYPES = frozenset({"chat", "language", "code", "llm", "text"})
_NOT_CHAT = re.compile(
    r"embed|whisper|tts|transcri|rerank|moderation|guard|dall-e|stable-diffusion|flux|image|vision-only|bge-|e5-",
    re.IGNORECASE,
)

# What a pasted address commonly ends in beyond the base the SDK wants.
_ENDPOINT_SUFFIXES = ("/chat/completions", "/completions", "/models")


class UnsafeEndpoint(ValueError):
    """An address Duct will not call. The message is safe to show."""


# Why discovery failed, in the same vocabulary verify answers in.
CODE_UNREACHABLE = "unreachable"
CODE_INVALID_KEY = "invalid_key"
CODE_NOT_COMPATIBLE = "not_compatible"
CODE_NO_MODELS = "no_models"
CODE_REFUSED = "refused"


class EndpointError(RuntimeError):
    """Discovery failed. ``code`` picks the sentence the app shows."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(detail or code)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class EndpointModel:
    id: str
    #: As the server reported it; 0 when it did not say.
    context_length: int = 0

    @property
    def window(self) -> int:
        return self.context_length or DEFAULT_CONTEXT_LENGTH


@dataclass(frozen=True)
class Endpoint:
    base_url: str
    api_key: str = ""
    #: The models the user chose, the first being what a run takes when no
    #: tier names one of them.
    models: tuple[EndpointModel, ...] = ()

    def model(self, served_id: str) -> EndpointModel | None:
        return next((m for m in self.models if m.id == served_id), None)

    @property
    def host(self) -> str:
        return urlsplit(self.base_url).netloc


def pack(endpoint: Endpoint) -> str:
    body = {
        "u": endpoint.base_url,
        "k": endpoint.api_key,
        "m": [[m.id, m.context_length] for m in endpoint.models],
    }
    raw = json.dumps(body, separators=(",", ":")).encode()
    return CREDENTIAL_PREFIX + base64.urlsafe_b64encode(raw).decode().rstrip("=")


def is_packed(value: str) -> bool:
    return (value or "").strip().startswith(CREDENTIAL_PREFIX)


def unpack(value: str) -> Endpoint | None:
    """The endpoint inside a credential, or None for anything that is not one."""
    value = (value or "").strip()
    if not value.startswith(CREDENTIAL_PREFIX):
        return None
    encoded = value[len(CREDENTIAL_PREFIX):]
    try:
        body = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
        url = str(body["u"]).strip()
        models = tuple(
            EndpointModel(str(entry[0]), int(entry[1] or 0))
            for entry in body.get("m") or ()
            if entry and str(entry[0]).strip()
        )
    except (binascii.Error, ValueError, TypeError, KeyError, IndexError):
        return None
    if not url or not models:
        return None
    return Endpoint(base_url=url, api_key=str(body.get("k") or ""), models=models)


def private_allowed(cfg: Configs | None = None) -> bool:
    """Whether an endpoint may be on a private network on this instance."""
    settings = cfg or config.get_configs()
    if getattr(settings, "private_model_endpoints", False):
        return True
    return bool(settings.duct_local) or settings.app_env == "local"


def canonical_base_url(raw: str, *, private_ok: bool) -> str:
    """The base URL Duct stores and calls, or ``UnsafeEndpoint``.

    Forgiving of what people paste: a full ``…/chat/completions`` URL becomes
    its base, and a trailing slash goes. Strict about where it points: no
    credentials in the address, and off a private network https only, judged
    here on the name and again on the resolved address before every request.
    """
    url = (raw or "").strip()
    if url and "://" not in url:
        url = f"https://{url}"
    try:
        parts = urlsplit(url)
        parts.port  # noqa: B018 — raises on a malformed port
    except ValueError as exc:
        raise UnsafeEndpoint("That isn't a web address.") from exc
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise UnsafeEndpoint("That isn't a web address.")
    if parts.username or parts.password:
        raise UnsafeEndpoint("Put the key in the key field, not in the address.")
    if not private_ok:
        try:
            validate_public_url(url)
        except SSRFError as exc:
            raise UnsafeEndpoint(
                "That address is on a private network, which Duct's servers can't reach."
            ) from exc
        if parts.scheme != "https":
            raise UnsafeEndpoint("Use an https:// address, so your key isn't sent in the clear.")
    path = parts.path.rstrip("/")
    for suffix in _ENDPOINT_SUFFIXES:
        if path.endswith(suffix):
            path = path[: -len(suffix)]
            break
    return urlunsplit((parts.scheme, parts.netloc.lower(), path, "", ""))


def _context_length(entry: dict) -> int:
    # Some servers nest it one level down, under `meta` or `metadata`.
    nested = entry.get("meta") or entry.get("metadata")
    for source in (entry, nested if isinstance(nested, dict) else {}):
        for field in _CONTEXT_FIELDS:
            value = source.get(field)
            if isinstance(value, int) and value > 0:
                return value
    return 0


def _chat_model(entry: dict) -> bool:
    kind = str(entry.get("type") or "").lower()
    if kind:
        return kind in _CHAT_TYPES
    return not _NOT_CHAT.search(str(entry.get("id") or ""))


def discover(base_url: str, api_key: str = "", *, private_ok: bool) -> list[EndpointModel]:
    """The chat models the server lists, from ``GET {base}/models``.

    Synchronous (``httpx.request``, the same call shape as the REST
    connectors, so tests fake it with ``FakeWire``); call it off the event
    loop. Raises ``EndpointError`` with a code the app can word.
    """
    url = f"{base_url}/models"
    if not private_ok:
        try:
            assert_public_url_sync(url)
        except SSRFError as exc:
            raise EndpointError(CODE_REFUSED, "That address resolves to a private network.") from exc
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    try:
        response = httpx.request("GET", url, headers=headers, timeout=_LIST_TIMEOUT_SECONDS)
    except httpx.HTTPError as exc:
        raise EndpointError(CODE_UNREACHABLE, f"Nothing answered at {urlsplit(base_url).netloc}.") from exc
    if response.status_code in (401, 403):
        raise EndpointError(CODE_INVALID_KEY, f"The server said {response.status_code}: the key is missing or wrong.")
    if response.status_code == 404:
        raise EndpointError(CODE_NOT_COMPATIBLE, "Nothing at that address lists models. Check it ends where /v1 does.")
    if response.status_code >= 400:
        raise EndpointError(CODE_UNREACHABLE, f"The server answered {response.status_code}.")
    try:
        body = response.json()
    except ValueError as exc:
        raise EndpointError(CODE_NOT_COMPATIBLE, "The server answered, but not in OpenAI's format.") from exc
    entries = body.get("data") if isinstance(body, dict) else body
    if not isinstance(entries, list):
        raise EndpointError(CODE_NOT_COMPATIBLE, "The server answered, but not in OpenAI's format.")
    models = [
        EndpointModel(str(entry["id"]), _context_length(entry))
        for entry in entries
        if isinstance(entry, dict) and entry.get("id") and _chat_model(entry)
    ]
    if not models:
        raise EndpointError(CODE_NO_MODELS, "The server lists no chat models.")
    return sorted(models, key=lambda m: m.id.lower())


# ---------------------------------------------------------------------------
# The transport's guard
# ---------------------------------------------------------------------------


def _refuse(url: str) -> None:
    if not url.startswith("https://"):
        raise SSRFError("An endpoint off a private network is https only.")


def _sync_guard(request: httpx.Request) -> None:
    url = str(request.url)
    _refuse(url)
    assert_public_url_sync(url)


async def _async_guard(request: httpx.Request) -> None:
    url = str(request.url)
    _refuse(url)
    await assert_public_url(url)


def guarded_http_clients(*, private_ok: bool) -> dict:
    """The ``http_client`` / ``http_async_client`` pair for ChatOpenAI, or
    nothing where a private address is allowed anyway.

    Every request the model client makes, redirects included, is judged on
    the address it resolves to. ``trust_env=False`` so an ambient proxy cannot
    carry a user's key somewhere nobody chose.
    """
    if private_ok:
        return {}
    return {
        "http_client": httpx.Client(trust_env=False, event_hooks={"request": [_sync_guard]}),
        "http_async_client": httpx.AsyncClient(trust_env=False, event_hooks={"request": [_async_guard]}),
    }


# ---------------------------------------------------------------------------
# Windows, for readers that hold a model id and no credential
# ---------------------------------------------------------------------------

# The run's own transport knows the window exactly (it holds the credential).
# The usage gauge and the context meter hold only the model id, so the window
# the transport last resolved for it is kept here. In-process and keyed by id,
# so two users whose servers name a model alike share a gauge figure; it sizes
# a display, never a request.
_windows: dict[str, int] = {}


def remember_window(model_id: str, window: int) -> None:
    _windows[model_id] = window


def window_for(model_id: str) -> int:
    return _windows.get(model_id, DEFAULT_CONTEXT_LENGTH)
