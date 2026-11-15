// Documents, the activity feed and the desk's thread list, answered from the
// story: Solo's week as the artifact store, the activity log and the
// conversation table would hold it on Monday 14 Sep, 09:30 in Madrid
// (07:30 UTC, the capture clock).
//
// Shapes are the backend's, field for field:
//   artifact rows   routes/artifacts.py _serialize (+ version_count on the
//                   list, + structured_json on GET /{id}); list order is
//                   service/artifact_store.py latest_versions (head
//                   created_at, newest first)
//   brief meta      agents/insights/brief.py brief_artifact_version
//   report meta     agents/insights/report.py report_artifact_version
//   audit row       service/artifact_store.py audit_report_version
//   document row    service/artifact_store.py create_artifact_group
//   activity        routes/activity.py _serialize / list_activity
//   summaries       service/artifact_store.py persist_artifact_version,
//                   service/execution/service.py, routes/execution.py,
//                   routes/project_connectors.py, service/mcp_server/tools.py
//   conversations   routes/agents.py _conversation_summary, ordered by
//                   last_active_at (agents/content/persistence.py)
//
// Not in the feed, because the backend writes no row for them: a memory
// saved, a post drafted, a thread started. The activity log has categories
// for execution, artifact, project, connector, content (failed publishes
// only) and schedule, and nothing else.
//
// GET …/content serves the stored bytes with the row's content_type
// (text/html, text/markdown), not JSON: those values here are strings.

// Ids are UUIDs on the wire. Fixed ones, so a desk row can point at its
// thread and its document and a re-run of the shots gets the same page.
const uuid = (prefix, n) => `${prefix}-0000-4000-8000-${String(n).padStart(12, "0")}`;
const artifactId = (n) => uuid("a7f1c0de", n);
const groupId = (n) => uuid("a7f19000", n);
const convId = (n) => uuid("c0a7c0de", n);
const activityId = (n) => uuid("ac71c0de", n);
// The document the canvas opens: the signups brief, two versions and pinned.
export const SHOWCASE_ARTIFACT_ID = artifactId(2);
// The dict routes hand back isoformat() of an aware datetime.
const at = (iso) => `${iso}+00:00`;

// Freehand is the audit agent's default (agents/audit/schema.py ReportMode):
// the report is the story's HTML document and the library draws its first
// screen. "template" stores AUDIT_REPORT as structured_data instead, which the
// viewer draws with AuditReportV1 and the library shows as an icon with the
// score on its pill.
const AUDIT_MODE = "freehand";

// The same token toolbox.mjs lists under Settings › Connect your AI agent,
// and the Clarity binding it lists on the Toolbox (uuid(201): clarity sorts
// first by connector_type).
const MCP_TOKEN = { id: "5010c0de-0000-4000-8000-000000000401", name: "Claude Code (duct)" };
const CLARITY_BINDING = { id: "5010c0de-0000-4000-8000-000000000201", accountId: "q4xm7slo2b", name: "Solo Android" };

const bytes = (text) => Buffer.byteLength(text, "utf8");
// Python's len(): code points, not UTF-16 units.
const chars = (text) => [...text].length;
const slugify = (text) => text.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 60).replace(/-+$/, "");

// difflib.unified_diff(n=3) for two versions that differ line for line,
// which is all the one revision below does.
function unifiedDiff(before, after, fromVersion, toVersion) {
  const a = before.split("\n");
  const b = after.split("\n");
  if (a.length !== b.length) throw new Error("unifiedDiff: versions must have the same line count");
  const changed = a.map((line, i) => line !== b[i]).flatMap((d, i) => (d ? [i] : []));
  if (!changed.length) throw new Error("unifiedDiff: the versions are identical");
  const out = [`--- v${fromVersion}`, `+++ v${toVersion}`];
  let i = 0;
  while (i < changed.length) {
    let j = i;
    while (j + 1 < changed.length && changed[j + 1] - changed[j] <= 6) j += 1;
    const start = Math.max(0, changed[i] - 3);
    const end = Math.min(a.length, changed[j] + 4);
    const len = end - start;
    out.push(`@@ -${start + 1},${len} +${start + 1},${len} @@`);
    for (let k = start; k < end; k += 1) {
      if (a[k] === b[k]) out.push(` ${a[k]}`);
      else out.push(`-${a[k]}`, `+${b[k]}`);
    }
    i = j + 1;
  }
  return out.join("\n");
}

// The scheduled brief from the Monday before (routes/generate.py, no
// conversation): the one the memory timeline cites as "the 7 Sep signups
// brief" (MEMORIES mem-brief). Markdown, because that is what the model wrote
// that morning; brief.py sniffs the format from the bytes.
const LAST_WEEK_BRIEF_MD = `# Signups held at 892. The paid half is the half that leaves.

Week of 1–7 Sep 2026 · Google Ads, GA4, Stripe

**The short version.** Signups were 892 against the 900 target and MRR rose to €17,850. Performance Max brought 104 of those signups at €17.80 each, and PMax signups had 7-day retention of 31% vs 54% organic. Watch it for one more week before moving budget.

| | 1–7 Sep | 25–31 Aug |
|---|---|---|
| Signups | 892 | 871 |
| MRR | €17,850 | €17,520 |
| CPA · Performance Max | €17.80 | €16.20 |
| CPA · Brand search | €8.90 | €9.10 |

## Findings

- **Performance Max cohorts churn faster than organic.** 31% retained at day 7 against 54%, on the cohorts from 18–24 Aug, before the Android rebuild.
- **The Android rebuild shipped on 2 Sep.** Retention comparisons across it are unreliable until two clean weeks are in, so this brief compares the cohorts before it.
- **The template hunters stopped spending.** The negatives added on 5 Sep (“budget template excel”, “free invoice generator”) took both terms to zero.

## Next week

1. Re-check the PMax cohort on the first full week after the rebuild.
2. Keep brand search on its €40 cap. It is still the cheapest signup on the account.
`;

// What Maya asked the audit chat for after the report: the outline for its
// fourth priority, written with CreateArtifact (agents/core/artifact_tools.py).
// Every number is the audit's own.
const OUTLINE_MD = `# Quarterly tax estimates for freelancers: guide outline

**Target query:** “quarterly tax estimate freelancer”, 1,300 searches a month. Ledgerly ranks #3, Tallyo #5, Solo has no page.
**Cluster:** Quarterly estimates, 3.9k searches a month, 0 pages today.
**Links in from:** the tax calendar, *How much to set aside for tax*, and the 12% rule post.

## Working title

How to estimate quarterly tax as a freelancer (without a spreadsheet)

## Outline

1. **The short answer.** What a quarterly estimate is, who pays one, and the four dates.
2. **Work out this quarter's number.** Income so far, minus expenses, times your rate. One worked example: €14,200 invoiced, €2,100 in expenses.
3. **Why 12% of every payment beats a guess in April.** Links to the 12% rule.
4. **Paid late, or paid short?** What happens, and how to catch up next quarter.
5. **Let Solo keep the pot.** The tax account, filled on every payment that lands.

## On the page

- A calculator above the fold: both competitors lead with one.
- FAQ schema for the four “when is it due” questions.
- An author and a date at the top. Twelve guides are missing both.

## Not in scope

Country-by-country rules past the dates. Link to each tax office's own calendar instead.
`;

// The Analytics tab's report (routes/content_reports.py): the growth_overview
// template over the last 30 days to yesterday (utils/dates.py last_n_days),
// refreshed daily, so it is on its second version this morning. The same
// month the briefs describe, from the sources that template takes and Solo has.
function growthReport(STORY) {
  const n = STORY.numbers;
  const window = "15 Aug – 13 Sep 2026";
  const vs = "vs 16 Jul – 14 Aug";
  // Sessions by day: weekday rhythm, a step up once PMax widened to Android
  // on 4 Sep. Written out rather than generated, so the chart is the same
  // every run.
  const sessions = [
    780, 812, 845, 828, 801, 640, 612, 798, 830, 861, 842, 818, 655, 630,
    815, 849, 872, 860, 838, 670, 641, 990, 1024, 1058, 1031, 1002, 820, 788, 1046, 1080,
  ];
  const day = (i) => {
    const d = new Date(Date.UTC(2026, 7, 15 + i));
    return d.toISOString().slice(0, 10);
  };
  const sources = [
    { id: "gsc", label: "Search Console", status: "read", window, note: "" },
    { id: "ga4", label: "Google Analytics", status: "read", window, note: "" },
    { id: "google_ads", label: "Google Ads", status: "read", window, note: "" },
    { id: "publishers", label: "Social posts", status: "read", window, note: "" },
  ];
  const block = (b) => ({
    source: "", window: "", insight_note: "", rows: [], x_field: "", y_field: "", group_by: "", y_unit: "",
    kpis: [], signals: [], actions: [], ...b,
  });
  return {
    title: "Organic is up a fifth; paid is buying churn",
    date_from: "2026-08-15",
    date_to: "2026-09-13",
    verdict: `Organic clicks rose 21% to 7,920 and the tax pages turned them into trials. Signups fell 6% anyway: Performance Max bought them at €${n.pmaxCpa} against the €${STORY.targets.cpa} target, and its Android users leave within a week.`,
    summary: "Sessions are up 7%, almost all of it Cross-network since PMax widened to Android on 4 Sep. Those visitors sign up and stall at Connect bank, where the 2 Sep rebuild put a permission prompt. Organic grew on the tax cluster; the invoicing pages win clicks on page two and lose them at the pricing paragraph.",
    takeaway: "Fix the Connect bank screen before buying more Android users.",
    sources,
    blocks: [
      block({
        block_id: "headline", block_type: "kpi_strip", title: "Headline numbers",
        kpis: [
          { label: "Organic clicks", value: "7,920", delta: `+21% ${vs}`, tone: "good", source: "Search Console" },
          { label: "Sessions", value: "26,300", delta: `+7% ${vs}`, tone: "good", source: "Google Analytics" },
          { label: "Signups", value: "3,540", delta: `−6% ${vs}`, tone: "bad", source: "Google Analytics" },
          { label: "Paid spend", value: "€9,480", delta: `+12% ${vs}`, tone: "neutral", source: "Google Ads" },
          { label: "Blended CPA", value: "€14.60", delta: `+€2.60 ${vs}`, tone: "bad", source: "Google Ads" },
          { label: "Post views", value: "52,400", delta: `+38% ${vs}`, tone: "good", source: "Social posts" },
        ],
        insight_note: "Traffic and spend moved up; signups moved down. The gap opens after 4 Sep, on Android.",
      }),
      block({
        block_id: "traffic", block_type: "time_series", title: "Visits over the period",
        source: "Google Analytics", window,
        rows: sessions.map((s, i) => ({ date: day(i), sessions: s })),
        x_field: "date", y_field: "sessions", y_unit: "sessions",
        insight_note: "A step up on 4 Sep, the day PMax started serving on Android. Signups did not step with it.",
      }),
      block({
        block_id: "channels", block_type: "bar_chart", title: "Where visitors came from",
        source: "Google Analytics", window,
        rows: [
          { channel: "Organic Search", sessions: 9840 }, { channel: "Cross-network", sessions: 6120 },
          { channel: "Direct", sessions: 4310 }, { channel: "Paid Search", sessions: 2650 },
          { channel: "Organic Social", sessions: 2240 }, { channel: "Referral", sessions: 1140 },
        ],
        x_field: "channel", y_field: "sessions", y_unit: "sessions",
        insight_note: "Cross-network is Performance Max: 23% of sessions, and the channel with the lowest day-7 retention.",
      }),
      block({
        block_id: "queries", block_type: "table", title: "Search: queries and pages that moved",
        source: "Search Console", window,
        rows: [
          { query: "freelancer tax calendar 2026", clicks: 1140, impressions: 18900, ctr: "6.0%", position: 3.1 },
          { query: "solo budget app", clicks: 880, impressions: 2400, ctr: "36.7%", position: 1.1 },
          { query: "freelance invoice template", clicks: 690, impressions: 31200, ctr: "2.2%", position: 11.2 },
          { query: "how much to set aside for tax freelance", clicks: 420, impressions: 14800, ctr: "2.8%", position: 12.4 },
          { query: "budget app for freelancers", clicks: 310, impressions: 16100, ctr: "1.9%", position: 13.0 },
        ],
        x_field: "query", y_field: "clicks",
        insight_note: `The tax pages earn the trials; the invoicing pages earn the clicks. Three of these sit on page two. ${n.blogPost} needs nothing.`,
      }),
      block({
        block_id: "posts", block_type: "bar_chart", title: "Posts by views",
        source: "Social posts", window,
        rows: [
          { post: "What a freelancer's September looks like (TikTok)", views: 14200 },
          { post: "Late-paying client? Say this. (TikTok)", views: 11800 },
          { post: "Quarterly taxes in 30 seconds (TikTok)", views: 9400 },
          { post: "Your first invoice, line by line (Instagram)", views: 6100 },
          { post: "Net 14 or net 30? (Instagram)", views: 4300 },
        ],
        x_field: "post", y_field: "views", y_unit: "views",
        insight_note: "Engagement 4.6% overall. The two September posts did a third of the month's views on their own.",
      }),
      block({
        block_id: "product", block_type: "kpi_strip", title: "Product",
        source: "Google Analytics", window,
        kpis: [
          { label: "Activation · Android", value: n.activation.androidAfter, delta: `from ${n.activation.androidBefore} before 2 Sep`, tone: "bad", source: "Google Analytics" },
          { label: "Activation · iOS", value: n.activation.iosAfter, delta: `from ${n.activation.iosBefore} before 2 Sep`, tone: "neutral", source: "Google Analytics" },
          { label: "Trial starts", value: "1,020", delta: `−11% ${vs}`, tone: "bad", source: "Google Analytics" },
        ],
        insight_note: "Activation is reaching Connect bank within a day of signing up. Only Android moved.",
      }),
      block({
        block_id: "signals", block_type: "signal_list", title: "What moved",
        signals: [
          { id: "s1", kind: "risk", title: "Performance Max is buying churn", impact: `€${n.pmaxCpa} a signup against the €${STORY.targets.cpa} target; its Android signups keep 31% at day 7 against 54% organic.`, action: "Pause it until the Connect bank screen is fixed.", source: "Google Ads" },
          { id: "s2", kind: "risk", title: "Android activation fell on 2 Sep", impact: `${n.activation.androidBefore} to ${n.activation.androidAfter} reached Connect bank within a day; iOS held at ${n.activation.iosAfter}.`, action: "Ask for the permission after the first budget.", source: "Google Analytics" },
          { id: "s3", kind: "win", title: "The tax pages carry organic", impact: "Organic clicks +21%; the tax calendar ranks #3 and the tax cluster earns 61% of organic trials.", action: "Link the page-two keywords from the tax guides.", source: "Search Console" },
          { id: "s4", kind: "watch", title: "Post views up 38% on the same cadence", impact: "Twelve posts against eleven; views per post up a quarter.", action: "Hold three a week.", source: "Social posts" },
        ],
      }),
      block({
        block_id: "actions", block_type: "action_list", title: "What to do next",
        actions: [
          { id: "a1", title: "Pause Performance Max", detail: "Proposed on 12 Sep and waiting for you on the review queue.", size: `${n.pmaxSpend} a week at €${n.pmaxCpa} a signup`, effort: "one click, reversible", check: `blended CPA back under €${STORY.targets.cpa} within two weeks`, owner: STORY.user.name.split(" ")[0] },
          { id: "a2", title: "Move the Android permission prompt", detail: "Ask after the first budget, not before Connect bank.", size: "every Android signup since 2 Sep", effort: "an app release", check: "Android activation back above 55%", owner: "App team" },
          { id: "a3", title: "Merge the two invoice-template pages", detail: "They split the clicks for “freelance invoice template”.", size: "2,400 searches a month, now at #11", effort: "1–3 days", check: "position under 10 within a month", owner: STORY.user.name.split(" ")[0] },
        ],
      }),
    ],
    could_not_check: [
      "Revenue by acquisition source: Stripe does not feed this report.",
      "Signups by campaign inside the app: no product analytics connected.",
    ],
    method_note: "15 Aug – 13 Sep against 16 Jul – 14 Aug. Sessions and signups are GA4's (sign_up key event). Brand queries stay in the query table.",
  };
}

export function routes(story) {
  const { STORY, BRIEF_HTML, PAID_BRIEF_HTML, PRODUCT_BRIEF_HTML, AUDIT_REPORT, AUDIT_REPORT_HTML, CHANGE_SET, PRODUCT_CHANGE_SET, CHANGE_SET_HISTORY } = story;
  const projectId = STORY.project.id;
  const week = STORY.week.label;
  const site = STORY.company.site;

  // ---------------------------------------------------------------------
  // Threads (agent_conversations). Insights binds no workspace artifact, its
  // mode is the request's focus or "insights", and the title is the first
  // thing the person typed (routes/agents.py _create_insights_session).
  // ---------------------------------------------------------------------
  const C = {
    organic: convId(1),
    spend: convId(2),
    activation: convId(3),
    signups: convId(4),
    cpa: convId(5),
    audit: convId(6),
  };
  const conversation = ({ id, agentType = "insights", mode = "insights", title, runStatus = "idle", pinned = false, lastSeq, created, active }) => ({
    id,
    agent_type: agentType,
    project_id: projectId,
    mode,
    artifact_type: null,
    artifact_id: null,
    title,
    status: "active",
    run_status: runStatus,
    run_error: null,
    pinned,
    last_seq: lastSeq,
    meta: {},
    created_at: at(created),
    last_active_at: at(active),
  });
  // Newest activity first, as list_conversations orders them. The organic
  // question is parked on its clarifying card; the rest finished their turn.
  const threads = [
    conversation({ id: C.organic, title: "Which content actually converts?", runStatus: "paused", lastSeq: 9, created: "2026-09-14T07:12:40", active: "2026-09-14T07:14:05" }),
    conversation({ id: C.spend, title: "Where is the ads budget leaking this week?", lastSeq: 31, created: "2026-09-14T06:38:10", active: "2026-09-14T06:52:30" }),
    conversation({ id: C.activation, title: "Why did activation drop after the Android onboarding release?", lastSeq: 29, created: "2026-09-13T07:01:20", active: "2026-09-13T07:16:45" }),
    conversation({ id: C.signups, title: "Why are signups down when ROAS is up?", pinned: true, lastSeq: 38, created: "2026-09-12T06:54:00", active: "2026-09-12T07:24:10" }),
    conversation({ id: C.cpa, title: "Is €12 a realistic CPA for Performance Max?", lastSeq: 16, created: "2026-08-21T09:01:00", active: "2026-08-21T09:19:30" }),
  ];

  // ---------------------------------------------------------------------
  // Artifact rows, one per version.
  // ---------------------------------------------------------------------
  const rows = [];
  const contents = {}; // artifact id -> stored text, for GET …/content
  const add = (row, content) => {
    rows.push(row);
    if (content != null) contents[row.id] = content;
    return row;
  };
  const row = ({ n, group, version = 1, conversationId = null, agentType, kind, contentType, title, slug, filename, content = null, summary = "", pinned = false, meta, structured = {}, created }) =>
    add({
      id: artifactId(n),
      group_id: groupId(group),
      slug,
      version,
      project_id: projectId,
      conversation_id: conversationId,
      agent_type: agentType,
      kind,
      content_type: contentType,
      title,
      filename,
      has_content: content != null,
      size_bytes: content != null ? bytes(content) : 0,
      summary,
      pinned,
      meta,
      created_at: at(created),
      // Read off below: GET /{id} adds it, the list and /versions never do.
      _structured: structured,
    }, content);

  // An insights brief (agents/insights/brief.py): text/html or text/markdown
  // by the bytes, kind "brief", slug and file stem both slugify(title).
  const brief = ({ n, group, version = 1, conversationId, title, content, label, summary, pinned, created }) => {
    const format = /^\s*(<!doctype|<html)/i.test(content) ? "html" : "markdown";
    const stem = slugify(title);
    return row({
      n, group, version, conversationId, agentType: "insights", kind: "brief",
      contentType: format === "html" ? "text/html" : "text/markdown",
      title, slug: stem, filename: `${created.slice(0, 10)}_${stem}_v${version}.${format === "html" ? "html" : "md"}`,
      content, summary, pinned,
      meta: { label: label || `Version ${version}`, format, chars: chars(content) },
      created,
    });
  };

  // The signups brief, twice: v2 is the follow-up in the same thread ("How
  // long has the Android retention been like this?") adding when the cohort
  // started. v1 is the same document without that sentence.
  const COHORT = " The cohort started on 4 Sep, two days after the onboarding rebuild.";
  if (!BRIEF_HTML.includes(COHORT)) throw new Error("library routes: BRIEF_HTML no longer carries the cohort sentence v2 adds");
  const SIGNUPS_V1 = BRIEF_HTML.replace(COHORT, "");
  const signupsTitle = `Signups brief · ${week}`;
  const signupsSummary = `PMax buys signups at €${STORY.numbers.pmaxCpa} who churn ${STORY.numbers.androidRetentionDrop} faster than organic on Android (31% vs 54% day-7); ROAS +14% hides it. Recommends pausing PMax, two negatives, and more brand budget (over the 25% guardrail). Window ${STORY.week.start} to ${STORY.week.end}.`;
  const signupsV1 = brief({ n: 1, group: 1, conversationId: C.signups, title: signupsTitle, content: SIGNUPS_V1, summary: signupsSummary, pinned: true, created: "2026-09-12T07:01:30" });
  const signupsV2 = brief({ n: 2, group: 1, version: 2, conversationId: C.signups, title: signupsTitle, content: BRIEF_HTML, label: "Android cohort start added", summary: `${signupsSummary} Adds that the PMax Android cohort started 4 Sep, two days after the rebuild.`, pinned: true, created: "2026-09-12T07:18:20" });

  const activation = brief({
    n: 3, group: 2, conversationId: C.activation, title: `Activation brief · ${week}`, content: PRODUCT_BRIEF_HTML,
    summary: `Android activation fell from ${STORY.numbers.activation.androidBefore} to ${STORY.numbers.activation.androidAfter} on 2 Sep when the rebuild put Connect bank behind a permission prompt; iOS flat. Recommends moving the prompt after the first budget and tracking two key events.`,
    created: "2026-09-13T07:09:40",
  });
  const spend = brief({
    n: 4, group: 3, conversationId: C.spend, title: `Spend brief · ${week}`, content: PAID_BRIEF_HTML,
    summary: `${STORY.numbers.pmaxSpend} went to Performance Max at €${STORY.numbers.pmaxCpa} a signup against the €${STORY.targets.cpa} target; brand search €${STORY.numbers.brandCpa}, capped by its €40 budget; two search terms wasted ${STORY.numbers.templateTermsSpend}.`,
    created: "2026-09-14T06:47:50",
  });
  const lastWeek = brief({
    n: 5, group: 4, conversationId: null, title: "Signups brief · 1–7 Sep 2026", content: LAST_WEEK_BRIEF_MD,
    summary: "892 signups against 900; PMax signups had 7-day retention of 31% vs 54% organic (cohorts before the 2 Sep rebuild). Recommends one more week before moving budget.",
    created: "2026-09-07T07:30:00",
  });

  // The Analytics tab's report: kind "growth-report", no bytes, the report in
  // structured_json, no conversation (routes/content_reports.py).
  const report = growthReport(STORY);
  const reportV1 = {
    ...report,
    title: "Organic up a fifth; signups slipping",
    date_from: "2026-08-14",
    date_to: "2026-09-12",
    verdict: `Organic clicks rose 19% to 7,760, mostly on the tax pages. Signups fell 4%: Performance Max is buying them at €${STORY.numbers.pmaxCpa} and the Android ones do not stay.`,
  };
  const reportRow = (n, version, body, created) => {
    const stem = "growth-report-growth-overview"; // slugify(f"growth-report-{template}")
    return row({
      n, group: 5, version, agentType: "insights", kind: "growth-report",
      contentType: "application/vnd.duct.growth-report+json",
      title: body.title, slug: stem, filename: `${created.slice(0, 10)}_${stem}_v${version}.json`,
      summary: body.verdict,
      meta: {
        label: `Version ${version}`, template: "growth_overview", date_from: body.date_from, date_to: body.date_to,
        sources: body.sources, blocks: body.blocks.length,
      },
      structured: body,
      created,
    });
  };
  const growthV1 = reportRow(6, 1, reportV1, "2026-09-13T06:04:10");
  const growthV2 = reportRow(7, 2, report, "2026-09-14T06:03:40");

  // The SEO audit, as audit_report_version stores it.
  const auditCreated = "2026-09-14T07:00:00";
  const auditBase = {
    url: `https://${site}`,
    generated_at: `${auditCreated}Z`,
    update_label: "",
    executive_summary: "",
    template_id: "",
  };
  const auditFindings = (AUDIT_REPORT.categories || []).reduce((sum, c) => sum + (c.findings || []).length, 0);
  const audit = AUDIT_MODE === "template"
    ? row({
      n: 8, group: 6, conversationId: C.audit, agentType: "audit_seo", kind: "report",
      contentType: "application/vnd.duct.report+json",
      title: `SEO audit — ${site}`, slug: slugify(`seo-audit-${site}`), filename: `2026-09-14_seo-audit_${site}_v1.json`,
      summary: AUDIT_REPORT.headline,
      meta: {
        url: auditBase.url, report_mode: "template", label: "Version 1", generated_at: auditBase.generated_at,
        overall_score: AUDIT_REPORT.overall_score, score_band: AUDIT_REPORT.score_band,
        categories: (AUDIT_REPORT.categories || []).length, findings: auditFindings,
      },
      structured: { ...auditBase, report_mode: "template", structured_data: AUDIT_REPORT },
      created: auditCreated,
    })
    : row({
      n: 8, group: 6, conversationId: C.audit, agentType: "audit_seo", kind: "report",
      contentType: "text/html",
      title: `SEO audit — ${site}`, slug: slugify(`seo-audit-${site}`), filename: `2026-09-14_seo-audit_${site}_v1.html`,
      content: AUDIT_REPORT_HTML,
      summary: AUDIT_REPORT.headline,
      meta: { url: auditBase.url, report_mode: "freehand", label: "Version 1", generated_at: auditBase.generated_at },
      structured: { ...auditBase, report_mode: "freehand", structured_data: null },
      created: auditCreated,
    });

  // A document the audit agent wrote on request (create_artifact_group).
  const outlineTitle = "Quarterly tax estimate guide · outline";
  const outline = row({
    n: 9, group: 7, conversationId: C.audit, agentType: "audit_seo", kind: "document",
    contentType: "text/markdown",
    title: outlineTitle, slug: slugify(outlineTitle), filename: `2026-09-14_${slugify(outlineTitle)}_v1.md`,
    content: OUTLINE_MD,
    summary: "Outline for the quarterly tax estimate guide the audit ranks fourth: target query, five sections, calculator and FAQ schema, internal links from the tax pages.",
    meta: { label: "Initial version" },
    created: "2026-09-14T07:12:15",
  });

  // ---------------------------------------------------------------------
  // The three shapes routes/artifacts.py serves.
  // ---------------------------------------------------------------------
  const serialize = ({ _structured, ...r }) => r;
  const versionsOf = (r) => rows.filter((x) => x.group_id === r.group_id).sort((a, b) => b.version - a.version);
  const heads = [...new Set(rows.map((r) => r.group_id))]
    .map((g) => versionsOf({ group_id: g })[0])
    .sort((a, b) => (a.created_at < b.created_at ? 1 : -1));
  const listOf = (pred) => heads.filter(pred).map((r) => ({ ...serialize(r), version_count: versionsOf(r).length }));

  const lists = {
    "": listOf(() => true),
    insights: listOf((r) => r.agent_type === "insights"),
  };
  const out = {};
  const listKey = (params) => `GET /api/user/artifacts?${new URLSearchParams({ project_id: projectId, ...params, limit: "50" })}`;
  // The library's tabs (app/(app)/artifacts/page.jsx KIND_TABS) and the desk.
  out[listKey({})] = lists[""];
  for (const kind of ["report", "brief", "document"]) out[listKey({ kind })] = listOf((r) => r.kind === kind);
  out[listKey({ agent_type: "insights" })] = lists.insights;
  // A thread's own documents, which InsightsWorkspace lists as it opens one.
  for (const t of threads) {
    out[listKey({ agent_type: "insights", conversation_id: t.id })] = listOf((r) => r.agent_type === "insights" && r.conversation_id === t.id);
  }
  for (const r of rows) {
    out[`GET /api/user/artifacts/${r.id}`] = { ...serialize(r), structured_json: r._structured };
    out[`GET /api/user/artifacts/${r.id}/versions`] = versionsOf(r).map(serialize);
    // Raw bytes, not JSON: the mock sends a `__raw__` body with its own type.
    if (contents[r.id] != null) out[`GET /api/user/artifacts/${r.id}/content`] = { __raw__: contents[r.id], type: serialize(r).content_type };
  }
  // "Show changes" on the signups brief's head (routes/artifacts.py diff_artifact_version).
  out[`GET /api/user/artifacts/${signupsV2.id}/diff?against=prev`] = {
    base_version: 1,
    target_version: 2,
    diff: unifiedDiff(SIGNUPS_V1, BRIEF_HTML, 1, 2),
  };

  // ---------------------------------------------------------------------
  // Activity (activity_logs), newest first. Every summary is the one the
  // writing call site formats; ids of the rows they point at are the rows above.
  // ---------------------------------------------------------------------
  const activity = [];
  const log = (r) => activity.push({
    id: activityId(activity.length + 1),
    category: r.category,
    action: r.action,
    source: r.source,
    summary: r.summary,
    agent_type: r.agent_type || "",
    connector_type: r.connector_type || "",
    account_id: r.account_id || "",
    target_type: r.target_type || "",
    target_id: r.target_id || "",
    conversation_id: r.conversation_id || null,
    data: r.data || {},
    created_at: at(r.created),
  });
  // service/artifact_store.py persist_artifact_version
  const artifactLog = (a, created = a.created_at.slice(0, 19)) => log({
    category: "artifact",
    action: a.version === 1 ? "artifact.created" : "artifact.version_added",
    source: "agent",
    agent_type: a.agent_type,
    conversation_id: a.conversation_id,
    target_type: "artifact",
    target_id: a.id,
    summary: a.version === 1
      ? `Created artifact “${a.title}” (${a.kind})`
      : `New version v${a.version} of “${a.title}”` + (a.meta.label ? ` — ${a.meta.label}` : ""),
    data: { group_id: a.group_id, version: a.version, kind: a.kind, slug: a.slug },
    created,
  });
  // service/execution/service.py log_change_set_transition, with each
  // transition's own summary (propose, approve in routes/execution.py, apply).
  const csLog = (cs, action, source, summary, data, created, conversationId = null) => log({
    category: "execution", action, source, summary, data, created,
    agent_type: cs.source === "user" ? "" : cs.source,
    connector_type: cs.connector_type, account_id: cs.account_id,
    target_type: "change_set", target_id: cs.id, conversation_id: conversationId,
  });
  const proposed = (cs, created, conversationId) => {
    const blocked = cs.changes.filter((c) => c.status === "blocked").length;
    csLog(cs, "change_set.proposed", cs.source === "user" ? "user" : "agent",
      `Proposed “${cs.title}” — ${cs.changes.length} change(s) on ${cs.connector_type}`
        + (blocked ? `, ${blocked} blocked by guardrails` : "")
        + (cs.auto_apply_eligible ? " · eligible for auto-apply" : ""),
      { change_count: cs.changes.length, blocked }, created, conversationId);
  };
  const approvedAndApplied = (cs, approvedAt, appliedAt) => {
    const count = cs.changes.length;
    csLog(cs, "change_set.approved", "user", `Approved “${cs.title}” — ${count} change(s)`, { approved: count, subset: false }, approvedAt);
    csLog(cs, "change_set.applied", "user", `Applied “${cs.title}” — ${count} applied, 0 failed`, { applied: count, failed: 0, held: 0, applied_by: cs.applied_by }, appliedAt);
  };

  // An outside agent's edit through the MCP server (update_project), the
  // row the feed offers Undo on. Maya asked Claude Code to sharpen the pitch
  // the crawl drafted from the homepage tagline.
  log({
    category: "project", action: "project.edited", source: "agent", agent_type: "mcp",
    target_type: "project", target_id: projectId,
    summary: `Edited pitch through “${MCP_TOKEN.name}”`,
    data: {
      fields: ["pitch"],
      after: { pitch: "Budgeting for freelancers with irregular income: sets aside tax from every payment that lands." },
      before: { pitch: STORY.company.tagline },
      before_labels: { pitch: "crawl" },
      token_id: MCP_TOKEN.id,
    },
    created: "2026-09-14T07:24:30",
  });
  artifactLog(outline);
  artifactLog(audit);
  artifactLog(spend);
  artifactLog(growthV2);
  proposed(PRODUCT_CHANGE_SET, "2026-09-13T07:10:00", C.activation);
  artifactLog(activation);
  artifactLog(growthV1);
  artifactLog(signupsV2);
  proposed(CHANGE_SET, "2026-09-12T07:02:00", C.signups);
  artifactLog(signupsV1);
  artifactLog(lastWeek);
  const [negatives, keyEvent, legacy] = CHANGE_SET_HISTORY;
  approvedAndApplied(negatives, "2026-09-05T09:11:20", "2026-09-05T09:11:24");
  proposed(negatives, negatives.created_at.slice(0, 19), null);
  // Clarity joined the stack two days after the rebuild (routes/project_connectors.py).
  log({
    category: "connector", action: "project_connector.bound", source: "user",
    connector_type: "clarity", account_id: CLARITY_BINDING.accountId,
    target_type: "project_connector", target_id: CLARITY_BINDING.id,
    summary: `Mapped clarity to ${CLARITY_BINDING.name} for this project`,
    created: "2026-09-04T11:30:00",
  });
  approvedAndApplied(keyEvent, "2026-09-02T09:20:05", "2026-09-02T09:20:08");
  proposed(keyEvent, keyEvent.created_at.slice(0, 19), null);
  approvedAndApplied(legacy, "2026-08-21T10:05:40", "2026-08-21T10:05:43");
  proposed(legacy, legacy.created_at.slice(0, 19), null);

  activity.sort((a, b) => (a.created_at < b.created_at ? 1 : -1));
  // list_activity: `limit` rows, and a cursor only when the page came back full.
  const page = (items, limit = 50) => {
    const slice = items.slice(0, limit);
    return { items: slice, next_before: slice.length === limit ? slice[slice.length - 1].created_at : null };
  };
  out[`GET /api/user/activity?project_id=${projectId}`] = page(activity);
  out[`GET /api/user/activity?project_id=${projectId}&limit=12`] = page(activity, 12);
  // The page's two category tabs (app/(app)/activity/page.jsx CATEGORY_TABS).
  for (const category of ["execution", "artifact"]) {
    out[`GET /api/user/activity?project_id=${projectId}&category=${category}`] = page(activity.filter((r) => r.category === category));
  }

  out[`GET /api/agents/insights/conversations?project_id=${projectId}`] = threads;

  return out;
}
