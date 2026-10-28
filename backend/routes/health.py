"""Public health check."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from fastapi import APIRouter

from config import get_configs
from routes.schemas import HealthResponse, RootLinks, RootResponse

router = APIRouter(tags=["health"])


def _package_version() -> str:
    try:
        return version("duct-backend")
    except PackageNotFoundError:
        return "0.1.0"


@router.get("/", response_model=RootResponse, response_model_exclude_none=True)
def root() -> RootResponse:
    cfg = get_configs()
    links = (
        RootLinks(openapi="/openapi.json", docs="/docs")
        if cfg.expose_openapi_docs
        else RootLinks()
    )
    return RootResponse(version=_package_version(), links=links)


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse()
