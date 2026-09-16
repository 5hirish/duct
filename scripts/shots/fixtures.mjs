// Agent streams for the mock backend, built from the story so the session
// screenshots tell the same week as the component ones. The shape mirrors
// app/src/lib/__fixtures__/*.json: one object per SSE frame, with two escape
// hatches the mock understands — `{ __answer__ }` answers the pending
// question, `{ __send__ }` is the user typing the next message.
import { readFileSync } from "node:fs";
import { BRIEF_HTML, CHANGE_SET, CHANGE_SET_HISTORY, DRAFT_POST, MEMORIES, PLAN, PRODUCT_CHANGE_SET, STORY } from "../../app/src/lib/__fixtures__/solo-story.mjs";

// The backend's slide CSS, rendered once from agents/content/templates.py
// (see assets/slides-head.html for how). The live slide preview reads its
// styles out of slides_html, so a draft without it renders unstyled.
const SLIDES_HEAD = readFileSync(new URL("./assets/slides-head.html", import.meta.url), "utf8");
const slidesHtml = () => `<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n${SLIDES_HEAD}\n</head>\n<body>\n</body>\n</html>`;

const usage = (input, output) => ({
  event: "token_usage",
  input_tokens: input, output_tokens: output, cache_read_tokens: Math.round(input * 0.6), cache_creation_tokens: 0,
  total_tokens: input + output, model: "claude-sonnet-5", context_window: 200000, scope: "thread",
});
const step = (id, label, connector) => [
  { event: "step_started", step_id: id, label, status: "running" },
  { event: "step_finished", step_id: id, label, status: "success", ...(connector ? { connector_id: connector } : {}) },
];
const say = (text) => ({ event: "agent_message_chunk", text });

export function insightsFrames() {
  const m = (id) => MEMORIES.find((x) => x.id === id);
  const recalled = ["mem-cpa", "mem-legacy", "mem-android"].map((id) => ({
    id, memory_id: `00000000-0000-4000-8000-${id.replace(/\D/g, "").padStart(12, "0")}`, title: m(id).title, kind: m(id).kind,
  }));
  const range = `${STORY.week.start} → ${STORY.week.end}`;
  return [
    { event: "pipeline_started", status: "running", autonomy: "ask", autonomy_configured: "assisted" },
    { event: "memory_recalled", memories: recalled },
    { event: "todo_update", todos: [
      { content: "Pull Ads, GA4, Stripe and Clarity for the week", status: "in_progress" },
      { content: "Compare the PMax cohort against organic", status: "pending" },
      { content: "Write the brief and propose changes", status: "pending" },
    ] },
    ...step("collect_source_data:google_ads", `google ads campaigns · ${range}`, "google_ads"),
    ...step("collect_source_data:ga4", `ga4 retention by acquisition source · ${range}`, "ga4"),
    ...step("collect_source_data:stripe", `stripe subscriptions · ${range}`, "stripe"),
    ...step("collect_source_data:clarity", `clarity rage clicks · ${range}`, "clarity"),
    { event: "thinking_chunk", text: "ROAS is up but signups are down. " },
    { event: "thinking_chunk", text: "Split retention by campaign before saying anything." },
    say("One thing before I write this up."),
    { event: "questions_required", interrupt_id: "int_solo_1", questions: [
      { question: "Which matters more this week?", header: "Goal", options: [
        { label: "Signups", description: "Hit 900 signups, retention second" },
        { label: "Retention", description: "Keep the signups that stay" },
      ] },
    ] },
    { event: "message_stop" },
    usage(41200, 900),
    { __answer__: { "Which matters more this week?": "Retention" } },
    { event: "todo_update", todos: [
      { content: "Pull Ads, GA4, Stripe and Clarity for the week", status: "completed" },
      { content: "Compare the PMax cohort against organic", status: "completed" },
      { content: "Write the brief and propose changes", status: "in_progress" },
    ] },
    ...step("verify", "verification sub-agent · re-checking 6 numbers"),
    say("Retention it is. **ROAS is up 14%, and that is the problem:** the campaign driving it brings in Android users who leave within a week. The brief is on the right. One change to approve below."),
    { event: "artifact_version", version_id: 1, label: "Version 1", payload: { title: `Signups brief · ${STORY.week.label}`, format: "html", content: BRIEF_HTML } },
    { event: "execution_proposed", change_set: CHANGE_SET },
    { event: "memory_written", memories: [
      { id: "mem-clarity", memory_id: "00000000-0000-4000-8000-000000000099", title: m("mem-clarity").title, kind: "watch" },
    ] },
    say(" The Legacy brand campaign stays untouched, as you asked in August."),
    { event: "message_stop" },
    usage(68400, 2100),
    { event: "pipeline_finished", status: "success" },
    { __send__: "How long has the Android retention been like this?" },
    say("Since the cohort that started on 4 Sep, two days after the onboarding rebuild. The cohorts before the rebuild retained at 49%, so this is new, and it lines up with the Connect bank rage clicks. I would fix the screen before turning PMax back on."),
    { event: "message_stop" },
    usage(74900, 600),
  ];
}

const recall = (ids) => ids.map((id) => {
  const m = MEMORIES.find((x) => x.id === id);
  return { id, memory_id: `00000000-0000-4000-8000-${id.replace(/\D/g, "").padStart(12, "0")}`, title: m.title, kind: m.kind };
});

// The same week asked from the product side: not "why are signups down" but
// "why did activation drop". Same rebuild, same rage clicks, same Android
// cohort; what it proposes is two GA4 key events, not a paused campaign.
// No brief this time, so the chat carries the whole answer.
export function productFrames() {
  const a = STORY.numbers.activation;
  const range = "25 Aug → 14 Sep";
  return [
    { event: "pipeline_started", status: "running", autonomy: "ask", autonomy_configured: "assisted" },
    { event: "memory_recalled", memories: recall(["mem-android", "mem-clarity", "mem-pref"]) },
    { event: "todo_update", todos: [
      { content: "Pull GA4 funnels, Clarity and Stripe either side of 2 Sep", status: "in_progress" },
      { content: "Split activation by platform and cohort", status: "pending" },
      { content: "Write it up and propose what to track", status: "pending" },
    ] },
    ...step("collect_source_data:ga4", `ga4 onboarding funnel by platform · ${range}`, "ga4"),
    ...step("collect_source_data:clarity", `clarity rage clicks by screen · ${range}`, "clarity"),
    ...step("collect_source_data:stripe", `stripe trial starts · ${range}`, "stripe"),
    { event: "thinking_chunk", text: "iOS is flat. Android moved the day the rebuild shipped. " },
    { event: "thinking_chunk", text: "Check the Connect bank step before blaming the release as a whole." },
    say("One thing before I split this."),
    { event: "questions_required", interrupt_id: "int_solo_2", questions: [
      { question: "Which step counts as activated?", header: "Activation", options: [
        { label: "Connect bank", description: "The step the rebuild moved" },
        { label: "First budget", description: "The first moment the app is useful" },
      ] },
    ] },
    { event: "message_stop" },
    usage(38700, 800),
    { __answer__: { "Which step counts as activated?": "Connect bank" } },
    { event: "todo_update", todos: [
      { content: "Pull GA4 funnels, Clarity and Stripe either side of 2 Sep", status: "completed" },
      { content: "Split activation by platform and cohort", status: "completed" },
      { content: "Write it up and propose what to track", status: "in_progress" },
    ] },
    ...step("verify", "verification sub-agent · re-checking 5 numbers"),
    say(`Connect bank it is. **Android activation fell from ${a.androidBefore} to ${a.androidAfter} on 2 Sep, the day the rebuild shipped. iOS did not move.** The rebuild put the bank step behind a system permission prompt, and Android users who tap Deny land on an empty screen: that is where this week's three rage-click clusters are. Two events to track below, so next week's brief can prove the fix.`),
    { event: "execution_proposed", change_set: PRODUCT_CHANGE_SET },
    { event: "memory_written", memories: [
      { id: "mem-activation", memory_id: "00000000-0000-4000-8000-000000000098", title: `Android activation dropped to ${a.androidAfter} after the 2 Sep rebuild; the permission prompt is the cause`, kind: "conclusion" },
    ] },
    say(" The fix is in the app, not the funnel: ask for the permission after the first budget, not before it."),
    { event: "message_stop" },
    usage(61200, 1700),
    { event: "pipeline_finished", status: "success" },
    { __send__: "Did iOS move at all?" },
    say(`No. iOS activation was ${a.iosBefore} the fortnight before and ${a.iosAfter} since, inside its usual week-to-week range. The permission prompt only exists on Android, so the rest of the rebuild looks fine.`),
    { event: "message_stop" },
    usage(66900, 500),
  ];
}

// The same week asked from the paid side: where is the budget leaking. Same
// change set as the signups session, reached from the spend rather than the
// retention, and no brief: the numbers are in the answer.
export function paidFrames() {
  const n = STORY.numbers;
  const range = `${STORY.week.start} → ${STORY.week.end}`;
  return [
    { event: "pipeline_started", status: "running", autonomy: "ask", autonomy_configured: "assisted" },
    { event: "memory_recalled", memories: recall(["mem-cpa", "mem-legacy", "mem-brief"]) },
    { event: "todo_update", todos: [
      { content: "Pull spend, search terms and conversions for the week", status: "in_progress" },
      { content: "Cost every campaign against the €12 target", status: "pending" },
      { content: "Propose the moves", status: "pending" },
    ] },
    ...step("collect_source_data:google_ads", `google ads campaigns · ${range}`, "google_ads"),
    ...step("collect_source_data:google_ads_terms", `google ads search terms · ${range}`, "google_ads"),
    ...step("collect_source_data:ga4", `ga4 signups by campaign · ${range}`, "ga4"),
    ...step("collect_source_data:stripe", `stripe subscriptions · ${range}`, "stripe"),
    { event: "thinking_chunk", text: "PMax is €7.40 over target and brand search is €3.30 under. " },
    { event: "thinking_chunk", text: "Read the search terms before touching budgets." },
    say("One thing before I move anything."),
    { event: "questions_required", interrupt_id: "int_solo_3", questions: [
      { question: "What do you want to protect this week?", header: "Priority", options: [
        { label: "The €12 CPA", description: "Cut what runs over it" },
        { label: "Signup volume", description: "Hold 900 signups, cost second" },
      ] },
    ] },
    { event: "message_stop" },
    usage(39900, 850),
    { __answer__: { "What do you want to protect this week?": "The €12 CPA" } },
    { event: "todo_update", todos: [
      { content: "Pull spend, search terms and conversions for the week", status: "completed" },
      { content: "Cost every campaign against the €12 target", status: "completed" },
      { content: "Propose the moves", status: "in_progress" },
    ] },
    ...step("verify", "verification sub-agent · re-checking 6 numbers"),
    say(`The CPA it is. **${n.pmaxSpend} of this week's spend went to Performance Max at €${n.pmaxCpa} a signup, against the €${STORY.targets.cpa} target.** Brand search is at €${n.brandCpa} and capped by its €40 budget. Two template-hunter search terms spent ${n.templateTermsSpend} for zero signups. The moves are below: two apply on your say-so, the budget raise is over the guardrail so it needs you.`),
    { event: "execution_proposed", change_set: CHANGE_SET },
    { event: "memory_written", memories: [
      { id: "mem-terms", memory_id: "00000000-0000-4000-8000-000000000097", title: "Watch PMax search terms weekly for template hunters", kind: "watch" },
    ] },
    say(" The Legacy brand campaign stays untouched, as you asked in August."),
    { event: "message_stop" },
    usage(64300, 1900),
    { event: "pipeline_finished", status: "success" },
    { __send__: "What do we lose by pausing PMax?" },
    say(`About 110 signups a week at this week's rate, and 69% of those are gone by day 7. Brand search at €60 a day buys about 48 a week at €${n.brandCpa}, and half of those stay.`),
    { event: "message_stop" },
    usage(70100, 550),
  ];
}

// The content agent drafting one post from the plan: the carousel for day 3,
// six slides, the first image already in. It stops there, mid-run, with the
// other five waiting for a go-ahead — that is the moment the screenshot wants.
export function contentFrames() {
  const day = PLAN.days[DRAFT_POST.day_index];
  const withoutImage = { ...DRAFT_POST, slides: DRAFT_POST.slides.map((s) => ({ ...s, image_url: "", image_prompt_used: "" })) };
  return [
    { event: "pipeline_started", status: "running", channel: "tiktok", channel_supported: true, channel_label: "TikTok" },
    ...step("load_project", "Loading Solo"),
    { event: "step_started", step_id: "enriching", label: "Reading the plan and the last 30 posts", status: "running" },
    ...step("dispatch_subagent:research_pillar", "Sub-agent · how freelancers talk about tax money"),
    { event: "step_finished", step_id: "enriching", status: "success" },
    { event: "todo_update", todos: [
      { content: `Draft day 3 · ${day.topic}`, status: "completed" },
      { content: "Render the first slide", status: "in_progress", activeForm: "Rendering the first slide" },
      { content: "Generate the other three images, one at a time", status: "pending" },
    ] },
    { event: "thinking_chunk", text: "Tax posts did best in August. Lead with the rule, not the fear." },
    say(`Day 3, *${day.topic}*. Six slides: the rule, why 12%, the one account that makes it stick, and a save prompt for the 25th.`),
    { event: "post_draft_updated", payload: { ...withoutImage, slides_html: slidesHtml() } },
    ...step("generate_image:slide-01", "Image · slide 1 of 6"),
    { event: "post_draft_updated", payload: { ...DRAFT_POST, slides_html: slidesHtml() } },
    say(" Slide 1 is in so you can see the look. Three more images to go: say the word, or change the hook first."),
    { event: "message_stop" },
    usage(23800, 3400),
    { __send__: "Go ahead" },
  ];
}

export function auditFrames() {
  // Not captured today; the mock still wants a file for the audit agent.
  return [{ event: "pipeline_started", status: "running" }, { event: "pipeline_finished", status: "success" }];
}

// What the app asks the backend for around a session, answered from the
// story so the shell around the workspace is not empty.
export function routes() {
  return {
    "GET /api/providers/status": {
      chatgpt_auth_enabled: true,
      providers: [
        { id: "openai", source: "subscription", reachable: true, stored: false },
        { id: "anthropic", source: "user", reachable: true, stored: true },
      ],
    },
    "GET /api/user/projects": [
      { id: STORY.project.id, name: STORY.project.name, url: `https://${STORY.company.site}`, profile: { company: { name: STORY.company.name, industry: STORY.company.industry } } },
    ],
    [`GET /api/user/projects/${STORY.project.id}/data-sources`]: [
      { connector_type: "google_ads", status: "connected", account_name: STORY.ads.accountName },
      { connector_type: "ga4", status: "connected", account_name: "Solo web + app" },
      { connector_type: "search_console", status: "connected", account_name: STORY.company.site },
      { connector_type: "stripe", status: "connected", account_name: "Solo" },
      { connector_type: "clarity", status: "connected", account_name: "Solo Android" },
    ],
    "GET /api/content/plans": [{ id: PLAN.id, name: PLAN.name, start_date: PLAN.start_date }],
    // The Executions page: this week's proposal on top of what already went through.
    "GET /api/execute": [CHANGE_SET, ...CHANGE_SET_HISTORY],
    "GET /api/execute/ops": [
      { op_type: "pause_campaign", destructive: true },
      { op_type: "add_negative_keywords", destructive: false },
      { op_type: "set_campaign_budget", destructive: false },
      { op_type: "mark_key_event", destructive: false },
    ],
  };
}
