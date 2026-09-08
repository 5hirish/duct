"""Cooling down a credential, and never anybody else's.

The store is a hint rather than a correctness boundary, so most of what could
go wrong here is cosmetic. Two things are not: cooling down the wrong account,
which routes a customer off a provider they are perfectly entitled to use, and
letting the key itself into anything that outlives the call.
"""

from __future__ import annotations

import pytest

from agents.core import quota
from agents.core.errors import ErrorCode
from agents.core.lc import ReportedRetryMiddleware
from agents.models import Provider

ALICE = "sk-ant-alice-key"
BOB = "sk-ant-bob-key"


@pytest.fixture(autouse=True)
def _clean():
    quota.reset()
    yield
    quota.reset()


def _id(key: str) -> str:
    return quota.credential_identity(key)


class TestMultiTenancy:
    def test_a_limit_on_one_key_does_not_cool_another(self):
        """The guarantee the whole design is keyed around.

        Duct is multi-tenant with bring-your-own keys: a 429 on Alice's
        Anthropic account says nothing about Bob's. Keying this by provider
        alone would let one heavy user route every other customer off a vendor.
        """
        quota.note_exhausted(_id(ALICE), Provider.ANTHROPIC, seconds=60)
        assert quota.cooling(_id(ALICE)) == frozenset({Provider.ANTHROPIC})
        assert quota.cooling(_id(BOB)) == frozenset()

    def test_a_limit_on_one_provider_does_not_cool_the_others(self):
        quota.note_exhausted(_id(ALICE), Provider.ANTHROPIC, seconds=60)
        assert Provider.OPENAI not in quota.cooling(_id(ALICE))

    def test_an_unattributed_limit_records_nothing(self):
        """No identity means no credential we can name.

        Recording under "" would make one shared bucket that every
        unattributed run then reads — the multi-tenancy bug wearing a
        different hat.
        """
        quota.note_exhausted("", Provider.ANTHROPIC, seconds=60)
        assert quota.cooling("") == frozenset()


class TestTheKeyNeverLands:
    def test_the_store_holds_no_key_material(self):
        """Asserted on the store's contents, not on the absence of a log line."""
        quota.note_exhausted(_id(ALICE), Provider.ANTHROPIC, seconds=60)
        assert ALICE not in repr(quota._entries)

    def test_identity_is_stable_and_not_reversible_by_length(self):
        assert _id(ALICE) == _id(ALICE)
        assert _id(ALICE) != _id(BOB)
        assert len(_id(ALICE)) == 16

    def test_an_empty_key_has_no_identity(self):
        """Otherwise every keyless caller shares one bucket."""
        assert _id("") == ""
        assert _id("   ") == ""


class TestWindows:
    def test_a_cooldown_expires_and_the_provider_comes_back(self):
        quota.note_exhausted(_id(ALICE), Provider.ANTHROPIC, seconds=60, now=1_000.0)
        assert quota.cooling(_id(ALICE), now=1_059.0) == frozenset({Provider.ANTHROPIC})
        assert quota.cooling(_id(ALICE), now=1_061.0) == frozenset()

    def test_a_silent_provider_gets_the_default_window(self):
        quota.note_exhausted(_id(ALICE), Provider.ANTHROPIC, seconds=None, now=0.0)
        left = quota.cooling_seconds(_id(ALICE), now=0.0)[Provider.ANTHROPIC]
        assert left == pytest.approx(quota.DEFAULT_COOLDOWN_SECONDS)

    def test_a_wild_retry_after_cannot_bench_a_tier_for_a_day(self):
        """A `retry-after` of a day is a mistake or a suspension.

        Either way, re-learning the limit in an hour is cheaper than a tier
        silently unavailable until tomorrow.
        """
        quota.note_exhausted(_id(ALICE), Provider.ANTHROPIC, seconds=86_400, now=0.0)
        left = quota.cooling_seconds(_id(ALICE), now=0.0)[Provider.ANTHROPIC]
        assert left == pytest.approx(quota.MAX_COOLDOWN_SECONDS)

    def test_seconds_remaining_counts_down(self):
        """A duration, not a timestamp — the client anchors it to its own clock."""
        quota.note_exhausted(_id(ALICE), Provider.ANTHROPIC, seconds=100, now=0.0)
        assert quota.cooling_seconds(_id(ALICE), now=40.0)[Provider.ANTHROPIC] == pytest.approx(60.0)


class TestSweeping:
    def test_the_store_stays_bounded(self):
        """A server seeing many keys must not grow this without limit."""
        for i in range(quota.MAX_ENTRIES + 50):
            quota.note_exhausted(f"identity-{i}", Provider.ANTHROPIC, seconds=600, now=0.0)
        assert len(quota._entries) <= quota.MAX_ENTRIES

    def test_expired_entries_are_dropped_on_write(self):
        quota.note_exhausted(_id(ALICE), Provider.ANTHROPIC, seconds=10, now=0.0)
        quota.note_exhausted(_id(BOB), Provider.OPENAI, seconds=10, now=100.0)
        assert (_id(ALICE), Provider.ANTHROPIC) not in quota._entries


class _RateLimit(Exception):
    """Shaped like a provider 429: the classifier reads the status off it."""

    status_code = 429


class _BadKey(Exception):
    status_code = 401


class TestTheRecordHook:
    """`_give_up` is the one place that knows a limit was final rather than
    transient — everything above it is still retrying."""

    def _mw(self, **kw):
        return ReportedRetryMiddleware(
            attempts=1, identity=_id(ALICE), provider=Provider.ANTHROPIC, **kw
        )

    def test_a_final_rate_limit_cools_the_credential(self):
        assert self._mw()._give_up(_RateLimit(), attempt=1) is True
        assert quota.cooling(_id(ALICE)) == frozenset({Provider.ANTHROPIC})

    def test_a_rejected_key_records_nothing(self):
        """A bad key must keep failing loudly, not quietly demote a tier.

        The user's fix is to paste a working key; a tier that silently stepped
        down for five minutes hides the thing they need to see.
        """
        assert ErrorCode.RATE_LIMITED is not None  # the code under test is the other branch
        self._mw()._give_up(_BadKey(), attempt=1)
        assert quota.cooling(_id(ALICE)) == frozenset()

    def test_an_injected_model_cools_nothing(self):
        """No identity, no credential of ours — guessing one would bench a tier
        for somebody else."""
        mw = ReportedRetryMiddleware(attempts=1, identity="", provider=None)
        mw._give_up(_RateLimit(), attempt=1)
        assert quota._entries == {}

    def test_a_transient_failure_mid_ladder_is_not_recorded(self):
        """Attempt 1 of 4 on a retryable error is not "out of quota"."""
        mw = ReportedRetryMiddleware(
            attempts=4, identity=_id(ALICE), provider=Provider.ANTHROPIC
        )
        assert mw._give_up(_RateLimit(), attempt=1) is False
        assert quota.cooling(_id(ALICE)) == frozenset()
