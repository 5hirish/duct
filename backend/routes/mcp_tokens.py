"""The person's MCP tokens and connected agents — GET/POST/DELETE /api/user/mcp-tokens.

Minting needs a signed-in session (a JWT), and an MCP token cannot mint
another: ``get_current_user`` reads sign-in JWTs only, so an agent holding a
token can never widen its own access or outlive a revocation by copying itself.
The list carries agents that signed in through the browser too
(``kind: "agent"``), and DELETE disconnects one the same way it revokes a
token.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session
from starlette.status import HTTP_409_CONFLICT

from db.session import get_session
from models.auth import McpToken, User
from service.auth import get_current_user
from service.mcp_tokens import (
    MAX_ACTIVE_TOKENS,
    NAME_MAX_CHARS,
    TokenLimitReached,
    active_tokens,
    is_connected_agent,
    mint,
    revoke,
)

router = APIRouter(tags=["mcp-tokens"])

KIND_TOKEN = "token"
KIND_AGENT = "agent"


class TokenIn(BaseModel):
    name: str = Field(min_length=1, max_length=NAME_MAX_CHARS)


class TokenOut(BaseModel):
    id: UUID
    # "token" was pasted into the agent; "agent" signed in through the browser.
    kind: str
    name: str
    hint: str
    created_at: datetime
    # For an agent, when the connection lapses unless it renews first.
    expires_at: datetime
    last_used_at: datetime | None


class MintedTokenOut(TokenOut):
    # The only time the plaintext leaves the server.
    token: str


def _out(row: McpToken) -> dict:
    agent = is_connected_agent(row)
    return {
        "id": row.id,
        "kind": KIND_AGENT if agent else KIND_TOKEN,
        "name": row.name,
        # An agent's access token changes every hour; its hint names nothing.
        "hint": "" if agent else row.hint,
        "created_at": row.created_at,
        "expires_at": row.refresh_expires_at if agent else row.expires_at,
        "last_used_at": row.last_used_at,
    }


@router.get("")
def list_tokens(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[TokenOut]:
    return [TokenOut(**_out(row)) for row in active_tokens(user, session)]


@router.post("", status_code=201)
def create_token(
    body: TokenIn,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> MintedTokenOut:
    if not body.name.strip():
        raise HTTPException(status_code=422, detail="Give the token a name.")
    try:
        row, raw = mint(user, body.name, session)
    except TokenLimitReached:
        raise HTTPException(
            status_code=HTTP_409_CONFLICT,
            detail=f"You have {MAX_ACTIVE_TOKENS} tokens already. Revoke one you no longer use first.",
        )
    return MintedTokenOut(**_out(row), token=raw)


@router.delete("/{token_id}", status_code=204)
def revoke_token(
    token_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> None:
    if not revoke(user, token_id, session):
        raise HTTPException(status_code=404, detail="Token not found")
