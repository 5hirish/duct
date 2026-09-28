"""Judge client construction + credential resolution.

Two judges, chosen by what the deliverable is:

* **Text** (every rubric without images: the insights brief, the audit
  report) runs through Duct's own model transport on OpenRouter, DeepSeek V4
  Pro by default: capable enough for binary markers, and a fraction of a
  frontier model's price per verdict, which is what lets a gate run on every
  harness PR. ``DUCT_JUDGE_PROVIDER`` / ``DUCT_JUDGE_MODEL`` override it.
  When the agent under test is the same family as the judge, only the binary
  markers gate (``tests/eval/gate.py``): self-preference moves a 1–5 score,
  and it is the scores that are logged, not gated.
* **Vision** (the content post's slides) stays on Gemini, below: DeepSeek does
  not read pixels, and a slide's legibility is graded by looking at it.

The vision judge is one Gemini call that scores the deliverable. Gemini — a different stack from the one
on — is used here instead of Claude because (a) the grading call must inspect
images and return JSON in a single shot, which google-genai does natively, and
(b) the Gemini key has the rate-limit headroom the raw Anthropic Messages API
path did not.

We call ``google-genai`` directly rather than through an agent harness: the
judge is one multimodal call that must accept image input and emit native
structured output, and needs no tool loop, memory or streaming around it. The
call shape mirrors service/google/brief.py (text + JSON) and
service/google/gemini/client.py (image parts).
"""

from __future__ import annotations

import os

# Default judge model: the v2 engine's Gemini default — multimodal (accepts
# images) and proven with JSON output in service/google/brief.py. Override per
# run with DUCT_JUDGE_MODEL (e.g. "gemini-3.1-flash-preview").
DEFAULT_JUDGE_MODEL = "gemini-2.5-flash"


class JudgeUnavailable(RuntimeError):
    """No usable Gemini credential / SDK is available for the judge."""


def _config_cred(name: str) -> str:
    """Best-effort read of a credential from Duct's settings (covers backend/.env
    for local runs). Never raises if config can't be imported."""
    try:
        from config import get_configs

        return str(getattr(get_configs(), name, "") or "")
    except Exception:
        return ""


def resolve_judge_api_key() -> str:
    """The Gemini API key for the judge — env first, then Duct config."""
    return (
        os.environ.get("GEMINI_API_KEY", "")
        or os.environ.get("GOOGLE_API_KEY", "")
        or _config_cred("gemini_api_key")
    ).strip()


def judge_available() -> bool:
    """True when the google-genai SDK is importable and a Gemini key is present."""
    try:
        from google import genai  # noqa: F401
    except Exception:
        return False
    return bool(resolve_judge_api_key())


def build_judge_client():
    """Construct a ``google.genai.Client`` from the resolved Gemini key. Raises
    ``JudgeUnavailable`` when the SDK is missing or no key is set."""
    try:
        from google import genai
    except Exception as exc:  # pragma: no cover - import guard
        raise JudgeUnavailable("the google-genai SDK is not installed") from exc

    key = resolve_judge_api_key()
    if not key:
        raise JudgeUnavailable("no Gemini credential found (set GEMINI_API_KEY)")
    return genai.Client(api_key=key)


# --- the text judge -----------------------------------------------------------

TEXT_JUDGE_PROVIDER = "openrouter"
DEFAULT_TEXT_JUDGE_MODEL = "deepseek/deepseek-v4-pro"


def resolve_text_judge() -> tuple[str, str, str]:
    """``(provider, model, api_key)`` for the text judge; the key is empty when
    none is configured. Env first (CI secrets), then Duct's own settings."""
    provider = (os.environ.get("DUCT_JUDGE_PROVIDER") or TEXT_JUDGE_PROVIDER).strip()
    model = (os.environ.get("DUCT_JUDGE_MODEL") or DEFAULT_TEXT_JUDGE_MODEL).strip()
    if provider == "gemini":
        return provider, model, resolve_judge_api_key()
    key = os.environ.get(f"{provider.upper()}_API_KEY", "") or _config_cred(f"{provider}_api_key")
    return provider, model, key.strip()


def text_judge_available() -> bool:
    provider, _, key = resolve_text_judge()
    return provider != "gemini" and bool(key)
