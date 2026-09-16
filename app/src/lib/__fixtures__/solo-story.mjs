// One customer's week, told the same way in every product screenshot.
//
// Solo is a fictional budgeting app for freelancers. Its growth lead, Maya,
// has connected the stack, set a CPA target, and is having a week where paid
// acquisition looks great on ROAS and terrible on retention. Every image on
// the README and the landing page is a frame of that one story, so the
// numbers, names and dates agree across them: the memory the insights agent
// recalls is the memory on the timeline, the change set it proposes is the
// card on the review queue, the plan the content agent writes is the board,
// the post it drafts is the one on the board marked draft.
//
// Used by scripts/shots (fixtures for the mock backend) and by the /preview
// scenes it captures. Nothing here is real: no company, person, account id,
// campaign or number below refers to anything outside this file.

export const STORY = Object.freeze({
  company: {
    name: "Solo",
    tagline: "Budgeting for freelancers",
    site: "solobudget.app",
    industry: "Personal finance app (iOS, Android, web)",
    currency: "€",
  },
  user: {
    name: "Maya Lindqvist",
    email: "maya@example.com",
    role: "Head of Growth",
    initials: "ML",
  },
  project: {
    id: "solo",
    name: "Solo",
  },
  week: {
    label: "8–14 Sep 2026",
    start: "2026-09-08",
    end: "2026-09-14",
  },
  targets: {
    cpa: 12,
    weeklySignups: 900,
  },
  ads: {
    accountId: "493-221-0815",
    accountName: "Solo · EU",
    campaigns: {
      brand: "Solo · Search · Brand EU",
      pmax: "Solo · Performance Max · Freelancers",
      legacy: "Solo · Brand · Legacy",
    },
  },
  numbers: {
    roasDelta: "+14%",
    androidRetentionDrop: "2.4×",
    pmaxCpa: 19.4,
    brandCpa: 8.7,
    signups: 812,
    signupsDelta: "-9%",
    mrr: "€18,400",
    mrrDelta: "+3.1%",
    rageClickClusters: 3,
    organicImpressionsDelta: "+23%",
    blogPost: "Freelancer tax calendar 2026",
    // Activation = reached Connect bank within a day of signing up. The
    // fortnight before the 2 Sep Android rebuild against the fortnight after.
    activation: { androidBefore: "58%", androidAfter: "34%", iosBefore: "63%", iosAfter: "61%" },
    pmaxSpend: "€2,140",
    templateTermsSpend: "€212",
  },
});

// The stack. The first five are what the insights agent pulls in the session;
// the rest are on the Connections page waiting. Copy matches the page.
export const CONNECTORS = Object.freeze([
  { id: "google_ads", title: "Google Ads", description: "Spend, clicks, impressions, conversions and ROAS, per campaign.", connected: true },
  { id: "ga4", title: "Google Analytics", description: "Traffic, sessions, engagement and conversions.", connected: true },
  { id: "gsc", title: "Google Search Console", description: "Search queries, clicks, impressions and average position.", connected: true },
  { id: "stripe", title: "Stripe", description: "Settled revenue, subscriptions, refunds and payment outcomes.", connected: true },
  { id: "clarity", title: "Microsoft Clarity", description: "Rage clicks, dead clicks, quick-backs and script errors, per page.", connected: true },
  { id: "meta_ads", title: "Meta Ads", description: "Facebook and Instagram spend, reach, conversions and CPA.", connected: false },
  { id: "mixpanel", title: "Mixpanel", description: "Signups, logins and upgrades, one name across web and app.", connected: false },
  { id: "revenuecat", title: "RevenueCat", description: "Trials, renewals, refunds and MRR across the App Store and Play.", connected: false },
  { id: "apple_ads", title: "Apple Search Ads", description: "Spend, taps and installs, by campaign and search term.", connected: false },
]);

// What the insights agent remembers about Solo before it starts. The same
// rows appear on the memory timeline, so a chip in the chat and a row on the
// page are visibly the same fact.
export const MEMORIES = Object.freeze([
  {
    id: "mem-cpa", short_id: "cpa12", kind: "goal", status: "confirmed", pinned: true,
    title: "CPA target is €12 across paid channels",
    body: "Set by Maya on 21 Aug. Applies to Google Ads and Meta; brand search is allowed to run under target.",
    source_type: "user", recorded_at: "2026-08-21T09:12:00Z", observed_at: "2026-08-21", recall_count: 14,
  },
  {
    id: "mem-legacy", short_id: "lgcy", kind: "decision", status: "confirmed", pinned: false,
    title: "Leave “Solo · Brand · Legacy” paused until the rebrand ships",
    body: "Maya: do not propose changes to it until the new brand terms are live.",
    source_type: "user", recorded_at: "2026-08-26T14:40:00Z", observed_at: "2026-08-26", recall_count: 6,
  },
  {
    id: "mem-android", short_id: "andr", kind: "event", status: "confirmed", pinned: false,
    title: "Android onboarding rebuilt on 2 Sep",
    body: "Retention comparisons that straddle 2 Sep are unreliable; compare cohorts on either side.",
    source_type: "agent", recorded_at: "2026-09-03T08:05:00Z", observed_at: "2026-09-03", recall_count: 3,
  },
  {
    id: "mem-brief", short_id: "brf07", kind: "conclusion", status: "confirmed", pinned: false,
    title: "Performance Max cohorts churn faster than organic",
    body: "From the 7 Sep signups brief: PMax signups had 7-day retention of 31% vs 54% organic.",
    source_type: "artifact", recorded_at: "2026-09-07T07:30:00Z", observed_at: "2026-09-07", recall_count: 2,
  },
  {
    id: "mem-target-old", short_id: "sgn7", kind: "goal", status: "superseded", pinned: false,
    title: "Weekly signups target is 700",
    body: "Raised to 900 on 30 Aug after the August plan review.",
    source_type: "user", recorded_at: "2026-08-02T10:00:00Z", observed_at: "2026-08-02", valid_to: "2026-08-30", recall_count: 9,
  },
  {
    id: "mem-target", short_id: "sgn9", kind: "goal", status: "confirmed", pinned: false,
    title: "Weekly signups target is 900",
    body: "Replaces the 700 target. Reviewed monthly.",
    source_type: "user", recorded_at: "2026-08-30T16:20:00Z", observed_at: "2026-08-30", recall_count: 5,
  },
  {
    id: "mem-clarity", short_id: "clrt", kind: "watch", status: "proposed", pinned: false,
    title: "Watch rage clicks on the Connect bank screen",
    body: "Clarity showed 3 clusters in the week of 8 Sep, all on Android, all from the PMax cohort.",
    source_type: "agent", recorded_at: "2026-09-12T06:50:00Z", observed_at: "2026-09-12", recall_count: 1,
  },
  {
    id: "mem-pref", short_id: "pref", kind: "status", status: "confirmed", pinned: false,
    title: "Reports in euros; the week starts on Monday",
    body: "Maya's preference for every brief and chart.",
    source_type: "user", recorded_at: "2026-08-21T09:12:00Z", observed_at: "2026-08-21", recall_count: 22,
  },
]);

// The change the insights agent proposes this week. Same object on the review
// queue and inside the insights session.
export const CHANGE_SET = Object.freeze({
  change_set_id: "cs_solo_0912",
  id: "cs_solo_0912",
  connector_type: "google_ads",
  account_id: STORY.ads.accountId,
  account_name: STORY.ads.accountName,
  title: "Pause Performance Max, keep brand search",
  context:
    "PMax · Freelancers costs €19.40 a signup against the €12 target and its Android users leave within a week. Brand search stays on at €8.70.",
  status: "proposed",
  source: "insights",
  project_id: STORY.project.id,
  created_at: "2026-09-12T07:02:00Z",
  auto_apply_eligible: false,
  applied_by: null,
  changes: [
    {
      id: "c1", op_type: "pause_campaign", status: "pending", destructive: true,
      diff: `Pause ${STORY.ads.campaigns.pmax}`,
      warnings: ["Spent €2,140 in the last 7 days"],
    },
    {
      id: "c2", op_type: "add_negative_keywords", status: "pending",
      diff: 'Add negatives “free budgeting app”, “excel budget template”',
    },
    {
      id: "c3", op_type: "set_campaign_budget", status: "blocked",
      diff: `Raise ${STORY.ads.campaigns.brand} budget €40 → €60 a day`,
      guardrail_violations: ["Over the 25% budget guardrail on this account, so it needs you"],
    },
  ],
});

// What the insights agent proposes when the question is about the product
// rather than the spend: nothing in the ad accounts moves, the funnel gains
// the two events the rebuild introduced so next week's brief can prove the
// fix. Auto-apply eligible, because a key event is reversible in one click.
export const PRODUCT_CHANGE_SET = Object.freeze({
  change_set_id: "cs_solo_0913",
  id: "cs_solo_0913",
  connector_type: "ga4",
  account_id: "ga4-solo",
  account_name: "Solo web + app",
  title: "Track the permission dead end",
  context:
    "The rebuild added a system permission prompt before Connect bank. Two events it emits, made key events, so the funnel shows who tapped Deny and who came back.",
  status: "proposed",
  source: "insights",
  project_id: STORY.project.id,
  created_at: "2026-09-13T07:10:00Z",
  auto_apply_eligible: true,
  applied_by: null,
  changes: [
    { id: "c1", op_type: "create_key_event", status: "pending", diff: "Mark bank_permission_denied as a key event" },
    { id: "c2", op_type: "create_key_event", status: "pending", diff: "Mark connect_bank_retry as a key event" },
  ],
});

// What sits under it on the Executions page: the changes Solo already let
// through this quarter, so the queue reads as a record and not a single card.
// The Legacy pause is the one the memory timeline says to leave alone.
export const CHANGE_SET_HISTORY = Object.freeze([
  {
    change_set_id: "cs_solo_0905", id: "cs_solo_0905",
    connector_type: "google_ads", account_id: STORY.ads.accountId, account_name: STORY.ads.accountName,
    title: "Add negatives from last week's search terms",
    context: "Two template-hunter queries spent €212 for zero signups.",
    status: "applied", source: "insights", project_id: STORY.project.id,
    created_at: "2026-09-05T07:40:00Z", auto_apply_eligible: false, applied_by: "maya@example.com",
    changes: [
      { id: "c1", op_type: "add_negative_keywords", status: "applied", diff: 'Add negatives “budget template excel”, “free invoice generator”' },
    ],
  },
  {
    change_set_id: "cs_solo_0902", id: "cs_solo_0902",
    connector_type: "ga4", account_id: "ga4-solo", account_name: "Solo web + app",
    title: "Mark connect_bank as a key event",
    context: "The onboarding rebuild moved the bank step; the funnel needs the new event.",
    status: "applied", source: "insights", project_id: STORY.project.id,
    created_at: "2026-09-02T09:15:00Z", auto_apply_eligible: true, applied_by: "maya@example.com",
    changes: [
      { id: "c1", op_type: "mark_key_event", status: "applied", diff: "Mark connect_bank as a key event" },
    ],
  },
  {
    change_set_id: "cs_solo_0821", id: "cs_solo_0821",
    connector_type: "google_ads", account_id: STORY.ads.accountId, account_name: STORY.ads.accountName,
    title: "Pause Brand · Legacy until the rebrand ships",
    context: "The old brand name still gets 40 clicks a day that land on a redirect.",
    status: "applied", source: "user", project_id: STORY.project.id,
    created_at: "2026-08-21T10:05:00Z", auto_apply_eligible: false, applied_by: "maya@example.com",
    changes: [
      { id: "c1", op_type: "pause_campaign", status: "applied", destructive: true, diff: `Pause ${STORY.ads.campaigns.legacy}` },
    ],
  },
]);

// One question per audience, and the answer the insights agent gives. The
// session shots open with the question and end on the answer; the answer
// cards on the landing pages show only this, so the two cannot disagree.
// Sources are the steps the agent reports, in order; `recalled` the memories
// it opened with.
export const ANSWERS = Object.freeze({
  product: {
    question: "Why did activation drop after the Android onboarding release?",
    recalled: ["mem-android", "mem-clarity"],
    sources: [
      { id: "ga4", label: "ga4 onboarding funnel by platform · 25 Aug → 14 Sep" },
      { id: "clarity", label: "clarity rage clicks by screen · 25 Aug → 14 Sep" },
      { id: "stripe", label: "stripe trial starts · 25 Aug → 14 Sep" },
    ],
    answer: `**Android activation fell from ${STORY.numbers.activation.androidBefore} to ${STORY.numbers.activation.androidAfter} on 2 Sep, the day the rebuild shipped. iOS did not move.** The rebuild put the bank step behind a system permission prompt, and Android users who tap Deny land on an empty screen: that is where this week's three rage-click clusters are. Two events to track below, so next week's brief can prove the fix.`,
  },
  paid: {
    question: "Where is the ads budget leaking this week?",
    recalled: ["mem-cpa", "mem-legacy"],
    sources: [
      { id: "google_ads", label: `google ads campaigns · ${STORY.week.start} → ${STORY.week.end}` },
      { id: "google_ads", label: `google ads search terms · ${STORY.week.start} → ${STORY.week.end}` },
      { id: "ga4", label: `ga4 signups by campaign · ${STORY.week.start} → ${STORY.week.end}` },
      { id: "stripe", label: `stripe subscriptions · ${STORY.week.start} → ${STORY.week.end}` },
    ],
    answer: `**${STORY.numbers.pmaxSpend} of this week's spend went to Performance Max at €${STORY.numbers.pmaxCpa} a signup, against the €${STORY.targets.cpa} target.** Brand search is at €${STORY.numbers.brandCpa} and capped by its €40 budget. Two template-hunter search terms spent ${STORY.numbers.templateTermsSpend} for zero signups. The moves are below: two apply on your say-so, the budget raise is over the guardrail so it needs you.`,
  },
  organic: {
    question: "Which content actually converts?",
    recalled: ["mem-brief"],
    sources: [
      { id: "search_console", label: `search console clicks by page · ${STORY.week.start} → ${STORY.week.end}` },
      { id: "ga4", label: `ga4 trials by landing page · ${STORY.week.start} → ${STORY.week.end}` },
      { id: "clarity", label: `clarity quick-backs by page · ${STORY.week.start} → ${STORY.week.end}` },
    ],
    answer: `**The tax cluster earns 61% of organic trials from 28% of the clicks. Invoicing gets 41% of the clicks and earns 9%.** The three invoicing pages on page one lose people at the pricing paragraph, where Clarity shows the quick-backs. Update those three first. *${STORY.numbers.blogPost}* is already on page one for two target terms and needs nothing.`,
  },
});

// The briefs the insights agent writes: self-contained HTML reports, the way
// the agents actually deliver one (the artifact pane renders it in a frame).
// Sized for the pane, not for print: a verdict, the numbers, one chart, then
// findings. One builder, three briefs, so the three sessions share a look
// and a change to the layout reaches all of them.
const n = STORY.numbers;
const BRIEF_CSS = `:root{--tx:#1a1d26;--mut:#6b7280;--line:#e6e7ea;--card:#fff;--bg:#fff;--crit:#c2410c;--warn:#b45309;--good:#15803d;--accent:#5b5bd6}
*{box-sizing:border-box;margin:0}
body{font:14px/1.5 -apple-system,"Segoe UI",Roboto,sans-serif;color:var(--tx);background:var(--bg);padding:20px 22px 32px}
h1{font-size:19px;font-weight:650;letter-spacing:-.01em}
h2{font-size:12px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--mut);margin:24px 0 10px}
.sub{color:var(--mut);font-size:12px;margin:3px 0 16px}
.verdict{background:#eef0ff;border-left:3px solid var(--accent);border-radius:8px;padding:12px 14px;font-size:14px}
.verdict b{color:var(--accent)}
.kpis{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}
.kpi{background:#fafafa;border:1px solid var(--line);border-radius:10px;padding:10px 12px}
.kpi .v{font-size:20px;font-weight:650;letter-spacing:-.01em;font-variant-numeric:tabular-nums}
.kpi .l{color:var(--mut);font-size:11px;margin-top:1px}
.kpi .d{font-size:11px;font-weight:600;margin-top:4px}
.up{color:var(--good)}.down{color:var(--crit)}.flat{color:var(--mut)}
.bars{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px;display:grid;gap:8px}
.bar{display:grid;grid-template-columns:150px 1fr 44px;align-items:center;gap:10px;font-size:12px}
.bar i{display:block;height:10px;border-radius:5px;background:var(--accent)}
.bar i.bad{background:#f0a48a}.bar i.good{background:#8fd3a2}
.bar b{text-align:right;font-variant-numeric:tabular-nums}
.bar span{color:var(--mut)}
.finding{background:var(--card);border:1px solid var(--line);border-left:3px solid var(--mut);border-radius:10px;padding:10px 14px;margin-bottom:8px}
.finding.crit{border-left-color:var(--crit)}.finding.warn{border-left-color:var(--warn)}.finding.good{border-left-color:var(--good)}
.finding h3{font-size:13px;font-weight:600;margin-bottom:2px}
.finding p{font-size:12.5px;color:#3f4350}
ol{padding-left:18px;font-size:13px}ol li{margin-bottom:5px}
footer{color:var(--mut);font-size:11px;margin-top:24px}`;
const kpi = (v, l, d, tone = "flat") => `<div class="kpi"><div class="v">${v}</div><div class="l">${l}</div><div class="d ${tone}">${d}</div></div>`;
const bar = (label, pct, tone = "", text = `${pct}%`) => `<div class="bar"><span>${label}</span><i class="${tone}" style="width:${pct}%"></i><b>${text}</b></div>`;
const finding = (tone, h, p) => `<div class="finding ${tone}"><h3>${h}</h3><p>${p}</p></div>`;

function brief({ title, h1, sources, verdict, kpis, chart, findings, todo }) {
  return `<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>${title} · week of ${STORY.week.label}</title>
<style>
${BRIEF_CSS}
</style></head><body>
<h1>${h1}</h1>
<p class="sub">Week of ${STORY.week.label} · ${sources}</p>

<div class="verdict"><b>The short version.</b> ${verdict}</div>

<h2>The numbers</h2>
<div class="kpis">
${kpis.join("\n")}
</div>

<h2>${chart.heading}</h2>
<div class="bars">
${chart.rows.join("\n")}
</div>

<h2>Findings</h2>
${findings.join("\n")}

<h2>What to do</h2>
<ol>
${todo.map((t) => `  <li>${t}</li>`).join("\n")}
</ol>
<footer>Every number re-checked by the verification sub-agent · ${STORY.week.label}</footer>
</body></html>`;
}

// Why are signups down when ROAS is up: the growth lead's question.
export const BRIEF_HTML = brief({
  title: "Signups",
  h1: "Signups are down. ROAS is up. Same campaign.",
  sources: "Google Ads, GA4, Stripe, Clarity, Search Console",
  verdict: `Performance Max is buying signups at €${n.pmaxCpa} who leave within a week. The ROAS gain is hiding a retention problem, not describing a win.`,
  kpis: [
    kpi(n.signups, "Signups", `▼ 9% · target ${STORY.targets.weeklySignups}`, "down"),
    kpi(n.mrr, "MRR", `▲ ${n.mrrDelta.replace("+", "")}`, "up"),
    kpi(n.roasDelta, "ROAS", "almost all from PMax"),
    kpi(`€${n.pmaxCpa}`, "CPA · PMax", "▲ €7.40 over target", "down"),
    kpi(`€${n.brandCpa}`, "CPA · Brand search", "▼ €3.30 under target", "up"),
    kpi(n.rageClickClusters, "Rage-click clusters", "all Android", "down"),
  ],
  chart: { heading: "7-day retention by source", rows: [
    bar("Organic", 54, "good"), bar("Brand search", 51, "good"), bar("PMax · iOS", 44), bar("PMax · Android", 31, "bad"),
  ] },
  findings: [
    finding("crit", `PMax Android users churn ${n.androidRetentionDrop} faster than organic`, "31% retained at day 7 against 54%. The cohort started on 4 Sep, two days after the onboarding rebuild."),
    finding("warn", "They get stuck on the Connect bank screen", "Three rage-click clusters this week, all Android, all from the PMax cohort. Fix the screen before buying more of them."),
    finding("good", "Organic is quietly working", `Impressions up ${n.organicImpressionsDelta}. <i>${n.blogPost}</i> ranks on page one for two target terms.`),
  ],
  todo: [
    "Pause <i>Performance Max · Freelancers</i> until the Android screen is fixed. Proposed in chat, waiting for you.",
    "Add the two negatives bringing in template hunters.",
    "Give brand search more budget. Over the 25% guardrail, so that one is yours to make.",
  ],
});

// Why did activation drop: the same week from the product side.
export const PRODUCT_BRIEF_HTML = brief({
  title: "Activation",
  h1: "Android activation halved the day the rebuild shipped.",
  sources: "GA4, Clarity, Stripe",
  verdict: `The 2 Sep rebuild put Connect bank behind a system permission prompt. Android users who tap Deny land on an empty screen and never come back. iOS, which has no prompt, did not move.`,
  kpis: [
    kpi(n.activation.androidAfter, "Activation · Android", `▼ from ${n.activation.androidBefore} before 2 Sep`, "down"),
    kpi(n.activation.iosAfter, "Activation · iOS", `${n.activation.iosBefore} before · unchanged`),
    kpi(n.rageClickClusters, "Rage-click clusters", "all on the empty screen", "down"),
    kpi("−11%", "Trial starts", "all of it Android", "down"),
    kpi("31%", "Day-7 retention · Android", "54% organic", "down"),
    kpi("2 Sep", "Rebuild shipped", "the day the drop starts"),
  ],
  chart: { heading: "Activation by platform, before and after 2 Sep", rows: [
    bar("iOS · before", 63, "good"), bar("iOS · after", 61, "good"), bar("Android · before", 58), bar("Android · after", 34, "bad"),
  ] },
  findings: [
    finding("crit", "Deny the permission and the funnel ends", "The prompt has no path back to Connect bank. GA4 shows the drop in the step after it; Clarity shows where people click when nothing happens."),
    finding("warn", "The rage clicks are the same screen", "Three clusters this week, all Android, all on the empty screen, all from users who signed up after 2 Sep."),
    finding("good", "The rest of the rebuild is fine", "iOS activation, time to first budget and trial starts on iOS are inside their usual week-to-week range."),
  ],
  todo: [
    "Ask for the permission after the first budget, not before it. The fix is in the app.",
    "Track <i>bank_permission_denied</i> and <i>connect_bank_retry</i> as key events. Proposed in chat, waiting for you.",
    "Keep Performance Max off Android until the screen is fixed: it is buying the users who hit it.",
  ],
});

// Where is the budget leaking: the same week from the paid side.
export const PAID_BRIEF_HTML = brief({
  title: "Spend",
  h1: `Performance Max buys signups at €${n.pmaxCpa}. The target is €${STORY.targets.cpa}.`,
  sources: "Google Ads, GA4, Stripe",
  verdict: `${n.pmaxSpend} of this week's spend went to one campaign that runs €7.40 over target and whose Android signups churn ${n.androidRetentionDrop} faster than organic. Brand search is under target and capped by its own budget.`,
  kpis: [
    kpi("€2,420", "Paid spend", `${n.pmaxSpend} of it PMax`),
    kpi("142", "Paid signups", "PMax 110 · Brand 32"),
    kpi("€17.0", "Blended CPA", `▲ €5.00 over target`, "down"),
    kpi(`€${n.pmaxCpa}`, "CPA · PMax", "▲ €7.40 over target", "down"),
    kpi(`€${n.brandCpa}`, "CPA · Brand search", "▼ €3.30 under target", "up"),
    kpi(n.templateTermsSpend, "Wasted on two terms", "zero signups", "down"),
  ],
  chart: { heading: `CPA by campaign against the €${STORY.targets.cpa} target`, rows: [
    bar("Brand search", 35, "good", `€${n.brandCpa}0`), bar("PMax · iOS", 64, "", "€16.10"), bar("PMax · Android", 91, "bad", "€22.80"),
  ] },
  findings: [
    finding("crit", "PMax is over target and buying churners", `€${n.pmaxCpa} a signup, and the Android half of them retain at 31% against 54% organic. The ROAS looks fine because it is measured before they leave.`),
    finding("warn", "Two search terms spent €212 for nothing", "“free budgeting app” and “excel budget template” bring template hunters, not freelancers. Negatives proposed in chat."),
    finding("good", "Brand search hits its cap by mid-afternoon", `€${n.brandCpa} a signup and half of them stay. The €40 daily budget is the only thing holding it back.`),
  ],
  todo: [
    "Pause <i>Performance Max · Freelancers</i>. Proposed in chat, waiting for you.",
    "Add the two negatives. Proposed in chat.",
    "Raise brand search to €60 a day. Over the 25% guardrail, so that one is yours to make.",
  ],
});

// The SEO audit of solobudget.app, as the audit agent writes it: nine
// categories, every finding tied to a page and a value, five priorities in
// the order to do them, a plan in three phases. Same week, same site, same
// facts as the organic answer (the tax pillar converts, the invoicing pages
// get the clicks and lose them at the pricing paragraph). Shape is the
// backend's StructuredAuditData; the app renders it with AuditReportV1.
const U = (url, issue_value) => ({ url, issue_value });
const F = (id, severity, title, description, tooltip, affected_urls, recommendation, impact, effort) =>
  ({ id, severity, title, description, tooltip, affected_urls, recommendation, impact, effort });

export const AUDIT_REPORT = Object.freeze({
  url: `https://${STORY.company.site}`,
  generated_at: "2026-09-14T09:00:00Z",
  overall_score: 68,
  score_band: "needs_work",
  headline: "Three invoicing pages win the clicks and lose the trial at the pricing paragraph",
  key_signals: [
    "3 tax pages earn 61% of organic trials",
    "Invoicing pages: 41% of clicks, 9% of trials",
    "Every template passes Core Web Vitals",
  ],
  strategic_narrative:
    "Solo competes with Ledgerly and Tallyo for the same freelancer, and both outrank it on the queries that lead to a trial: “freelance tax calculator”, “invoice template for freelancers”, “quarterly tax estimate”. Solo wins on tax habits, the one pillar neither competitor writes about with any care, and that pillar produces 61% of organic trials from 28% of the clicks. The invoicing cluster gets the clicks and loses them: three pages on page one, a pricing paragraph that reads as a wall, quick-backs at 44%. The plan below is hygiene first, then the pricing paragraph, then the two guides the competitors own and Solo does not have.",
  pages_crawled: 41,
  total_sitemap_urls: 44,
  total_issues: 8,
  total_warnings: 9,
  total_opportunities: 4,
  crawl_summary: { avg_ttfb_ms: 380, pages_with_redirects: 2, spa_pages_count: 0, pages_noindex: 1, pages_missing_title: 3, pages_missing_h1: 0 },
  wins: [
    "Every template passes Core Web Vitals",
    "Article schema on every guide, SoftwareApplication on pricing",
    "No page blocked by robots.txt",
    "The tax calendar ranks on page one for two target terms",
  ],
  top_priorities: [
    { rank: 1, title: "Rewrite the pricing paragraph on the three invoicing pages", why_it_matters: "41% of organic clicks land on these pages and 44% leave without a second one.", severity: "fail", affected_url_count: 3, category_id: "on_page_seo", finding_id: "invoicing-pricing-wall" },
    { rank: 2, title: "Remove the three sitemap entries that 404", why_it_matters: "Crawl budget spent proving pages are missing; Search Console flags all three.", severity: "fail", affected_url_count: 3, category_id: "technical_foundation", finding_id: "sitemap-404" },
    { rank: 3, title: "Link the tax calendar from every invoicing page", why_it_matters: "The page that converts is three clicks from the pages that get the traffic.", severity: "fail", affected_url_count: 3, category_id: "internal_linking", finding_id: "tax-calendar-deep" },
    { rank: 4, title: "Write the quarterly tax estimate guide", why_it_matters: "Both competitors rank for it, Solo has no page, and the tax pillar already converts.", severity: "opportunity", affected_url_count: 0, category_id: "blog_content_strategy", finding_id: "gap-quarterly-estimate" },
    { rank: 5, title: "Put an author and a date on every guide", why_it_matters: "No guide says who wrote it; the competitors' do, and trust is the E-E-A-T factor that weighs most.", severity: "fail", affected_url_count: 12, category_id: "eeat_signals", finding_id: "no-author" },
  ],
  categories: [
    {
      id: "on_page_seo", label: "On-page SEO", score: 52, tooltip: "Titles, headings, body copy and images on each page: what the page says it is about, and whether a reader agrees.",
      fail_count: 2, warn_count: 1, pass_count: 1, opp_count: 0,
      findings: [
        F("invoicing-pricing-wall", "fail", "The pricing paragraph on the invoicing pages reads as a wall", "The three invoicing pages rank on page one and lose 44% of visitors at the same 190-word paragraph; Clarity shows the quick-backs on it.", "People arrive, hit a dense block about prices, and leave without reading further.",
          [U("/invoicing", "quick-backs 44%"), U("/invoice-template", "quick-backs 41%"), U("/late-payment-letter", "quick-backs 39%")],
          "Split the paragraph into a three-row price table and move the free-tier line to the top.", "critical", "low"),
        F("title-brand-only", "fail", "Three posts are titled with the brand name alone", "Three guides carry the title “Solo” and nothing else, so search results show the brand where the topic should be.", "The title is what shows up as the blue link in Google; “Solo” tells a searcher nothing.",
          [U("/guides/vat-for-freelancers", "title: “Solo”"), U("/guides/set-aside-tax", "title: “Solo”"), U("/guides/first-invoice", "title: “Solo”")],
          "Title each guide with its question, under 60 characters, brand last.", "high", "low"),
        F("imgs-no-alt", "warn", "28 images have no alt text", "Screenshots in the guides carry no alt text, so image search and screen readers get nothing from them.", "Alt text is the one-line description a browser reads when it cannot show the image.",
          [U("/guides/first-invoice", "9 images"), U("/guides/set-aside-tax", "7 images"), U("/blog/september-freelancer", "12 images")],
          "Describe what each screenshot shows in one line; skip decorative ones with an empty alt.", "medium", "low"),
        F("h1-present", "pass", "An H1 on every page describes the page", "Every crawled page has one H1 and it names the topic, not the brand.", "The main heading tells search engines and readers what the page is about.", [], "", "low", "low"),
      ],
    },
    {
      id: "technical_foundation", label: "Technical foundation", score: 56, tooltip: "Whether search engines can reach, read and index the pages at all: sitemap, status codes, redirects, noindex, render mode.",
      fail_count: 1, warn_count: 3, pass_count: 2, opp_count: 0,
      findings: [
        F("sitemap-404", "fail", "The sitemap lists three pages that return 404", "Three sitemap entries point at pages that no longer exist, so every crawl spends budget confirming they are missing.", "A sitemap is the list of pages you ask Google to visit; three of them are dead.",
          [U("/guides/old-invoicing", "HTTP 404"), U("/pricing-2024", "HTTP 404"), U("/blog/launch", "HTTP 404")],
          "Remove the three entries from the sitemap, or redirect each to its replacement.", "high", "low"),
        F("redirect-once", "warn", "Two templates redirect once before they load", "Two landing pages answer with a 301 to their trailing-slash twin, one hop on every visit and every crawl.", "A redirect is a detour; each one costs a little time and a little trust.",
          [U("/pricing", "301 → /pricing/"), U("/download", "301 → /download/")],
          "Link the final URL directly and drop the redirect.", "medium", "low"),
        F("noindex-guide", "warn", "One guide is noindex by mistake", "The VAT guide carries a noindex tag left over from its draft, so it cannot rank for the term it was written for.", "noindex tells Google to leave the page out of results.",
          [U("/guides/vat-for-freelancers", "noindex")],
          "Remove the noindex tag and resubmit the page in Search Console.", "high", "low"),
        F("sitemap-lastmod", "warn", "Sitemap lastmod is the deploy date on every page", "All 44 entries share one lastmod, so the sitemap says nothing about which pages changed.", "lastmod is the sitemap's way of saying “this page changed”; the same date everywhere says nothing.",
          [U("/sitemap.xml", "44 × 2026-09-01")],
          "Set lastmod from each page's real change date.", "low", "low"),
        F("ttfb", "pass", "Average time to first byte is 380 ms", "Every page answers well under the one-second mark.", "How long the server takes to start replying.", [], "", "low", "low"),
        F("no-spa", "pass", "No page depends on JavaScript to render its content", "All 41 pages deliver their text in the HTML.", "Search engines read the raw page; content that needs scripts to appear is easy to miss.", [], "", "low", "low"),
      ],
    },
    {
      id: "blog_content_strategy", label: "Blog and content strategy", score: 79, tooltip: "Whether the content answers what the audience searches for, and whether it is kept fresh.",
      fail_count: 1, warn_count: 1, pass_count: 1, opp_count: 2,
      findings: [
        F("no-commercial-query", "fail", "No page targets a query someone searches before buying", "Every landing page reads as an about page; nothing answers “invoice template for freelancers” or “freelance tax calculator”, the two queries competitors rank for.", "Commercial queries are the searches people make when they are ready to pick a tool.",
          [U("/", "brand query only"), U("/pricing", "brand query only")],
          "Give each commercial query a page of its own with the query in the title and H1.", "critical", "high"),
        F("stale-posts", "warn", "Four posts have not been updated in 19 months", "Four 2025 posts still rank on page two and have not been touched since they were written.", "Search engines prefer pages that are kept current, especially on topics that change yearly.",
          [U("/blog/tax-deadlines-2025", "lastmod 2025-02-11"), U("/blog/invoice-mistakes", "lastmod 2025-02-20"), U("/blog/quarterly-review", "lastmod 2025-03-02"), U("/blog/freelance-rates", "lastmod 2025-03-15")],
          "Refresh the four with this year's figures and a new date.", "medium", "medium"),
        F("gap-quarterly-estimate", "opportunity", "There is no quarterly tax estimate guide", "Ledgerly and Tallyo both rank for “quarterly tax estimate freelancer”; Solo's tax pillar is the strongest on the site and has no page for it.", "A topic the competitors cover and the site does not.",
          [], "Write the guide in the tax pillar's voice and link it from the tax calendar.", "high", "medium"),
        F("gap-invoice-template", "opportunity", "The invoice template query has no page of its own", "“Invoice template for freelancers” is answered halfway down /invoicing; a dedicated page would rank for it.", "A query that deserves its own page, not a paragraph on another one.",
          [], "Create /invoice-template-for-freelancers with the template itself above the fold.", "high", "medium"),
        F("tax-pillar-depth", "pass", "The tax pillar posts each run over 900 words", "The five tax posts answer their question in full and rank for it.", "Depth is the sign a page actually answers the question.", [], "", "low", "low"),
      ],
    },
    {
      id: "internal_linking", label: "Internal linking", score: 79, tooltip: "How pages link to each other: whether authority flows to the pages that matter and whether any are stranded.",
      fail_count: 1, warn_count: 1, pass_count: 1, opp_count: 0,
      findings: [
        F("tax-calendar-deep", "fail", "The tax calendar is three clicks from the invoicing pages", "The page that converts best is reachable from the pages that get the most traffic only through the blog index.", "Pages that link to each other pass on their standing; the best page here is left out.",
          [U("/invoicing", "0 links to tax calendar"), U("/invoice-template", "0 links to tax calendar"), U("/late-payment-letter", "0 links to tax calendar")],
          "Add a “next: your tax calendar” link at the end of each invoicing page.", "high", "low"),
        F("orphan-posts", "warn", "Six posts have no inbound internal link", "Six older posts are reachable only from the sitemap, so neither readers nor crawlers arrive at them.", "A page nothing links to is invisible in practice.",
          [U("/blog/freelance-rates", "0 inbound"), U("/blog/quarterly-review", "0 inbound"), U("/blog/invoice-mistakes", "0 inbound")],
          "Link each from the most related guide, or fold it into one.", "medium", "low"),
        F("nav-reach", "pass", "The navigation reaches every landing page in one click", "All eight landing pages sit in the header or footer.", "One click from the home page is as close as a page can be.", [], "", "low", "low"),
      ],
    },
    {
      id: "eeat_signals", label: "E-E-A-T signals", score: 71, tooltip: "Experience, expertise, authority and trust: who is behind the content, and whether the site says so.",
      fail_count: 2, warn_count: 1, pass_count: 1, opp_count: 0,
      findings: [
        F("no-author", "fail", "No guide names an author", "All twelve guides are published without a name, a role or a date, on a topic where the competitors' guides carry all three.", "Readers and search engines both want to know who is speaking and when.",
          [U("/guides/first-invoice", "no author, no date"), U("/guides/set-aside-tax", "no author, no date"), U("/guides/vat-for-freelancers", "no author, no date")],
          "Add an author line with a role and a published date to every guide.", "high", "low"),
        F("about-thin", "fail", "The about page names no one", "The about page has no team, no address and no company registration, so nothing on the site vouches for the app.", "Trust signals are the boring facts: who, where, since when.",
          [U("/about", "no team, no address")],
          "Add the founder, the company, the address and a support contact.", "high", "low"),
        F("no-reviews", "warn", "No reviews or ratings anywhere on the site", "The pricing page makes claims without a single quote, rating or named customer.", "Other people's words carry more weight than your own.",
          [U("/pricing", "0 reviews")],
          "Add three named quotes and a link to the app-store rating.", "medium", "medium"),
        F("legal-pages", "pass", "Privacy and terms are present and linked from every page", "Both pages exist and sit in the footer.", "The legal pages are the minimum sign of a real company.", [], "", "low", "low"),
      ],
    },
    {
      id: "geo_aio", label: "AI search visibility", score: 88, tooltip: "Whether AI answers can quote the site: a direct answer up top, questions answered in full, a file that tells crawlers what is here.",
      fail_count: 1, warn_count: 0, pass_count: 1, opp_count: 1,
      findings: [
        F("no-direct-answer", "fail", "No guide answers its question in the first paragraph", "Every guide opens with a story; the answer arrives in paragraph four, past where an AI answer would quote it.", "AI answers lift the first clear sentence that answers the question.",
          [U("/guides/set-aside-tax", "answer at ¶4"), U("/guides/first-invoice", "answer at ¶5"), U("/guides/vat-for-freelancers", "answer at ¶3")],
          "Open each guide with a two-sentence answer, then tell the story.", "high", "low"),
        F("faq-blocks", "opportunity", "FAQ blocks on the tax pillar would be quoted", "The tax posts get the questions in comments and support; none of them carry a Q&A block.", "A question with a short answer under it is the easiest thing for an AI to cite.",
          [], "Add three questions and answers to each tax post, with FAQ schema.", "medium", "low"),
        F("llms-txt", "pass", "llms.txt is present and current", "The file lists the guides and the pricing page.", "A short file telling AI crawlers what the site is and where the good pages are.", [], "", "low", "low"),
      ],
    },
    {
      id: "structured_data", label: "Structured data", score: 97, tooltip: "Schema markup that lets search engines show rich results: articles, software, FAQs.",
      fail_count: 0, warn_count: 1, pass_count: 2, opp_count: 0,
      findings: [
        F("faq-schema-missing", "warn", "FAQ content without FAQ schema", "Two pages carry a question-and-answer section with no FAQPage markup, so it cannot show as a rich result.", "Schema is a label that tells Google what a block of content is.",
          [U("/pricing", "4 Q&As, no schema"), U("/download", "3 Q&As, no schema")],
          "Wrap both sections in FAQPage JSON-LD.", "low", "low"),
        F("article-schema", "pass", "Article schema on every guide", "All twelve guides carry Article markup with headline and dates.", "Article markup marks the page as a piece of writing.", [], "", "low", "low"),
        F("software-schema", "pass", "SoftwareApplication markup on the pricing page", "Price, platform and category are declared.", "Software markup lets Google show price and platform in results.", [], "", "low", "low"),
      ],
    },
    {
      id: "open_graph_social", label: "Open Graph and social", score: 97, tooltip: "How a link to the site looks when it is shared: title, description and image.",
      fail_count: 0, warn_count: 1, pass_count: 1, opp_count: 0,
      findings: [
        F("og-image-shared", "warn", "Twelve guides share one Open Graph image", "Every guide previews with the same logo card, so a shared link says nothing about the guide.", "The preview image is the poster for a shared link.",
          [U("/guides/*", "12 × og-default.png")],
          "Give each guide its own image, the first screenshot will do.", "low", "low"),
        F("og-present", "pass", "og:title and og:description on every page", "All 41 pages preview with a title and a description.", "The text under a shared link.", [], "", "low", "low"),
      ],
    },
    {
      id: "off_page_authority", label: "Off-page authority", score: 74, tooltip: "Who links to the site. Graded fully only with Search Console or Ahrefs connected; the crawl sees a part of it.",
      fail_count: 0, warn_count: 0, pass_count: 0, opp_count: 1,
      findings: [
        F("connect-gsc", "opportunity", "Connect Search Console to grade this category", "From the crawl alone, eleven domains link to the tax calendar and none to the invoicing pages; the full picture needs Search Console or Ahrefs.", "Backlinks are votes from other sites; the crawl can only see the ones it stumbles on.",
          [U("/guides/tax-calendar-2026", "11 referring domains seen")],
          "Connect Search Console in Duct and rerun the audit.", "medium", "low"),
      ],
    },
  ],
  roadmap: [
    { label: "Week 1", theme: "Unblock", tasks: [
      { task: "Remove the three dead sitemap entries", effort_estimate: "under_1hr" },
      { task: "Drop the noindex on the VAT guide", effort_estimate: "under_1hr" },
      { task: "Retitle the three brand-only posts", effort_estimate: "2_to_4hrs" },
      { task: "Add alt text to the 28 screenshots", effort_estimate: "2_to_4hrs" },
    ] },
    { label: "Weeks 2–4", theme: "Structure", tasks: [
      { task: "Rewrite the pricing paragraph on the three invoicing pages as a table", effort_estimate: "1_to_3_days" },
      { task: "Link the tax calendar from every invoicing page", effort_estimate: "2_to_4hrs" },
      { task: "Add author and date to the twelve guides", effort_estimate: "1_to_3_days" },
      { task: "Open each guide with the answer", effort_estimate: "1_to_3_days" },
    ] },
    { label: "Months 2–3", theme: "Compound", tasks: [
      { task: "Write the quarterly tax estimate guide", effort_estimate: "1_to_2_wks" },
      { task: "Build the invoice template page", effort_estimate: "1_to_2_wks" },
      { task: "Refresh the four stale posts", effort_estimate: "1_to_3_days" },
      { task: "Add FAQ blocks and schema to the tax pillar", effort_estimate: "ongoing", note: "One post a week; measure AI citations in Search Console." },
    ] },
  ],
});

// The content plan for the story week. Five days on the board: two published,
// one drafted and scheduled, two still planned. TikTok first, because that is
// where Solo's freelancers are.
const PILLARS = ["Money habits", "Tax without fear", "Invoicing", "Behind the app"];
const DAYS = [
  { topic: "What a freelancer's September looks like", pillar: "Money habits", hook_type: "story", post_type: "slideshow" },
  { topic: "Late-paying client? Say this.", pillar: "Invoicing", hook_type: "hook", post_type: "video" },
  { topic: "The 12% rule for tax money", pillar: "Tax without fear", hook_type: "hook", post_type: "slideshow" },
  { topic: "Net 30 is a choice", pillar: "Invoicing", hook_type: "hook", post_type: "slideshow" },
  { topic: "We rebuilt Android onboarding. Here's why.", pillar: "Behind the app", hook_type: "story", post_type: "video" },
];
const STATUS = ["posted", "posted", "draft", "pending", "pending"];

export const PLAN = Object.freeze({
  id: "plan_solo_w37",
  name: `Week of ${STORY.week.label}`,
  start_date: STORY.week.start,
  character: "Practical, warm, a little dry. Numbers over adjectives.",
  days: DAYS.map((d, i) => ({
    day: i + 1,
    ...d,
    hook_text: d.topic,
    platforms: d.post_type === "video" ? ["tiktok", "youtube"] : ["tiktok", "instagram"],
    format_slug: d.post_type === "video" ? "talking-head" : "carousel",
    status: STATUS[i],
    post_id: STATUS[i] === "pending" ? null : `post_${i + 1}`,
  })),
});

// Cover images for the posts that exist. Served by the mock backend from
// scripts/shots/assets when the shots tool runs; relative, like the real
// upload paths, so the app resolves them against the API it is pointed at.
const COVERS = {
  post_1: "/uploads/story/post-september.jpg",
  post_2: "/uploads/story/post-invoice.jpg",
  post_3: "/uploads/story/post-tax-jar.jpg",
};

const dayAt = (i, time = "17:30") => `2026-09-${String(8 + i).padStart(2, "0")}T${time}:00Z`;

// The posts the plan links to: two published through Duct, one draft
// scheduled for Wednesday. The draft is the post the content session drafts.
export const POSTS = Object.freeze(
  Object.fromEntries(
    PLAN.days.filter((d) => d.post_id).map((d, i) => [
      d.post_id,
      {
        id: d.post_id,
        topic: d.topic,
        hook_text: d.hook_text,
        pillar: d.pillar,
        post_type: d.post_type,
        platforms: d.platforms,
        format_name: d.post_type === "video" ? "Talking head" : "Carousel",
        status: d.status,
        published_via: d.status === "posted" ? "duct" : "",
        posted_at: d.status === "posted" ? dayAt(i) : null,
        scheduled_at: d.status === "draft" ? dayAt(i) : null,
        thumbnail_url: COVERS[d.post_id],
        slide_count: d.post_type === "video" ? 1 : 6,
        caption: `${d.topic} — the short version. Full breakdown in Solo.`,
        hashtags: ["freelance", "budgeting", "selfemployed", "solo"],
      },
    ]),
  ),
);

// The carousel the content agent drafts in the session: six structured
// slides, the first one already rendered. Same shape the backend's PostDraft
// emits on post_draft_updated (slides_html is added by the shots tool, which
// carries the backend's slide CSS).
const TAX_PROMPT =
  "Freelancer's desk from slightly above, laptop with a blurred spreadsheet, ceramic mug, a glass jar of folded euro notes and coins, warm window light, no text";

export const DRAFT_POST = Object.freeze({
  ...POSTS.post_3,
  plan_id: PLAN.id,
  day_index: 2,
  layout: "full-bleed",
  tiktok_title: "The 12% rule for tax money",
  caption: "Every payment that lands, move 12% out the same day. Not 30%, not “whatever is left”. It is not your tax rate, it is the amount you will not miss. Full breakdown in Solo.",
  hashtags: ["freelancetax", "selfemployed", "moneyhabits", "solo"],
  slides: [
    { slide_id: "slide-01", kind: "photo", role: "hook", caption_style: "hook", headline: "The 12% rule", subtext: "for tax money", image_prompt: TAX_PROMPT, image_prompt_used: TAX_PROMPT, image_url: COVERS.post_3, aspect_ratio: "9:16" },
    { slide_id: "slide-02", kind: "text", role: "finding", caption_style: "body-neutral", headline: "Every payment that lands: move 12% out the same day.", subtext: "Before rent. Before coffee." },
    { slide_id: "slide-03", kind: "photo", role: "finding", caption_style: "cap-stroke", headline: "Not 30%. Not “whatever is left”.", image_prompt: "Close-up of a hand moving a single coin from a small pile to a jar, wooden table, soft morning light", aspect_ratio: "9:16" },
    { slide_id: "slide-04", kind: "text", role: "reveal", caption_style: "body-neutral", headline: "It is not your tax rate.", subtext: "It is the amount you will not miss." },
    { slide_id: "slide-05", kind: "photo", role: "bridge", caption_style: "cap-whisper", headline: "One account. Named “not mine”.", image_prompt: "A phone on a desk showing a plain banking screen with one highlighted account, out of focus, warm light, no readable text", aspect_ratio: "9:16" },
    { slide_id: "slide-06", kind: "photo", role: "cta", caption_style: "cap-pill", headline: "Save this for the 25th.", subtext: "Solo moves it for you.", image_prompt: "The same freelancer desk at golden hour, jar now fuller, laptop closed, calm", aspect_ratio: "9:16" },
  ],
});

export const PLAN_PILLARS = PILLARS;
