"""Signing in to an MCP server, as Duct: discovery, registration, code, refresh.

The MCP authorization spec makes the server a protected resource and leaves the
client to find its authorization server, so connecting one is four steps, each
of which is a request to an address the server chose (hence ``mcp_http``):

1. **Probe.** An unauthenticated ``initialize``. A 401 means sign-in; its
   ``WWW-Authenticate`` header may point at the resource metadata.
2. **Discover.** Protected-resource metadata (RFC 9728) names the
   authorization server; its metadata (RFC 8414, or OIDC discovery) names the
   endpoints. The reference SDK builds the candidate URLs in spec order,
   including the 2025-03-26 fallback for servers that predate the split.
3. **Register.** Duct has no account with any of these vendors, so it either
   presents a client metadata document (the ``client_id`` is a URL Duct
   serves, nothing to register) where the server says it takes one, or
   registers dynamically. A server offering neither cannot be signed in to by
   a client it has never heard of, and the user pastes a key instead.
4. **Authorize and exchange.** Authorization code with PKCE, and the RFC 8707
   ``resource`` on both legs so the token is minted for this server alone.

The hosted flow is a browser redirect between two of our requests, so nothing
here holds a callback open the way the SDK's own ``OAuthClientProvider`` does;
the route parks what the second request needs (``service/auth_exchange``).
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass
from urllib.parse import urlencode, urlsplit

import httpx
from mcp.client.auth import PKCEParameters
from mcp.client.auth.utils import (
    build_oauth_authorization_server_metadata_discovery_urls,
    build_protected_resource_metadata_discovery_urls,
    extract_resource_metadata_from_www_auth,
    extract_scope_from_www_auth,
    get_client_metadata_scopes,
    is_valid_client_metadata_url,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthMetadata, OAuthToken, ProtectedResourceMetadata
from mcp.types import LATEST_PROTOCOL_VERSION
from pydantic import ValidationError

from config import get_configs
from service.crawl.fetcher import SSRFError
from service.mcp import http as mcp_http

logger = logging.getLogger(__name__)

CLIENT_NAME = "Duct"
CLIENT_URI = "https://getduct.ai"
CLIENT_VERSION = "1"

# Paths under the API's public address. The callback is what every
# registration names; the metadata document's URL *is* the client id.
# Not under /auth/connectors/{connector_id}/…, whose path parameter would
# claim "mcp" first and hand it to the Google and GitHub flows.
CALLBACK_PATH = "/auth/mcp/callback"
CLIENT_METADATA_PATH = "/auth/mcp/client-metadata.json"

AUTH_NONE = "none"
AUTH_OAUTH = "oauth"
AUTH_KEY = "key"

# Refresh this long before the server says a token dies, so a call that
# starts with a live token does not finish with a dead one.
REFRESH_MARGIN_SECONDS = 60

_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


class OAuthUnavailable(Exception):
    """The server wants a sign-in Duct cannot start. The user pastes a key."""


class OAuthFailed(Exception):
    """A step of the sign-in failed. The message is safe to show and to log."""


@dataclass(frozen=True)
class AuthPlan:
    """What a server needs before it will talk, and where to get it."""

    kind: str
    resource: str = ""
    scope: str = ""
    issuer: str = ""
    authorization_endpoint: str = ""
    token_endpoint: str = ""
    registration_endpoint: str = ""
    accepts_metadata_document: bool = False


@dataclass(frozen=True)
class ClientRegistration:
    client_id: str
    client_secret: str = ""
    # How the token endpoint authenticates us: "none" for a public client,
    # or whatever the server decided when it issued a secret anyway.
    auth_method: str = "none"


@dataclass(frozen=True)
class Tokens:
    access_token: str
    refresh_token: str = ""
    expires_at: float | None = None  # epoch seconds; None when the server did not say
    scope: str = ""

    def as_dict(self) -> dict:
        return asdict(self)

    def expiring(self, now: float | None = None) -> bool:
        if self.expires_at is None:
            return False
        return (now or time.time()) >= self.expires_at - REFRESH_MARGIN_SECONDS


# ---------------------------------------------------------------------------
# Our own addresses
# ---------------------------------------------------------------------------


def redirect_uri() -> str:
    return f"{get_configs().api_public_url}{CALLBACK_PATH}"


def client_metadata_url() -> str:
    return f"{get_configs().api_public_url}{CLIENT_METADATA_PATH}"


def _loopback() -> bool:
    return (urlsplit(get_configs().api_public_url).hostname or "") in _LOOPBACK_HOSTS


def client_metadata_document() -> dict:
    """The JSON an authorization server fetches when our ``client_id`` is its URL.

    Public by design: it names us and where codes may be sent, nothing more.
    A loopback address cannot be fetched by anyone else, so a local or
    self-hosted instance falls back to registration (``register``).
    """
    return {
        "client_id": client_metadata_url(),
        "client_name": CLIENT_NAME,
        "client_uri": CLIENT_URI,
        "redirect_uris": [redirect_uri()],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
    }


# ---------------------------------------------------------------------------
# 1–2. Probe and discover
# ---------------------------------------------------------------------------


def _initialize_probe() -> dict:
    return {
        "jsonrpc": "2.0",
        "id": 0,
        "method": "initialize",
        "params": {
            "protocolVersion": LATEST_PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": CLIENT_NAME, "version": CLIENT_VERSION},
        },
    }


async def _first_json(client: httpx.AsyncClient, urls: list[str], model: type) -> object | None:
    """The first candidate URL that answers with a document ``model`` accepts."""
    for url in urls:
        try:
            resp = await client.get(url, headers={"MCP-Protocol-Version": LATEST_PROTOCOL_VERSION})
        except httpx.HTTPError:
            # One candidate down is why there is a list. A refused address
            # (SSRFError) is not an HTTPError and ends the discovery instead.
            continue
        if resp.status_code != httpx.codes.OK:
            continue
        try:
            return model.model_validate_json(resp.content)
        except ValidationError:
            continue
    return None


async def discover(url: str) -> AuthPlan:
    """Ask the server what it needs. ``url`` is already ``canonical_url``'d.

    Raises ``OAuthUnavailable`` when the server wants credentials but publishes
    no authorization server, and ``OAuthFailed`` when it cannot be reached.
    """
    try:
        async with mcp_http.guarded_client() as client:
            probe = await client.post(
                url,
                json=_initialize_probe(),
                headers={
                    "Accept": "application/json, text/event-stream",
                    "MCP-Protocol-Version": LATEST_PROTOCOL_VERSION,
                },
            )
            if probe.status_code == httpx.codes.FORBIDDEN:
                raise OAuthUnavailable("The server refused an unauthenticated client.")
            if probe.status_code >= 500:
                raise OAuthFailed(f"The server answered {probe.status_code}.")
            if probe.status_code != httpx.codes.UNAUTHORIZED:
                return AuthPlan(kind=AUTH_NONE)

            resource_meta = await _first_json(
                client,
                build_protected_resource_metadata_discovery_urls(
                    extract_resource_metadata_from_www_auth(probe), url
                ),
                ProtectedResourceMetadata,
            )
            auth_server = (
                str(resource_meta.authorization_servers[0])
                if resource_meta and resource_meta.authorization_servers
                else None
            )
            server_meta = await _first_json(
                client,
                build_oauth_authorization_server_metadata_discovery_urls(auth_server, url),
                OAuthMetadata,
            )
    except SSRFError as exc:
        raise OAuthFailed("The server, or the sign-in it points to, is not on the public internet.") from exc
    except httpx.HTTPError as exc:
        raise OAuthFailed(f"The server could not be reached ({type(exc).__name__}).") from exc

    if server_meta is None:
        raise OAuthUnavailable("The server asks for credentials but publishes no sign-in.")
    methods = server_meta.code_challenge_methods_supported
    if methods is not None and "S256" not in methods:
        # PKCE is not optional in MCP, and a server without S256 is one whose
        # codes anybody who sees the redirect could redeem.
        raise OAuthUnavailable("The server's sign-in does not support PKCE.")

    resource = str(resource_meta.resource) if resource_meta and resource_meta.resource else url
    return AuthPlan(
        kind=AUTH_OAUTH,
        resource=resource,
        # The spec's order: the 401's scope, else the resource's, else none.
        # Not the authorization server's whole list, which the SDK would fall
        # back to and which can carry every write scope the vendor has.
        scope=get_client_metadata_scopes(extract_scope_from_www_auth(probe), resource_meta) or "",
        issuer=str(server_meta.issuer),
        authorization_endpoint=str(server_meta.authorization_endpoint),
        token_endpoint=str(server_meta.token_endpoint),
        registration_endpoint=str(server_meta.registration_endpoint or ""),
        accepts_metadata_document=bool(server_meta.client_id_metadata_document_supported),
    )


# ---------------------------------------------------------------------------
# 3. Register
# ---------------------------------------------------------------------------


async def register(plan: AuthPlan) -> ClientRegistration:
    """Who Duct is to this authorization server.

    A client metadata document first, because it registers nothing: the
    server fetches our document and the id is its URL. Dynamic registration
    otherwise, a fresh public client per connect, which is what the spec's
    DCR path amounts to for a client with no prior relationship.
    """
    metadata_url = client_metadata_url()
    if plan.accepts_metadata_document and not _loopback() and is_valid_client_metadata_url(metadata_url):
        return ClientRegistration(client_id=metadata_url)
    if not plan.registration_endpoint:
        raise OAuthUnavailable("The server's sign-in does not register new clients.")

    body = {
        "client_name": CLIENT_NAME,
        "client_uri": CLIENT_URI,
        "redirect_uris": [redirect_uri()],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
        # Required by the current spec for a registering client; a loopback
        # redirect is a native app's, anything else a web app's.
        "application_type": "native" if _loopback() else "web",
    }
    if plan.scope:
        body["scope"] = plan.scope
    try:
        async with mcp_http.guarded_client() as client:
            resp = await client.post(plan.registration_endpoint, json=body)
    except (SSRFError, httpx.HTTPError) as exc:
        raise OAuthFailed(f"Registering with the server's sign-in failed ({type(exc).__name__}).") from exc
    if resp.status_code not in (httpx.codes.OK, httpx.codes.CREATED):
        raise OAuthUnavailable(f"The server's sign-in refused to register Duct ({resp.status_code}).")
    try:
        info = OAuthClientInformationFull.model_validate_json(resp.content)
    except ValidationError as exc:
        raise OAuthFailed("The server's sign-in answered registration with something unreadable.") from exc
    secret = info.client_secret or ""
    # RFC 7591's default when a server issues a secret and names no method.
    method = info.token_endpoint_auth_method or ("client_secret_basic" if secret else "none")
    return ClientRegistration(client_id=info.client_id or "", client_secret=secret, auth_method=method)


# ---------------------------------------------------------------------------
# 4. Authorize, exchange, refresh
# ---------------------------------------------------------------------------


def new_pkce() -> tuple[str, str]:
    """(verifier, S256 challenge)."""
    params = PKCEParameters.generate()
    return params.code_verifier, params.code_challenge


def authorize_url(plan: AuthPlan, registration: ClientRegistration, *, state: str, challenge: str) -> str:
    params = {
        "response_type": "code",
        "client_id": registration.client_id,
        "redirect_uri": redirect_uri(),
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "resource": plan.resource,
    }
    if plan.scope:
        params["scope"] = plan.scope
    joiner = "&" if "?" in plan.authorization_endpoint else "?"
    return f"{plan.authorization_endpoint}{joiner}{urlencode(params)}"


async def _token_request(
    *,
    token_endpoint: str,
    registration: ClientRegistration,
    data: dict[str, str],
) -> Tokens:
    form = {**data, "client_id": registration.client_id}
    auth: httpx.Auth | None = None
    if registration.client_secret:
        if registration.auth_method == "client_secret_post":
            form["client_secret"] = registration.client_secret
        else:
            auth = httpx.BasicAuth(registration.client_id, registration.client_secret)
    try:
        async with mcp_http.guarded_client() as client:
            resp = await client.post(token_endpoint, data=form, auth=auth)
    except (SSRFError, httpx.HTTPError) as exc:
        raise OAuthFailed(f"The server's sign-in could not be reached ({type(exc).__name__}).") from exc
    if resp.status_code != httpx.codes.OK:
        # The body may echo the code or a token back; log the status only.
        logger.warning("mcp oauth: token endpoint answered %s", resp.status_code)
        raise OAuthFailed(f"The server's sign-in refused the request ({resp.status_code}).")
    try:
        token = OAuthToken.model_validate_json(resp.content)
    except ValidationError as exc:
        raise OAuthFailed("The server's sign-in answered with something unreadable.") from exc
    expires_at = time.time() + token.expires_in if token.expires_in else None
    return Tokens(
        access_token=token.access_token,
        refresh_token=token.refresh_token or "",
        expires_at=expires_at,
        scope=token.scope or "",
    )


async def exchange_code(
    *,
    token_endpoint: str,
    registration: ClientRegistration,
    code: str,
    verifier: str,
    resource: str,
) -> Tokens:
    return await _token_request(
        token_endpoint=token_endpoint,
        registration=registration,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri(),
            "code_verifier": verifier,
            "resource": resource,
        },
    )


async def refresh(
    *,
    token_endpoint: str,
    registration: ClientRegistration,
    refresh_token: str,
    resource: str,
) -> Tokens:
    """A fresh access token. Keeps the old refresh token when the server
    does not rotate it, which most do not."""
    fresh = await _token_request(
        token_endpoint=token_endpoint,
        registration=registration,
        data={"grant_type": "refresh_token", "refresh_token": refresh_token, "resource": resource},
    )
    if fresh.refresh_token:
        return fresh
    return Tokens(fresh.access_token, refresh_token, fresh.expires_at, fresh.scope)
