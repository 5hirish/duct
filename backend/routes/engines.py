"""Inference-engine availability, and what the chosen model can be asked to do.

Reports, per engine, whether it is usable (`active`), needs credentials it can
still recover from (`needs_auth`, OAuth-capable engines only), or is unusable
(`inactive`). The frontend dialog disables non-active rows and shows setup help
for `needs_auth`.

`/engines/thinking` answers the second question the composer needs: which
thinking levels this engine's model actually accepts, already translated into
Duct's four rungs. It is computed here rather than mirrored in JavaScript
because a picker offering a rung the API rejects is worse than no picker.
"""

from __future__ import annotations

from fastapi import APIRouter

from agents.engines import (
    ENGINE_DEFAULT_PROVIDER,
    ENGINE_SUPPORTS_OAUTH,
    PROVIDER_CONFIG_ATTR,
    Engine,
    resolve_engine_model,
)
from agents.thinking import describe_model
from config import claude_oauth_available, get_configs
from routes.schemas import EngineStatus, EngineStatusResponse

router = APIRouter(tags=["engines"])

# Shown for v3 when no Claude credentials are configured. Leads with the
# compliant production method (Console API key); the subscription token is a
# local/self-hosted-operator convenience only.
_V3_NEEDS_AUTH_DETAIL = (
    "Set ANTHROPIC_API_KEY (from the Claude Console) to use this engine. "
    "For local/self-hosted use you can instead run `claude setup-token` and set "
    "CLAUDE_CODE_OAUTH_TOKEN."
)


def _engine_status(engine: Engine, cfg) -> EngineStatus:
    default_provider = ENGINE_DEFAULT_PROVIDER[engine]
    has_api_key = bool(getattr(cfg, PROVIDER_CONFIG_ATTR[default_provider], ""))
    supports_oauth = ENGINE_SUPPORTS_OAUTH[engine]

    if has_api_key:
        return EngineStatus(
            key=engine.value,
            status="active",
            auth_method="api_key",
            supports_oauth=supports_oauth,
        )

    if supports_oauth and claude_oauth_available():
        return EngineStatus(
            key=engine.value,
            status="active",
            auth_method="oauth",
            supports_oauth=supports_oauth,
        )

    if supports_oauth:
        return EngineStatus(
            key=engine.value,
            status="needs_auth",
            supports_oauth=True,
            detail=_V3_NEEDS_AUTH_DETAIL,
        )

    return EngineStatus(
        key=engine.value,
        status="inactive",
        supports_oauth=False,
        detail="No API key configured for this engine.",
    )


@router.get("/engines/status", response_model=EngineStatusResponse)
def engines_status() -> EngineStatusResponse:
    cfg = get_configs()
    return EngineStatusResponse(engines=[_engine_status(e, cfg) for e in Engine])


@router.get("/engines/thinking")
def engine_thinking(engine: str = "") -> dict:
    """The thinking levels available on the model this engine would use.

    Resolved server-side because the model is: the engine's default provider
    and its default model are config, not something the browser knows. An
    unknown engine falls back to the default rather than 404-ing — the picker
    degrading to "no dial" is a better failure than the composer erroring.
    """
    try:
        resolved = Engine(engine) if engine else Engine.V1
    except ValueError:
        resolved = Engine.V1
    provider = ENGINE_DEFAULT_PROVIDER[resolved]
    model = resolve_engine_model(resolved, provider)
    return {"engine": resolved.value, **describe_model(model)}
