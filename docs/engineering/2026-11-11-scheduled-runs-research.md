# Scheduled runs: a small in-process scheduler, not Celery

**Author:** Shirish Kadam, Claude · **Date:** 2026-11-11

Duct needs agent runs that nobody starts by hand: weekly feed plans
([2026-11-11-content-feed-mode-plan.md](2026-11-11-content-feed-mode-plan.md))
and scheduled insights briefs (#544). Nothing in the repository schedules a
run today. Schedules live in the database like every other record. The hard
requirement is **execution**: the same code has to fire and run them in the
cloud (Railway, Postgres, deploys that restart the process) and locally (the
desktop sidecar, SQLite, a process that exists only while the app is open).

| | Executes in the desktop sidecar | Executes on Railway | Moving parts added | Verdict |
|---|---|---|---|---|
| Celery + beat | no: a worker, beat and a broker beside a sidecar the shell starts and stops | yes | Redis or RabbitMQ, two services | cloud only |
| Huey | only with a second consumer process the shell must also manage | yes | a consumer | awkward locally; sync workers around an async runner |
| Procrastinate, Chancy, pg_cron | no: Postgres only | yes | a worker | cloud only |
| APScheduler 3.11 | yes, in-process | yes, in-process | its own job store beside our schedule table | works, but see below |
| APScheduler 4 | yes | yes | the same | still pre-release (4.0.0a6), no migration path from 3.x stores |
| **Our own ticker** | yes, an asyncio task in `lifespan` | yes, the same task, or the same module as a worker service | none | **recommended** |

**At a glance**

- **Runs here are few and long.** A handful a week per project, each a
  multi-minute agent session. That calls for a clock, not a queue.
- **Our own ticker reuses a pattern Duct already runs.** The memory
  consolidation sweep is a loop in `server.py`'s `lifespan` that wakes every
  300 seconds. The scheduler is one more such loop over one table.
- **APScheduler runs in both, but would double the state.** Its SQLAlchemy
  store pickles each job into its own table, beside the schedule row the UI
  edits, pauses and shows history for. Every edit then writes two places,
  for about 100 lines of firing logic saved.
- **One code path, two hosts.** The loop is identical in the cloud and on a
  laptop. Only *where it is hosted* differs, and the cloud can later move it
  into its own worker service without changing a line of it.
- **No cron library in v1.** The presets (hourly, daily, weekdays, weekly,
  manual) are computed with stdlib `zoneinfo`. Custom cron comes later through
  `cronsim`, a small pure-Python evaluator from Healthchecks, rather than
  `croniter`, whose maintenance status is unclear.

## How it works: one loop, one table, the existing audit log

1. **Tick.** Every 60 seconds the loop selects schedules that are enabled and
   whose `next_run_at` has passed.
2. **Claim.** `UPDATE … SET next_run_at = <next> WHERE id = ? AND
   next_run_at = <seen>`. Only one claimant wins, on SQLite and Postgres
   alike, so a second Railway replica or an overlapping tick cannot double-run.
3. **Run.** The agent run starts as an asyncio task, one at a time per
   project and two at a time overall. A schedule whose previous run is still
   going records "skipped: previous run in progress".
4. **Record.** Each run, including skipped ones, is an `activity_logs` row
   with actor `auto` and the schedule's id, linked by `conversation_id` to the
   session it produced. Cost comes from `model_usage` for that conversation.
   No second history table: `docs/engineering/data-model.md` asks for exactly
   this check before adding one.
5. **Catch up.** On startup and on wake, a schedule that missed runs in the
   last 7 days gets **one** run for the most recent missed time, and older
   misses are discarded. That is Claude Code Desktop's rule for its local
   tasks. A catch-up still plans from today, not from the missed date.

The one new table, `agent_schedules`, holds project, agent and mode, config
(sources, horizon, days it may change), trigger (preset, time, time zone, plus
`on_release`), enabled, `next_run_at`, the feed watermark, the monthly cap and
who created it.

## What the loop builds, and what it leaves to task queues

Task-queue features, measured against a few long runs a week per project,
each producing a proposal a person accepts.

| Feature | Build? | What Duct does instead, or how |
|---|---|---|
| Process, thread or greenlet pools | **no** | asyncio tasks in one process, since a run waits on model calls. A semaphore allows one run per project and two overall. Sync tools already go through `run_in_threadpool`. The later cloud worker is a whole process, not a pool |
| Run at a given time, or after a delay | **yes** | it is `next_run_at`. A delay is `now + delay`; "Run once at" and a retry's backoff are the same field |
| Recurring, like crontab | **yes, as presets** | hourly, daily, weekdays, weekly, at a wall-clock time in a named time zone, so DST moves with the user. Custom cron later through `cronsim` |
| Automatic retry | **yes, narrow** | classify before retrying. Transient (model 429 or 5xx, network, interrupted by a deploy) retries once at +15 minutes. Deterministic (credential expired, monthly cap, gate found nothing new) never retries, and shows *Needs you* or the reason |
| Prioritisation | **no** | there is no queue to order. *Run now* skips the ticker and starts at once, which is the only priority anyone needs |
| Result storage | **yes, as records we already keep** | the result is the conversation and its proposal. The outcome, reason, cost and duration go on an `activity_logs` row. No result backend, no pickled return values |
| Expiration | **yes, two kinds** | a missed run older than 7 days is discarded (the catch-up rule). And one open proposal per schedule: a new run supersedes an unanswered one instead of stacking a second |
| Locking | **yes** | the compare-and-set claim, the renewed lease, and the per-project semaphore |
| Rate limits | **yes, as budgets** | a monthly run cap per project and a cost ceiling per run. Provider 429s are already handled by the quota-aware tier ladder, and GitHub's limits by its client |
| Timeouts | **yes** | a wall-clock limit per run (15 minutes to start with). On expiry the run is cancelled and recorded as *failed: timeout* |
| Pipelines and chains | **no** | the feed run is a fixed sequence (collect, filter, gate, model) inside one function. What follows a proposal is started by a person's Accept, not by a chain |
| Groups and chords | **no** | fan-out already lives inside the agent (the pillar sub-agents), and collecting several feeds is one `asyncio.gather` |

Seven things no task queue gives, which the loop needs anyway:

1. **A gate before the run.** A cheap check in code ("anything new since the
   watermark?") decides whether a model call happens at all.
2. **Event triggers.** "On release" is a check function run at the tick. The
   trigger kinds are a registry, so "on milestone" is one more entry.
3. **Catch-up on wake, detected from the clock.** The sidecar cannot see the
   laptop sleep, but a wall-clock jump much larger than the tick says it slept.
   Startup and that jump both run the catch-up rule.
4. **Jitter.** A fixed offset of 0 to 10 minutes derived from the schedule's
   id, so hosted users' 09:00 runs do not all hit the model APIs together.
   Claude Code Desktop staggers its tasks the same way.
5. **An idempotency key.** Each occurrence is `(schedule id, scheduled-for
   time)`. The claim already lets one process take it, and the key is written
   on the run's conversation, which a retry checks first. So a retry can never
   leave two proposals for one occurrence.
6. **Permission checked at fire time.** A run acts as the schedule's creator,
   and only while that person is still a project member. A creator who has
   been removed disables the schedule. This is the membership rule from the
   root `AGENTS.md`, applied to a run nobody watches.
7. **A credential precheck.** A bound connector that needs reauthorising sets
   *Needs you* before any model call, rather than failing partway through.

Cancelling a running run, and pausing or resuming a schedule, come from the
Scheduled page. Each run is one span in the existing OpenTelemetry traces, so
Jaeger shows a slow or failed scheduled run like any other.

## Execution is the same code in the cloud and on a laptop

| | Cloud (Railway) | Local (desktop sidecar) |
|---|---|---|
| Where the loop runs | inside the uvicorn process in v1; its own Railway service later, same module, started as `python -m` | inside the sidecar, always |
| Database | Postgres | SQLite |
| Can reach | server-residency credentials, hosted model keys | everything above, plus device-residency credentials and a local model (Ollama) |
| What interrupts a run | a deploy restarting the process | the app quitting, or the machine sleeping |
| Two copies running at once | yes, briefly: Railway starts the new deploy before stopping the old one | no |

Three rules make one code path safe in both columns:

1. **A schedule executes only in the backend that owns its row.** A schedule
   made in the desktop app runs on that computer, never in the cloud, so
   device credentials and the user's local model never leave it. A schedule
   made in hosted Duct runs in the cloud. That keeps the open-source desktop
   a real alternative to the cloud product, and the Scheduled page shows each
   schedule's host ("This computer" or "Duct cloud"), as Claude Desktop does.
2. **The claim, plus a lease.** The claim in step 2 settles the deploy
   overlap. A run also takes a lease that it renews every minute. A run whose
   lease lapses was killed by a deploy or by the app quitting, so the next
   tick marks it *interrupted* and retries it once. Retrying is safe because
   a run's output is a proposal, never a publish.
3. **Long runs leave the web process when they need to.** A multi-minute
   agent run inside uvicorn shares the event loop with requests. At a few runs
   a week that is fine. When run history shows request latency suffering, or
   deploys interrupting runs, the cloud starts the same loop as a worker
   service, and the web process stops starting it (one setting, documented in
   `backend/.env.example`). The desktop never needs the split.

## The laptop-shut downside, and what softens it

A desktop schedule runs only while the app is open and the machine is awake.
Claude Code Desktop has the same limit and says so plainly: "If your computer
sleeps through a scheduled time, the run is skipped". Its answer is the
one-run catch-up above.

| Option | What it buys | Cost | When |
|---|---|---|---|
| One-run catch-up on launch and wake | Monday's plan arrives when the laptop opens | none beyond the ticker | v1 |
| Keep running in the menu bar when the window closes | runs survive a closed window | the sidecar outlives the window; a tray icon | Phase 2b |
| Keep computer awake (off by default) | runs survive idle sleep, not a closed lid | a power assertion while a run is due | Phase 2b, only if the history shows sleep skips |
| launchd agent (macOS) or Task Scheduler (Windows) starting a headless sidecar | runs with the app closed; macOS folds missed times into one run after wake; Windows can wake the machine | a headless sidecar and keychain access without the shell: real work | only if users ask |
| Hosted Duct | runs with the laptop off | it is the cloud product | exists |

## The Scheduled page: list, pause, run now, history

One page lists every schedule across agents, reached from the sidebar and
from the plan board's "Next feed plan: Mon 09:00" line.

| Column | Example |
|---|---|
| Name | Weekly plan from your work |
| Agent and project | Content Studio · Duct |
| Trigger | Weekly, Mon 09:00 Europe/Berlin, and on release |
| Status | Active, Paused, or Needs you (reconnect GitHub) |
| Next run | Mon 17 Nov, 09:00 |
| Last run | Proposed 3 days, waiting on you · 2 min · its cost |
| This month | 3 of 6 runs |

The detail view has **Run now**, **Pause / Resume**, **Edit** (trigger,
sources, horizon, days it may change, monthly cap) and **Delete**. Its
**History** lists every run with its outcome, linked to the proposal: plan
proposed, nothing new (gate), skipped (app closed, previous run still going,
monthly cap reached), caught up late, or failed (credential expired, model
error). Notices: an OS notification and the in-app "Needs you" (#171) when a
proposal is waiting, and a notice when a catch-up run starts.

## Issue spec

**Agents: scheduled runs and a Scheduled page.** *Problem:* feed plans and
#544 both need runs nobody starts, and nothing schedules a run today.
*Non-goals:* a job queue, a broker, a separate cloud worker (until history
asks for it), sub-hourly presets, custom cron, running with the desktop app
closed, a desktop schedule executing in the cloud.
*Smallest version:* the table, the ticker embedded in both hosts, the claim and lease, catch-up, run history in `activity_logs`, and
the Scheduled page with each schedule's host, Run now, Pause and Edit. *Done means:* a weekly schedule fires for 2 weeks on
hosted and on desktop, with no double run across a deploy, and every skip
shows its reason in History.

## Sources

- Claude Code Desktop local scheduled tasks (sleep, catch-up, the management UI): [code.claude.com](https://code.claude.com/docs/en/desktop-scheduled-tasks)
- APScheduler 4 pre-release status and migration: [migration guide](https://apscheduler.readthedocs.io/en/master/migration.html), [version history](https://apscheduler.readthedocs.io/en/master/versionhistory.html)
- Huey storage backends: [Huey](https://openapps.pro/packages/huey); Chancy (Postgres only): [Django forum](https://forum.djangoproject.com/t/chancy-a-batteries-included-task-queue-built-on-postgres-with-easy-django-integration/41701)
- croniter under Pallets Eco: [ecosyste.ms](https://awesome.ecosyste.ms/projects/github.com%2Fpallets-eco%2Fcroniter); cronsim: [ecosyste.ms](https://awesome.ecosyste.ms/projects/github.com%2Fcuu508%2Fcronsim)
- launchd folds missed calendar intervals into one run after wake: [launchd-dev list](https://lists.macosforge.org/pipermail/launchd-dev/2009-June/000543.html)
