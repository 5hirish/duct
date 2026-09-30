#!/usr/bin/env python3
"""Run the agent eval gate: every case k times, and a verdict per case.

    poetry run python scripts/agent_eval.py                        # every case, k=3
    poetry run python scripts/agent_eval.py --agent insights -k 1  # one trial, a quick look
    poetry run python scripts/agent_eval.py --write-baseline       # a ratchet PR, nothing else

Defaults to DeepSeek V4 Flash on OpenRouter for the agent, about a sixth of
V4 Pro's cost per trial, and GLM 5.3 Flash for the judge, a different family
pinned to hosts that can answer (tests/eval/client.py). Override with
``--provider`` / ``--model`` and ``DUCT_JUDGE_PROVIDER`` / ``DUCT_JUDGE_MODEL``.
A baseline records the model it was measured on, and a run on another model
is INCONCLUSIVE until one is written for it.
The key is ``OPENROUTER_API_KEY`` from the environment, else this instance's
settings: the eval is a run Duct pays for itself.

**It never touches a real database.** ``DATABASE_URL`` is pointed at a
throwaway SQLite before anything reads the settings, because ``.env.local``
names the hosted one and a stray query from a tool would otherwise land
there. Connectors are answered by the case's synthetic account.

Writes ``eval-results.jsonl`` (one line per trial, brief and chat reply
included) and the markdown report, also to ``$GITHUB_STEP_SUMMARY`` when set.
Exits 1 on any FAIL; INCONCLUSIVE is reported and does not fail the run. A
case's trials run at once, so ``--budget`` is checked before each batch, and
judge calls are not counted against it (a verdict is about a cent).

See tests/eval/gate.py for the verdict rules, and never raise k, lower a
threshold or delete a case to turn a run green: loosening the gate is its own
PR, with the numbers.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# Before any import that reads the settings. See the module docstring.
_SCRATCH = Path(tempfile.mkdtemp(prefix="duct-eval-"))
os.environ["DATABASE_URL"] = f"sqlite:///{_SCRATCH / 'eval.db'}"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import argparse  # noqa: E402
import json  # noqa: E402
from datetime import date  # noqa: E402

DEFAULT_PROVIDER = "openrouter"
DEFAULT_MODEL = "deepseek/deepseek-v4-flash"
DEFAULT_BUDGET_USD = 3.0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--agent", default="all", help="insights | all")
    parser.add_argument("--case", default="", help="run one case by id")
    parser.add_argument("-k", "--trials", type=int, default=0, help="trials per case (default 3)")
    parser.add_argument("--provider", default=os.environ.get("DUCT_EVAL_PROVIDER", DEFAULT_PROVIDER))
    parser.add_argument("--model", default=os.environ.get("DUCT_EVAL_MODEL", DEFAULT_MODEL))
    parser.add_argument("--budget", type=float, default=float(os.environ.get("DUCT_EVAL_BUDGET_USD", DEFAULT_BUDGET_USD)))
    parser.add_argument("--no-judge", action="store_true", help="deterministic checks only")
    parser.add_argument("--no-rerun", action="store_true", help="do not re-run an INCONCLUSIVE case")
    parser.add_argument("--write-baseline", action="store_true", help="record this run as the baseline")
    parser.add_argument("--out", default="eval-results.jsonl")
    args = parser.parse_args(argv)

    from db.session import init_db
    import models  # noqa: F401 — registers every table for init_db

    init_db()

    from agents.engines import ProviderKeyRequired, resolve_provider_key
    from agents.models import Provider
    from tests.eval.cases import CASES, cases_for
    from tests.eval.gate import (
        BASELINES, DEFAULT_TRIALS, FAIL, INCONCLUSIVE, CaseResult, baseline_entry,
        baseline_mismatch, decide, load_baselines, report, run_trials, trial_record,
    )

    provider = Provider(args.provider)
    try:
        api_key = os.environ.get(f"{provider.value.upper()}_API_KEY") or resolve_provider_key(
            provider, duct_pays=True
        ).key
    except ProviderKeyRequired:
        print(f"no {provider.value} key: set {provider.value.upper()}_API_KEY", file=sys.stderr)
        return 2

    cases = [CASES[args.case]] if args.case else cases_for(args.agent)
    k = args.trials or DEFAULT_TRIALS
    baselines = load_baselines()
    results: list[CaseResult] = []
    spent = 0.0

    def trials_for(case, start: int, count: int) -> list:
        nonlocal spent
        if spent >= args.budget:
            print(f"  budget ${args.budget:.2f} spent; no more trials", flush=True)
            return []

        def done(trial) -> None:
            state = "pass" if trial.passed else "FAIL: " + "; ".join(trial.failures)
            print(f"  #{trial.n} {state} · ${trial.cost_usd:.3f} · {trial.model_calls} calls · "
                  f"{trial.seconds:.0f}s", flush=True)

        trials = run_trials(
            case, range(start, start + count), provider=provider, model=args.model, api_key=api_key,
            judge=not args.no_judge, on_done=done,
        )
        spent += sum(t.cost_usd for t in trials)
        return trials

    for case in cases:
        print(f"{case.id} ({k} trials)", flush=True)
        base = baselines.get(case.id)
        trials = trials_for(case, 1, k)
        verdict, reason = decide(case.id, trials, base, model=args.model)
        # A baseline from another model stays inconclusive however many more
        # trials run, so it never earns the re-run.
        rerun = not (args.no_rerun or args.write_baseline or baseline_mismatch(base, args.model))
        if verdict == INCONCLUSIVE and trials and rerun:
            print("  inconclusive; three more", flush=True)
            trials += trials_for(case, len(trials) + 1, DEFAULT_TRIALS)
            verdict, reason = decide(case.id, trials, base, model=args.model)
        results.append(CaseResult(case.id, verdict, reason, trials))

    text = report(results, provider=provider.value, model=args.model, spent=spent)
    print("\n" + text)
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(text + "\n")
    with open(args.out, "w", encoding="utf-8") as fh:
        for result in results:
            for trial in result.trials:
                fh.write(trial_record(result, trial, provider=provider.value, model=args.model) + "\n")

    if args.write_baseline:
        recorded = date.today().isoformat()
        for result in results:
            baselines[result.case_id] = baseline_entry(
                result, provider=provider.value, model=args.model, recorded=recorded
            )
        BASELINES.write_text(json.dumps(baselines, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"baseline written to {BASELINES}")
    return 1 if any(r.verdict == FAIL for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
