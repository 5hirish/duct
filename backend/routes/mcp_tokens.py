"""The person's MCP tokens — GET/POST/DELETE /api/user/mcp-tokens.

Minting needs a signed-in session (a JWT), and an MCP token cannot mint
another: ``get_current_user`` reads sign-in JWTs only, so an agent holding a
token can never widen its own access or outlive a revocation by copying itself.
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
    mint,
    revoke,
)

router = APIRouter(tags=["mcp-tokens"])


class TokenIn(BaseModel):
    name: str = Field(min_length=1, max_length=NAME_MAX_CHARS)


class TokenOut(BaseModel):
    id: UUID
    name: str
    hint: str
    created_at: datetime
    expires_at: datetime
    last_used_at: datetime | None


class MintedTokenOut(TokenOut):
    # The only time the plaintext leaves the server.
    token: str


def _out(row: McpToken) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "hint": row.hint,
        "created_at": row.created_at,
        "expires_at": row.expires_at,
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
