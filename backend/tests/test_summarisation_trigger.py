"""deepagents summarises inside the window Duct budgets, not the one published.

deepagents sizes its summariser from `model.profile["max_input_tokens"]` (the
trigger is 0.85 of it). The integrations publish the vendor's figure — a
million tokens on Opus 5.5 and Sonnet 5.5 — while Duct budgets those threads
at 200k, so the summariser was set to fire at ~850k. Rulebook gap 3.
"""

from __future__ import annotations

from deepagents.middleware.summarization import compute_summarization_defaults

from agents.core.lc import resolve_chat_model
from agents.models import PRICING, ModelName, Provider, context_window_for, provider_of


def test_every_catalogue_model_carries_ducts_window_in_its_profile():
    for model in PRICING:
        provider = provider_of(model)
        if provider is None:
            continue
        llm = resolve_chat_model(provider, model, "unused-no-network")
        assert llm.profile["max_input_tokens"] == context_window_for(model), model.value
        assert compute_summarization_defaults(llm)["trigger"] == ("fraction", 0.85), model.value


def test_the_summariser_fires_inside_the_budget_not_the_published_window():
    """Sonnet 5.5 publishes a million tokens; Duct budgets 200k, so the
    trigger is 170k, which is also the floor `RunLimits` keeps pruning under."""
    from agents.core.deep_session import SUMMARIZATION_FLOOR_TOKENS

    llm = resolve_chat_model(Provider.ANTHROPIC, ModelName.CLAUDE_SONNET, "sk-ant-x")
    fraction = compute_summarization_defaults(llm)["trigger"][1]
    assert int(fraction * llm.profile["max_input_tokens"]) == SUMMARIZATION_FLOOR_TOKENS


def test_the_rest_of_the_profile_survives():
    """The integrations read other keys from the profile (output limits,
    modalities); only the window is Duct's to say."""
    llm = resolve_chat_model(Provider.ANTHROPIC, ModelName.CLAUDE_SONNET, "sk-ant-x")
    assert len(llm.profile) > 1
    assert "max_output_tokens" in llm.profile


def test_the_chatgpt_plan_route_is_budgeted_too():
    llm = resolve_chat_model(Provider.OPENAI, ModelName.GPT_5_MINI, "eyJhbGciOiJSUzI1NiJ9.e30.EXAMPLE|acct-1")
    assert llm.profile["max_input_tokens"] == context_window_for(ModelName.GPT_5_MINI)
