"""The agent eval gate: run each case k times, check it, and decide.

Tier 1 of docs/engineering/2026-09-27-agent-eval-gating-design.md. What it
adds to the rubric and judge beside it is the plumbing the design found
missing: repeated trials, a three-valued verdict, a budget, and a baseline to
compare against. Deliberately small and ours, because the frameworks each
want to own the agent loop, and the point is to run Duct's own harness.

One trial is one real insights session on a synthetic account
(``tests/eval/cases/``) with the connectors answered by that account and no
database, recorder, memory or execution tools. It passes when every
deterministic check holds and every binary judge marker does; the judge's
1–5 dimensions are logged, never gated.

Verdicts, per case:

* **PASS** — the case passed as often as its baseline says it does.
* **INCONCLUSIVE** — one trial short of that, or the median cost or model
  calls moved more than :data:`DRIFT` either way from the baseline. The CLI
  runs three more trials once before settling on it. Not a block; the PR says
  in one line why it is acceptable.
* **FAIL** — two or more trials short: the change broke the case.

A case's trials run at once, each on its own thread. A cost, call or time
cap stops a trial, a trial that will not stop is abandoned, and the run
budget is checked before each batch.
"""

from __future__ import annotations

import asyncio
import json
import logging
import queue
import re
import statistics
import threading
import time
import uuid
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from tests.eval.rubric import Marker

logger = logging.getLogger(__name__)

PASS = "PASS"
INCONCLUSIVE = "INCONCLUSIVE"
FAIL = "FAIL"

DEFAULT_TRIALS = 3
#: A median cost or call count moving this much, either way, is worth a look:
#: an effort downgrade shows up first as a cost drop with no visible change.
DRIFT = 0.30
BASELINES = Path(__file__).with_name("baselines.json")
#: A judge verdict is one call; a minute is slow, five is a stalled stream.
JUDGE_SECONDS = 300.0

# Figures worth tracing: three or more significant digits, the size of number
# a reader repeats. Percentages, abbreviations (10.7k) and dates are skipped:
# a delta is derived, a rounded restatement cannot be traced, and a date is
# not a figure.
_FIGURE = re.compile(
    r"(?<![\w.%/-])(?:€|\$|£)?(\d{1,3}(?:[,\u202f ]\d{3})+|\d+)(?:\.(\d+))?(?![\d%/kKmM-])"
)
_MIN_SIGNIFICANT = 3


@dataclass(frozen=True)
class QuotedTotal:
    """A figure the brief must quote exactly, read from the pulls the run made.

    ``paths`` are dotted paths into a pull's envelope (``totals.sessions``,
    ``subtotals.channel.Organic Search.sessions``); any window, any one of them.
    """

    entity_id: str
    paths: tuple[str, ...]
    label: str


@dataclass(frozen=True)
class Case:
    id: str
    agent: str
    question: str
    business_context: str
    world: Callable[[], Any]
    must_fetch: tuple[str, ...] = ()
    must_quote: tuple[QuotedTotal, ...] = ()
    markers: tuple[Marker, ...] = ()
    cost_cap_usd: float = 1.0
    max_model_calls: int = 40
    #: A wall clock beside the cost and call caps. OpenRouter keeps a stalled
    #: stream alive with keep-alive bytes, so no read timeout ever fires and
    #: one call hung a six-trial run for three hours on 2026-09-28. A slow
    #: trial has taken eight minutes.
    max_seconds: float = 900.0


@dataclass
class Trial:
    case_id: str
    n: int
    passed: bool = False
    failures: list[str] = field(default_factory=list)
    cost_usd: float = 0.0
    model_calls: int = 0
    tool_calls: int = 0
    seconds: float = 0.0
    fetches: list[list[str]] = field(default_factory=list)
    duplicate_pulls: int = 0
    unknown_entities: list[str] = field(default_factory=list)
    figures: int = 0
    figures_traced: int = 0
    judge: dict | None = None
    brief: str = ""
    reply: str = ""

    @property
    def provenance(self) -> float | None:
        return self.figures_traced / self.figures if self.figures else None


@dataclass
class CaseResult:
    case_id: str
    verdict: str
    reason: str
    trials: list[Trial]

    @property
    def passes(self) -> int:
        return sum(t.passed for t in self.trials)

    def median(self, attr: str) -> float:
        values = [getattr(t, attr) for t in self.trials]
        return statistics.median(values) if values else 0.0


# ---------------------------------------------------------------------------
# Trials
# ---------------------------------------------------------------------------

#: How long a trial past its clock may take to stop before it is abandoned.
#: On 2026-09-28 a trial cancelled on a stalled OpenRouter stream never
#: finished stopping, and ``asyncio.wait_for`` and ``asyncio.run``'s cleanup
#: both wait for a cancelled task to finish, so the run hung with it.
STOP_GRACE_SECONDS = 60.0

# Each trial's pulls, recorded by one wrapper around ``fetch_entity``: the
# trials of a case run at once, and a context variable is what follows a
# trial into the executor threads its tools run on.
_PULLS: ContextVar[list[dict] | None] = ContextVar("eval_pulls", default=None)


def run_trials(
    case: Case,
    ns: Any,
    *,
    provider: Any,
    model: str,
    api_key: str,
    llm: Any = None,
    judge: bool = True,
    on_done: Callable[[Trial], None] | None = None,
) -> list[Trial]:
    """Trials ``ns`` of one case, all at once, each on its own thread and loop.

    At once because a trial is minutes of waiting on a model, and six in a
    row took half an hour. On threads because a thread can be abandoned: one
    still running past its clock, :data:`STOP_GRACE_SECONDS` and the judge's
    is recorded as timed out and left to die with the process. ``on_done``
    sees each trial as it finishes. ``llm`` is the offline seam: a scripted
    fake drives the same harness, so the gate's own plumbing is tested for
    free on every PR.
    """
    from agents.insights import data_tools

    world = case.world()
    real_fetch = data_tools.fetch_entity

    def recording_fetch(entity_id: str, **kw: Any) -> dict:
        result = real_fetch(entity_id, **kw)
        if (pulls := _PULLS.get()) is not None:
            pulls.append(result)
        return result

    working = {n: Trial(case_id=case.id, n=n) for n in ns}
    finished: queue.Queue[Trial] = queue.Queue()

    def run(trial: Trial) -> None:
        try:
            asyncio.run(_run_one(case, trial, world, provider=provider, model=model,
                                 api_key=api_key, llm=llm, judge=judge))
        except Exception as exc:  # noqa: BLE001 — one trial's crash is that trial's failure
            trial.failures.append(f"crashed: {type(exc).__name__}: {exc}")
        finished.put(trial)

    done: dict[int, Trial] = {}
    started = time.monotonic()
    deadline = started + case.max_seconds + STOP_GRACE_SECONDS + (JUDGE_SECONDS if judge else 0.0)
    data_tools.fetch_entity = recording_fetch
    try:
        with world.install():
            for trial in working.values():
                threading.Thread(target=run, args=(trial,), name=f"trial-{trial.n}", daemon=True).start()
            while len(done) < len(working):
                try:
                    trial = finished.get(timeout=max(0.0, deadline - time.monotonic()))
                except queue.Empty:
                    break
                done[trial.n] = trial
                if on_done is not None:
                    on_done(trial)
    finally:
        data_tools.fetch_entity = real_fetch

    for n, trial in working.items():
        if n in done:
            continue
        # A copy: the abandoned thread still holds its trial and may write to it.
        done[n] = Trial(
            case_id=case.id, n=n, cost_usd=round(trial.cost_usd, 4), model_calls=trial.model_calls,
            seconds=round(time.monotonic() - started, 1),
            failures=[f"timed out after {case.max_seconds:.0f}s and did not stop; abandoned"],
        )
        if on_done is not None:
            on_done(done[n])
    return [done[n] for n in ns]


def run_trial(case: Case, n: int, **kwargs: Any) -> Trial:
    """One trial, the same way :func:`run_trials` runs several."""
    return run_trials(case, [n], **kwargs)[0]


async def _run_one(
    case: Case, trial: Trial, world: Any, *, provider: Any, model: str, api_key: str, llm: Any, judge: bool,
) -> None:
    """One real session on the case's synthetic account, then the checks."""
    from agents.core.events import AgentEvent
    from agents.insights.setup import render_data_sources
    from agents.insights.v1.runner import AutonomousInsightsRunner
    from models.execution import AUTONOMY_ASK

    events: list[dict] = []
    pulls: list[dict] = []
    _PULLS.set(pulls)
    runner = AutonomousInsightsRunner(
        api_key=api_key, provider=provider, model=model, thinking="",
        verify_provider=provider, verify_model=model, verify_api_key=api_key,
    )
    task: asyncio.Task | None = None

    async def emit(event: dict) -> None:
        events.append(event)
        if event.get("event") == AgentEvent.TOKEN_USAGE:
            trial.model_calls += 1
            trial.cost_usd += float(event.get("cost_usd") or 0.0)
            over = trial.cost_usd > case.cost_cap_usd or trial.model_calls > case.max_model_calls
            if over and task is not None and not task.done():
                task.cancel()

    started = time.monotonic()
    task = asyncio.ensure_future(runner.run_session(
        f"eval-{case.id}-{trial.n}-{uuid.uuid4().hex[:6]}",
        emit,
        llm=llm,
        prompt=case.question,
        business_context=case.business_context,
        data_sources=render_data_sources(world.data_sources()),
        project_id=None,
        user_id=uuid.uuid4(),
        conversation_id=None,
        remember=False,
        artifact_format="markdown",
        autonomy=AUTONOMY_ASK,
        chat_idle_timeout=1.0,
        interactive=False,
        execute=False,
    ))
    try:
        await asyncio.wait_for(task, timeout=case.max_seconds)
    except asyncio.CancelledError:
        trial.failures.append(
            f"stopped at ${trial.cost_usd:.2f} / {trial.model_calls} model calls "
            f"(caps ${case.cost_cap_usd:.2f} / {case.max_model_calls})"
        )
    except TimeoutError:
        trial.failures.append(f"timed out after {case.max_seconds:.0f}s and {trial.model_calls} model calls")
    trial.seconds = round(time.monotonic() - started, 1)
    trial.cost_usd = round(trial.cost_usd, 4)

    _check(case, trial, events, pulls)
    if judge and trial.brief:
        _judge(case, trial)
    trial.passed = not trial.failures


def _check(case: Case, trial: Trial, events: list[dict], pulls: list[dict]) -> None:
    from agents.core.events import AgentEvent

    versions = [e for e in events if e.get("event") == AgentEvent.ARTIFACT_VERSION]
    trial.brief = str(((versions[-1].get("payload") or {}).get("content")) or "") if versions else ""
    # The chat side of the run. Without a brief it is the only account of why:
    # the first CI run lost two briefs out of six and could not say how.
    trial.reply = "".join(
        str(e.get("text") or "") for e in events if e.get("event") == AgentEvent.AGENT_MESSAGE_CHUNK
    ).strip()
    if not trial.brief:
        # The stream parser drops a <duct_artifact> that never closes, and the
        # runner an empty one, so a started brief leaves chunks and no version.
        started = any(e.get("event") == AgentEvent.ARTIFACT_CHUNK for e in events)
        trial.failures.append(
            "no brief: one was started and never published" if started
            else "no brief: the run ended without an artifact"
        )
    errors = [e for e in events if e.get("event") in (AgentEvent.PIPELINE_FAILED, AgentEvent.STEP_FAILED)]
    if errors:
        trial.failures.append(f"error event: {errors[0].get('code') or errors[0].get('error')}")

    # The lead agent's calls; the verifier's run in a sub-graph and are not
    # drawn as activity, though its pulls are counted below with the rest.
    trial.tool_calls = len({
        e.get("activity_id") for e in events if e.get("event") == AgentEvent.TOOL_ACTIVITY
    })
    trial.fetches = [[p.get("entity_id", ""), p.get("date_from", ""), p.get("date_to", "")] for p in pulls]
    # The session cache answers a repeat before fetch_entity runs, so a
    # duplicate here is one the cache keyed differently.
    trial.duplicate_pulls = len(trial.fetches) - len({tuple(f) for f in trial.fetches})
    trial.unknown_entities = sorted(
        {p.get("entity_id", "") for p in pulls if p.get("status") == "unknown_entity"}
    )

    fetched_ok = {p.get("entity_id") for p in pulls if p.get("status") == "ok"}
    for entity in case.must_fetch:
        if entity not in fetched_ok:
            trial.failures.append(f"never read {entity}")

    for want in case.must_quote:
        truths = [
            value for p in pulls if p.get("entity_id") == want.entity_id and p.get("status") == "ok"
            for path in want.paths if (value := dig(p, path)) is not None
        ]
        if truths and not any(quotes(trial.brief, v) for v in truths):
            trial.failures.append(
                f"does not quote {want.label} as Duct totalled it (any of {sorted(set(truths))})"
            )

    known = numbers_in(pulls)
    figures = figures_in(trial.brief)
    trial.figures = len(figures)
    trial.figures_traced = sum(1 for f in figures if f in known)


def _judge(case: Case, trial: Trial) -> None:
    from tests.eval.judge import evaluate
    from tests.eval.rubrics.insights_brief import insights_brief_rubric, render_brief_artifact

    outcome: dict[str, Any] = {}

    def verdict() -> None:
        try:
            outcome["card"] = evaluate(insights_brief_rubric(case.markers),
                                       render_brief_artifact(trial.brief, question=case.question))
        except Exception as exc:  # noqa: BLE001 — a judge outage is not the agent's failure
            outcome["error"] = exc

    # The judge is a blocking call, so no asyncio deadline reaches it. A
    # daemon thread can be abandoned when it stalls, and does not hold the
    # process open at exit the way an executor's worker would.
    worker = threading.Thread(target=verdict, name=f"judge-{trial.n}", daemon=True)
    worker.start()
    worker.join(JUDGE_SECONDS)
    if worker.is_alive() or "error" in outcome:
        reason = "Timeout" if worker.is_alive() else type(outcome["error"]).__name__
        logger.warning("gate: judge unavailable for %s #%d: %s", case.id, trial.n, reason)
        trial.judge = {"skipped": reason}
        return
    card = outcome["card"]
    trial.judge = card.as_dict()
    trial.failures += [f"judge: {f}" for f in card.failures if "marker" in f]


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------

def dig(envelope: dict, path: str) -> float | None:
    node: Any = envelope
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return float(node) if isinstance(node, (int, float)) and not isinstance(node, bool) else None


def spellings(value: float) -> set[str]:
    """How a brief may write an exact figure: 10662, 10,662, 10 662, 10.662,
    and one-decimal thousands (10.7k) when that is how it was rounded."""
    out: set[str] = set()
    if float(value).is_integer():
        n = int(value)
        out |= {str(n), f"{n:,}", f"{n:,}".replace(",", " "), f"{n:,}".replace(",", ".")}
        if n >= 10_000:
            out.add(f"{n / 1000:.1f}k")
    else:
        out |= {f"{value:.2f}", f"{value:,.2f}", f"{value:.1f}"}
    return out


def quotes(text: str, value: float) -> bool:
    return any(re.search(rf"(?<![\d.,]){re.escape(s)}(?!\d|[.,]\d)", text) for s in spellings(value))


def figures_in(text: str) -> list[float]:
    """Figures of three or more significant digits a reader would repeat."""
    out = []
    for match in _FIGURE.finditer(text or ""):
        whole, decimals = re.sub(r"[,\u202f ]", "", match.group(1)), match.group(2) or ""
        if len(whole.lstrip("0")) + len(decimals) < _MIN_SIGNIFICANT:
            continue
        value = float(f"{whole}.{decimals}") if decimals else float(whole)
        if 1900 <= value <= 2100 and not decimals and "," not in match.group(1):
            continue  # a year
        out.append(round(value, 2))
    return out


def numbers_in(pulls: list[dict]) -> set[float]:
    """Every number any pull returned, envelope and rows alike, to two places."""
    found: set[float] = set()

    def walk(node: Any) -> None:
        if isinstance(node, bool):
            return
        if isinstance(node, (int, float)):
            found.add(round(float(node), 2))
        elif isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    for pull in pulls:
        walk(pull)
    return found


# ---------------------------------------------------------------------------
# Verdicts
# ---------------------------------------------------------------------------

def decide(case_id: str, trials: list[Trial], baseline: dict | None) -> tuple[str, str]:
    """The case's verdict from its trials and its baseline, with the reason."""
    if not trials:
        return INCONCLUSIVE, "no trials ran (budget)"
    k = len(trials)
    passes = sum(t.passed for t in trials)
    expected = float((baseline or {}).get("pass_rate", 1.0))
    short = expected * k - passes
    if short >= 2 - 1e-9:
        return FAIL, f"{passes}/{k} passed; the baseline passes {expected:.0%}"
    if short >= 1 - 1e-9:
        return INCONCLUSIVE, f"{passes}/{k} passed; the baseline passes {expected:.0%}"
    for attr, key in (("cost_usd", "median_cost_usd"), ("model_calls", "median_model_calls")):
        base = float((baseline or {}).get(key) or 0)
        if base:
            now = statistics.median(getattr(t, attr) for t in trials)
            if abs(now - base) / base > DRIFT:
                return INCONCLUSIVE, f"median {attr} {now:g} against a baseline of {base:g}"
    return PASS, f"{passes}/{k} passed"


def load_baselines(path: Path = BASELINES) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def baseline_entry(result: CaseResult, *, provider: str, model: str, recorded: str) -> dict:
    return {
        "pass_rate": round(result.passes / len(result.trials), 3) if result.trials else 0.0,
        "median_cost_usd": round(result.median("cost_usd"), 4),
        "median_model_calls": result.median("model_calls"),
        "trials": len(result.trials),
        "provider": provider,
        "model": model,
        "recorded": recorded,
    }


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def report(results: list[CaseResult], *, provider: str, model: str, spent: float) -> str:
    lines = [
        f"### Agent eval · {provider} · {model} · ${spent:.2f}",
        "",
        "| Case | Verdict | Passed | Median cost | Median calls | Median time | Figures traced |",
        "| --- | --- | :---: | ---: | ---: | ---: | ---: |",
    ]
    for r in results:
        traced = [t.provenance for t in r.trials if t.provenance is not None]
        lines.append(
            f"| `{r.case_id}` | **{r.verdict}** | {r.passes}/{len(r.trials)} | "
            f"${r.median('cost_usd'):.3f} | {r.median('model_calls'):g} | {r.median('seconds'):.0f}s | "
            f"{(statistics.median(traced) if traced else 0):.0%} |"
        )
    for r in results:
        failing = [t for t in r.trials if t.failures]
        if failing or r.verdict != PASS:
            lines += ["", f"**{r.case_id}** — {r.reason}"]
            for t in failing:
                lines += [f"- trial {t.n}: " + "; ".join(t.failures)]
                if not t.brief:
                    lines += [f"  > ended on: {_tail(t.reply) or '(nothing said in chat)'}"]
    return "\n".join(lines)


def _tail(text: str, limit: int = 280) -> str:
    """The end of a reply on one line: where a run that wrote no brief stopped."""
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else "…" + flat[-limit:]


def trial_record(result: CaseResult, trial: Trial, *, provider: str, model: str) -> str:
    """One JSONL line per trial: what CI keeps as an artifact."""
    row = asdict(trial) | {"verdict": result.verdict, "provider": provider, "model": model}
    row["brief"] = trial.brief[:20_000]
    row["reply"] = trial.reply[:20_000]
    return json.dumps(row, default=str)
