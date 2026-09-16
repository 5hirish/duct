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

// The brief the insights agent writes: a self-contained HTML report, the way
// the agents actually deliver one (the artifact pane renders it in a frame).
// Sized for the pane, not for print: a verdict, the numbers, then findings.
const n = STORY.numbers;
export const BRIEF_HTML = `<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Signups · week of ${STORY.week.label}</title>
<style>
:root{--tx:#1a1d26;--mut:#6b7280;--line:#e6e7ea;--card:#fff;--bg:#fff;--crit:#c2410c;--warn:#b45309;--good:#15803d;--accent:#5b5bd6}
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
footer{color:var(--mut);font-size:11px;margin-top:24px}
</style></head><body>
<h1>Signups are down. ROAS is up. Same campaign.</h1>
<p class="sub">Week of ${STORY.week.label} · Google Ads, GA4, Stripe, Clarity, Search Console</p>

<div class="verdict"><b>The short version.</b> Performance Max is buying signups at €${n.pmaxCpa} who leave within a week. The ROAS gain is hiding a retention problem, not describing a win.</div>

<h2>The numbers</h2>
<div class="kpis">
  <div class="kpi"><div class="v">${n.signups}</div><div class="l">Signups</div><div class="d down">▼ 9% · target ${STORY.targets.weeklySignups}</div></div>
  <div class="kpi"><div class="v">${n.mrr}</div><div class="l">MRR</div><div class="d up">▲ ${n.mrrDelta.replace("+", "")}</div></div>
  <div class="kpi"><div class="v">${n.roasDelta}</div><div class="l">ROAS</div><div class="d flat">almost all from PMax</div></div>
  <div class="kpi"><div class="v">€${n.pmaxCpa}</div><div class="l">CPA · PMax</div><div class="d down">▲ €7.40 over target</div></div>
  <div class="kpi"><div class="v">€${n.brandCpa}</div><div class="l">CPA · Brand search</div><div class="d up">▼ €3.30 under target</div></div>
  <div class="kpi"><div class="v">${n.rageClickClusters}</div><div class="l">Rage-click clusters</div><div class="d down">all Android</div></div>
</div>

<h2>7-day retention by source</h2>
<div class="bars">
  <div class="bar"><span>Organic</span><i class="good" style="width:54%"></i><b>54%</b></div>
  <div class="bar"><span>Brand search</span><i class="good" style="width:51%"></i><b>51%</b></div>
  <div class="bar"><span>PMax · iOS</span><i style="width:44%"></i><b>44%</b></div>
  <div class="bar"><span>PMax · Android</span><i class="bad" style="width:31%"></i><b>31%</b></div>
</div>

<h2>Findings</h2>
<div class="finding crit"><h3>PMax Android users churn ${n.androidRetentionDrop} faster than organic</h3><p>31% retained at day 7 against 54%. The cohort started on 4 Sep, two days after the onboarding rebuild.</p></div>
<div class="finding warn"><h3>They get stuck on the Connect bank screen</h3><p>Three rage-click clusters this week, all Android, all from the PMax cohort. Fix the screen before buying more of them.</p></div>
<div class="finding good"><h3>Organic is quietly working</h3><p>Impressions up ${n.organicImpressionsDelta}. <i>${n.blogPost}</i> ranks on page one for two target terms.</p></div>

<h2>What to do</h2>
<ol>
  <li>Pause <i>Performance Max · Freelancers</i> until the Android screen is fixed. Proposed in chat, waiting for you.</li>
  <li>Add the two negatives bringing in template hunters.</li>
  <li>Give brand search more budget. Over the 25% guardrail, so that one is yours to make.</li>
</ol>
<footer>Every number re-checked by the verification sub-agent · ${STORY.week.label}</footer>
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
