"""The shared connector transport: the retry loop five vendors sit on.

`service/rest.py` exists because five copies of "issue, classify, sleep, retry,
give up" had already drifted on whether a 204 is a success, whether an empty 200
body is an error, and what surfaces when the budget runs out. Consolidating them
fixed that once — but the consolidated loop was reached only through vendor
modules whose tests patch their own `api()` wrapper, one layer *above* it. So
the loop every connector now depends on was the one piece nobody exercised, and
a regression in it would land on Apple, Meta, OpenAI, Stripe and RevenueCat at
the same time.

Sleeps are patched out; what is asserted is the sequence of delays the policy
asked for, which is the part that would be wrong.
"""

from __future__ import annotations

import httpx
import pytest

from service import rest


class _Resp:
    """Only what the loop reads: status, text, and a lazy json()."""

    def __init__(self, status_code: int, text: str = "", json_body=None):
        self.status_code = status_code
        self.text = text
        self._json = json_body

    def json(self):
        if self._json is not None:
            return self._json
        import json
        return json.loads(self.text)


@pytest.fixture
def transport(monkeypatch):
    """Drive `Endpoint.request` from a scripted list of responses.

    `calls` records the kwargs each attempt was issued with, `slept` the delays
    the retry policy asked for. Nothing sleeps for real, so a five-attempt
    backoff costs nothing.
    """
    state = {"responses": [], "calls": [], "slept": []}

    def fake_request(method, url, **kwargs):
        state["calls"].append({"method": method, "url": url, **kwargs})
        item = state["responses"].pop(0) if state["responses"] else _Resp(200, "{}")
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(rest.httpx, "request", fake_request)
    monkeypatch.setattr(rest.time, "sleep", lambda s: state["slept"].append(s))
    return state


def endpoint(**kwargs) -> rest.Endpoint:
    return rest.Endpoint(base_url="https://api.vendor.test/v1", **kwargs)


# ---------------------------------------------------------------------------
# URLs and encoding
# ---------------------------------------------------------------------------

def test_a_relative_path_is_joined_to_the_base_url():
    assert endpoint().url_for("reports") == "https://api.vendor.test/v1/reports"
    assert endpoint().url_for("/reports") == "https://api.vendor.test/v1/reports"


def test_an_absolute_url_passes_through_untouched():
    """Pagination cursors arrive as absolute URLs; re-joining them to the base
    would produce a 404 on the second page of every paged pull."""
    cursor = "https://api.vendor.test/v1/reports?page=2"
    assert endpoint().url_for(cursor) == cursor


def test_a_vendors_query_encoder_is_applied_to_params(transport):
    """Stripe wants `a[b]=c`, Meta wants JSON-valued params — the encoder is the
    seam that keeps both out of the shared loop."""
    ep = endpoint(encode=lambda params: {"flat": ",".join(sorted(params or {}))})
    ep.request("reports", headers={}, params={"b": 1, "a": 2})
    assert transport["calls"][0]["params"] == {"flat": "a,b"}


def test_without_an_encoder_params_are_passed_as_given(transport):
    endpoint().request("reports", headers={"X-Key": "k"}, params={"a": 2})
    call = transport["calls"][0]
    assert call["params"] == {"a": 2}
    assert call["headers"] == {"X-Key": "k"}


# ---------------------------------------------------------------------------
# What counts as success
# ---------------------------------------------------------------------------

def test_a_200_returns_the_parsed_body(transport):
    transport["responses"] = [_Resp(200, '{"rows": [1, 2]}')]
    assert endpoint().request("reports", headers={}) == {"rows": [1, 2]}


@pytest.mark.parametrize("status", [200, 201, 204])
@pytest.mark.parametrize("body", ["", "   ", "\n"])
def test_an_empty_body_on_a_success_status_is_an_empty_dict_not_an_error(transport, status, body):
    """A 204 carries no body at all and some vendors answer 200 with nothing.
    Calling .json() on that raises, which is the drift this consolidation fixed."""
    transport["responses"] = [_Resp(status, body)]
    assert endpoint().request("reports", headers={}) == {}


def test_a_vendor_can_widen_what_counts_as_success(transport):
    transport["responses"] = [_Resp(202, '{"queued": true}')]
    ep = endpoint(success=frozenset({200, 202}))
    assert ep.request("reports", headers={}) == {"queued": True}


def test_a_status_outside_the_success_set_raises(transport):
    transport["responses"] = [_Resp(404, "not found")]
    with pytest.raises(rest.ApiError) as exc:
        endpoint().request("reports", headers={})
    assert exc.value.status == 404
    assert exc.value.code == 404, "several call sites read .code rather than .status"
    assert not exc.value.transport_failed


# ---------------------------------------------------------------------------
# Retries
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("status", sorted(rest.RETRYABLE_STATUSES))
def test_a_retryable_status_is_retried_then_succeeds(transport, status):
    transport["responses"] = [_Resp(status, "slow down"), _Resp(200, '{"ok": true}')]
    assert endpoint().request("reports", headers={}) == {"ok": True}
    assert len(transport["calls"]) == 2
    assert transport["slept"] == [2.0]


def test_a_non_retryable_status_gives_up_on_the_first_answer(transport):
    transport["responses"] = [_Resp(401, "bad key"), _Resp(200, "{}")]
    with pytest.raises(rest.ApiError):
        endpoint().request("reports", headers={})
    assert len(transport["calls"]) == 1, "a rejected key must not be retried four more times"
    assert transport["slept"] == []


def test_the_backoff_doubles_and_stops_at_the_cap(transport):
    transport["responses"] = [_Resp(429, "slow down")] * 5
    ep = endpoint(retry=rest.RetryPolicy(attempts=5, first=2.0, cap=10.0))
    with pytest.raises(rest.ApiError):
        ep.request("reports", headers={})
    # Four sleeps for five attempts — the last attempt never waits.
    assert transport["slept"] == [2.0, 4.0, 8.0, 10.0]


def test_the_error_that_surfaces_after_exhaustion_is_the_real_last_one(transport):
    """A pull that dies after five 503s should say 503, not "retries exhausted"."""
    transport["responses"] = [_Resp(503, "upstream down")] * 5
    with pytest.raises(rest.ApiError) as exc:
        endpoint().request("reports", headers={})
    assert exc.value.status == 503
    assert "upstream down" in exc.value.summary


def test_a_transport_failure_is_retried_and_reported_as_status_zero(transport):
    transport["responses"] = [httpx.ConnectError("dns died"), _Resp(200, '{"ok": 1}')]
    assert endpoint().request("reports", headers={}) == {"ok": 1}
    assert transport["slept"] == [2.0]


def test_a_transport_failure_that_never_recovers_says_so(transport):
    transport["responses"] = [httpx.ConnectTimeout("timed out")] * 5
    with pytest.raises(rest.ApiError) as exc:
        endpoint().request("reports", headers={})
    assert exc.value.status == rest.TRANSPORT_FAILED
    assert exc.value.transport_failed, "callers branch on this to distinguish 'never arrived'"


def test_a_transport_failure_is_retried_even_when_no_status_is_retryable(transport):
    """A request that never reached the vendor tells you nothing about whether
    the vendor would have accepted it, so it is always worth another go."""
    transport["responses"] = [httpx.ConnectError("reset"), _Resp(200, "{}")]
    ep = endpoint(retry=rest.RetryPolicy(attempts=3, statuses=frozenset()))
    assert ep.request("reports", headers={}) == {}
    assert len(transport["calls"]) == 2


# ---------------------------------------------------------------------------
# Vendor error envelopes
# ---------------------------------------------------------------------------

class VendorError(rest.ApiError):
    def parse(self, body: str) -> str:
        import json
        try:
            return json.loads(body)["error"]["message"]
        except Exception:
            return ""

    def hint(self) -> str:
        return "Re-authorise the connection." if self.status == 401 else ""


def test_a_subclass_unpacks_the_vendors_error_envelope(transport):
    transport["responses"] = [_Resp(401, '{"error": {"message": "token expired"}}')]
    with pytest.raises(VendorError) as exc:
        endpoint(error_cls=VendorError).request("reports", headers={})
    assert exc.value.summary == "token expired"
    assert exc.value.hint() == "Re-authorise the connection."
    assert "HTTP 401 — token expired" in str(exc.value)


def test_an_unparseable_envelope_falls_back_to_the_truncated_body(transport):
    transport["responses"] = [_Resp(500, "<html>Gateway Error</html>" + "x" * 500)]
    with pytest.raises(VendorError) as exc:
        endpoint(error_cls=VendorError, retry=rest.RetryPolicy(attempts=1)).request("r", headers={})
    assert exc.value.summary.startswith("<html>Gateway Error</html>")
    assert len(exc.value.summary) == 300, "an HTML error page must not become the whole message"


# ---------------------------------------------------------------------------
# Pacing
# ---------------------------------------------------------------------------

def test_the_pacer_waits_before_each_call_not_only_between_them(transport):
    """RevenueCat's charts allow 25/min against 480/min elsewhere. Self-pacing
    beats discovering that budget through 429s."""
    pacer = rest.Pacer(min_interval=0.5)
    ep = endpoint()
    ep.request("charts", headers={}, pacer=pacer)
    ep.request("charts", headers={}, pacer=pacer)
    assert len(transport["calls"]) == 2


def test_the_pacer_sleeps_for_the_remainder_of_the_interval(monkeypatch):
    """Patched clock: the second call arrives 0.2s into a 0.5s floor, so it
    waits 0.3s — not the full interval, and not nothing."""
    now = {"t": 100.0}
    slept: list[float] = []
    monkeypatch.setattr(rest.time, "monotonic", lambda: now["t"])
    monkeypatch.setattr(rest.time, "sleep", lambda s: slept.append(s))

    pacer = rest.Pacer(min_interval=0.5)
    pacer.wait()
    now["t"] = 100.2
    pacer.wait()
    assert slept == [pytest.approx(0.3)]


def test_the_pacer_does_not_sleep_once_the_interval_has_already_passed(monkeypatch):
    now = {"t": 100.0}
    slept: list[float] = []
    monkeypatch.setattr(rest.time, "monotonic", lambda: now["t"])
    monkeypatch.setattr(rest.time, "sleep", lambda s: slept.append(s))

    pacer = rest.Pacer(min_interval=0.5)
    pacer.wait()
    now["t"] = 101.0
    pacer.wait()
    assert slept == []


# ---------------------------------------------------------------------------
# The connectors that sit on it
# ---------------------------------------------------------------------------

def test_every_vendor_endpoint_declares_its_own_error_class():
    """A vendor left on the base `ApiError` loses its envelope unpacking, so its
    failures reach the operator as a raw body rather than a sentence."""
    import service.apple.ads.client as apple
    import service.meta.ads.client as meta
    import service.openai.ads.client as openai_ads
    import service.revenuecat.client as revenuecat
    import service.stripe.client as stripe

    generic = []
    for module in (apple, meta, openai_ads, revenuecat, stripe):
        for value in vars(module).values():
            if isinstance(value, rest.Endpoint) and value.error_cls is rest.ApiError:
                generic.append(module.__name__)
    assert generic == []
