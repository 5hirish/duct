"""A run lands on a provider the caller can pay for.

``resolve_run_model`` lets a lone bring-your-own key pick the provider only
when the operator set no default. The hosted deployment always sets one, so
a user holding just an OpenAI key was asked for a Google key. These pin the
resolver that reads the tier map over the *reachable* set instead — and the
fallback for when the map (all one vendor by default) names nobody the
caller holds a key for.

No network; config is a plain ``Configs`` handed in.
"""

from __future__ import annotations

import pytest

import config as config_module
from agents.engines import PROVIDER_CONFIG_ATTR, ProviderKeyRequired, resolve_job_run
from agents.models import Provider, provider_of
from agents.tiers import JOB_TIER, PROVIDER_TRIPLES, Job, Tier
from config import Configs


@pytest.fixture
def hosted(monkeypatch):
    """The hosted shape: Google is the operator default and holds a server
    key, and a run may not spend it."""
    cfg = Configs(
        generate_provider="google_genai",
        **{PROVIDER_CONFIG_ATTR[Provider.GOOGLE_GENAI]: "server-google-key"},
    )
    monkeypatch.setattr(config_module, "get_configs", lambda: cfg)
    monkeypatch.setattr(config_module, "allow_server_provider_keys", lambda: False)
    return cfg


def test_an_openai_only_caller_runs_on_openai_at_the_jobs_tier(hosted):
    run = resolve_job_run(Job.AUDIT, user_keys={Provider.OPENAI: "sk-user"})

    assert run.provider is Provider.OPENAI
    assert run.api_key == "sk-user"
    assert run.source == "user"
    assert run.model == PROVIDER_TRIPLES[Provider.OPENAI][JOB_TIER[Job.AUDIT]]
    assert run.tier == JOB_TIER[Job.AUDIT].value


def test_the_tier_map_is_read_when_the_caller_can_pay_for_it(hosted):
    anthropic_map = {tier.value: model.value for tier, model in PROVIDER_TRIPLES[Provider.ANTHROPIC].items()}
    run = resolve_job_run(
        Job.AUDIT, user_keys={Provider.ANTHROPIC: "sk-ant-user"}, tier_map=anthropic_map
    )
    assert run.provider is Provider.ANTHROPIC
    assert provider_of(run.model) is Provider.ANTHROPIC
    assert run.tier == Tier.HEAVY.value


def test_a_saved_key_counts_but_a_header_key_comes_first(hosted):
    run = resolve_job_run(
        Job.AUDIT,
        user_keys={Provider.OPENAI: "sk-header"},
        stored_keys={Provider.ANTHROPIC: "sk-ant-saved"},
    )
    assert run.provider is Provider.OPENAI

    saved_only = resolve_job_run(Job.AUDIT, stored_keys={Provider.ANTHROPIC: "sk-ant-saved"})
    assert saved_only.provider is Provider.ANTHROPIC
    assert saved_only.source == "stored"


def test_nothing_to_spend_is_a_402_not_a_guess(hosted):
    with pytest.raises(ProviderKeyRequired):
        resolve_job_run(Job.AUDIT)


def test_a_duct_funded_run_may_spend_the_server_key(hosted):
    run = resolve_job_run(Job.AUDIT, duct_pays=True)
    assert run.provider is Provider.GOOGLE_GENAI
    assert run.api_key == "server-google-key"
    # env vs cloud is decided by where the instance runs (`app_env`), which a
    # bare Configs reports as local; what matters here is that the server's
    # key was reachable at all, which the test above proves it is not by default.
    assert run.source in ("env", "cloud")


def test_a_local_instance_spends_its_own_env_key(hosted, monkeypatch):
    monkeypatch.setattr(config_module, "allow_server_provider_keys", lambda: True)
    run = resolve_job_run(Job.AUDIT)
    assert run.provider is Provider.GOOGLE_GENAI
    assert run.api_key == "server-google-key"
