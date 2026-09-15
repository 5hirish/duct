// Agent streams for the mock backend, built from the story so the session
// screenshots tell the same week as the component ones. The shape mirrors
// app/src/lib/__fixtures__/*.json: one object per SSE frame, with two escape
// hatches the mock understands — `{ __answer__ }` answers the pending
// question, `{ __send__ }` is the user typing the next message.
import { readFileSync } from "node:fs";
import { BRIEF_HTML, CHANGE_SET, DRAFT_POST, MEMORIES, PLAN, STORY } from "../../app/src/lib/__fixtures__/kestrel-story.mjs";

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
    { event: "questions_required", interrupt_id: "int_kestrel_1", questions: [
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

// The content agent drafting one post from the plan: the carousel for day 3,
// six slides, the first image already in. It stops there, mid-run, with the
// other five waiting for a go-ahead — that is the moment the screenshot wants.
export function contentFrames() {
  const day = PLAN.days[DRAFT_POST.day_index];
  const withoutImage = { ...DRAFT_POST, slides: DRAFT_POST.slides.map((s) => ({ ...s, image_url: "", image_prompt_used: "" })) };
  return [
    { event: "pipeline_started", status: "running", channel: "tiktok", channel_supported: true, channel_label: "TikTok" },
    ...step("load_project", "Loading Kestrel"),
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
      { connector_type: "ga4", status: "connected", account_name: "Kestrel web + app" },
      { connector_type: "search_console", status: "connected", account_name: STORY.company.site },
      { connector_type: "stripe", status: "connected", account_name: "Kestrel" },
      { connector_type: "clarity", status: "connected", account_name: "Kestrel Android" },
    ],
    "GET /api/content/plans": [{ id: PLAN.id, name: PLAN.name, start_date: PLAN.start_date }],
  };
}
