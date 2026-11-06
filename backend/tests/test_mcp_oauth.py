"""Signing in to an MCP server: discovery, registration, the code, the refresh.

Faked at the transport (``httpx2.MockTransport`` under ``guarded_client``), so
the real discovery order, request bodies and token parsing run. What matters
most here is what Duct sends: PKCE and the RFC 8707 ``resource`` on both legs,
a public client by default, and no registration at all where the server takes
a client metadata document. And what it refuses: metadata that names another
server as the resource or the issuer.
"""

from __future__ import annotations

import base64
import json
from urllib.parse import parse_qs, urlparse

import httpx2
import pytest

import service.mcp.http as mcp_http
from config import Configs
from service.mcp import oauth

SERVER = "https://mcp.vendor.test/mcp"
AUTH = "https://auth.vendor.test"
API = "https://api.duct.test"


@pytest.fixture
def cfg(monkeypatch):
    config = Configs(api_public_url=API, frontend_origin="https://app.duct.test")
    monkeypatch.setattr(oauth, "get_configs", lambda: config)
    return config


class Vendor:
    """A protected MCP server and its authorization server, over one transport."""

    def __init__(
        self,
        *,
        cimd: bool = False,
        s256: bool = True,
        prm: bool = True,
        rotate: bool = False,
        resource: str = SERVER,
        issuer: str = AUTH,
    ):
        self.cimd, self.s256, self.prm, self.rotate = cimd, s256, prm, rotate
        self.resource, self.issuer = resource, issuer
        self.requests: list[httpx2.Request] = []

    def handler(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        url = str(request.url)
        if request.method == "POST" and url == SERVER:
            header = 'Bearer scope="keywords:read"'
            if self.prm:
                header += ', resource_metadata="https://mcp.vendor.test/.well-known/oauth-protected-resource/mcp"'
            return httpx2.Response(401, headers={"WWW-Authenticate": header})
        if self.prm and url == "https://mcp.vendor.test/.well-known/oauth-protected-resource/mcp":
            return httpx2.Response(200, json={"resource": self.resource, "authorization_servers": [AUTH]})
        if url == f"{AUTH}/.well-known/oauth-authorization-server":
            return httpx2.Response(200, json={
                "issuer": self.issuer,
                "authorization_endpoint": f"{AUTH}/authorize",
                "token_endpoint": f"{AUTH}/token",
                "registration_endpoint": f"{AUTH}/register",
                "response_types_supported": ["code"],
                "code_challenge_methods_supported": ["S256"] if self.s256 else ["plain"],
                "client_id_metadata_document_supported": self.cimd,
            })
        if url == f"{AUTH}/register":
            return httpx2.Response(201, json={"client_id": "dcr-client", **json.loads(request.content)})
        if url == f"{AUTH}/token":
            form = parse_qs(request.content.decode())
            body = {"access_token": "at-1", "token_type": "Bearer", "expires_in": 3600}
            if form["grant_type"] == ["authorization_code"] or self.rotate:
                body["refresh_token"] = "rt-1" if form["grant_type"] == ["authorization_code"] else "rt-2"
            return httpx2.Response(200, json=body)
        return httpx2.Response(404)

    def install(self, monkeypatch) -> "Vendor":
        transport = httpx2.MockTransport(self.handler)
        monkeypatch.setattr(
            mcp_http, "guarded_client",
            lambda headers=None: httpx2.AsyncClient(transport=transport, headers=headers or {}),
        )
        return self

    def sent(self, path: str) -> httpx2.Request:
        return next(r for r in self.requests if r.url.path == path)


async def test_discovery_follows_the_resource_metadata_to_the_authorization_server(monkeypatch, cfg):
    Vendor().install(monkeypatch)
    plan = await oauth.discover(SERVER)

    assert plan.kind == oauth.AUTH_OAUTH
    assert plan.resource == SERVER
    assert plan.scope == "keywords:read"  # the 401's own scope wins
    assert plan.token_endpoint == f"{AUTH}/token"
    assert plan.registration_endpoint == f"{AUTH}/register"


def install_legacy(vendor: Vendor, monkeypatch) -> Vendor:
    """2025-03-26 servers put the authorization metadata at their own origin."""

    def legacy(request):
        if str(request.url) == "https://mcp.vendor.test/.well-known/oauth-authorization-server":
            return vendor.handler(httpx2.Request("GET", f"{AUTH}/.well-known/oauth-authorization-server"))
        return vendor.handler(request)

    transport = httpx2.MockTransport(legacy)
    monkeypatch.setattr(mcp_http, "guarded_client", lambda headers=None: httpx2.AsyncClient(transport=transport))
    return vendor


async def test_a_server_from_before_resource_metadata_is_still_found(monkeypatch, cfg):
    """A legacy server's metadata sits at its own origin and names it as the issuer."""
    install_legacy(Vendor(prm=False, issuer="https://mcp.vendor.test"), monkeypatch)
    plan = await oauth.discover(SERVER)

    assert plan.kind == oauth.AUTH_OAUTH
    assert plan.resource == SERVER


async def test_a_resource_the_metadata_names_elsewhere_ends_the_sign_in(monkeypatch, cfg):
    """The token would be minted for, and sent to, an address nobody typed."""
    Vendor(resource="https://other.vendor.test/mcp").install(monkeypatch)
    with pytest.raises(oauth.OAuthUnavailable):
        await oauth.discover(SERVER)


async def test_a_parent_resource_is_the_one_the_token_is_minted_for(monkeypatch, cfg):
    """One token for a server that serves /mcp and /mcp/v2: the SDK's rule."""
    Vendor(resource="https://mcp.vendor.test/").install(monkeypatch)
    plan = await oauth.discover(SERVER)

    assert plan.resource == "https://mcp.vendor.test/"


async def test_a_sign_in_found_under_one_issuer_may_not_claim_another(monkeypatch, cfg):
    """RFC 8414 §3.3: the issuer is the server the metadata was fetched for."""
    Vendor(issuer="https://other.vendor.test").install(monkeypatch)
    with pytest.raises(oauth.OAuthUnavailable):
        await oauth.discover(SERVER)

    # On the legacy path that server is the MCP server's own origin, so a
    # document there calling itself auth.vendor.test is the same mismatch.
    install_legacy(Vendor(prm=False, issuer=AUTH), monkeypatch)
    with pytest.raises(oauth.OAuthUnavailable):
        await oauth.discover(SERVER)


async def test_an_open_server_needs_nothing(monkeypatch, cfg):
    transport = httpx2.MockTransport(lambda r: httpx2.Response(200, json={"jsonrpc": "2.0", "id": 0, "result": {}}))
    monkeypatch.setattr(mcp_http, "guarded_client", lambda headers=None: httpx2.AsyncClient(transport=transport))
    assert (await oauth.discover(SERVER)).kind == oauth.AUTH_NONE


async def test_a_server_with_no_sign_in_to_find_asks_for_a_key(monkeypatch, cfg):
    transport = httpx2.MockTransport(
        lambda r: httpx2.Response(401) if r.method == "POST" else httpx2.Response(404)
    )
    monkeypatch.setattr(mcp_http, "guarded_client", lambda headers=None: httpx2.AsyncClient(transport=transport))
    with pytest.raises(oauth.OAuthUnavailable):
        await oauth.discover(SERVER)


async def test_a_sign_in_without_pkce_is_refused(monkeypatch, cfg):
    Vendor(s256=False).install(monkeypatch)
    with pytest.raises(oauth.OAuthUnavailable):
        await oauth.discover(SERVER)


async def test_a_metadata_document_server_gets_our_url_and_no_registration(monkeypatch, cfg):
    vendor = Vendor(cimd=True).install(monkeypatch)
    registration = await oauth.register(await oauth.discover(SERVER))

    assert registration.client_id == f"{API}{oauth.CLIENT_METADATA_PATH}"
    assert not any(r.url.path == "/register" for r in vendor.requests)
    # And the document behind that URL names the same id and our callback.
    document = oauth.client_metadata_document()
    assert document["client_id"] == registration.client_id
    assert document["redirect_uris"] == [f"{API}{oauth.CALLBACK_PATH}"]


async def test_otherwise_duct_registers_as_a_public_web_client(monkeypatch, cfg):
    vendor = Vendor().install(monkeypatch)
    registration = await oauth.register(await oauth.discover(SERVER))

    body = json.loads(vendor.sent("/register").content)
    assert registration.client_id == "dcr-client"
    assert registration.auth_method == "none"
    assert body["token_endpoint_auth_method"] == "none"
    assert body["application_type"] == "web"
    assert body["redirect_uris"] == [f"{API}{oauth.CALLBACK_PATH}"]


async def test_a_loopback_instance_registers_as_a_native_app_even_where_documents_work(monkeypatch):
    """Nobody else can fetch a document from a laptop."""
    config = Configs(api_public_url="http://localhost:8002")
    monkeypatch.setattr(oauth, "get_configs", lambda: config)
    vendor = Vendor(cimd=True).install(monkeypatch)
    await oauth.register(await oauth.discover(SERVER))

    assert json.loads(vendor.sent("/register").content)["application_type"] == "native"


async def test_authorize_and_exchange_carry_pkce_and_the_resource(monkeypatch, cfg):
    vendor = Vendor().install(monkeypatch)
    plan = await oauth.discover(SERVER)
    registration = await oauth.register(plan)
    verifier, challenge = oauth.new_pkce()

    query = parse_qs(urlparse(oauth.authorize_url(plan, registration, state="s1", challenge=challenge)).query)
    assert query["code_challenge_method"] == ["S256"]
    assert query["code_challenge"] == [challenge]
    assert query["resource"] == [SERVER]
    assert query["state"] == ["s1"]
    assert query["scope"] == ["keywords:read"]

    tokens = await oauth.exchange_code(
        token_endpoint=plan.token_endpoint, registration=registration,
        code="the-code", verifier=verifier, resource=plan.resource,
    )
    form = parse_qs(vendor.sent("/token").content.decode())
    assert form["code_verifier"] == [verifier]
    assert form["resource"] == [SERVER]
    assert form["client_id"] == ["dcr-client"]
    assert tokens.access_token == "at-1" and tokens.refresh_token == "rt-1"
    assert tokens.expires_at is not None and not tokens.expiring()


async def test_a_refresh_keeps_a_refresh_token_the_server_did_not_rotate(monkeypatch, cfg):
    Vendor(rotate=False).install(monkeypatch)
    fresh = await oauth.refresh(
        token_endpoint=f"{AUTH}/token", registration=oauth.ClientRegistration(client_id="c"),
        refresh_token="rt-1", resource=SERVER,
    )
    assert fresh.access_token == "at-1" and fresh.refresh_token == "rt-1"


async def test_a_secret_the_server_issued_goes_in_basic_auth(monkeypatch, cfg):
    vendor = Vendor().install(monkeypatch)
    await oauth.refresh(
        token_endpoint=f"{AUTH}/token",
        registration=oauth.ClientRegistration(client_id="c", client_secret="s", auth_method="client_secret_basic"),
        refresh_token="rt-1", resource=SERVER,
    )
    header = vendor.sent("/token").headers["Authorization"]
    assert header == "Basic " + base64.b64encode(b"c:s").decode()


async def test_a_refused_token_request_never_echoes_the_body(monkeypatch, cfg):
    transport = httpx2.MockTransport(lambda r: httpx2.Response(400, json={"error": "invalid_grant", "code": "the-code"}))
    monkeypatch.setattr(mcp_http, "guarded_client", lambda headers=None: httpx2.AsyncClient(transport=transport))
    with pytest.raises(oauth.OAuthFailed) as caught:
        await oauth.refresh(
            token_endpoint=f"{AUTH}/token", registration=oauth.ClientRegistration(client_id="c"),
            refresh_token="rt", resource=SERVER,
        )
    assert "the-code" not in str(caught.value)


@pytest.mark.parametrize("url", [
    "http://mcp.vendor.test/mcp",
    "https://localhost/mcp",
    "https://127.0.0.1/mcp",
    "https://169.254.169.254/latest",
    "https://user:pass@mcp.vendor.test/mcp",
    "not a url",
])
def test_only_public_https_addresses_are_accepted(url):
    with pytest.raises(mcp_http.UnsafeServerUrl):
        mcp_http.canonical_url(url)


def test_one_server_is_one_address():
    assert mcp_http.canonical_url(" https://MCP.Vendor.test:443/mcp#x ") == "https://mcp.vendor.test/mcp"
