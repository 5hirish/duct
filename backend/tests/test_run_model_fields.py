"""What a run-start event says about its model (agents/models.py).

One helper feeds five PIPELINE_STARTED emitters, so the transcript can draw
"Switched to Claude Sonnet 5" when a thread comes back on a different model.
The label is the one the settings page shows; an unlabelled model falls back
to its id rather than to nothing, because a divider with no name is worse
than one with a raw id.
"""

from __future__ import annotations

from agents.models import MODEL_LABELS, ModelName, Provider, model_label, run_model_fields


def test_fields_name_the_provider_the_model_and_a_human_label():
    fields = run_model_fields(Provider.ANTHROPIC, ModelName.CLAUDE_SONNET)
    assert fields == {
        "provider": Provider.ANTHROPIC.value,
        "model": ModelName.CLAUDE_SONNET.value,
        "model_label": "Claude Sonnet 5",
    }


def test_a_bare_string_and_an_unknown_id_still_produce_fields():
    assert run_model_fields("openai", "gpt-99") == {
        "provider": "openai",
        "model": "gpt-99",
        "model_label": "gpt-99",
    }
    assert run_model_fields(None, None) == {"provider": "", "model": "", "model_label": ""}


def test_every_chat_model_has_a_label():
    """A new catalogue row without a name is a divider that reads as a slug."""
    missing = sorted(m.value for m in ModelName if m.value not in MODEL_LABELS)
    assert not missing, f"models with no display name: {missing}"
    assert model_label(ModelName.GPT_5_6_TERRA) == "GPT-5.6 Terra"
