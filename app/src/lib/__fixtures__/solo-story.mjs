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
// Sources are the pulls the agent reports, in order (`label` for the answer
// cards, `entity` and the window for the session's logo rows); `recalled` the
// memories it opened with.
export const ANSWERS = Object.freeze({
  product: {
    question: "Why did activation drop after the Android onboarding release?",
    recalled: ["mem-android", "mem-clarity"],
    sources: [
      { id: "ga4", label: "ga4 onboarding funnel by platform · 25 Aug → 14 Sep", entity: "ga4_landing_pages", from: "2026-08-25", to: "2026-09-14" },
      { id: "clarity", label: "clarity rage clicks by screen · 25 Aug → 14 Sep", entity: "clarity_friction", from: "2026-09-12", to: "2026-09-14" },
      { id: "stripe", label: "stripe trial starts · 25 Aug → 14 Sep", entity: "stripe_subscriptions", from: "2026-08-25", to: "2026-09-14" },
    ],
    answer: `**Android activation fell from ${STORY.numbers.activation.androidBefore} to ${STORY.numbers.activation.androidAfter} on 2 Sep, the day the rebuild shipped. iOS did not move.** The rebuild put the bank step behind a system permission prompt, and Android users who tap Deny land on an empty screen: that is where this week's three rage-click clusters are. Two events to track below, so next week's brief can prove the fix.`,
  },
  paid: {
    question: "Where is the ads budget leaking this week?",
    recalled: ["mem-cpa", "mem-legacy"],
    sources: [
      { id: "google_ads", label: `google ads campaigns · ${STORY.week.start} → ${STORY.week.end}`, entity: "campaign_performance", from: STORY.week.start, to: STORY.week.end },
      { id: "google_ads", label: `google ads search terms · ${STORY.week.start} → ${STORY.week.end}`, entity: "search_terms", from: STORY.week.start, to: STORY.week.end },
      { id: "ga4", label: `ga4 signups by campaign · ${STORY.week.start} → ${STORY.week.end}`, entity: "ga4_conversion_paths", from: STORY.week.start, to: STORY.week.end },
      { id: "stripe", label: `stripe subscriptions · ${STORY.week.start} → ${STORY.week.end}`, entity: "stripe_subscriptions", from: STORY.week.start, to: STORY.week.end },
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

// One session per connector, for its page on the site: the question that
// connector is the one to answer, the sources it reads beside it, one
// clarifying question, the answer, the brief, and the change set where Duct
// can act on that tool. Each is told from what the connector really reads
// (its fetcher and its knowledge pack under backend/agents/knowledge), so a
// page never shows Duct answering from data it cannot see. Google Ads and
// GA4 already have theirs: the paid and product sessions above.
const src = (id, entity, from = STORY.week.start, to = STORY.week.end) => ({ id, entity, from, to });
const opt = (label, description) => ({ label, description });
const titled = (spec) => ({ title: spec.title, h1: spec.h1, html: brief(spec) });

export const CONNECTOR_SESSIONS = Object.freeze([
  {
    connector: "openai_ads", shot: "session-chatgpt-ads", verify: 5,
    question: "What is ChatGPT Ads actually buying us?",
    recalled: ["mem-cpa", "mem-pref"],
    todos: ["Pull ChatGPT Ads spend and clicks for the week", "Follow the clicks through GA4 to Stripe", "Cost the channel per paying customer"],
    sources: [src("openai_ads", "openai_ads_campaign_performance"), src("ga4", "ga4_landing_pages"), src("stripe", "stripe_subscriptions")],
    thinking: ["ChatGPT's report stops at spend and clicks. ", "The signups have to come from GA4 and the payments from Stripe."],
    ask: { question: "What should ChatGPT Ads be judged on?", header: "Goal", options: [opt("Paying customers", "What Stripe settled"), opt("Signups", "The €12 CPA target")], pick: "Paying customers" },
    answer: "Paying customers it is. **€640 bought 1,130 clicks and 48 signups at €13.30, close to the €12 target. Three of them have paid: €213 a paying customer, against €24 on brand search.** ChatGPT's own report ends at the click; the signups are GA4's and the payments Stripe's. The brief is on the right.",
    close: "Two of the three who paid came in on the tax calendar. I'll check again on 28 Sep, when this week's trials end.",
    memory: { title: "Re-check ChatGPT Ads paying customers on 28 Sep", kind: "watch" },
    brief: titled({
      title: "ChatGPT Ads",
      h1: "ChatGPT Ads buys signups on target and customers at €213.",
      sources: "ChatGPT Ads, GA4, Stripe",
      verdict: "The channel looks cheap in its own report because the report ends at the click. Joined to GA4 and Stripe it brings signups near the €12 target, and very few who pay so far.",
      kpis: [
        kpi("€640", "Spend", "this week"),
        kpi("1,130", "Clicks", "€0.57 a click"),
        kpi("48", "Signups · GA4", "€13.30 each"),
        kpi("3", "Paying · Stripe", "€213 each", "down"),
        kpi("€24", "Brand search", "per paying customer", "up"),
        kpi("0", "Conversions in its report", "it has no such metric"),
      ],
      chart: { heading: "Cost per paying customer, by channel", rows: [
        bar("Brand search", 11, "good", "€24"), bar("Performance Max", 25, "", "€54"), bar("ChatGPT Ads", 100, "bad", "€213"),
      ] },
      findings: [
        finding("crit", "The report can't see a conversion", "ChatGPT Ads reports impressions, clicks, spend, CTR, CPC and CPM. Nothing after the click, so CPC is not the number to judge it on."),
        finding("warn", "Signups arrive, payments lag", "48 signups at €13.30 is near target. Most of their trials end on 28 Sep, so the three will move."),
        finding("good", "The tax calendar lands", `Two of the three payers came in on <i>${n.blogPost}</i>, the page that already converts from search.`),
      ],
      todo: [
        "Hold the budget until the trials end on 28 Sep.",
        "Point the ads at the tax calendar, the page the payers came in on.",
        "Judge it on paying customers, not CPC.",
      ],
    }),
  },
  {
    connector: "stripe", shot: "session-stripe", verify: 6,
    question: "How many paying customers did the ads bring this week?",
    recalled: ["mem-cpa", "mem-pref"],
    todos: ["Pull Google Ads and Meta conversions for the week", "Count first payments in Stripe", "Reconcile the two"],
    sources: [src("google_ads", "campaign_performance"), src("meta_ads", "meta_ads_campaign_insights"), src("stripe", "stripe_subscriptions"), src("stripe", "stripe_charges")],
    thinking: ["The two platforms claim 64 purchases. ", "Separate first payments from upgrades and abandoned checkouts before comparing."],
    ask: { question: "Count upgrades as new customers?", header: "Counting", options: [opt("New customers only", "First payments, no plan changes"), opt("Include upgrades", "Any new paid subscription")], pick: "New customers only" },
    answer: "New customers only. **Stripe settled 23 first payments this week, from every channel together. Google Ads and Meta claim 64 between them.** Another 18 checkouts started and never charged, and 6 new subscriptions were upgrades from people already paying. The brief is on the right.",
    close: "From next week, every paid number in the brief is checked against Stripe first.",
    memory: { title: "Paid conversions are reconciled to Stripe first payments", kind: "decision" },
    brief: titled({
      title: "Revenue",
      h1: "The ads claim 64 customers. Stripe settled 23.",
      sources: "Stripe, Google Ads, Meta Ads",
      verdict: "Each ad platform counts conversions its own way, and some of the same people twice. Stripe counts money: 23 new paying customers this week, across every channel, organic included.",
      kpis: [
        kpi("23", "First payments", "every channel"),
        kpi("64", "Claimed by the ads", "Google 23 · Meta 41", "down"),
        kpi("18", "Never charged", "abandoned checkouts", "down"),
        kpi("6", "Upgrades", "expansion, not new"),
        kpi("€276", "New MRR", "23 × €12 a month", "up"),
        kpi(n.mrr, "MRR", `▲ ${n.mrrDelta.replace("+", "")}`, "up"),
      ],
      chart: { heading: "Paying customers: claimed and settled", rows: [
        bar("Meta · default window", 100, "bad", "41"), bar("Google Ads", 56, "", "23"), bar("Stripe · every channel", 56, "good", "23"),
      ] },
      findings: [
        finding("crit", "The platforms claim nearly three times what settled", "64 claimed against 23 first payments, and Stripe's 23 includes organic and ChatGPT. Some customers are counted by both platforms."),
        finding("warn", "18 checkouts never charged", "Incomplete subscriptions are abandoned or failed checkouts, not sales. Counting them would have made it 41."),
        finding("good", "Upgrades are healthy", "6 customers moved to annual this week. Expansion, counted apart from acquisition."),
      ],
      todo: [
        "Judge paid channels on Stripe first payments, not platform conversions.",
        "Look at the 18 abandoned checkouts: 11 failed on card authentication.",
        "Compare Meta on one-day click before moving budget to it.",
      ],
    }),
  },
  {
    connector: "meta_ads", shot: "session-meta-ads", verify: 6,
    question: "Why does Meta look three times cheaper than Google?",
    recalled: ["mem-cpa", "mem-pref"],
    todos: ["Pull Meta campaigns and ad sets, paused ones included", "Re-count purchases on Google's window", "Compare cost per purchase"],
    sources: [src("meta_ads", "meta_ads_ad_sets"), src("meta_ads", "meta_ads_campaign_insights"), src("google_ads", "campaign_performance")],
    thinking: ["Meta's default credits a click for a week and a view for a day. ", "And one purchase can arrive under three action types. Count it once."],
    ask: { question: "Compare on which attribution window?", header: "Attribution", options: [opt("One-day click", "The way Google counts"), opt("Meta's default", "7-day click, 1-day view")], pick: "One-day click" },
    answer: "One-day click it is. **Meta isn't cheaper. On its default window it claims 41 purchases at €34; counted the way Google counts, one-day click and one action type, it's 14, at €100. Google is at €105.** The lookalike ad set earns its budget; retargeting mostly collects credit from views. The brief is on the right.",
    close: "Meta is read-only in Duct, so moving retargeting's €25 a day into the lookalike is yours to make.",
    memory: { title: "Compare Meta and Google on one-day click, one purchase action type", kind: "decision" },
    brief: titled({
      title: "Meta",
      h1: "Meta's €34 purchase is €100 on Google's terms.",
      sources: "Meta Ads, Google Ads",
      verdict: "Two things flatter Meta: a longer attribution window, and one purchase reported under up to three action types. On one-day click, counting the pixel purchase once, it costs what Google costs.",
      kpis: [
        kpi("€1,400", "Spend", "3 ad sets"),
        kpi("41", "Purchases · default", "7-day click, 1-day view"),
        kpi("14", "Purchases · 1-day click", "one action type", "down"),
        kpi("€100", "Per purchase · 1-day click", "€34 on the default", "down"),
        kpi("€105", "Google Ads", "per purchase"),
        kpi("€71", "Lookalike ad set", "per purchase", "up"),
      ],
      chart: { heading: "Cost per purchase at one-day click, by ad set", rows: [
        bar("Lookalike · freelancers", 44, "good", "€71"), bar("Interest · finance", 66, "", "€106"), bar("Retargeting · site", 100, "bad", "€160"),
      ] },
      findings: [
        finding("crit", "One purchase, three action types", "Meta reports the same order as pixel purchase, purchase and omni purchase. Summed, that alone triples the count; Duct reads the pixel purchase once."),
        finding("warn", "Retargeting lives on views", "€160 a purchase at one-day click. Most of its default-window credit comes from people who saw an ad, not people who clicked one."),
        finding("good", "The lookalike works", "€71 a purchase on Google's terms, under Google and under the account average."),
      ],
      todo: [
        "Move retargeting's €25 a day into the lookalike. Read-only in Duct, so that one's yours.",
        "Report Meta on one-day click from now on.",
        "Budgets come back in cents: 2500 is €25 a day, not €2,500.",
      ],
    }),
  },
  {
    connector: "apple_ads", shot: "session-apple-search-ads", verify: 5,
    question: "Is the Discovery bid raise on Apple Search Ads paying off?",
    recalled: ["mem-cpa", "mem-pref"],
    todos: ["Pull Solo's Apple Search Ads campaigns, day by day", "Check trials in RevenueCat over the same days", "Decide whether the raise pays"],
    sources: [src("apple_ads", "apple_ads_campaign_report"), src("apple_ads", "apple_ads_daily_report", "2026-09-01"), src("revenuecat", "revenuecat_metrics_overview", "", "")],
    thinking: ["The org also runs Solo Invoices. ", "Condition the report on Solo's four campaigns before adding anything up."],
    ask: { question: "Which installs should I count?", header: "Installs", options: [opt("Tap-through only", "Tapped the ad, then installed"), opt("Include view-through", "Saw the ad, installed later")], pick: "Tap-through only" },
    answer: "Tap-through it is. **Not yet. Discovery's installs doubled after the 5 Sep raise, to 610 at €1.90 each, and active trials in RevenueCat stayed at 214.** Apple reports installs, never subscribers, so RevenueCat is the check. Everything is scoped to Solo's four campaigns: the org-wide report also carries Solo Invoices, which would have added €1,180. The brief is on the right.",
    close: "Apple Search Ads is read-only in Duct, so the Discovery bid is yours to lower. Brand and Category can keep theirs.",
    memory: { title: "Scope Apple Search Ads reports to Solo's campaigns; Solo Invoices shares the org", kind: "status" },
    brief: titled({
      title: "Apple Search Ads",
      h1: "Discovery doubled its installs. Trials didn't move.",
      sources: "Apple Search Ads, RevenueCat",
      verdict: "The 5 Sep bid raise bought installs that don't start trials. Brand and Category keep converting; Discovery's extra 300 installs a week show up nowhere in RevenueCat.",
      kpis: [
        kpi("€1,920", "Spend · Solo only", "org total adds €1,180"),
        kpi("1,370", "Tap installs", "€1.40 each"),
        kpi("610", "Discovery installs", "2× since 5 Sep"),
        kpi("€1.90", "Discovery per install", "▲ from €1.10", "down"),
        kpi("214", "Active trials · RevenueCat", "211 a week ago"),
        kpi("1,120", "Active subscriptions", "App Store + Play"),
      ],
      chart: { heading: "Tap installs by campaign, this week", rows: [
        bar("Brand", 38, "good", "230"), bar("Category", 57, "good", "350"), bar("Competitors", 30, "", "180"), bar("Discovery", 100, "bad", "610"),
      ] },
      findings: [
        finding("crit", "Discovery buys installs that don't trial", "610 installs this week, twice the week before, and active trials went from 211 to 214."),
        finding("warn", "The org-wide report mixes two apps", "Without a campaign filter Apple adds Solo Invoices' spend to Solo's. Every number here is scoped to Solo's four campaigns."),
        finding("good", "Brand and Category hold", "580 installs between them at €1.10, steady since August."),
      ],
      todo: [
        "Take Discovery back to its old bid. Read-only in Duct, so that one's yours.",
        "Leave Brand and Category alone.",
        "Judge Apple on RevenueCat trials, never on installs.",
      ],
    }),
  },
  {
    connector: "gsc", shot: "session-search-console", verify: 5,
    question: `Impressions are up ${n.organicImpressionsDelta.replace("+", "")}. Why are organic trials flat?`,
    recalled: ["mem-pref"],
    todos: ["Pull queries, pages and query × page from Search Console", "Match landing pages to trials in GA4", "Find where the impressions went"],
    sources: [src("gsc", "gsc_query_performance", "2026-08-18"), src("gsc", "gsc_query_page", "2026-08-18"), src("ga4", "ga4_landing_pages", "2026-08-18")],
    thinking: ["The last three days aren't final yet. ", "Read query × page: a flat table can't show two pages splitting one query."],
    ask: { question: "The last three days aren't final yet. Include them?", header: "Window", options: [opt("Include, labelled", "Newest data, marked unfinished"), opt("Final data only", "Stop on 11 Sep")], pick: "Include, labelled" },
    answer: "Included and labelled. **The new impressions are on queries you don't convert. Two invoicing queries gained 38,000 impressions at positions 11 and 12 and drew 190 clicks, and each is split between two of your pages.** The tax pages still earn 61% of organic trials from 28% of the clicks. The brief is on the right.",
    close: "Nothing to change in Search Console itself: merging /invoice-template into /invoicing stops the two pages splitting both queries.",
    memory: { title: "/invoicing and /invoice-template split the same two queries", kind: "watch" },
    brief: titled({
      title: "Organic",
      h1: `Impressions up ${n.organicImpressionsDelta.replace("+", "")}, on queries that don't convert.`,
      sources: "Search Console, GA4",
      verdict: "The growth is invoicing queries ranking just off page one, where two Solo pages compete for each. The tax cluster, which earns most organic trials, is flat and healthy.",
      kpis: [
        kpi(n.organicImpressionsDelta, "Impressions", "28 days", "up"),
        kpi("+2%", "Clicks", "28 days"),
        kpi("312", "Organic trials", "▲ 1%"),
        kpi("38,000", "New invoicing impressions", "positions 11–12"),
        kpi("190", "Clicks from them", "0.5% CTR", "down"),
        kpi("2", "Pages per query", "cannibalised", "down"),
      ],
      chart: { heading: "Share of clicks and trials, by cluster", rows: [
        bar("Tax · clicks", 28), bar("Tax · trials", 61, "good"), bar("Invoicing · clicks", 41), bar("Invoicing · trials", 9, "bad"),
      ] },
      findings: [
        finding("crit", "Two pages split each invoicing query", "Query × page shows /invoicing and /invoice-template both ranking for “freelance invoice template” and “invoice generator for freelancers”. Neither reaches page one."),
        finding("warn", "Most clicks have no query attached", "The page table shows 3.4× the clicks of the query table: Google anonymises rare queries. Totals here use pages."),
        finding("good", "The tax cluster converts", `28% of the clicks, 61% of organic trials. <i>${n.blogPost}</i> ranks on page one for two target terms.`),
      ],
      todo: [
        "Merge /invoice-template into /invoicing with a 301.",
        "Leave the tax pages alone.",
        "Re-read query × page in two weeks, once the merge is indexed.",
      ],
    }),
  },
  {
    connector: "gtm", shot: "session-tag-manager", verify: 4,
    question: "Why did GA4 stop counting Connect bank on the web?",
    recalled: ["mem-android", "mem-pref"],
    todos: ["Find where connect_bank stopped counting", "Check the app and the web apart", "Stage the fix in Tag Manager"],
    sources: [src("ga4", "ga4_landing_pages", "2026-09-01"), src("mixpanel", "mixpanel_event_counts", "2026-09-01")],
    thinking: ["Mixpanel still sees connect_bank on the web. GA4 went to zero on 9 Sep. ", "Something in the web container changed that day."],
    ask: { question: "Fix it in Tag Manager or in GA4?", header: "Fix", options: [opt("The tag in Tag Manager", "Send connect_bank again, one name everywhere"), opt("The key event in GA4", "Count connectBank too, two names from now on")], pick: "The tag in Tag Manager" },
    answer: "The tag it is. **Version 14, published 9 Sep, renamed the event the GA4 · Connect bank tag sends to connectBank. GA4's key event is still connect_bank, so web completions went from 212 a week to zero that day.** The app sends the event directly and never stopped. Two changes below: fix the tag in the workspace, then publish. The publish replaces the live container, so it waits for you.",
    close: "If anything looks wrong after the publish, rolling back republishes version 14.",
    memory: { title: "Container version 14 renamed connect_bank; web counts from 9 to 14 Sep are missing", kind: "event" },
    change_set: {
      change_set_id: "cs_solo_0914", id: "cs_solo_0914",
      connector_type: "gtm", account_id: "GTM-K7S0L9Q", account_name: "solobudget.app · web",
      title: "Send connect_bank from the web again",
      context: "Version 14 renamed the event the GA4 · Connect bank tag sends. Fix the tag in the workspace, then publish; rollback republishes version 14.",
      status: "proposed", source: "insights", project_id: STORY.project.id,
      created_at: "2026-09-14T08:20:00Z", auto_apply_eligible: false, applied_by: null,
      changes: [
        { id: "c1", op_type: "gtm.upsert_tag", status: "pending", diff: "Update tag “GA4 · Connect bank” in Default Workspace: event name connectBank → connect_bank" },
        { id: "c2", op_type: "gtm.publish_version", status: "pending", destructive: true, diff: "Publish the workspace as version 15, replacing live version 14 for every visitor", warnings: ["Rollback republishes version 14"] },
      ],
    },
    brief: titled({
      title: "Tracking",
      h1: "Web Connect bank stopped counting on 9 Sep.",
      sources: "GA4, Tag Manager",
      verdict: "Nothing broke in the product. A container version renamed the event the web tag sends, and GA4 kept counting the old name. The funnel has read zero web completions since.",
      kpis: [
        kpi("0", "Web connect_bank", "▼ from 212 a week", "down"),
        kpi("1,040", "App connect_bank", "same as the week before"),
        kpi("v14", "Live container", "published 9 Sep"),
        kpi("1", "Tag changed", "GA4 · Connect bank"),
        kpi("6 days", "Web data missing", "9 → 14 Sep", "down"),
        kpi("v14", "Rollback target", "if the publish misbehaves"),
      ],
      chart: { heading: "connect_bank a week, by platform", rows: [
        bar("Web · before 9 Sep", 20, "", "212"), bar("Web · since 9 Sep", 1, "bad", "0"), bar("App · before 9 Sep", 100, "good", "1,050"), bar("App · since 9 Sep", 99, "good", "1,040"),
      ] },
      findings: [
        finding("crit", "The tag fires. It sends the wrong name.", "Version 14 changed the event name in GA4 · Connect bank from connect_bank to connectBank. The tag fired on every completion; GA4 counted none of them as the key event."),
        finding("warn", "Six days of web funnel are missing", "9–14 Sep can't be recovered in GA4. Mixpanel saw those completions, so use it for that week."),
        finding("good", "The app was never affected", "iOS and Android send connect_bank directly, not through the container."),
      ],
      todo: [
        "Point the tag back at connect_bank in the workspace. Proposed in chat.",
        "Publish it as version 15. It replaces the live container, so it waits for you.",
        "Use Mixpanel for web Connect bank from 9 to 14 Sep.",
      ],
    }),
  },
  {
    connector: "mixpanel", shot: "session-mixpanel", verify: 5,
    question: "Did the Android rebuild lift upgrades?",
    recalled: ["mem-android", "mem-pref"],
    todos: ["Pull upgrades from Mixpanel either side of 2 Sep", "Take internal accounts out", "Check it against Stripe"],
    sources: [src("mixpanel", "mixpanel_event_counts", "2026-08-19"), src("stripe", "stripe_subscriptions", "2026-08-19")],
    thinking: ["Upgrades jumped the fortnight the new paywall was in QA. ", "Mixpanel has no internal-traffic filter. Check who those upgrades are."],
    ask: { question: "Which accounts are internal?", header: "Internal", options: [opt("@solobudget.app and qa-*", "Staff and the QA test accounts"), opt("@solobudget.app only", "Staff accounts")], pick: "@solobudget.app and qa-*" },
    answer: "Both, then. **No. Upgrades look up 18% since 2 Sep, and 12 of them came from QA accounts testing the new paywall. Without them the upgrade rate is 4.0%, against 4.1% before.** Stripe agrees: 46 new paid subscriptions this fortnight, 47 the one before. Two changes below, both reversible.",
    close: "With the annotation in, anyone reading a Mixpanel chart that crosses 2 Sep will see why.",
    memory: { title: "Exclude @solobudget.app and qa-* accounts from every Mixpanel count", kind: "decision" },
    change_set: {
      change_set_id: "cs_solo_0915", id: "cs_solo_0915",
      connector_type: "mixpanel", account_id: "mp-solo", account_name: "Solo (EU)",
      title: "Mark the rebuild, hide the typo event",
      context: "An annotation on 2 Sep so every chart that crosses the rebuild says why, and the Android 3.x typo event hidden so no one sums it with its twin.",
      status: "proposed", source: "insights", project_id: STORY.project.id,
      created_at: "2026-09-14T08:40:00Z", auto_apply_eligible: false, applied_by: null,
      changes: [
        { id: "c1", op_type: "mixpanel.create_annotation", status: "pending", diff: "Annotate 2 Sep 2026: “Android onboarding rebuild shipped”" },
        { id: "c2", op_type: "mixpanel.hide_event", status: "pending", diff: "Hide plan_upgrade_initated in Lexicon, the typo twin of plan_upgrade_initiated" },
      ],
    },
    brief: titled({
      title: "Upgrades",
      h1: "The rebuild didn't lift upgrades. The QA team did.",
      sources: "Mixpanel, Stripe",
      verdict: "The 18% jump after 2 Sep is test accounts running through the new paywall. Without them the upgrade rate is flat, and Stripe's new paid subscriptions say the same.",
      kpis: [
        kpi("+18%", "Upgrades · raw", "what the dashboard shows"),
        kpi("12", "QA upgrades", "inside the funnel", "down"),
        kpi("4.0%", "Upgrade rate · clean", "4.1% before 2 Sep"),
        kpi("46", "New paid · Stripe", "47 the fortnight before"),
        kpi("2", "Upgrade events", "one is a typo", "down"),
        kpi("89%", "Untagged signups", "no utm is not organic"),
      ],
      chart: { heading: "Upgrades a fortnight, either side of 2 Sep", rows: [
        bar("Before · clean", 81, "", "47"), bar("After · raw", 100, "bad", "58"), bar("After · clean", 79, "good", "46"), bar("Stripe · after", 79, "good", "46"),
      ] },
      findings: [
        finding("crit", "Test accounts are inside every funnel", "Mixpanel has no internal-traffic filter. 12 of the 58 upgrades since 2 Sep came from qa-* accounts on the new paywall."),
        finding("warn", "Two names for one event", "plan_upgrade_initated, a typo from Android 3.x, still fires beside plan_upgrade_initiated. One saved funnel counts both."),
        finding("good", "Stripe and Mixpanel agree once it's clean", "46 against 46. Mixpanel is the count across platforms; Stripe is the money."),
      ],
      todo: [
        "Annotate 2 Sep on the Mixpanel timeline. Proposed in chat.",
        "Hide plan_upgrade_initated in Lexicon. Proposed in chat.",
        "Leave the paywall as it is: it neither helped nor hurt.",
      ],
    }),
  },
  {
    connector: "clarity", shot: "session-clarity", verify: 5,
    question: "Why does the Freelancers landing page lose paid visitors?",
    recalled: ["mem-clarity", "mem-pref"],
    todos: ["Pull Clarity friction per page for the last three days", "Match pages to paid sessions in GA4", "Find what people are clicking"],
    sources: [src("clarity", "clarity_friction", "2026-09-12"), src("ga4", "ga4_landing_pages")],
    thinking: ["312 of 2,140 sessions are bots. Take them out before any rate. ", "Compare pages by share of sessions, not raw counts."],
    ask: { question: "Clarity only keeps three days. Is that enough?", header: "Window", options: [opt("Read them, then watch daily", "Pull every morning until it's fixed"), opt("Just these three days", "One read, no follow-up")], pick: "Read them, then watch daily" },
    answer: "Three days now, then daily. **The pricing toggle on /freelancers is broken on Android Chrome. 14% of that page's sessions had a rage click, almost all on the monthly/annual switch, beside a script error on the same page.** Paid search sends 71% of the page's visitors, so the campaign is paying for a page that doesn't work. The brief is on the right.",
    close: "Nothing to apply: the fix is in the page. I'll pull Clarity every morning until the toggle stops failing.",
    memory: { title: "Watch rage clicks on the /freelancers pricing toggle daily", kind: "watch" },
    brief: titled({
      title: "Landing page",
      h1: "/freelancers has a broken pricing toggle on Android.",
      sources: "Clarity, GA4",
      verdict: "Not a bidding problem. The page most paid visitors land on throws a script error on Android Chrome, and the monthly/annual switch stops responding.",
      kpis: [
        kpi("14%", "Rage-click sessions", "/freelancers", "down"),
        kpi("1%", "Rage-click sessions", "home page", "up"),
        kpi("9%", "Script-error sessions", "all Android Chrome", "down"),
        kpi("22%", "Quick-backs", "left within seconds", "down"),
        kpi("71%", "From paid search", "of /freelancers sessions"),
        kpi("312", "Bot sessions removed", "of 2,140"),
      ],
      chart: { heading: "Sessions with a rage click, by page", rows: [
        bar("/freelancers · Android", 100, "bad", "21%"), bar("/freelancers · iOS", 14, "", "3%"), bar("/tax-calendar", 10, "good", "2%"), bar("Home", 5, "good", "1%"),
      ] },
      findings: [
        finding("crit", "The toggle throws on Android Chrome", "Script errors on 9% of /freelancers sessions, every one on Android Chrome, and the rage clicks sit on the same switch."),
        finding("warn", "Paid visitors hit it first", "71% of the page's sessions come from paid search. The ads are fine; the page after them isn't."),
        finding("good", "The rest of the site is calm", "The tax calendar and the home page sit at 1–2% rage-click sessions."),
      ],
      todo: [
        "Fix the toggle's script error on Android Chrome.",
        "Until then, send Performance Max to /tax-calendar instead.",
        "Clarity keeps three days, so it gets read every morning.",
      ],
    }),
  },
  {
    connector: "growthbook", shot: "session-growthbook", verify: 4,
    question: "Is the annual-first pricing test ready to call?",
    recalled: ["mem-pref"],
    todos: ["Pull the experiment, its phases and results", "Check exposures are still arriving", "Check the result against Stripe"],
    sources: [src("growthbook", "growthbook_experiments", "2026-07-20"), src("stripe", "stripe_subscriptions", "2026-07-20")],
    thinking: ["It says running, with a 94% chance to win. ", "Check exposures first: running is a setting, not a signal."],
    ask: { question: "What should the test be judged on?", header: "Metric", options: [opt("Annual share of new subscriptions", "What the test was set up to move"), opt("Checkout starts", "Earlier, noisier")], pick: "Annual share of new subscriptions" },
    answer: "Annual share it is. **No. It stopped bucketing on 1 Sep, when its assignment query was edited, and the control arm has 62 users against a minimum of 150.** GrowthBook still shows it running at a 94% chance to win; on 62 users that is noise. Stripe puts annual at 31% of new subscriptions before and during the test. The brief is on the right.",
    close: "Duct doesn't change GrowthBook: fixing the assignment query and restarting the test are yours.",
    memory: { title: "Annual-first test stopped bucketing on 1 Sep; results after that are not results", kind: "event" },
    brief: titled({
      title: "Experiment",
      h1: "The pricing test says running. It stopped on 1 Sep.",
      sources: "GrowthBook, Stripe",
      verdict: "The test has bucketed nobody for two weeks and never reached its minimum sample. Its 94% chance to win is computed on 62 control users. Nothing here can be called.",
      kpis: [
        kpi("56 days", "Marked running", "since 20 Jul"),
        kpi("1 Sep", "Last exposure", "assignment query edited", "down"),
        kpi("62", "Control users", "minimum 150", "down"),
        kpi("94%", "Chance to win", "on an underpowered arm"),
        kpi("31%", "Annual share · Stripe", "before and during"),
        kpi("0", "Exposures this week", "stale", "down"),
      ],
      chart: { heading: "Users per arm against the minimum sample", rows: [
        bar("Minimum", 100, "", "150"), bar("Control", 41, "bad", "62"), bar("Annual first", 45, "bad", "68"),
      ] },
      findings: [
        finding("crit", "Nobody has been bucketed since 1 Sep", "Exposures stopped the day the assignment query was edited. The experiment still shows running, and nothing in GrowthBook flagged it."),
        finding("warn", "Both arms are under the minimum", "62 and 68 users against a minimum sample of 150. A chance to win on that is a guess with a percentage sign."),
        finding("good", "Stripe gives the honest baseline", "Annual is 31% of new subscriptions before and during the test. That's the number a restarted test has to beat."),
      ],
      todo: [
        "Fix the assignment query, then restart the test. Duct doesn't write to GrowthBook, so that's yours.",
        "Don't call it on today's numbers.",
        "Once it restarts, check exposures weekly.",
      ],
    }),
  },
  {
    connector: "revenuecat", shot: "session-revenuecat", verify: 5,
    question: "What is the app earning next to the web?",
    recalled: ["mem-pref", "mem-android"],
    todos: ["Pull RevenueCat's overview and a customer sample", "Pull Stripe for the web", "Put app and web side by side"],
    sources: [src("revenuecat", "revenuecat_metrics_overview", "", ""), src("revenuecat", "revenuecat_customers", "", ""), src("stripe", "stripe_subscriptions")],
    thinking: ["Every brief so far has quoted Stripe's MRR. That's the web only. ", "The App Store and Play subscriptions live in RevenueCat."],
    ask: { question: "Count active trials as revenue?", header: "Trials", options: [opt("No, paid only", "MRR from paying subscriptions"), opt("Yes, at the usual rate", "Trials × last month's conversion")], pick: "No, paid only" },
    answer: `Paid only. **The app earns €6,900 MRR on top of Stripe's ${n.mrr}, so Solo is at €25,300, not ${n.mrr}.** RevenueCat shows 1,120 active subscriptions and 214 active trials. In a 500-customer sample, Android users are 41% of the app's users and hold 27% of its paid entitlements. The brief is on the right.`,
    close: "From now on the brief reports MRR as web plus app. RevenueCat is read-only in Duct, so there's nothing to apply.",
    memory: { title: "Report MRR as Stripe (web) plus RevenueCat (app)", kind: "decision" },
    brief: titled({
      title: "Subscriptions",
      h1: `Solo earns €25,300 a month. The briefs said ${n.mrr}.`,
      sources: "RevenueCat, Stripe",
      verdict: "Every brief so far quoted Stripe, which only sees the web. The App Store and Play add €6,900 MRR, most of it from iOS. Android users pay at half the iOS rate.",
      kpis: [
        kpi("€25,300", "MRR · web + app", "first full count", "up"),
        kpi("€6,900", "MRR · app", "RevenueCat"),
        kpi(n.mrr, "MRR · web", "Stripe"),
        kpi("1,120", "Active subscriptions", "App Store + Play"),
        kpi("214", "Active trials", "not counted as revenue"),
        kpi("27%", "Android share of paid", "41% of app users", "down"),
      ],
      chart: { heading: "Share of app users and of paid entitlements, by platform", rows: [
        bar("iOS · users", 52), bar("iOS · paying", 66, "good"), bar("Android · users", 41), bar("Android · paying", 27, "bad"),
      ] },
      findings: [
        finding("crit", "Android pays at half the iOS rate", "41% of the app's users, 27% of its paid entitlements. The Connect bank dead end after the 2 Sep rebuild is the likeliest reason."),
        finding("warn", "The briefs have reported the web alone", `${n.mrr} is Stripe. The app's €6,900 was never in it.`),
        finding("good", "iOS carries the app", "66% of paid entitlements from 52% of the app's users."),
      ],
      todo: [
        "Report MRR as web plus app from now on.",
        "Fix Connect bank on Android before buying more Android users.",
        "Re-read in two weeks, after the fix ships.",
      ],
    }),
  },
]);

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

// The same audit as the agent hands it over, on the briefs' CSS, and the one
// document on the site that has to sell a URL paste on its own: it is looked
// at, not read, and it speaks the language of the person pasting, which is
// keywords, clusters, positions and gaps. A navy header with the score ring
// and what was read; three signals as big numbers; the clusters on a
// position map; the page-two keywords worth a push; the topics competitors
// own; nine score tiles; five fixes of eight words each. What makes it
// Duct's is in the header and the first signal: Search Console positions
// weighed by GA4 trials, so the opportunity is the keywords whose pages
// already convert, and a memory recalled from an earlier brief.
const AUDIT_CSS = `
body{max-width:820px;margin:0 auto;padding:16px 18px 24px}
.hd{background:#0d0f1a;color:#f4ece2;border-radius:14px;padding:20px 22px 18px;display:grid;grid-template-columns:1fr auto;gap:18px;align-items:center;margin-bottom:10px;position:relative;overflow:hidden}
.hd:after{content:"";position:absolute;left:0;right:0;bottom:0;height:3px;background:linear-gradient(90deg,#ff5c00,#ff8c42 60%,transparent)}
.hd .u{font-size:12px;color:#ff8c42;margin-bottom:8px}
.hd h1{font-size:24px;line-height:1.2;color:#fff;font-weight:650;letter-spacing:-.015em;max-width:440px}
.hd .ch{display:flex;flex-wrap:wrap;gap:6px;margin-top:14px}
.hd .ch span{display:inline-flex;align-items:center;gap:6px;font-size:11px;color:#f4ece2;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.12);border-radius:999px;padding:3px 10px 3px 8px}
.hd .ch i{width:7px;height:7px;border-radius:50%;background:#8b8fa8;flex:none}
.hd .ch .gsc i{background:#4285f4}.hd .ch .ga4 i{background:#e37400}.hd .ch .clr i{background:#3aa0ff}.hd .ch .mem i{background:#a78bfa}
.ring{position:relative;width:128px;height:128px;flex:none}
.ring svg{width:128px;height:128px;transform:rotate(-90deg)}
.ring .n{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;line-height:1}
.ring .n b{font-size:40px;font-weight:650;letter-spacing:-.02em;color:#fff;font-variant-numeric:tabular-nums}
.ring .n span{font-size:10px;color:#ff8c42;margin-top:6px;text-transform:uppercase;letter-spacing:.08em;font-weight:600}
.sig{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:6px}
.sg{border-radius:12px;padding:14px 14px 12px;border:1px solid var(--line);background:#fafafa;display:grid;gap:2px}
.sg .v{font-size:30px;font-weight:650;letter-spacing:-.02em;line-height:1;font-variant-numeric:tabular-nums}
.sg .l{font-size:12.5px;color:var(--tx);margin-top:6px;line-height:1.3}
.sg .s{font-size:11px;color:var(--mut)}
.sg.good{background:#f0faf3;border-color:#cfeeda}.sg.good .v{color:var(--good)}
.sg.warn{background:#fff7ed;border-color:#fbd9b9}.sg.warn .v{color:#c2410c}
.sg.bad{background:#fdf1ec;border-color:#f6cbb8}.sg.bad .v{color:var(--crit)}
h2{margin:18px 0 8px}
.map{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 14px 12px}
.ax{display:grid;grid-template-columns:150px 1fr 40px;gap:12px;font-size:10px;color:var(--mut);text-transform:uppercase;letter-spacing:.06em;margin-bottom:6px}
.ax .z{display:grid;grid-template-columns:1fr 1fr 1fr}
.ax .z span:nth-child(2){text-align:center}.ax .z span:nth-child(3){text-align:right}
.cl{display:grid;grid-template-columns:150px 1fr 40px;gap:12px;align-items:center;padding:8px 0;font-size:12.5px}
.cl+.cl{border-top:1px solid #f1f1f3}
.cl .c b{display:block;font-weight:600}.cl .c span{font-size:11px;color:var(--mut)}
.cl .tr{position:relative;height:14px;border-radius:7px;background:linear-gradient(90deg,#e5f6ea 0,#e5f6ea 33.3%,#fdf3e1 33.3%,#fdf3e1 66.6%,#f4f4f6 66.6%)}
.cl .tr i{position:absolute;top:50%;width:18px;height:18px;margin:-9px 0 0 -9px;border-radius:50%;background:var(--accent);border:3px solid #fff;box-shadow:0 1px 3px rgba(0,0,0,.25)}
.cl .tr i.good{background:#22a353}.cl .tr i.warn{background:#e59a2a}.cl .tr i.bad{background:#dc4f2b}
.cl .tr i.none{background:#fff;border:2px dashed #b8bac6;box-shadow:none}
.cl .p{text-align:right;font-weight:650;font-variant-numeric:tabular-nums}
.cl .p.none{color:var(--mut);font-weight:500}
.kw{display:grid;grid-template-columns:34px 1fr 124px 176px;gap:12px;align-items:center;padding:7px 12px;background:var(--card);border:1px solid var(--line);border-radius:10px;margin-bottom:5px;font-size:12.5px}
.kw .pos{width:34px;height:26px;border-radius:7px;background:#fdf3e1;color:#b45309;font-weight:650;font-size:12px;display:flex;align-items:center;justify-content:center;font-variant-numeric:tabular-nums}
.kw .q{font-weight:600}
.kw .vol{display:grid;grid-template-columns:1fr 54px;align-items:center;gap:8px;font-size:11px;color:var(--mut)}
.kw .vol i{display:block;height:6px;border-radius:3px;background:#ececef;overflow:hidden}
.kw .vol i:after{content:"";display:block;height:100%;width:var(--w);border-radius:3px;background:var(--accent)}
.kw .vol b{font-weight:600;color:var(--tx);text-align:right;font-variant-numeric:tabular-nums}
.kw code{font:11px/1.6 ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--mut);text-align:right;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.gap{background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden;font-size:12.5px}
.gap .g{display:grid;grid-template-columns:1fr 92px 92px 92px;align-items:center;padding:8px 14px}
.gap .g+.g{border-top:1px solid #f1f1f3}
.gap .g.h{font-size:10px;color:var(--mut);text-transform:uppercase;letter-spacing:.06em;background:#fafafa}
.gap .g b{font-weight:600}
.gap .g span{text-align:center;font-variant-numeric:tabular-nums}
.gap .ok{color:var(--good);font-weight:600}.gap .no{color:var(--crit);font-weight:650}
.cats{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}
.cat{background:#fafafa;border:1px solid var(--line);border-radius:10px;padding:10px 12px 11px;display:grid;gap:6px}
.cat .r{display:flex;justify-content:space-between;align-items:baseline;font-size:12px;color:var(--mut)}
.cat .r b{font-size:22px;font-weight:650;letter-spacing:-.01em;color:var(--tx);font-variant-numeric:tabular-nums}
.cat i{display:block;height:6px;border-radius:3px;background:#ececef;overflow:hidden}
.cat i:after{content:"";display:block;height:100%;width:var(--w);border-radius:3px;background:var(--accent)}
.cat.bad i:after{background:#ef7a55}.cat.bad .r b{color:var(--crit)}
.cat.good i:after{background:#57c47a}.cat.good .r b{color:var(--good)}
.fix{display:grid;grid-template-columns:28px 1fr 96px 64px;gap:12px;align-items:center;padding:9px 12px;background:var(--card);border:1px solid var(--line);border-radius:10px;margin-bottom:6px;font-size:13px}
.fix .k{width:26px;height:26px;border-radius:8px;font-size:12px;font-weight:650;display:flex;align-items:center;justify-content:center;color:#fff;background:var(--mut)}
.fix.crit .k{background:var(--crit)}.fix.warn .k{background:var(--warn)}
.fix h3{font-size:13px;font-weight:600}
.fix .w{display:flex;align-items:center;gap:6px;font-size:11px;color:var(--mut)}
.fix .w i{display:block;flex:1;height:6px;border-radius:3px;background:#ececef;overflow:hidden}
.fix .w i:after{content:"";display:block;height:100%;width:var(--w);border-radius:3px;background:#ef7a55}
.fix.warn .w i:after{background:#f0b35a}
.fix .e{font-size:11px;color:var(--mut);text-align:right;white-space:nowrap}
footer{margin-top:16px}`;

const R = 56, CIRC = 2 * Math.PI * R;
const ring = (score) => `<div class="ring"><svg viewBox="0 0 128 128"><circle cx="64" cy="64" r="${R}" fill="none" stroke="rgba(255,255,255,.1)" stroke-width="10"/><circle cx="64" cy="64" r="${R}" fill="none" stroke="#ff5c00" stroke-width="10" stroke-linecap="round" stroke-dasharray="${(CIRC * score / 100).toFixed(1)} ${CIRC.toFixed(1)}"/></svg><div class="n"><b>${score}</b><span>needs work</span></div></div>`;
const signal = (tone, v, l, s) => `<div class="sg ${tone}"><div class="v">${v}</div><div class="l">${l}</div><div class="s">${s}</div></div>`;
// Position map: 1–30 across the track, page one in the green third.
const cluster = (name, meta, pos, tone) =>
  `<div class="cl"><div class="c"><b>${name}</b><span>${meta}</span></div><div class="tr">${pos ? `<i class="${tone}" style="left:${Math.min(pos, 30) / 30 * 100}%"></i>` : `<i class="none" style="left:100%"></i>`}</div><div class="p${pos ? "" : " none"}">${pos ? pos.toFixed(1) : "none"}</div></div>`;
const kw = (q, pos, vol, max, url) =>
  `<div class="kw"><div class="pos">${pos}</div><div class="q">${q}</div><div class="vol"><i style="--w:${Math.round(vol / max * 100)}%"></i><b>${vol.toLocaleString("en-GB")}</b></div><code>${url}</code></div>`;
const gapRow = (topic, a, b, c) =>
  `<div class="g"><b>${topic}</b><span class="${a ? "ok" : "no"}">${a ? "#" + a : "✗"}</span><span class="${b ? "ok" : "no"}">${b ? "#" + b : "✗"}</span><span class="${c ? "ok" : "no"}">${c ? "#" + c : "✗"}</span></div>`;
const cat = (label, score) =>
  `<div class="cat ${score < 60 ? "bad" : score >= 85 ? "good" : ""}" style="--w:${score}%"><div class="r"><span>${label}</span><b>${score}</b></div><i></i></div>`;
const fix = (k, tone, h, impact, effort) =>
  `<div class="fix ${tone}"><div class="k">${k}</div><h3>${h}</h3><div class="w"><i style="--w:${impact}%"></i></div><span class="e">${effort}</span></div>`;

export const AUDIT_REPORT_HTML = `<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>SEO audit · ${STORY.company.site} · 14 Sep 2026</title>
<style>
${BRIEF_CSS}
${AUDIT_CSS}
</style></head><body>
<div class="hd">
  <div>
    <div class="u">${STORY.company.site} · 14 Sep 2026 · 41 pages · 212 keywords</div>
    <h1>Six keywords are one push from page one.</h1>
    <div class="ch"><span><i></i>Crawl</span><span class="gsc"><i></i>Search Console</span><span class="ga4"><i></i>GA4</span><span class="clr"><i></i>Clarity</span><span><i></i>Ledgerly · Tallyo</span><span class="mem"><i></i>Recalled · 7 Sep brief</span></div>
  </div>
  ${ring(AUDIT_REPORT.overall_score)}
</div>

<div class="sig">
${signal("good", "11.4k", "searches a month on page two, on pages that already convert", "Search Console × GA4")}
${signal("warn", "2 pages", "compete for “freelance invoice template”", "cannibalisation · Search Console")}
${signal("bad", "3 topics", "both competitors rank for, Solo has no page", "Ledgerly · Tallyo")}
</div>

<h2>Keyword clusters · average position</h2>
<div class="map">
  <div class="ax"><span>cluster</span><div class="z"><span>page 1</span><span>page 2</span><span>page 3+</span></div><span>pos</span></div>
${cluster("Freelance taxes", "14 keywords · 8.2k/mo", 4.1, "good")}
${cluster("Invoicing", "9 keywords · 12.6k/mo", 6.8, "good")}
${cluster("Late payments", "5 keywords · 3.4k/mo", 9.2, "warn")}
${cluster("Budgeting for freelancers", "7 keywords · 5.1k/mo", 13.5, "warn")}
${cluster("VAT and registration", "6 keywords · 2.7k/mo", 22.0, "bad")}
${cluster("Quarterly estimates", "0 pages · 3.9k/mo", 0, "")}
</div>

<h2>Hidden opportunities · page two, high volume</h2>
${[
  kw("freelance invoice template", 11, 2400, 2400, "/invoice-template"),
  kw("budget app for freelancers", 13, 2100, 2400, "/"),
  kw("how much to set aside for tax freelance", 12, 1900, 2400, "/guides/set-aside-tax"),
  kw("late payment letter template", 14, 1600, 2400, "/late-payment-letter"),
  kw("quarterly tax estimate freelancer", 16, 1300, 2400, "none yet"),
  kw("vat for freelancers", 19, 1100, 2400, "/guides/vat-for-freelancers"),
].join("\n")}

<h2>Topics the competitors own</h2>
<div class="gap">
  <div class="g h"><span style="text-align:left">topic</span><span>Ledgerly</span><span>Tallyo</span><span>Solo</span></div>
${gapRow("quarterly tax estimate", 3, 5, 0)}
${gapRow("freelance tax calculator", 2, 4, 0)}
${gapRow("invoice template for freelancers", 6, 8, 11)}
</div>

<h2>Scores by category</h2>
<div class="cats">
${AUDIT_REPORT.categories.map((c) => cat(c.label, c.score)).join("\n")}
</div>

<h2>Fix these first</h2>
${[
  fix("1", "crit", "Merge the two invoice-template pages into one", 100, "1–3 days"),
  fix("2", "crit", "Link the six page-two keywords from the tax guides", 85, "2–4 hrs"),
  fix("3", "warn", "Write the quarterly tax estimate guide", 70, "1–2 wks"),
  fix("4", "warn", "Remove 3 dead sitemap URLs and a stray noindex", 50, "under 1 hr"),
  fix("5", "warn", "Put an author and a date on 12 guides", 40, "1–3 days"),
].join("\n")}
<footer>Every number re-checked by the verification sub-agent · Search Console, GA4 and Clarity read for ${STORY.week.label}</footer>
</body></html>`;

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
