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
is entered, and every request after is resolved once, judged
(``service/crawl/fetcher``'s rule, the one every other user-aimed fetch in
Duct follows) and connected to the address that passed, so a second DNS
answer never gets a say. A private address (LM Studio on localhost, vLLM on the
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
import time
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

import httpx2

import config
from config import Configs
from service.crawl.fetcher import SSRFError, resolve_public, resolve_public_sync, validate_public_url

logger = logging.getLogger(__name__)

# Versioned, so the shape can change without a stored credential becoming a
# string nobody can read.
CREDENTIAL_PREFIX = "oaic1."

# A server that does not say how long a model's context is gets this. Low on
# purpose: budgeting a thread in less than the model has costs an early
# summary, and budgeting in more than it has is a request it refuses.
DEFAULT_CONTEXT_LENGTH = 32_768

_LIST_TIMEOUT_SECONDS = 10.0
# A host's whole catalogue is a few hundred kilobytes; past these, a listing
# is not one Duct needs to finish reading.
_LIST_DEADLINE_SECONDS = 15.0
_LIST_MAX_BYTES = 4 * 1024 * 1024
_LIST_MAX_ENTRIES = 2_000

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
    """An address Duct will not call. ``detail`` is safe to show.

    Routes answer with ``detail``, never ``str(exc)``: every raise below
    passes one of our own sentences, but ``str()`` of an exception is whatever
    the next raise site, or a chained cause, puts there.
    """

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


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

    Synchronous; call it off the event loop. Read as a stream and held to
    ``_LIST_MAX_BYTES`` and ``_LIST_DEADLINE_SECONDS`` overall: the server is
    one the caller named, and a listing that never ends, or arrives a byte at
    a time, must cost a bounded amount. Raises ``EndpointError`` with a code
    the app can word.
    """
    url = f"{base_url}/models"
    host = urlsplit(base_url).netloc
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    started = time.monotonic()
    try:
        with _list_client(private_ok) as client, client.stream("GET", url, headers=headers) as response:
            if response.status_code in (401, 403):
                raise EndpointError(CODE_INVALID_KEY, f"The server said {response.status_code}: the key is missing or wrong.")
            if response.status_code == 404:
                raise EndpointError(CODE_NOT_COMPATIBLE, "Nothing at that address lists models. Check it ends where /v1 does.")
            if response.status_code >= 400:
                raise EndpointError(CODE_UNREACHABLE, f"The server answered {response.status_code}.")
            body = bytearray()
            for chunk in response.iter_bytes():
                body += chunk
                if len(body) > _LIST_MAX_BYTES:
                    raise EndpointError(CODE_NOT_COMPATIBLE, "The server's model list is too large to read.")
                if time.monotonic() - started > _LIST_DEADLINE_SECONDS:
                    raise EndpointError(CODE_UNREACHABLE, f"{host} took too long to list its models.")
    except SSRFError as exc:
        raise EndpointError(CODE_REFUSED, "That address resolves to a private network.") from exc
    except httpx2.HTTPError as exc:
        raise EndpointError(CODE_UNREACHABLE, f"Nothing answered at {host}.") from exc
    try:
        payload = json.loads(bytes(body))
    except ValueError as exc:
        raise EndpointError(CODE_NOT_COMPATIBLE, "The server answered, but not in OpenAI's format.") from exc
    entries = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(entries, list):
        raise EndpointError(CODE_NOT_COMPATIBLE, "The server answered, but not in OpenAI's format.")
    models = [
        EndpointModel(str(entry["id"]), _context_length(entry))
        for entry in entries[:_LIST_MAX_ENTRIES]
        if isinstance(entry, dict) and entry.get("id") and _chat_model(entry)
    ]
    if not models:
        raise EndpointError(CODE_NO_MODELS, "The server lists no chat models.")
    return sorted(models, key=lambda m: m.id.lower())


# ---------------------------------------------------------------------------
# The transport: every request to the address that was checked
# ---------------------------------------------------------------------------
#
# Judging a name and then letting the client resolve it again leaves a window
# a hostile DNS server can use: public on the check, 169.254.169.254 on the
# connect. So off a private network each request is resolved once, every
# answer judged, and the connection made to the address that passed, with the
# real hostname kept for TLS (SNI and certificate checks) and the Host header.
# Redirects pass through the transport too, so each hop is pinned the same way.
#
# httpx2 because it is the OpenAI SDK's own client, which ChatOpenAI hands
# these to; discovery shares the transport so the rule exists once.


def _pin(request: httpx2.Request, address: str) -> None:
    if request.url.scheme != "https":
        raise SSRFError("An endpoint off a private network is https only.")
    host = request.url.host
    request.extensions = {**request.extensions, "sni_hostname": host}
    request.url = request.url.copy_with(host=address)


class _PinnedTransport(httpx2.HTTPTransport):
    def handle_request(self, request: httpx2.Request) -> httpx2.Response:
        _pin(request, resolve_public_sync(request.url.host))
        return super().handle_request(request)


class _AsyncPinnedTransport(httpx2.AsyncHTTPTransport):
    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        _pin(request, await resolve_public(request.url.host))
        return await super().handle_async_request(request)


def _list_transport(private_ok: bool) -> httpx2.BaseTransport:
    return httpx2.HTTPTransport() if private_ok else _PinnedTransport()


def _list_client(private_ok: bool) -> httpx2.Client:
    return httpx2.Client(
        transport=_list_transport(private_ok), timeout=_LIST_TIMEOUT_SECONDS, trust_env=False
    )


def guarded_http_clients(*, private_ok: bool) -> dict:
    """The ``http_client`` / ``http_async_client`` pair for ChatOpenAI, or
    nothing where a private address is allowed anyway.

    ``trust_env=False`` so an ambient proxy cannot carry a user's key
    somewhere nobody chose.
    """
    if private_ok:
        return {}
    return {
        "http_client": httpx2.Client(transport=_PinnedTransport(), trust_env=False),
        "http_async_client": httpx2.AsyncClient(transport=_AsyncPinnedTransport(), trust_env=False),
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
