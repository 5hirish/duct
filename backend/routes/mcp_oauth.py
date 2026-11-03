"""Browser sign-in for Duct's MCP server: Duct as the OAuth authorization server.

``router`` is what an agent calls: discovery, registration, the authorize
redirect and the token exchange. None of it is under ``/api`` or behind
``validate_api_key``, because an agent is not the Duct app, and none of it
reads a session: the browser that opens ``/oauth/authorize`` carries no
header, and the agent that calls ``/oauth/token`` has none to send.

``consent_router`` is what the app's ``/authorize`` page calls, behind the
app's key: read the parked request, then allow it (as the signed-in person)
or decline it. ``service/mcp_server/oauth.py`` says why it is shaped this way.

Errors follow the specs the clients parse: a token or registration error is
``{"error", "error_description"}`` (RFC 6749 §5.2, RFC 7591 §3.2.2), never
FastAPI's ``detail``.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel
from sqlmodel import Session
from starlette.status import HTTP_403_FORBIDDEN, HTTP_404_NOT_FOUND

from db.session import get_session
from models.auth import User
from service.auth import get_current_user
from service.auth_exchange import (
    consume_agent_code,
    consume_agent_request,
    peek_agent_request,
    store_agent_code,
    store_agent_request,
)
from service.mcp_server import oauth
from service.mcp_server.protocol import MCP_PATH
from service.mcp_tokens import ACCESS_LIFETIME, connect_agent, renew_agent
from service.ratelimit import RateLimit, client_address
from service.user_store import is_guest_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["mcp"])
consent_router = APIRouter(tags=["mcp"])

# Per address. Registration is free and stateless, but each one is a
# signature we compute and a client id someone can hand to a person.
_REGISTER_LIMIT = RateLimit(limit=20, window_seconds=3600.0)
# Each authorize parks a request in memory for ten minutes.
_AUTHORIZE_LIMIT = RateLimit(limit=30, window_seconds=600.0)
# Renewals are hourly per agent; anything near this is a loop or a guess.
_TOKEN_LIMIT = RateLimit(limit=60, window_seconds=60.0)

# RFC 6749 §5.1: a response that carries a token is never cached.
_NO_STORE = {"Cache-Control": "no-store", "Pragma": "no-cache"}

# What the consent page is told when the request could not be checked.
CONSENT_ERROR_INVALID = "invalid_request"

_EXPIRED = "This sign-in request has expired. Start again from your agent."


def _oauth_error(code: str, description: str, status: int = 400) -> JSONResponse:
    return JSONResponse({"error": code, "error_description": description}, status_code=status, headers=_NO_STORE)


def _redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=302, headers={"Cache-Control": "no-store"})


def _require_available() -> None:
    if not oauth.available():
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Not Found")


# -- discovery ------------------------------------------------------------------

def _metadata(document: dict[str, Any]) -> JSONResponse:
    return JSONResponse(document, headers={"Cache-Control": "public, max-age=3600"})


# Both spellings of RFC 9728's address: the path-suffixed one the spec builds
# from ``/mcp``, and the bare one older clients try first.
@router.get(oauth.RESOURCE_METADATA_PATH + MCP_PATH)
@router.get(oauth.RESOURCE_METADATA_PATH)
def protected_resource_metadata() -> JSONResponse:
    _require_available()
    return _metadata(oauth.protected_resource_metadata())


@router.get(oauth.SERVER_METADATA_PATH)
def authorization_server_metadata() -> JSONResponse:
    _require_available()
    return _metadata(oauth.authorization_server_metadata())


# -- registration -----------------------------------------------------------------

@router.post(oauth.REGISTER_PATH)
async def register_client(request: Request) -> JSONResponse:
    _require_available()
    _REGISTER_LIMIT.enforce(client_address(request), "Too many registrations. Try again later.")
    try:
        metadata = await request.json()
    except ValueError:
        return _oauth_error("invalid_client_metadata", "Send the registration as a JSON object.")
    if not isinstance(metadata, dict):
        return _oauth_error("invalid_client_metadata", "Send the registration as a JSON object.")
    try:
        registration = oauth.register(metadata)
    except oauth.RegistrationError as exc:
        return _oauth_error(exc.code, exc.description)
    return JSONResponse(registration, status_code=201, headers=_NO_STORE)


# -- authorize --------------------------------------------------------------------

@router.get(oauth.AUTHORIZE_PATH)
def authorize(
    request: Request,
    response_type: str = Query(default=""),
    client_id: str = Query(default=""),
    redirect_uri: str = Query(default=""),
    code_challenge: str = Query(default=""),
    code_challenge_method: str = Query(default=""),
    state: str = Query(default=""),
    resource: str = Query(default=""),
) -> RedirectResponse:
    _require_available()
    _AUTHORIZE_LIMIT.enforce(client_address(request), "Too many sign-in attempts. Try again shortly.")

    # Until the client and its redirect check out, nothing goes back to the
    # address the request named (RFC 6749 §4.1.2.1).
    client = oauth.client(client_id)
    if client is None or not oauth.redirect_allowed(client, redirect_uri):
        return _redirect(oauth.consent_page(error=CONSENT_ERROR_INVALID))

    def back(error: str, description: str) -> RedirectResponse:
        return _redirect(oauth.with_query(
            redirect_uri, error=error, error_description=description, state=state, iss=oauth.issuer(),
        ))

    if response_type != "code":
        return back("unsupported_response_type", "Duct supports response_type=code only.")
    # PKCE is what ties the code to the client that asked; a public client
    # has nothing else (OAuth 2.1 §7.5.1).
    if not code_challenge or code_challenge_method != "S256":
        return back("invalid_request", "Send a PKCE code_challenge with code_challenge_method=S256.")
    if not oauth.resource_allowed(resource):
        return back("invalid_target", f"Duct issues tokens for {oauth.resource()} only.")

    # Scope is not carried: there is one, and the token response names it.
    request_code = store_agent_request({
        "client_id": client_id,
        "client_name": client.name,
        "redirect_uri": redirect_uri,
        "code_challenge": code_challenge,
        "state": state,
    })
    return _redirect(oauth.consent_page(request=request_code))


# -- token ------------------------------------------------------------------------

def _tokens(access: str, refresh: str) -> JSONResponse:
    return JSONResponse(
        {
            "access_token": access,
            "token_type": "Bearer",
            "expires_in": int(ACCESS_LIFETIME.total_seconds()),
            "refresh_token": refresh,
            "scope": oauth.SCOPE,
        },
        headers=_NO_STORE,
    )


def _exchange_code(
    session: Session, *, code: str, client_id: str, redirect_uri: str, code_verifier: str, resource: str
) -> JSONResponse:
    # Spent before it is checked, so a wrong verifier cannot be retried
    # against the same code (RFC 6749 §4.1.2).
    grant = consume_agent_code(code) if code else None
    if grant is None:
        return _oauth_error("invalid_grant", "That code is unknown, used or expired. Sign in again.")
    client = oauth.client(client_id)
    if client is None or grant["client_id"] != client_id:
        return _oauth_error("invalid_grant", "That code was issued to another client.")
    if redirect_uri != grant["redirect_uri"]:
        return _oauth_error("invalid_grant", "redirect_uri does not match the one the code was issued for.")
    if not oauth.pkce_matches(code_verifier, grant["code_challenge"]):
        return _oauth_error("invalid_grant", "The code_verifier does not match the code_challenge.")
    if not oauth.resource_allowed(resource):
        return _oauth_error("invalid_target", f"Duct issues tokens for {oauth.resource()} only.")
    user = session.get(User, UUID(grant["user_id"]))
    if user is None:
        return _oauth_error("invalid_grant", "The account that allowed this sign-in no longer exists.")
    _, access, refresh = connect_agent(user, client_id=client_id, client_name=client.name, session=session)
    return _tokens(access, refresh)


@router.post(oauth.TOKEN_PATH)
def token(
    request: Request,
    grant_type: str = Form(default=""),
    code: str = Form(default=""),
    redirect_uri: str = Form(default=""),
    client_id: str = Form(default=""),
    code_verifier: str = Form(default=""),
    refresh_token: str = Form(default=""),
    resource: str = Form(default=""),
    session: Session = Depends(get_session),
) -> JSONResponse:
    _require_available()
    _TOKEN_LIMIT.enforce(client_address(request), "Too many token requests. Slow down and try again shortly.")
    if grant_type == oauth.GRANT_AUTHORIZATION_CODE:
        return _exchange_code(
            session, code=code, client_id=client_id, redirect_uri=redirect_uri,
            code_verifier=code_verifier, resource=resource,
        )
    if grant_type == oauth.GRANT_REFRESH:
        if not oauth.resource_allowed(resource):
            return _oauth_error("invalid_target", f"Duct issues tokens for {oauth.resource()} only.")
        renewed = renew_agent(refresh_token, client_id, session) if oauth.client(client_id) else None
        if renewed is None:
            return _oauth_error("invalid_grant", "That refresh token is unknown, used, revoked or expired. Sign in again.")
        _, access, refresh = renewed
        return _tokens(access, refresh)
    return _oauth_error("unsupported_grant_type", "Use authorization_code or refresh_token.")


# -- the consent page's calls -------------------------------------------------------

class ConsentRequestOut(BaseModel):
    # Whatever the client registered as: unverified, and the page says so.
    client_name: str
    # Where the browser goes after Allow: this device, a website or an app.
    destination: str
    destination_name: str


class ConsentAnswerOut(BaseModel):
    redirect_to: str


@consent_router.get("/{request_code}")
def describe_request(request_code: str) -> ConsentRequestOut:
    parked = peek_agent_request(request_code)
    if parked is None:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=_EXPIRED)
    kind, name = oauth.destination(parked["redirect_uri"])
    return ConsentRequestOut(client_name=parked["client_name"], destination=kind, destination_name=name)


@consent_router.post("/{request_code}/approve")
def approve_request(request_code: str, user: User = Depends(get_current_user)) -> ConsentAnswerOut:
    # A guest is an install, not a person; what it connected would be lost
    # when it signs in properly, and nobody could find it to revoke it.
    if is_guest_user(user):
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="Sign in to Duct to connect an agent.")
    parked = consume_agent_request(request_code)
    if parked is None:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=_EXPIRED)
    code = store_agent_code({
        "user_id": str(user.id),
        "client_id": parked["client_id"],
        "redirect_uri": parked["redirect_uri"],
        "code_challenge": parked["code_challenge"],
    })
    logger.info("mcp sign-in: %s allowed %r", user.id, parked["client_name"])
    return ConsentAnswerOut(
        redirect_to=oauth.with_query(parked["redirect_uri"], code=code, state=parked["state"], iss=oauth.issuer())
    )


@consent_router.post("/{request_code}/deny")
def deny_request(request_code: str) -> ConsentAnswerOut:
    # No session needed: declining grants nothing, and the code is the proof
    # that this redirect address was checked.
    parked = consume_agent_request(request_code)
    if parked is None:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=_EXPIRED)
    return ConsentAnswerOut(redirect_to=oauth.with_query(
        parked["redirect_uri"], error="access_denied", error_description="The person declined.",
        state=parked["state"], iss=oauth.issuer(),
    ))
