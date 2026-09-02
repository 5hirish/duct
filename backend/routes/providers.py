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

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session

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
from config import allow_server_provider_keys, claude_oauth_available, get_configs
from db.session import get_session as db_session
from models.auth import User
from service.auth import (
    get_current_user,
    get_current_user_optional,
    get_user_provider_keys,
)
from service.provider_keys import (
    delete_provider_key,
    has_stored_provider_keys,
    save_provider_key,
)

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
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(db_session),
) -> dict:
    """Per-provider reachability — the union of the caller's keys and ours.

    ``source`` is the field the UI actually renders, because "reachable" alone
    hides the thing a customer cares about: whose account pays. One of:

    * ``user``         — a key this request supplied via ``X-Provider-*``
    * ``stored``       — this user's saved key, decrypted per run
    * ``env``          — this instance's own env file (desktop, or local dev)
    * ``cloud``        — Duct's hosted key; our account is paying
    * ``subscription`` — the operator's Claude subscription on this machine
    * ``none``         — nothing; this provider cannot be reached

    The env/cloud split matters: they are the same config field and completely
    different answers to "who is paying for this run". So does user/stored: only
    a stored key can serve a scheduled run, which is why the tile says which
    one it is rather than collapsing both to "your key".

    ``cloud`` is unreachable on the hosted deployment unless the run is one
    Duct funds deliberately (``allow_server_provider_keys``), so a tile
    reporting it there is reporting a fallback that will not actually happen.

    Never returns a key, a prefix, or a length — only whether one exists.
    """
    cfg = get_configs()
    saved = has_stored_provider_keys(db, user.id if user else None)
    # A key in the env is only a way in where the gate would actually let a run
    # spend it. On the hosted deployment it will not, so reporting the provider
    # as reachable there would be describing a fallback that no longer happens
    # — the tile would read green and every run would still 402.
    server_usable = allow_server_provider_keys()
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
        has_stored = provider in saved
        has_server = server_usable and bool(
            getattr(cfg, PROVIDER_CONFIG_ATTR.get(provider, ""), "")
        )
        # Anthropic has a third way in: a subscription token the operator holds
        # on this machine. It authenticates v3 without any API key at all, so
        # reporting Anthropic as unreachable there would be false.
        oauth = (
            server_usable
            and provider is Provider.ANTHROPIC
            and claude_oauth_available()
        )

        if has_user:
            source = "user"
        elif has_stored:
            source = "stored"
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
            # Distinct from `source`: a header key outranks a saved one, so a
            # provider can be serving from `user` and still have one saved. The
            # settings page needs to know to offer "Forget".
            "stored": has_stored,
            "engines": _engines_for(provider),
        })
    return {"providers": providers}


class StoreProviderKeyRequest(BaseModel):
    """One provider key to remember for this user."""

    model_config = ConfigDict(extra="forbid")

    api_key: str = Field(min_length=1, max_length=512)


def _provider_or_404(provider_id: str) -> Provider:
    try:
        return Provider(provider_id.strip().lower())
    except ValueError:
        raise HTTPException(404, f"Unknown provider {provider_id!r}") from None


@router.put("/providers/{provider_id}/key")
def store_provider_key(
    provider_id: str,
    body: StoreProviderKeyRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(db_session),
) -> dict:
    """Remember this user's key for one provider, encrypted at rest.

    The opt-in half of bring-your-own-key. Without it a key lives only in
    ``sessionStorage`` and rides along as a header, which means it is gone on
    refresh and absent entirely from anything that runs without a browser —
    scheduled briefs, memory consolidation. Those are exactly the runs that
    would otherwise fall back to Duct's key, so "remember it" and "your key
    actually funds your runs" are the same feature.

    Encrypted with CREDENTIALS_ENCRYPTION_KEY (``service/credentials.py``),
    decrypted only to be spent, and never returned by any endpoint — including
    this one, which answers with presence and nothing else.
    """
    provider = _provider_or_404(provider_id)
    key = body.api_key.strip()
    if not key:
        raise HTTPException(422, "api_key must not be blank")
    save_provider_key(db, user.id, provider, key)
    return {"provider": provider.value, "stored": True}


@router.delete("/providers/{provider_id}/key")
def forget_provider_key(
    provider_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(db_session),
) -> dict:
    """Forget this user's saved key for one provider. Idempotent.

    Deleting the secret, not merely unlinking it — a "removed" key still on
    disk is the version of this feature nobody wants.
    """
    provider = _provider_or_404(provider_id)
    delete_provider_key(db, user.id, provider)
    return {"provider": provider.value, "stored": False}


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
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(db_session),
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
    # Same gate as providers_status, and for the same reason: this endpoint's
    # output is a promise ("Light jobs run on X"), and a promise that counts a
    # server key the resolver would refuse to spend is a promise that breaks on
    # the first run.
    server_usable = allow_server_provider_keys()
    stored = has_stored_provider_keys(db, user.id if user else None)
    reachable = {
        provider
        for provider in Provider
        if user_keys.get(provider)
        or provider in stored
        or (server_usable and getattr(cfg, PROVIDER_CONFIG_ATTR.get(provider, ""), ""))
    }
    if server_usable and claude_oauth_available():
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
