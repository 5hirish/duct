// Every number and name in the film comes from the story fixture the README
// screenshots and the /preview scenes already use, so the three cannot drift.
// The one deliberate difference: the company is called Solo on screen. The
// fixture still says Kestrel until it is renamed and the README re-shot, so
// the swap happens here, in one place, and nowhere else.
import { CHANGE_SET, MEMORIES, PLAN, STORY } from "../../../app/src/lib/__fixtures__/kestrel-story.mjs";

export const COMPANY = "Solo";
export const brand = (s) => String(s).replaceAll(STORY.company.name, COMPANY);

export const USER = STORY.user;
export const ASKER = { name: "Jonas", initials: "JO" };
export const N = STORY.numbers;
export const TARGETS = STORY.targets;
export const WEEK = STORY.week;
export const WEEK_SHORT = "week of 8 Sep";
export const CAMPAIGN = {
  pmax: brand(STORY.ads.campaigns.pmax),
  brand: brand(STORY.ads.campaigns.brand),
  account: brand(STORY.ads.accountName),
};

export const QUESTION = "why are signups down this week?";
export const REPLY = `Android users from Performance Max churn ${N.androidRetentionDrop} faster than organic. Paused the campaign, brand search stays on. Brief attached.`;

const byId = Object.fromEntries(MEMORIES.map((m) => [m.id, m]));
export const MEMORY = {
  brief: byId["mem-brief"],
  clarity: byId["mem-clarity"],
  android: byId["mem-android"],
  cpa: byId["mem-cpa"],
};

const change = (id) => CHANGE_SET.changes.find((c) => c.id === id);
export const CHANGE = {
  title: CHANGE_SET.title,
  pause: { ...change("c1"), diff: brand(change("c1").diff) },
  budget: { ...change("c3"), diff: brand(change("c3").diff) },
};

// The five sources the brief cites, in the order the session reads them.
export const SOURCES = [
  { id: "google-ads", label: "Google Ads" },
  { id: "googleanalytics", label: "GA4" },
  { id: "stripe", label: "Stripe" },
  { id: "clarity", label: "Clarity" },
  { id: "googlesearchconsole", label: "Search Console" },
];

const WEEKDAY = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const COVER = { post_1: "post-september.jpg", post_2: "post-invoice.jpg", post_3: "post-tax-jar.jpg" };

// The content board for scene 7: the plan's week, grouped the way the app's
// board groups it (pending / draft / posted).
export const BOARD = PLAN.days
  .filter((d) => d.status)
  .map((d) => ({
    day: WEEKDAY[d.day - 1],
    topic: d.topic,
    status: d.status,
    cover: d.post_id ? COVER[d.post_id] : null,
  }));
