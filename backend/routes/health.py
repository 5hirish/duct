"""Public health check."""

from __future__ import annotations

from fastapi import APIRouter

from routes.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse()
