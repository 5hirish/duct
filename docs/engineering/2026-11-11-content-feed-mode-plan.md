# Content Studio feed mode: plan from what you shipped

**Author:** Shirish Kadam, Claude · **Date:** 2026-11-11

Content Studio plans from intent today: pillars, goals, a direction you type.
This plan adds a second way in, **planning from shipped work**: a feed of what
already happened (merged PRs, releases, Duct's own record, metric milestones,
later RSS, Linear and Notion) proposes the next days of the calendar. You can
start it by hand, or let a schedule propose it for you to accept. The
scheduler it needs is its own record:
[2026-11-11-scheduled-runs-research.md](2026-11-11-scheduled-runs-research.md).

| | Intent-driven (today) | From shipped work (new) |
|---|---|---|
| Starts from | pillars, goals, a typed direction | events since the last feed plan |
| Answers | "what should we say?" | "what did we do that is worth saying?" |
| Triggered by | you, from the plan board | you, a weekly schedule, or a release shipping |
| Produces | a plan proposal | proposed changes to days of the **same** plan, each citing its sources |
| Learns from results | channel mix and plan review shift the next plan | the same, plus results grouped by source kind |

**At a glance**

- **One calendar, two ways to fill it.** Feed mode proposes day changes
  through the existing proposal and Accept path. It never creates a rival plan.
- **#270 folds in.** The parked Daily Reflection's source loader, its
  `gh:`/`art:`/`cs:`/`mem:` refs and its citation check become the front half
  of feed mode. The daily journal UI is dropped.
- **UX first, then the test.** The feed-mode UX ships in Phase 1, and the
  acceptance test runs inside it, not in a no-code prompt beforehand.
- **Auto means auto-propose.** A scheduled run leaves a proposal for you to
  accept. Nothing publishes without a person.
- **A free check gates the model call.** Code decides whether there is enough
  new material, so a quiet week costs nothing.

## The gap competitors leave: one post per event, no plan

| What Ship Social or OpenTweet does | Take it? | In Duct |
|---|---|---|
| Star and fork thresholds as events (OpenTweet) | yes | a cheap, high-engagement event type inside Metric milestones |
| Releases detected within minutes; GitHub Actions or a deploy webhook as a trigger | partly | hourly release check on desktop and hosted; a webhook later, hosted only |
| Review queue by default, auto-scheduling as an opt-in | yes | auto-propose now; auto-accept later through `autonomy_level` (#244) |
| An RSS connector on `github.com/OWNER/REPO/releases.atom` | yes | the RSS reader covers public repos with no GitHub connection at all |
| Evergreen queue that recycles milestone posts with cooldowns | later | "re-run a winner", picked from Duct's own performance data, which they lack |
| A memory so the same release is not posted twice | parity | refs used on an accepted day are excluded |
| Tone extracted from past posts (Ship Social) | parity | voice rules and writing samples exist. Feed setup asks for three past posts when there are none |
| Drafts copied out by hand (Ship Social) | beat it | Duct publishes through PostBridge and Zernio |

Both produce **one post per event, mostly for X**. Neither groups events into
stories, plans across days and channels, or reads outcomes from another tool.
OpenTweet's own blog has a section on keeping automated posts from "looking
like a bot", which says where raw event-to-post output fails. Pricing anchors
the category at $9 to $20 a month (Shiploud $9, OpenTweet from $11.99 or
$19.99 depending on the page), so feed mode keeps users rather than setting
Duct's price. That makes cost per run matter more than features.

## A feed run is three code steps, two model steps, then the existing path

1. **Collect (code).** Pull events since the feed's watermark: GitHub through
   `fetch_github`, Duct's record (briefs, applied change sets with results,
   new memories) through the reflection branch's loader.
2. **Filter (code).** Drop bots and dependency bumps. Drop `ci`, `chore`,
   `test` and internal-only `docs` changes. Fold commits into their PR. Apply
   the private-repo disclosure level (D3).
3. **Gate (code).** Run the model only if there is enough material: at least
   one release, three user-facing merged PRs, a milestone, or an applied
   change with a measured result. Otherwise record "nothing new" and stop.
4. **Stories (model).** Group the events into stories, such as a release, a
   feature built across several PRs, or an experiment and its result. Each
   story cites refs and states an angle. "The lesson" from #270 is one angle.
5. **Place (model, existing planner).** Put the chosen stories on open or
   replaceable days inside the horizon, with channel and format taken from the
   channel mix. Use `revise_plan_days` when a plan covers the period and
   `submit_plan` when none does.
6. **Propose (existing).** The proposal waits in `agent_conversations.meta`
   for Accept, Modify or Reject.
7. **Learn (existing, extended).** A post links to its plan day, so results
   can be grouped by source kind with no new column.

Code loads the feed into the prompt before the model starts. A scheduled run
has no person present, so the runner drops AskUserQuestion and approval-carded
tools. One change follows from that: MCP servers marked `trust_read_only`
(Linear and Notion already are) stay mounted in unattended runs, and every
other MCP server is dropped.

## The UX: provenance before plans

**1. Entry.** The plan board's **Plan** button becomes a split button:
*From your goals* (today's flow) and *From your work*. The first time someone
picks *From your work*, a setup sheet opens:

| Field | Default |
|---|---|
| Sources | GitHub repo if bound, Duct's record always on; Milestones, RSS, Linear and Notion appear when connected, each with a connect link |
| Look back | since the last feed plan (7, 14 or 30 days on the first run) |
| Plan ahead | next 7 days (or 14) |
| Days it may change | 2 of 7, pending and undrafted only |
| Disclosure, private repos | Shipped |
| Channels | the project's active channels |

The sheet ends with *Run now* and *Repeat weekly…*, which opens the schedule
form described in the scheduler record.

**2. What we found.** The session opens on story cards before any plan
exists. Each card has a title, its angle, a line on why it is worth a post,
and source chips (PR #412, Release v1.4, "Signups +18% that week") that open
the PR or the brief. Each card can be kept or skipped, and skipping asks one
optional reason, which becomes a memory. Above the cards, one collapsed line
shows the filter's work: "41 events left out: 18 dependency bumps, 12 chores,
11 CI". In a scheduled run the agent picks the stories itself and shows the
same cards on the proposal.

**3. The proposal.** This is the existing plan-board review, with feed days
marked *From your work*, their source chips, and a replaced day shown as
before and after. Accept, Modify and Reject are unchanged.

**4. After accept.** The chips stay on the day and in the post editor, so the
draft is written with its sources in front of it.

**5. Nothing new.** "6 events since 3 Nov, all chores. Next check Monday
09:00." No model call was made, and the card says so.

## Six decisions, settled

**D1. #270 folds into feed mode.** It closes as superseded, with a pointer
here, once the Phase 1 issue is filed.

**D2. Auto proposes, you accept.** Auto-accept waits for acceptance-rate
evidence, through `autonomy_level` and #244.

**D3. Private repositories get a disclosure level, enforced in code.** The
levels are *Releases only*, *Shipped* (releases plus PRs merged to the default
branch, titles and bodies only; the default for private repos) and
*Everything* (the default for public repos). A draft never contains file
paths, branch names, open issues, diffs or code. The filter enforces this and
the prompt repeats it.

**D4. Default triggers are weekly plus on release.** The weekly run fires
Monday 09:00 in the user's time zone and plans 7 days ahead. The release
check is a free GitHub call each hour. A daily run is opt-in.

**D5. The feed may change at most N days per horizon.** The default is 2 of 7
pending, undrafted days. The existing merge protects past and drafted days.

**D6. RSS is a connector card in the Toolbox, not an MCP server.** It is a
manual connector `rss` on the Mixpanel template, so it gets the Toolbox card,
project binding and agent access through FetchData for free, for Insights as
well as Content Studio. One credential row holds a **list** of feed URLs,
typed one per line into the multiline field `ManualConnectorCard` already
supports. That sidesteps the one-binding-per-type rule on
`project_connectors`, since one binding carries every feed. The row is
encrypted like any other, which suits feeds whose URL is the secret (paid
Substack, private podcast feeds). `list_accounts` returns the feeds, each
verified on save by fetching it once. An MCP server would add a third-party
host and a model tool call for what is one HTTP GET and a parse, while the
gate step needs it in plain code.

Fetching goes through `service/url_safety.py`, because a typed URL is an
SSRF risk. Parsing uses `feedparser`, one dependency that covers RSS 0.9x to
2.0, Atom and their malformed variants. A catalog entity `rss_items` gives the
agents title, link, published date and summary. The card reads Duct's own
`site/changelog/feed.xml`, any blog or Substack, YouTube uploads
(`videos.xml?channel_id=`) and public GitHub releases.

## Feeds, in the order they ship

| Phase | Feed | Pipe | Notes |
|---|---|---|---|
| 1 | GitHub | built | merged PRs, releases, changelog and docs changes |
| 1 | Duct's own record | reflection branch | "the agent proposed it, I approved it, here is what happened": no competitor has this |
| 3 | Metric milestones | connectors exist (GA4, Stripe, RevenueCat, Mixpanel, GitHub stars) | round numbers and best weeks, detected in code. Revenue stays off until the user opts in |
| 3 | RSS/Atom | new manual connector card (D6) | many URLs in one card, readable by every agent |
| 3 | Linear | MCP preset, read-only endpoint `/mcp/readonly` | shipped issues and project updates. Needs a paid Linear plan |
| 3 | Notion | MCP preset | changelog and launch pages. Searching beyond the workspace needs Notion AI |

Later, unfiled: long-form YouTube to shorts. YouTube's caption download needs
a scope that can manage the account, which breaks the read-only rule, so the
route is to detect uploads from the channel RSS feed and cut clips with
Descript's MCP. Meeting notes (Granola) wait for consent rules.

## Cost is measured from the first run, then capped

There is no measured number yet, so this record guesses no dollar figure.
`model_usage` records every call's tokens and cost, so cost per feed run is
known from the first Phase 1 run. Users bring their own key, which means an
unattended run spends their money. Three things limit that: the gate, a
per-project cap (default 6 scheduled runs a month), and the last run's cost
shown on the schedule.

| Metric | Read from | Target | Stop and rethink if |
|---|---|---|---|
| Feed days accepted / proposed | `plan_decision` events | ≥ 50% | under 30% after 4 weekly runs |
| Accepted feed days that get published | `content_posts.status` | ≥ 60% | under 30% |
| Stories skipped / shown | skip memories | under 50% | over 70%: the filter or the gate is wrong |
| Cost per published feed post | `model_usage` ÷ posts | set after 4 runs | rises run over run |
| Scheduled runs the gate skips | run history | 30 to 60% on a quiet repo | 0%: the gate is too loose |
| Private details in a draft | review | 0 | any |

## Three phases, each with an exit test

| Phase | Ships | Permanent surface | Exit test |
|---|---|---|---|
| 1. From your work, manual | split button and setup sheet, collect-filter-gate, story cards, `sources` on a plan day, chips on day and editor, the reflection branch's loader | none: a day lives in the `content_plans.days` JSON, and the setup is saved on the plan's strategy | 3 weekly runs on this repo, ≥ 50% accepted, every feed day cites a ref |
| 2. Scheduled runs | the scheduler, the Scheduled page, unattended feed plans, the release trigger, notices (see the scheduler record) | one table, one migration | 4 unattended weeks with acceptance at least Phase 1's |
| 3. More feeds | RSS/Atom, metric milestones, Linear and Notion through read-only MCP | `feedparser`, the `rss` connector and its catalog entity | a second feed in use on a project other than Duct |

## Issues to file, as one batch

| Title | Labels | Priority | Milestone |
|---|---|---|---|
| Content Studio: plan from your work (feed mode, manual) | `enhancement` `content` `agents` `app` | P1 | Q4 2026 |
| Agents: scheduled runs and a Scheduled page (content feeds, insights briefs) | `enhancement` `backend` `app` `agents` | P1 | Q4 2026 |
| Content Studio: weekly and on-release feed plans | `enhancement` `content` | P1 | Q4 2026, after the two above |
| Content Studio feeds: RSS/Atom and metric milestones | `enhancement` `content` `backend` | P1 | none yet |
| Content Studio feeds: Linear and Notion through read-only MCP | `enhancement` `content` `mcp` | P2 | none |

#270 closes as *not planned: superseded*, with a link to the first issue.

**Feed mode, manual.** *Problem:* a founder who ships weekly posts rarely,
because turning a merged PR into a post is a separate job nobody schedules.
*Non-goals:* publishing without approval, git summaries alone, reading code,
a daily journal. *Smallest version:* GitHub plus Duct's record, a 7-day
horizon, X and LinkedIn, the five UX states above. *Done means:* the Phase 1
exit test.

**Weekly and on-release feed plans.** *Problem:* a manual button gets
forgotten in exactly the weeks that matter. *Non-goals:* auto-accept, a daily
default. *Smallest version:* weekly plus on release, the gate, the cap, a
notice when a proposal is waiting. *Done means:* the Phase 2 exit test.

The scheduler's spec is in its own record.

## Sources

- Daily Reflection: [#270](https://github.com/5hirish/duct/issues/270), commit `a20e5a23` on `feat/reflection-drafts-queue`
- GitHub connector record: [2026-09-28-github-connector-research.md](2026-09-28-github-connector-research.md)
- OpenTweet: [GitHub connector](https://opentweet.io/help/github-connector), [build-in-public automation](https://opentweet.io/help/build-in-public-automation), [tweet when you ship](https://opentweet.io/blog/automatically-tweet-when-you-ship), [auto-post product updates](https://opentweet.io/use-cases/auto-post-product-updates)
- Ship Social: [PeerPush listing](https://peerpush.com/p/ship-social); Shiploud pricing: [Product Hunt](https://www.producthunt.com/products/shiploud/launches)
- Other tools in the category: [BuiltPublic](https://www.producthunt.com/products/builtpublic), [Trace](https://www.producthunt.com/p/trace-29/trace-99e13c22-ddf4-4215-a3c1-2e90d5675c22)
- YouTube captions scope and quota: [captions.download](https://developers.google.com/youtube/v3/docs/captions/download); channel RSS (community-documented): [RSS by platform](https://finder.wprssaggregator.com/rss-feeds/platform/youtube)
- Linear MCP: [Linear MCP server](https://www.developersdigest.tech/mcp-servers/linear); Notion MCP: [supported tools](https://developers.notion.com/docs/mcp-supported-tools)

## Addendum, 2026-11-11: the first trial on this repository

Three fortnights of this repository's real history, read through the GitHub
connector, planned by DeepSeek V4 Pro through OpenRouter, with a stand-in
person keeping the first two stories offered. The acceptance half of the
done-means needs a real person and is still open.

| Window | Read | Stories offered | Feed days | Cited | Private detail | Model calls | Cost |
|---|---|---|---|---|---|---|---|
| Oct 29 to Nov 11 | 40 kept, 347 left out | 5 | 2 | all | none | 3 | $0.10 |
| same, run again | 40 kept, 347 left out | 5 (4 the same) | 2 | all | none | 6 | $0.09 |
| Oct 15 to Oct 28 | 40 kept, 282 left out | 5 | 2 | all | none | 5 | $0.11 |
| Oct 1 to Oct 14 | 0 kept: 25 bot, 8 merge commits | none | none | n/a | n/a | 0 | $0 |

- **The gate earns its place.** The first fortnight of October on `main` was
  only Dependabot. The run stopped at the read and spent nothing.
- **The cap bites on a busy fortnight.** 142 events were cut at 40, mostly
  commits, because releases and pull requests sort first. The stories still
  came out whole; raising the cap is a cost decision, not a fix.
- **Cost came in under the estimate**: $0.09 to $0.11 a run on a $0.66/$1.98
  model, against $0.21 estimated for Gemini Flash. A scheduled run on the same
  model cost $0.05.

