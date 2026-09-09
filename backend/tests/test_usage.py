"""What a model call cost, recorded and read back.

The properties worth defending here are all about trust in a number. This table
feeds a page whose entire job is to tell someone what Duct spent on their own
provider account, so a wrong figure is worse than a missing one.
"""

from __future__ import annotations

import uuid

import pytest

from service.usage import MICROS_PER_USD, UsageSlice, _micros


class TestCostConversion:
    """Dollars in, integer micros out — and "unknown" preserved as unknown."""

    def test_a_price_becomes_integer_micros(self):
        assert _micros(1.23) == 1_230_000
        assert _micros(0.000001) == 1

    def test_an_unknown_price_stays_unknown_rather_than_zero(self):
        """The pricing table does not know every model.

        A missing price rendered as $0.00 would quietly understate a bill, and
        the model most likely to be missing is the newest and most expensive
        one. None travels all the way to the UI, which then shows tokens with
        no dollar figure — the same thing the live tooltip already does.
        """
        assert _micros(None) is None
        assert _micros("") is None

    def test_a_bool_is_not_a_price(self):
        """`isinstance(True, int)` is True in Python, so a stray boolean would
        otherwise be recorded as one micro-dollar."""
        assert _micros(True) is None

    def test_rounding_does_not_accumulate_error(self):
        """The reason the column is an integer at all.

        Ten calls at $0.10 must total exactly $1.00. Summing 0.1 as a float ten
        times gives 0.9999999999999999, and this page cannot be the place a
        customer first sees that.
        """
        micros = sum(_micros(0.10) for _ in range(10))
        assert micros == 1_000_000
        assert micros / MICROS_PER_USD == 1.0


class TestUsageSlice:
    def test_total_tokens_is_input_plus_output(self):
        row = UsageSlice(key="claude", input_tokens=100, output_tokens=25)
        assert row.total_tokens == 125

    def test_cost_is_dollars_at_the_edge(self):
        """Micros inside, dollars at the boundary — the browser never sees the
        internal unit."""
        assert UsageSlice(key="x", cost_micros=2_500_000).as_dict()["cost_usd"] == 2.5

    def test_unknown_cost_serialises_as_null_not_zero(self):
        assert UsageSlice(key="x", cost_micros=None).as_dict()["cost_usd"] is None


class TestRecorderAttribution:
    """The recorder is where every agent's usage is captured, so the guarantees
    live on it rather than on any one agent's route."""

    def _recorder(self):
        from agents.content.persistence import ConversationRecorder

        return ConversationRecorder(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_no_owner_means_no_row(self, monkeypatch):
        """An unattributed run writes nothing.

        A usage row with no user is a charge nobody can be shown and nobody can
        query — worse than absent, because it inflates any total computed
        without a WHERE clause.
        """
        called: list = []
        monkeypatch.setattr(
            "service.usage.record_usage_event", lambda *a, **k: called.append(k)
        )
        rec = self._recorder()  # set_usage_context never called
        await rec._record_usage({"model": "claude-sonnet-5", "input_tokens": 10})
        assert called == []

    @pytest.mark.asyncio
    async def test_the_provider_comes_from_the_model_that_answered(self, monkeypatch):
        """Not from the route's resolution.

        After a fallback step the model that replied is not the one asked for,
        and the bill follows what replied. Deriving the provider from the
        response is what keeps a step-down visible in the numbers afterwards.
        """
        seen: dict = {}
        monkeypatch.setattr("service.usage.record_usage_event", lambda *a, **k: seen.update(k))
        rec = self._recorder()
        rec.set_usage_context(user_id=uuid.uuid4(), project_id=None, agent_type="insights")
        await rec._record_usage({"model": "claude-haiku-4-5-20251001", "input_tokens": 5})
        assert seen["provider"] == "anthropic"
        assert seen["agent_type"] == "insights"

    @pytest.mark.asyncio
    async def test_an_unknown_model_records_without_a_provider(self, monkeypatch):
        """An unrecognised model id must not lose the row.

        The tokens were still spent. `provider_of` returning None is a real
        answer, so the row is written with an empty provider rather than
        dropped or attributed to a guess.
        """
        seen: dict = {}
        monkeypatch.setattr("service.usage.record_usage_event", lambda *a, **k: seen.update(k))
        rec = self._recorder()
        rec.set_usage_context(user_id=uuid.uuid4(), agent_type="audit")
        await rec._record_usage({"model": "some-model-we-have-never-heard-of"})
        assert seen["provider"] == ""
