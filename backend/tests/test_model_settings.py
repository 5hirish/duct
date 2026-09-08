"""The model choices, once they live on the server rather than in one browser.

The reason this table exists is the scheduled brief: it has no browser, so a
tier map kept in localStorage could never reach it. So the tests that matter
are the ones about a run nobody is watching reading the same preference as the
one somebody is.
"""

from __future__ import annotations

import pytest

from agents.tiers import Tier, describe_skip, tier_fields
from service.model_settings import DEFAULTS, ModelSettings, _clean


class TestCleaning:
    def test_only_the_three_known_tiers_survive(self):
        """A key nobody resolves is a key that rots. The ladder has three rungs."""
        assert _clean({"heavy": "a", "standard": "b", "light": "c", "epic": "d"}) == {
            "heavy": "a",
            "standard": "b",
            "light": "c",
        }

    def test_an_empty_pick_is_dropped_not_stored(self):
        """Absent means "unset", which resolves to the shipped default.

        Storing "" would make an explicitly-blanked tier and an untouched one
        two different states that resolve the same way.
        """
        assert _clean({"heavy": "  ", "light": "gpt-x"}) == {"light": "gpt-x"}

    def test_junk_is_not_a_map(self):
        assert _clean(None) == {}
        assert _clean("heavy") == {}

    def test_an_unknown_model_id_is_kept(self):
        """Validation belongs to the resolver, not to storage.

        `agents.tiers.tier_pick` degrades an unusable pick to the tier's
        default. Rejecting it here would need a second copy of the catalogue,
        and the copy is what goes stale when a model ships.
        """
        assert _clean({"heavy": "some-model-from-next-year"}) == {
            "heavy": "some-model-from-next-year"
        }


class TestDefaults:
    def test_an_install_that_never_opened_the_page_gets_todays_behaviour(self):
        """An empty map resolves byte-for-byte the way it did before this table."""
        assert DEFAULTS.tiers == {}
        assert DEFAULTS.engine == ""

    def test_stepping_down_is_on_by_default(self):
        """A brief on the Standard model beats no brief.

        Off is a legitimate choice — some people would rather see the rate
        limit than a quieter answer — but it is the one you have to go and
        make.
        """
        assert DEFAULTS.auto_fallback is True

    def test_an_anonymous_caller_gets_the_defaults_without_a_query(self):
        from service.model_settings import get_model_settings

        assert get_model_settings(None) == DEFAULTS


class TestRunStartFields:
    """`tier_fields` is what the browser and the stored brief both read."""

    class _Run:
        tier = "standard"
        tier_requested = "heavy"
        tier_skipped = (("heavy", "quota_exhausted"),)
        tier_retry_in = 214.4

    def test_a_clean_run_says_nothing(self):
        """Silence on the happy path.

        A chip that appears when nothing happened is the noise that teaches
        people to stop reading the status row.
        """
        class Clean:
            tier = "heavy"
            tier_requested = "heavy"
            tier_skipped = ()
            tier_retry_in = 0.0

        assert tier_fields(Clean()) == {}

    def test_a_step_down_names_both_tiers(self):
        got = tier_fields(self._Run())
        assert got["tier"] == "standard"
        assert got["tier_requested"] == "heavy"

    def test_the_reason_travels_as_a_sentence_the_backend_owns(self):
        """One source for the copy.

        `describe_skip` already turns a reason into a sentence for the settings
        page; a second wording in JSX is how the two drift.
        """
        got = tier_fields(self._Run())
        assert got["tier_skipped"][0]["detail"] == describe_skip(Tier.HEAVY, "quota_exhausted")

    def test_the_wait_is_a_duration_not_a_timestamp(self):
        """The client anchors it to its own clock, so a skewed server clock
        cannot show a countdown that is already over."""
        assert tier_fields(self._Run())["tier_retry_in"] == pytest.approx(214.4)


class TestSettingsShape:
    def test_settings_are_comparable(self):
        """The route returns them and the tests compare them; a dataclass that
        compares by identity would make every assertion here vacuous."""
        assert ModelSettings(tiers={}, auto_fallback=True, engine="") == DEFAULTS
