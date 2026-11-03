"""Signing an outside agent in to Duct's MCP server: Duct as the authorization server.

The other side of ``service/mcp/oauth.py``. There Duct is the client signing
in to someone else's MCP server; here Claude Code, Codex, Cursor or OpenCode
signs in to Duct's, so adding Duct to an agent is one address and a browser
window rather than a token copied out of a settings page.

The MCP authorization spec fixes the shape, and every client follows it:

1. ``/mcp`` answers an unsigned call with a 401 whose ``WWW-Authenticate``
   names the protected-resource metadata (RFC 9728).
2. That document names this API as the authorization server, and its own
   metadata (RFC 8414) names the endpoints in ``routes/mcp_oauth.py``.
3. The client registers itself (RFC 7591) and opens the browser on
   ``/oauth/authorize``, which hands the person to the app's ``/authorize``
   page to allow it while signed in as themselves.
4. The client trades the code for tokens with PKCE (RFC 7636), bound to
   ``/mcp`` by the RFC 8707 ``resource``.

Three decisions worth knowing before changing any of it:

* **Registration is stateless.** Anyone may register, by design: a client
  this server has never heard of is the whole point. So registering writes
  no row: the ``client_id`` *is* the registration (its name and redirect
  addresses), signed with a key derived from ``JWT_SECRET``. Nothing for a
  script to fill or for us to prune, and an edited id fails the signature.
  The key is derived, never the secret itself, because ``get_current_user``
  accepts any HS256 JWT signed with the secret: a client id signed with it
  would be a session.
* **What the exchange mints is an MCP token.** A row in ``mcp_tokens`` like a
  pasted token's (``service/mcp_tokens.connect_agent``), so ``/mcp`` resolves
  both one way and revoking either is one button. It adds a refresh token,
  because a year-long bearer string in an agent's config is the thing browser
  sign-in exists to replace.
* **The backend renders no page.** ``/oauth/authorize`` checks the request,
  parks it (``service/auth_exchange``) and sends the browser to the app,
  which asks the person and calls back with their session. A request whose
  client or redirect fails the check goes to the app's error state, never to
  the address it named: following an unchecked redirect is an open redirect.

Not on the desktop sidecar: its address changes on every launch and its app
is ``tauri://``, which the system browser a sign-in opens cannot reach. A
sidecar keeps the pasted token.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode, urlsplit, urlunsplit

import jwt

from config import get_configs
from service.mcp_server.protocol import MCP_PATH

SCOPE = "mcp"

RESOURCE_METADATA_PATH = "/.well-known/oauth-protected-resource"
SERVER_METADATA_PATH = "/.well-known/oauth-authorization-server"
AUTHORIZE_PATH = "/oauth/authorize"
TOKEN_PATH = "/oauth/token"
REGISTER_PATH = "/oauth/register"
# The app's page that asks the person. Outside its signed-in shell, like an
# invitation, because the person may arrive signed out.
CONSENT_PAGE = "/authorize"

GRANT_AUTHORIZATION_CODE = "authorization_code"
GRANT_REFRESH = "refresh_token"
GRANT_TYPES = (GRANT_AUTHORIZATION_CODE, GRANT_REFRESH)

# Shown by a client that lists who it talks to.
DOCUMENTATION_URL = "https://getduct.ai/connect-agent"

# What the app's consent page shows as the place the browser returns to.
DESTINATION_DEVICE = "device"  # a loopback listener: the agent on this computer
DESTINATION_WEB = "web"  # https: a hosted client such as claude.ai
DESTINATION_APP = "app"  # a private-use scheme: a desktop app such as Cursor

# Room for a client that registers a loopback and a hosted address together,
# and a bound on what one registration makes us sign and later parse.
MAX_REDIRECT_URIS = 5
REDIRECT_URI_MAX_CHARS = 512
CLIENT_NAME_MAX_CHARS = 60

_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
# A browser runs these itself instead of handing them to an app, so an
# address on one is script or a local file, never an agent's callback.
_REFUSED_SCHEMES = frozenset({"javascript", "data", "file", "vbscript", "about", "blob", "ws", "wss", "ftp"})
_SCHEME = re.compile(r"^[a-z][a-z0-9+.-]*$")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]+")

_CLIENT_TYPE = "mcp_client"
_KEY_CONTEXT = b"duct mcp oauth client id v1"

# RFC 7636 §4.1: 43 to 128 characters from the unreserved set.
_VERIFIER = re.compile(r"^[A-Za-z0-9._~-]{43,128}$")


class RegistrationError(ValueError):
    """A registration refused, with its RFC 7591 §3.2.2 error code."""

    def __init__(self, code: str, description: str) -> None:
        super().__init__(description)
        self.code = code
        self.description = description


@dataclass(frozen=True)
class Client:
    client_id: str
    name: str
    redirect_uris: tuple[str, ...]


def available() -> bool:
    """Whether this instance signs agents in. Without a JWT secret there is
    nothing to sign a client id with; on a sidecar, see the module note."""
    configs = get_configs()
    return bool(configs.jwt_secret) and not configs.duct_local


def issuer() -> str:
    return get_configs().api_public_url.rstrip("/")


def resource() -> str:
    return issuer() + MCP_PATH


def resource_metadata_url() -> str:
    # RFC 9728 §3.1: the well-known path, then the resource's own path.
    return issuer() + RESOURCE_METADATA_PATH + MCP_PATH


def protected_resource_metadata() -> dict[str, Any]:
    return {
        "resource": resource(),
        "authorization_servers": [issuer()],
        "scopes_supported": [SCOPE],
        "bearer_methods_supported": ["header"],
        "resource_name": "Duct",
        "resource_documentation": DOCUMENTATION_URL,
    }


def authorization_server_metadata() -> dict[str, Any]:
    base = issuer()
    return {
        "issuer": base,
        "authorization_endpoint": base + AUTHORIZE_PATH,
        "token_endpoint": base + TOKEN_PATH,
        "registration_endpoint": base + REGISTER_PATH,
        "scopes_supported": [SCOPE],
        "response_types_supported": ["code"],
        "grant_types_supported": list(GRANT_TYPES),
        "token_endpoint_auth_methods_supported": ["none"],
        "code_challenge_methods_supported": ["S256"],
        # RFC 9207: the redirect back names us, so a client talking to two
        # authorization servers cannot be handed a code from the wrong one.
        "authorization_response_iss_parameter_supported": True,
        "service_documentation": DOCUMENTATION_URL,
    }


# -- registration ---------------------------------------------------------------

def _signing_key() -> bytes:
    secret = get_configs().jwt_secret
    return hmac.new(secret.encode(), _KEY_CONTEXT, hashlib.sha256).digest()


def _is_loopback(parts) -> bool:
    return parts.scheme == "http" and (parts.hostname or "") in _LOOPBACK_HOSTS


def _check_redirect_uri(uri: Any) -> str:
    if not isinstance(uri, str) or not uri or len(uri) > REDIRECT_URI_MAX_CHARS:
        raise RegistrationError("invalid_redirect_uri", "Each redirect URI must be a string under 512 characters.")
    try:
        parts = urlsplit(uri)
    except ValueError:
        raise RegistrationError("invalid_redirect_uri", f"Not a URI: {uri}")
    scheme = parts.scheme.lower()
    if parts.fragment or not _SCHEME.match(scheme) or scheme in _REFUSED_SCHEMES:
        raise RegistrationError("invalid_redirect_uri", f"Duct cannot send a sign-in to {uri}.")
    if scheme == "https" and not parts.hostname:
        raise RegistrationError("invalid_redirect_uri", f"Not a web address: {uri}")
    # Plain http only to this computer (RFC 8252 §7.3). Anywhere else it would
    # carry the code across the network in the clear.
    if scheme == "http" and not _is_loopback(parts):
        raise RegistrationError(
            "invalid_redirect_uri", f"Use https, or http to localhost or 127.0.0.1, not {uri}."
        )
    return uri


def _clean_name(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(_CONTROL.sub(" ", value).split())[:CLIENT_NAME_MAX_CHARS]


def register(metadata: dict[str, Any]) -> dict[str, Any]:
    """An RFC 7591 registration response for ``metadata``, or a
    ``RegistrationError``. The client id carries everything a later request
    is checked against, so there is nothing to store."""
    uris = metadata.get("redirect_uris")
    if not isinstance(uris, list) or not uris:
        raise RegistrationError("invalid_redirect_uri", "Register at least one redirect URI.")
    if len(uris) > MAX_REDIRECT_URIS:
        raise RegistrationError("invalid_redirect_uri", f"Register at most {MAX_REDIRECT_URIS} redirect URIs.")
    uris = [_check_redirect_uri(uri) for uri in uris]

    # A public client: it runs on someone's machine or in their browser and
    # cannot keep a secret, so PKCE is what proves it is the one that asked.
    auth_method = metadata.get("token_endpoint_auth_method") or "none"
    if auth_method != "none":
        raise RegistrationError(
            "invalid_client_metadata", "Duct registers public clients only: use token_endpoint_auth_method 'none'."
        )
    grant_types = metadata.get("grant_types") or [GRANT_AUTHORIZATION_CODE]
    if not isinstance(grant_types, list) or not set(grant_types) <= set(GRANT_TYPES):
        raise RegistrationError("invalid_client_metadata", "Supported grant types: authorization_code, refresh_token.")
    response_types = metadata.get("response_types") or ["code"]
    if response_types != ["code"]:
        raise RegistrationError("invalid_client_metadata", "The only supported response type is 'code'.")

    name = _clean_name(metadata.get("client_name"))
    # The nonce makes every registration its own client, so two installs of
    # one agent with identical metadata cannot use each other's refresh tokens.
    claims = {"typ": _CLIENT_TYPE, "jti": secrets.token_urlsafe(9), "name": name, "redirect_uris": uris}
    client_id = jwt.encode(claims, _signing_key(), "HS256")
    return {
        "client_id": client_id,
        "client_name": name,
        "redirect_uris": uris,
        "grant_types": grant_types,
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
        "scope": SCOPE,
    }


def client(client_id: str) -> Client | None:
    """The registration a client id carries, or None when it is not one this
    server signed."""
    if not client_id or not available():
        return None
    try:
        claims = jwt.decode(client_id, _signing_key(), algorithms=["HS256"])
    except jwt.InvalidTokenError:
        return None
    uris = claims.get("redirect_uris")
    if claims.get("typ") != _CLIENT_TYPE or not isinstance(uris, list):
        return None
    return Client(client_id=client_id, name=str(claims.get("name") or ""), redirect_uris=tuple(uris))


def redirect_allowed(registered: Client, uri: str) -> bool:
    """Whether ``uri`` is one the client registered. A loopback address
    matches on any port: a native app listens on whatever port the OS gives it
    for each sign-in, after it registered (RFC 8252 §7.3)."""
    if uri in registered.redirect_uris:
        return True
    try:
        asked = urlsplit(uri)
    except ValueError:
        return False
    if not _is_loopback(asked) or asked.fragment:
        return False
    for known in registered.redirect_uris:
        parts = urlsplit(known)
        if _is_loopback(parts) and (parts.hostname, parts.path, parts.query) == (asked.hostname, asked.path, asked.query):
            return True
    return False


def destination(uri: str) -> tuple[str, str]:
    """Where the browser goes after the person allows, as the consent page
    shows it: the kind of place and a name for it."""
    parts = urlsplit(uri)
    if _is_loopback(parts):
        return DESTINATION_DEVICE, parts.hostname or ""
    if parts.scheme == "https":
        return DESTINATION_WEB, parts.hostname or ""
    return DESTINATION_APP, parts.scheme


# -- the authorization request ---------------------------------------------------

def resource_allowed(value: str) -> bool:
    """RFC 8707: a token for this server, or for this API as a whole, which
    protects nothing else. Absent is allowed; most clients send it."""
    if not value:
        return True
    return value.rstrip("/") in (resource(), issuer())


def pkce_matches(verifier: str, challenge: str) -> bool:
    if not _VERIFIER.match(verifier or ""):
        return False
    digest = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return hmac.compare_digest(digest, challenge)


def with_query(uri: str, **params: str) -> str:
    """``uri`` with ``params`` appended, keeping any query it already has.
    Empty values are left out: an absent ``state`` stays absent."""
    parts = urlsplit(uri)
    extra = urlencode({key: value for key, value in params.items() if value})
    query = f"{parts.query}&{extra}" if parts.query and extra else parts.query or extra
    return urlunsplit(parts._replace(query=query))


def consent_page(**params: str) -> str:
    return with_query(get_configs().frontend_origin.rstrip("/") + CONSENT_PAGE, **params)
