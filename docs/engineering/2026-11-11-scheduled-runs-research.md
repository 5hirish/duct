# Scheduled runs: a small in-process scheduler, not Celery

**Author:** Shirish Kadam, Claude · **Date:** 2026-11-11

Duct needs agent runs that nobody starts by hand: weekly feed plans
([2026-11-11-content-feed-mode-plan.md](2026-11-11-content-feed-mode-plan.md))
and scheduled insights briefs (#544). Nothing in the repository schedules a
run today. The same backend has to run in two places, which rules out most
task queues: hosted on Railway with Postgres, and on a laptop as the desktop
sidecar with SQLite, where it stops when the app quits.

| | Extra processes | Broker | SQLite and Postgres | Per-user schedules | Run history for the UI | Verdict |
|---|---|---|---|---|---|---|
| Celery + beat | worker and beat | Redis or RabbitMQ | no (needs the broker) | needs django-celery-beat or RedBeat | needs a result backend | three processes on a laptop: no |
| Huey | a consumer | none (SQLite storage) | SQLite yes, Postgres not confirmed | no: periodic tasks are decorators fixed at import | partial | per-user schedules need our own table anyway |
| Procrastinate, Chancy, pg_cron | worker, or none | Postgres | Postgres only | yes | yes | fails desktop |
| APScheduler 3.11 | none, in-process | none | yes, through its SQLAlchemy job store | yes: add, pause, resume | no | close; see below |
| APScheduler 4 | none | none | yes | yes | partial | still pre-release (4.0.0a6), no migration path from 3.x stores |
| **Our own ticker** | none, an asyncio task in `lifespan` | none | yes | yes | yes, it *is* the UI's state | **recommended** |

**At a glance**

- **Runs here are few and long.** A handful a week per project, each a
  multi-minute agent session. That calls for a clock, not a queue.
- **Our own ticker reuses a pattern Duct already runs.** The memory
  consolidation sweep is a loop in `server.py`'s `lifespan` that wakes every
  300 seconds. The scheduler is one more such loop over one table.
- **APScheduler loses on state, not on features.** It would hold the schedule
  in its own pickled job store while the UI, pause state and history live in
  ours: two sources of truth for about 100 lines saved.
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
*Non-goals:* a job queue, a broker, sub-hourly presets, custom cron, running
with the desktop app closed. *Smallest version:* the table, the ticker, the
claim, catch-up, run history in `activity_logs`, and the Scheduled page with
Run now, Pause and Edit. *Done means:* a weekly schedule fires for 2 weeks on
hosted and on desktop, with no double run across a deploy, and every skip
shows its reason in History.

## Sources

- Claude Code Desktop local scheduled tasks (sleep, catch-up, the management UI): [code.claude.com](https://code.claude.com/docs/en/desktop-scheduled-tasks)
- APScheduler 4 pre-release status and migration: [migration guide](https://apscheduler.readthedocs.io/en/master/migration.html), [version history](https://apscheduler.readthedocs.io/en/master/versionhistory.html)
- Huey storage backends: [Huey](https://openapps.pro/packages/huey); Chancy (Postgres only): [Django forum](https://forum.djangoproject.com/t/chancy-a-batteries-included-task-queue-built-on-postgres-with-easy-django-integration/41701)
- croniter under Pallets Eco: [ecosyste.ms](https://awesome.ecosyste.ms/projects/github.com%2Fpallets-eco%2Fcroniter); cronsim: [ecosyste.ms](https://awesome.ecosyste.ms/projects/github.com%2Fcuu508%2Fcronsim)
- launchd folds missed calendar intervals into one run after wake: [launchd-dev list](https://lists.macosforge.org/pipermail/launchd-dev/2009-June/000543.html)
