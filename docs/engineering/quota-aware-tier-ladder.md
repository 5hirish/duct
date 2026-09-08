# Quota-aware tier ladder

*Status: spec, not built. Sept 2026.*

Make provider exhaustion a routing input instead of a terminal error, so a run
that could have finished on the user's Standard model stops failing on their
Heavy one.

## The gap

Duct classifies rate limits correctly and then does nothing structural with the
answer.

`agents/core/errors.py` maps a 429 to `ErrorCode.RATE_LIMITED` and
`retry_after_seconds` already digs the provider's own reset window out of
`retry-after-ms`, `retry-after`, or a `retry_after` attribute.
`ReportedRetryMiddleware` retries four times with jitter, tells the browser
each attempt, and gives up early when the provider asks for longer than
`MODEL_RETRY_HEADER_MAX_DELAY` — with a comment saying exactly why: waiting the
cap and retrying only fails again.

At that point it raises, and the run ends.

Meanwhile `agents/tiers.py::resolve_tier_model` walks the user's three picks
from the job's tier downward, skipping a tier for one of two reasons:

```python
SKIP_NO_CREDENTIAL = "no_credential"
SKIP_ENGINE        = "engine_unsupported"
```

Both are static properties of the request. Neither says *this provider told us,
forty seconds ago, that we are out of quota until 14:32.* So the ladder happily
resolves to Heavy, the run dies on a 429 the retry loop already knew was
hopeless, and the Standard model the user picked — on a different vendor, with
its own quota, sitting right there in their tier map — is never tried.

The scheduled brief is where this costs the most. `backend/AGENTS.md` is
explicit that it is the product and can never block on a human; today a
five-hour Claude window that emptied at 08:40 takes the 09:00 brief with it.

## What already exists

This is a small change because most of it is built:

| Piece | Where | Status |
|---|---|---|
| 429 → typed code | `agents/core/errors.py::classify_error` | done |
| Provider's own reset window | `agents/core/errors.py::retry_after_seconds` | done |
| Give-up decision | `agents/core/lc.py::ReportedRetryMiddleware._give_up` | done — **the record hook** |
| Ladder with skip reasons | `agents/tiers.py::resolve_tier_model` | done — **the consume hook** |
| Skip explanation for UI/logs | `agents/tiers.py::describe_skip` | done |
| Per-request reachability | `agents/engines.py::resolve_job_run` | done |

Nothing new is needed in the error classifier, the retry loop's timing, or the
event vocabulary.

## The constraint that makes this Duct-specific

**Cool down a credential, never a provider.**

Duct is multi-tenant with bring-your-own keys. A 429 on one customer's
Anthropic key says nothing whatsoever about another's — they are different
accounts with different limits. A provider-keyed cooldown would let one heavy
user route every other customer off Anthropic.

`resolve_job_run` already computes `reachable` per request rather than reading
globals, and `resolve_tier_model`'s docstring gives the reason: a module that
reaches for globals "races across concurrent callers carrying different
bring-your-own keys". A provider-keyed cooldown is that same bug wearing a
different hat.

So the store is keyed by a **hash of the credential**, plus the provider:

```python
identity = sha256(api_key.encode()).hexdigest()[:16]
key = (identity, provider)
```

Provider-level, not per-model, for two reasons. The window that actually bites
(Anthropic's five-hour, OpenAI's plan quota) is an account property rather than
a model one; and the consumer is the tier ladder, which resolves a tier *to a
provider*, so a per-model entry would have to be collapsed to provider before
anyone could use it. Record the model alongside for diagnostics, key on the
pair.

The key itself is never stored, never logged, never emitted. The hash is a
correlation handle and nothing else.

This is also the thing that cannot be borrowed from 9Router's design, which
prompted this: it is single-tenant by construction — one dashboard password,
one shared pool of provider connections — so "this provider is out of quota" is
a true global statement there and a false one here.

## Design

### 1. Record — `agents/core/quota.py` (new)

A small module with no framework imports, so it stays domain code under
`tests/test_harness_boundaries.py`.

```python
def note_exhausted(identity: str, provider: Provider, *, seconds: float, model: str = "") -> None
def cooling(identity: str, *, now: float | None = None) -> frozenset[Provider]
```

- In-process TTL map, bounded in size, swept on write.
- **Deliberately not durable.** A cooldown is a hint, not a correctness
  boundary: the worst case on a fresh worker is one wasted 429 that records its
  own cooldown. That is cheaper than a DB write on the hot path of every rate
  limit, and it keeps the desktop sidecar identical to the server. If Railway
  ever runs enough workers that the waste shows up in the logs, the upgrade is
  a Redis or table-backed implementation behind the same two functions — which
  is why the API is two functions and not a dict.
- Expiry comes from `retry_after_seconds(exc)` when the provider said, and a
  conservative default (suggest 300s) when it did not. Cap it (suggest 1h) so a
  provider sending a wild `retry-after` cannot bench a tier for a day.

### 2. Hook the record into the give-up branch

`ReportedRetryMiddleware._give_up` is the one place that already knows the
difference between "having a moment" and "genuinely out". Record only in the
second case, and only for `RATE_LIMITED` — a bad API key must not cool anything
down, it must keep failing loudly.

The middleware is constructed in exactly one place —
`agents/core/deep_session.py:255` — but `build_deep_session_agent` is handed an
already-built `llm` and a `fallbacks` list, never the key. So the identity has
to arrive as a parameter: the runner has `self._api_key`, and
`resolve_job_run` is the natural place to hash it once and hang it on `JobRun`
beside `provider` and `source`. Then `build_deep_session_agent(identity=…,
provider=…)` passes both into `ReportedRetryMiddleware`.

One ordering note for whoever writes it: `ModelFallbackMiddleware` sits
*outside* the retry middleware, so when retries are exhausted on the primary
the fallback middleware then tries the next model in the chain, and the retry
middleware never learns which one it is serving. That is exactly why the key is
`(identity, provider)` — `MODEL_FALLBACK` never crosses a provider, so the
provider is correct for every model in the chain while the model is not.

### 3. Consume — a third skip reason

```python
SKIP_COOLED_DOWN = "quota_exhausted"
```

`resolve_tier_model` grows one parameter, mirroring `reachable`:

```python
def resolve_tier_model(
    job, engine, *,
    tier_map=None,
    reachable=frozenset(),
    cooling=frozenset(),      # new: reachable, but out of quota right now
    override_tier=None,
) -> TierResolution | None
```

and one check, after the credential check so the reasons stay honest:

```python
if provider in cooling:
    skipped.append((tier, SKIP_COOLED_DOWN))
    continue
```

Keep it a separate set rather than subtracting from `reachable`: "you have no
key for this" and "your key is out of quota until 14:32" are different
sentences, and the user gets shown the difference.

`resolve_job_run` fills it from `quota.cooling(identity)`.

**The engine floor must ignore cooling.** When every tier is cooled, falling
through to a provider that is also cooled is still better than raising
`ProviderKeyRequired` — a 429 the user can retry beats a 402 they cannot act
on. The floor is the floor.

### 4. Say so

`describe_skip` gains a line, and the existing `skipped` tuple carries it to
the composer and the models page for free:

> Heavy is out of quota until 14:32 — running on Standard.

This is most of the user-visible value. A brief that quietly ran on a cheaper
model than asked, with no explanation, is a support ticket.

## Scope

**In: at-the-door routing.** The next run skips a cooled tier. This is where
the value is and it is contained to resolution — no session, no streaming, no
mid-flight model swap.

**Out: mid-run hopping.** A run twenty minutes deep that hits a 429 still dies.
Rescuing it means rebuilding the chat model mid-stream, and `fallback_chain`
today mounts LangChain fallbacks that are same-provider and one step, because
`MODEL_FALLBACK` is deliberately same-provider.

Worth noting for whoever picks that up: the usual objection does **not** apply
here. `agents/tiers.py` already argues that a cross-provider hop is legitimate
when it walks the user's own three picks — *"the user chose these three models
and this order, so the hop is asked for rather than assumed."* The blocker on
mid-run is mechanical, not architectural. Do at-the-door first and see whether
mid-run still hurts.

## Files

| File | Change |
|---|---|
| `backend/agents/core/quota.py` | new — the store, two functions |
| `backend/agents/core/lc.py` | record in `_give_up`; thread identity into the middleware |
| `backend/agents/core/deep_session.py` | pass identity through to the middleware |
| `backend/agents/tiers.py` | `SKIP_COOLED_DOWN`, `cooling` param, one check, one `describe_skip` line |
| `backend/agents/engines.py` | `resolve_job_run` computes identity + fills `cooling` |
| `backend/tests/test_model_tiers.py` | ladder behaviour |
| `backend/tests/test_quota_cooldown.py` | new — the store's boundaries |

No migration, no new env var, no `.env.example` entry — the defaults are
constants in `quota.py`, and a setting nobody will tune is a setting that rots.

## Tests

The ones that would catch a real regression:

- **A 429 on one credential does not cool another.** The multi-tenancy
  guarantee, and the whole reason the store is keyed by hash. If one test
  survives from this list, it is this one.
- **The key never enters the store.** Assert on the store's contents, not on
  the absence of a log line.
- **A cooldown expires**, and the tier comes back.
- **A non-rate-limit failure records nothing** — a rejected key must not
  quietly demote a tier for five minutes.
- **The ladder skips a cooled tier and names why**, distinct from
  `no_credential`.
- **All tiers cooled still resolves** via the engine floor rather than raising.

## What this must not do

- **Never route to a provider the user did not pick.** The ladder walks their
  three tiers and the engine floor. "We found you a cheaper vendor with free
  quota" is 9Router's product, not Duct's — and it would move a customer's
  workload onto a vendor they never agreed to.
- **Never let a cooldown outlive its window.** A tier benched by a stale entry
  is worse than the failure this replaces, because it is silent.
- **Never spend Duct's key to dodge a customer's rate limit.** That decision
  belongs to `resolve_provider_key`'s `duct_pays`, which the ladder does not
  get to override.

## Open question

`MODEL_FALLBACK`'s same-provider step and this cross-tier walk both fire on a
429, and they will now interleave: retry four times → step down within the
provider → still failing → cool the credential → next run starts a tier lower.
That is coherent but it is three mechanisms deep, and nobody has watched it
happen end to end. Worth one deliberate trace against a real rate-limited key
before calling it done.
