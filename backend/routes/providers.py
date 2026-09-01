"""Which providers this request can actually reach, and what models they offer.

Two reads, both answering questions the browser cannot answer for itself.

``/providers/status`` is the important one. A bring-your-own key lives in the
caller's ``sessionStorage`` (or the desktop keychain) and arrives as an
``X-Provider-*`` header; Duct's own keys live in server config. Neither side
sees both, so "can this model run?" has exactly one honest answer and it is
computed here — which is why this endpoint must be called *with* the provider
headers attached, exactly like a generate call.

``/models/catalogue`` exists so the settings page never hard-codes a model
list. The current Engine dialog does exactly that and it is already wrong:
``engines.js`` advertises ``defaultModel: "Gemini 2.5 Flash"`` for v1 as a
literal string, which stopped being true the moment the catalogue moved on.
Serving the list from ``ModelName`` makes that class of drift impossible.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from agents.engines import ENGINE_SUPPORTED_PROVIDERS, PROVIDER_CONFIG_ATTR, Engine
from agents.models import ModelName, Provider, provider_of
from agents.tiers import (
    DEFAULT_TIER_MODELS,
    JOB_TIER,
    PROVIDER_TRIPLES,
    SKIP_ENGINE,
    SKIP_NO_CREDENTIAL,
    TIER_ORDER,
    Job,
    Tier,
    resolve_tier_model,
)
from config import claude_oauth_available, get_configs
from service.auth import get_user_provider_keys

router = APIRouter(tags=["providers"])


# Shown on the tile. Kept here rather than in the browser bundle for the same
# reason as the model list: one source, and it is the side that knows.
_PROVIDER_LABELS: dict[Provider, tuple[str, str]] = {
    Provider.ANTHROPIC: (
        "Anthropic",
        "Claude models. The only provider the Claude Agent SDK (v3) accepts.",
    ),
    Provider.OPENAI: ("OpenAI", "GPT models on the LangChain (v1) engine."),
    Provider.GOOGLE_GENAI: (
        "Google Gemini",
        "Gemini models, and every image Duct generates.",
    ),
    Provider.OPENROUTER: (
        "OpenRouter",
        "One key, 500+ models — and any OpenAI-compatible gateway you point it at.",
    ),
}

# Human-facing tier hint per model, so the picker can group options the way the
# page is organised. Derived from the catalogue's own comments (`gpt-5.6-sol`
# is annotated "flagship", `luna` "cost-sensitive") rather than invented here.
_MODEL_TIER_HINT: dict[str, Tier] = {
    ModelName.CLAUDE_OPUS.value: Tier.HEAVY,
    ModelName.CLAUDE_OPUS_1M.value: Tier.HEAVY,
    ModelName.CLAUDE_SONNET.value: Tier.STANDARD,
    ModelName.CLAUDE_HAIKU.value: Tier.LIGHT,
    ModelName.GPT_5_6_SOL.value: Tier.HEAVY,
    ModelName.GPT_5_6_TERRA.value: Tier.STANDARD,
    ModelName.GPT_5_6_LUNA.value: Tier.LIGHT,
    ModelName.GPT_5_MINI.value: Tier.LIGHT,
    ModelName.GPT_4O.value: Tier.STANDARD,
    ModelName.GPT_4O_MINI.value: Tier.LIGHT,
    ModelName.GEMINI_3_1_PRO_PREVIEW.value: Tier.HEAVY,
    ModelName.GEMINI_3_7_FLASH.value: Tier.STANDARD,
    ModelName.GEMINI_3_5_FLASH_LITE.value: Tier.LIGHT,
    ModelName.GEMINI_2_5_FLASH.value: Tier.LIGHT,
    ModelName.GEMINI_2_5_FLASH_LITE.value: Tier.LIGHT,
}


def _engines_for(provider: Provider) -> list[str]:
    return [e.value for e in Engine if provider in ENGINE_SUPPORTED_PROVIDERS.get(e, frozenset())]


@router.get("/providers/status")
def providers_status(
    user_keys: dict[Provider, str] = Depends(get_user_provider_keys),
) -> dict:
    """Per-provider reachability — the union of the caller's keys and ours.

    ``source`` is the field the UI actually renders, because "reachable" alone
    hides the thing a customer cares about: whose account pays. One of:

    * ``user``         — a key this request supplied via ``X-Provider-*``
    * ``env``          — this instance's own env file (desktop, or local dev)
    * ``cloud``        — Duct's hosted key; our account is paying
    * ``subscription`` — the operator's Claude subscription on this machine
    * ``none``         — nothing; this provider cannot be reached

    The env/cloud split matters: they are the same config field and completely
    different answers to "who is paying for this run".

    Never returns a key, a prefix, or a length — only whether one exists.
    """
    cfg = get_configs()
    # A server-side key means something different depending on where this
    # instance runs, and the difference is the one a customer actually cares
    # about: on a laptop or a self-hosted box it is *their* env file, and on
    # the hosted deployment it is Duct's account paying. "Duct's key" was true
    # in both cases and informative in neither.
    server_source = "env" if (cfg.duct_local or cfg.app_env == "local") else "cloud"

    providers = []
    for provider in Provider:
        label, description = _PROVIDER_LABELS.get(provider, (provider.value, ""))
        has_user = bool(user_keys.get(provider))
        has_server = bool(getattr(cfg, PROVIDER_CONFIG_ATTR.get(provider, ""), ""))
        # Anthropic has a third way in: a subscription token the operator holds
        # on this machine. It authenticates v3 without any API key at all, so
        # reporting Anthropic as unreachable there would be false.
        oauth = provider is Provider.ANTHROPIC and claude_oauth_available()

        if has_user:
            source = "user"
        elif has_server:
            source = server_source
        elif oauth:
            source = "subscription"
        else:
            source = "none"

        providers.append({
            "id": provider.value,
            "label": label,
            "description": description,
            "reachable": source != "none",
            "source": source,
            "engines": _engines_for(provider),
        })
    return {"providers": providers}


@router.get("/models/catalogue")
def models_catalogue() -> dict:
    """Every model the tier pickers may offer, plus the defaults and the job map.

    The job map ships so the settings page can render "what runs on each tier"
    without a second round trip and without a copy of ``JOB_TIER`` in
    JavaScript that would silently stop matching.
    """
    models = []
    for model in ModelName:
        provider = provider_of(model)
        if provider is None:
            continue
        models.append({
            "id": model.value,
            "provider": provider.value,
            "tier_hint": (_MODEL_TIER_HINT.get(model.value) or Tier.STANDARD).value,
            # v3's harness is provider-locked, and a CLI-only id 404s on the
            # Messages API — both facts live in engines.py and are surfaced
            # here so the picker can disable rather than let a run discover it.
            "engines": (
                ["v3"] if model.value.endswith("[1m]") else _engines_for(provider)
            ),
        })

    return {
        "models": models,
        "tiers": [
            {
                "id": tier.value,
                "default_model": DEFAULT_TIER_MODELS[tier].value,
                "jobs": [job.value for job, assigned in JOB_TIER.items() if assigned is tier],
            }
            for tier in TIER_ORDER
        ],
        "provider_triples": {
            provider.value: {tier.value: model.value for tier, model in triple.items()}
            for provider, triple in PROVIDER_TRIPLES.items()
        },
        "jobs": [{"id": job.value, "tier": JOB_TIER[job].value} for job in Job],
    }


class TierPreviewRequest(BaseModel):
    """The three picks, plus the engine they would run on."""

    model_config = ConfigDict(extra="ignore")

    tiers: dict[str, str] = Field(default_factory=dict)
    engine: str = ""


@router.post("/models/preview")
def models_preview(
    body: TierPreviewRequest,
    user_keys: dict[Provider, str] = Depends(get_user_provider_keys),
) -> dict:
    """What each tier would actually run, resolved by the code that will run it.

    The settings page needs to print a sentence like "Light jobs run on Claude
    Sonnet 5 until you add an OpenAI key". That sentence is a promise, and a
    promise computed in JavaScript from a list of which keys the browser
    happens to hold is a promise that drifts the first time the resolver gains
    a rule. So the browser sends its draft map and renders whatever comes back
    — ``resolve_tier_model`` is the single author of the claim.

    Called on every change to an unsaved draft, so it stays a pure read: it
    resolves, it does not persist.
    """
    cfg = get_configs()
    reachable = {
        provider
        for provider in Provider
        if user_keys.get(provider) or getattr(cfg, PROVIDER_CONFIG_ATTR.get(provider, ""), "")
    }
    if claude_oauth_available():
        reachable.add(Provider.ANTHROPIC)
    reachable = frozenset(reachable)

    try:
        engine = Engine(body.engine) if body.engine else Engine.V1
    except ValueError:
        engine = Engine.V1

    # One representative job per tier — every job on a tier resolves
    # identically, since the ladder depends on the tier and not the job.
    representative = {tier: next((j for j in Job if JOB_TIER[j] is tier), None) for tier in TIER_ORDER}

    rows = []
    for tier in TIER_ORDER:
        job = representative[tier]
        picked = str(body.tiers.get(tier.value) or DEFAULT_TIER_MODELS[tier].value).strip()
        picked_provider = provider_of(picked)
        resolution = (
            resolve_tier_model(job, engine, tier_map=body.tiers, reachable=reachable)
            if job is not None
            else None
        )

        row = {
            "id": tier.value,
            "model": picked,
            "provider": getattr(picked_provider, "value", None),
            "runnable": bool(resolution and not resolution.degraded),
            "serves": None,
            "reason": None,
        }
        if resolution is None:
            # Nothing below it can run either — the run would fail at the door.
            row["reason"] = (
                SKIP_ENGINE
                if picked_provider not in ENGINE_SUPPORTED_PROVIDERS.get(engine, frozenset())
                else SKIP_NO_CREDENTIAL
            )
        elif resolution.degraded:
            row["reason"] = next(
                (reason for skipped_tier, reason in resolution.skipped if skipped_tier is tier),
                SKIP_NO_CREDENTIAL,
            )
            # `tier` is None when the ladder ran out and the engine's own
            # default caught it — the stock case for Content Studio, whose
            # harness cannot run the Google triple this install ships with.
            row["serves"] = {
                "tier": resolution.tier.value if resolution.tier else None,
                "model": getattr(resolution.model, "value", str(resolution.model)),
                "engine_default": resolution.engine_default,
            }
        rows.append(row)

    return {"engine": engine.value, "tiers": rows}
