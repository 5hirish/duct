// Content Studio's REST answers for the mock backend, from the Solo story.
//
// The plan board, the Posts tab and its drafts queue, a post's own page, and
// the Library, Brand, Accounts and Analytics tabs. Every answer has the shape
// its route returns (backend/routes/content.py) and is built from the story's
// PLAN, POSTS, DRAFT_POST and PLAN_PILLARS, so the board, the queue and the
// post page tell the same week as the session screenshots. What the story does
// not say (the numbers, three text posts, the brand's words, the accounts) is
// invented to fit it: Solo, a budgeting app for freelancers, the week of
// 8–14 Sep 2026, seen on the morning of the 14th.
//
// Two things are read from the repository instead of copied: the built-in
// formats (backend/data/formats/*.md, parsed the way agents/content/formats.py
// parses them) and the backend's slide CSS (scripts/shots/assets/
// slides-head.html), without which a carousel's preview renders unstyled.
// Neither found, the Library lists only Solo's own formats and the slides go
// unstyled; pass `slidesHtml` to supply the CSS from elsewhere.
//
// What is copied: the channel rules and platform guides (agents/content/
// channels.py, platform_guides.py, checked 2026-11) and the two schedulers'
// specs (service/post_bridge, service/zernio). The pre-publish checks are
// recomputed here the way agents/content/assessment.py computes them.
import { createHash } from "node:crypto";
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

// ---------------------------------------------------------------------------
// Backend tables this file mirrors
// ---------------------------------------------------------------------------

// agents/content/platform_guides.MEDIA_KINDS and the Platform enum, in their
// order: a format's filters are normalised to it.
const MEDIA_KINDS = ["video", "slideshow", "image", "text", "article"];
const PLATFORMS = [
  "tiktok", "instagram", "youtube", "linkedin", "twitter", "facebook",
  "threads", "bluesky", "pinterest", "google_business", "blog", "wordpress",
];
// channels.OFFERED: the Accounts tab's rows, in its order.
const OFFERED = ["tiktok", "instagram", "youtube", "facebook", "twitter", "linkedin", "blog", "wordpress"];

// channels.RULES for the offered channels (ChannelRules field order).
const RULES = {
  tiktok:    { label: "TikTok", max_chars: 4000, fold_chars: 0, requires_media: true, hashtags: true, long_form: false },
  instagram: { label: "Instagram", max_chars: 2200, fold_chars: 125, requires_media: true, hashtags: true, long_form: false },
  youtube:   { label: "YouTube", max_chars: 5000, fold_chars: 0, requires_media: true, hashtags: true, long_form: false },
  facebook:  { label: "Facebook", max_chars: 63206, fold_chars: 0, requires_media: false, hashtags: true, long_form: false },
  twitter:   { label: "Twitter / X", max_chars: 280, fold_chars: 0, requires_media: false, hashtags: false, long_form: false },
  linkedin:  { label: "LinkedIn", max_chars: 3000, fold_chars: 210, requires_media: false, hashtags: false, long_form: false },
  blog:      { label: "Blog", max_chars: 60000, fold_chars: 0, requires_media: false, hashtags: false, long_form: true },
  wordpress: { label: "WordPress", max_chars: 60000, fold_chars: 0, requires_media: false, hashtags: false, long_form: true },
};
const PLAYBOOKS = { tiktok: "tiktok", twitter: "twitter", linkedin: "linkedin" };
const TEXT_PLAYBOOKS = new Set(["twitter", "linkedin"]);

// The schedulers' PublisherSpecs. Solo's owner connected PostBridge with her
// own key; Zernio is offered and not connected.
const POSTBRIDGE = {
  id: "post_bridge", label: "PostBridge", dashboard_url: "https://app.post-bridge.com",
  replies: { twitter: 1, threads: 1 },
  metrics: ["tiktok", "youtube", "instagram", "facebook"],
  strips_links: ["twitter"],
};
const ZERNIO = {
  id: "zernio", label: "Zernio", dashboard_url: "https://zernio.com/dashboard",
  metrics: ["tiktok", "instagram", "youtube", "facebook", "linkedin", "twitter", "threads", "pinterest", "bluesky", "google_business"],
};

// platform_guides.GUIDES as guide_payload sends them (CHECKED = "2026-11").
const GUIDES_CHECKED = "2026-11";
const GUIDES = {
  tiktok: {"formats": ["Video 9:16, 15 s to 10 min uploads; 21 to 60 s finishes most often", "Photo carousel (photo mode), up to 35 photos, with a sound", "On-screen text for the sound-off viewer"], "limits": ["Caption 4,000 characters; the first 50 carry the search weight", "3 to 5 hashtags", "Links in the caption are not clickable"], "wins": ["Completion and rewatches first, then shares and saves", "A hook in the first second and a payoff that makes the loop", "Captions written as the search phrase a viewer would type; creators can set a video's search keywords", "A trending sound only when it fits the post"], "avoid": ["Watermarked reposts from other apps", "Twenty hashtags", "Undisclosed AI-made footage: it is labelled and viewers can turn it down"], "cadence": "Daily if the quality holds, three to five a week at least", "media": ["video", "slideshow", "image"]},
  instagram: {"formats": ["Reels 9:16 up to 3 min; 15 to 90 s is the working range", "Carousel 4:5, up to 20 slides; slide 2 is shown to people who scrolled past slide 1", "Single image 4:5; Stories 9:16 for the daily touch"], "limits": ["Caption 2,200 characters, folded after about 125", "At most 5 hashtags", "No clickable link in a caption: bio or sticker"], "wins": ["Sends per reach, then watch time and saves", "Carousels with a sound also surface in Reels", "Keywords in the caption and on-screen text: Instagram search reads them", "Alt text on every image"], "avoid": ["Undisclosed AI-generated content: reach drops", "Hashtags as the first line", "Engagement bait"], "cadence": "Three to five posts a week, a Story most days", "media": ["video", "slideshow", "image"]},
  youtube: {"formats": ["Shorts 9:16 up to 3 min; 15 to 50 s is the sweet spot", "Long-form 16:9 with chapters when the topic needs more than a minute"], "limits": ["Title 100 characters, about 60 visible", "Description 5,000 characters; the first three hashtags show above the title", "More than 60 hashtags and none count"], "wins": ["Shorts: viewed vs swiped away, then rewatches and a loop that ends where it began", "Long-form: click-through and retention; the title carries the keyword", "Captions on, because many Shorts play muted"], "avoid": ["Mass-produced or repetitive uploads: YouTube calls it inauthentic content and demonetises it", "Realistic altered or synthetic footage without the AI disclosure", "A Short that restates a long video's title and nothing else"], "cadence": "Two or three Shorts a week; one long-form a week or fortnight", "media": ["video"]},
  facebook: {"formats": ["Reels (every video posts as one); keep it under 90 s", "Photo and carousel posts", "Text posts that ask something; link posts sparingly"], "limits": ["63,206 characters; about three lines show before 'See more'", "Hashtags optional, at most 2 or 3"], "wins": ["Watch time and shares, then comments worth reading", "Native video over links to video", "A question in the first line"], "avoid": ["A link in the post body: reach is cut, so it goes in the first comment", "Engagement bait ('tag a friend who…')", "Posting more than once a day"], "cadence": "Three to five posts a week", "media": ["video", "slideshow", "image", "text"]},
  twitter: {"formats": ["A post of 280 characters (Premium can write longer, but the feed shows the first lines)", "A thread: a hook post and five to eight that pay it off", "Native video up to 2 min 20 s on a free account; images 16:9 or 4:5"], "limits": ["280 characters per post, every link counts as 23", "0 or 1 hashtag"], "wins": ["Replies weigh far more than likes, so write the post that gets answered", "Native media and text; an outbound link belongs in the first reply", "The first line is the whole post for most readers"], "avoid": ["A link in the post itself: reach drops hard on a free account", "Hashtag strings", "Reposting the LinkedIn version unchanged"], "cadence": "One to three a day, replies included", "media": ["text", "image", "video"]},
  linkedin: {"formats": ["Text post; the first 210 characters are what shows before 'see more'", "Document carousel (a PDF of 8 to 12 pages) for a how-to", "Vertical video of 1 to 2 min; polls; a newsletter for the long form"], "limits": ["3,000 characters", "0 to 3 hashtags", "No outbound link in the post body"], "wins": ["Comments and dwell time, especially in the first hour", "A specific story or a number in the first two lines", "Replying to every comment the same day"], "avoid": ["Template-shaped AI prose: it is down-ranked", "A link in the post: put it in a comment", "Tagging people who will not reply"], "cadence": "Three to five posts a week, weekday mornings", "media": ["text", "slideshow", "image", "video"]},
  blog: {"formats": ["An article of 800 to 1,500 words, as long as the answer needs and no longer", "One H1, an H2 per question the reader has, 40 to 60 words of direct answer under each", "A short FAQ at the end, and a figure or table where a comparison is made"], "limits": ["Title under 60 characters with the keyword in it", "Meta description 120 to 155 characters", "One topic per article; a second topic is a second article"], "wins": ["The answer in the first paragraph: search and AI answers both quote it", "Named sources, dates and numbers, which is what gets cited", "Internal links to the two posts a reader would want next", "An author, a date, and an update when the facts change"], "avoid": ["Thin generated prose padded to a word count", "Keyword-stuffed headings", "Publishing without a canonical URL"], "cadence": "One or two a week, and a refresh of an old post a month", "media": ["article"]},
  wordpress: {"formats": ["An article of 800 to 1,500 words in blocks: heading, paragraph, list, image, table", "One H1 (the title), an H2 per question, 40 to 60 words of answer under each", "A featured image at 1200 by 675 with alt text"], "limits": ["Title under 60 characters; slug three to five words", "Excerpt and meta description 120 to 155 characters", "One category, three to five tags"], "wins": ["The answer in the first paragraph; FAQ and Article schema from the SEO plugin", "Internal links to related posts and a clear next step", "Scheduled publishing at a steady hour"], "avoid": ["Thin generated prose", "Uncategorised posts and empty alt text", "A second H1 inside the body"], "cadence": "One or two a week", "media": ["article"]},
};

// voice_rules.DEFAULT_BANNED_WORDS: what GET /content/brand answers as the defaults.
const DEFAULT_BANNED_WORDS = [
  "game-changer", "revolutionary", "excited to share", "dive in", "unpopular opinion",
  "hot take", "here's a thread", "a few thoughts on", "today I learned", "quick reminder", "let that sink in",
];

// assessment.py: the reviewer's weights, the penalty per failed check, the bands.
const MARKER_WEIGHTS = {
  hook_strength: 0.25, narrative_momentum: 0.20, save_worthiness: 0.20,
  shareability_resonance: 0.15, visual_quality: 0.12, cta_caption_fit: 0.08,
};
const PENALTY = { hard: 8, soft: 3 };
const BANDS = [[80, "strong"], [60, "good"], [40, "needs_work"], [0, "not_ready"]];
const CAPTION_MAX = 2200;
const PLACEHOLDER_RE = /\b(todo|fixme|tbd|lorem ipsum|placeholder|xxx|tk tk)\b/i;
const BRACKET_RE = /\[\s*(?:insert|your|name|brand|topic|product|company|audience|x|tk|fill[\s-]?in|placeholder|tbd)\b[^\]\n]*\]/i;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** A timestamp the way the backend's isoformat() writes a UTC one. */
const iso = (value) => new Date(value).toISOString().replace(/\.\d{3}Z$/, "+00:00");

/** The repository this file runs against: $REPO, or the nearest parent of this file or the cwd holding the backend. */
function findRepo() {
  const starts = [process.env.REPO, dirname(fileURLToPath(import.meta.url)), process.cwd()].filter(Boolean);
  for (const start of starts) {
    for (let dir = resolve(start); ; dir = dirname(dir)) {
      if (existsSync(join(dir, "backend", "data", "formats"))) return dir;
      if (dirname(dir) === dir) break;
    }
  }
  return null;
}

function readSlidesHtml(root) {
  const file = root && join(root, "scripts", "shots", "assets", "slides-head.html");
  if (!file || !existsSync(file)) return "";
  // fixtures.mjs slidesHtml(): the head is what the preview reads (lib/slideDoc extractStyleHead).
  return `<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n${readFileSync(file, "utf8")}\n</head>\n<body>\n</body>\n</html>`;
}

// formats.parse_frontmatter / load_builtin, line for line.
const FRONTMATTER_RE = /^---\s*\n([\s\S]*?)\n---\s*\n?/;
function scalar(raw) {
  const text = raw.trim();
  if (text.length >= 2 && text[0] === text[text.length - 1] && `"'`.includes(text[0])) return text.slice(1, -1);
  if (text.startsWith("[") && text.endsWith("]")) {
    const inner = text.slice(1, -1).trim();
    return inner ? inner.split(",").map(scalar) : [];
  }
  return text;
}
function parseFrontmatter(text) {
  const m = FRONTMATTER_RE.exec(text);
  if (!m) return [{}, text];
  const meta = {};
  let key = null;
  for (const line of m[1].split(/\r?\n/)) {
    if (!line.trim() || line.trimStart().startsWith("#")) continue;
    const stripped = line.trim();
    if (stripped.startsWith("- ") && key !== null) {
      if (!Array.isArray(meta[key])) meta[key] = [];
      meta[key].push(scalar(stripped.slice(2)));
      continue;
    }
    const at = stripped.indexOf(":");
    if (at < 0) continue;
    key = stripped.slice(0, at).trim();
    const value = stripped.slice(at + 1);
    meta[key] = value.trim() ? scalar(value) : [];
  }
  return [meta, text.slice(m[0].length)];
}
const asList = (v) => (v == null || v === "" ? [] : typeof v === "string" ? [v] : v.map(String));
const inOrder = (value, order) => {
  const wanted = new Set(asList(value).map((v) => v.trim().toLowerCase()).filter(Boolean));
  return order.filter((k) => wanted.has(k));
};
function builtinFormats(root) {
  const dir = root && join(root, "backend", "data", "formats");
  if (!dir || !existsSync(dir)) return [];
  return readdirSync(dir).filter((f) => f.endsWith(".md")).sort().map((file) => {
    const [meta, body] = parseFrontmatter(readFileSync(join(dir, file), "utf8"));
    const slug = file.slice(0, -3);
    return {
      id: null, slug, name: String(meta.title || "").trim() || slug, source: "builtin",
      data: {
        description: String(meta.description || "").trim(),
        media: inOrder(meta.media, MEDIA_KINDS),
        channels: inOrder(meta.channels, PLATFORMS),
        spec_markdown: body.trim() + "\n",
      },
      created_at: "", updated_at: "",
    };
  });
}

/** channels.channel_payload(channel, PostBridge): the rules a post's preview counts against. */
function channelPayload(channel) {
  const id = channel || "tiktok";
  const rules = RULES[id];
  const playbook = PLAYBOOKS[id] || "tiktok";
  return {
    id, supported: id in PLAYBOOKS, playbook, text_first: TEXT_PLAYBOOKS.has(playbook) || rules.long_form,
    ...rules,
    publisher: POSTBRIDGE.id,
    publishable_replies: POSTBRIDGE.replies[id] || 0,
    synced_metrics: POSTBRIDGE.metrics.includes(id),
    strips_links: POSTBRIDGE.strips_links.includes(id),
  };
}

// Python's json.dumps(sort_keys=True), so a fingerprint here is the backend's.
function pyJson(v) {
  if (v === null || v === undefined) return "null";
  if (typeof v === "boolean") return v ? "true" : "false";
  if (typeof v === "number") return String(v);
  if (typeof v === "string") {
    return JSON.stringify(v).replace(/[\u007f-￿]/g, (c) => `\\u${c.charCodeAt(0).toString(16).padStart(4, "0")}`);
  }
  if (Array.isArray(v)) return `[${v.map(pyJson).join(", ")}]`;
  return `{${Object.keys(v).sort().map((k) => `${pyJson(k)}: ${pyJson(v[k])}`).join(", ")}}`;
}
function fingerprint(slides, caption, hashtags, replies) {
  const parts = [slides || [], (caption || "").trim(), hashtags || []];
  if (replies?.length) parts.push([...replies]);
  return createHash("sha256").update(pyJson(parts)).digest("hex").slice(0, 16);
}

const hasPlaceholder = (text) => Boolean(text) && (PLACEHOLDER_RE.test(text) || BRACKET_RE.test(text));
const staleImage = (t) => Boolean((t.image_url || "").trim()) && (t.image_prompt || "").trim() !== (t.image_prompt_used || "").trim();
const check = (id, offenders, { failed, severity = "hard" } = {}) => ({
  id, passed: failed === undefined ? offenders.length === 0 : !failed, severity, offenders,
});

/** assessment.compute_sanity over a post's stored fields. */
function sanity(post) {
  const ch = channelPayload(post.platforms?.[0]);
  const limit = ch.text_first ? ch.max_chars : CAPTION_MAX;
  const caption = (post.caption || "").trim();
  const noImage = [], stale = [], noCopy = [], placeholder = [];
  post.slides.forEach((s, i) => {
    const sid = s.slide_id || `slide-${String(i + 1).padStart(2, "0")}`;
    const cells = s.items || [];
    const missing = cells.length ? cells.some((c) => !(c.image_url || "").trim()) : !(s.image_url || "").trim();
    if (s.kind !== "text" && missing) noImage.push(sid);
    if (staleImage(s) || cells.some(staleImage)) stale.push(sid);
    if ((i === 0 || s.kind === "text") && !(s.headline || "").trim()) noCopy.push(sid);
    if ([s.headline, s.subtext, ...cells.map((c) => c.label)].some((t) => hasPlaceholder(t || ""))) placeholder.push(sid);
  });
  if (hasPlaceholder(caption)) placeholder.push("caption");
  const tooLong = [...caption].length > limit ? ["caption"] : [];
  post.replies.forEach((reply, i) => {
    if (hasPlaceholder(reply)) placeholder.push(`reply-${i + 1}`);
    if ([...reply].length > limit) tooLong.push(`reply-${i + 1}`);
  });
  const tags = post.hashtags.map((t) => t.trim().toLowerCase().replace(/^#+/, "")).filter(Boolean);
  const repeated = [...new Set(tags.filter((t, _, all) => all.filter((x) => x === t).length > 1).map((t) => `#${t}`))].sort();
  const checks = [
    check("slides_have_images", noImage),
    check("images_fresh", stale),
    check("slides_have_headlines", noCopy),
    check("caption_present", [], { failed: !caption }),
    check("caption_length", tooLong, { severity: ch.text_first ? "hard" : "soft" }),
    check("no_placeholder_text", placeholder),
  ];
  if (ch.hashtags) {
    checks.push(
      check("hashtags_present", [], { failed: tags.length === 0, severity: "soft" }),
      check("hashtags_unique", repeated, { severity: "soft" }),
    );
  }
  return checks;
}

/** assessment.reassess: fresh checks, and the stored review's scores at the server's weights. */
function assessment(post, review) {
  const checks = sanity(post);
  const current = fingerprint(post.slides, post.caption, post.hashtags, post.replies);
  const markers = Object.keys(MARKER_WEIGHTS)
    .filter((id) => review?.markers?.[id])
    .map((id) => ({ id, ...review.markers[id], weight: MARKER_WEIGHTS[id] }));
  let overall = null, contentScore = null, band = null;
  if (markers.length) {
    const weightSum = markers.reduce((n, m) => n + m.weight, 0);
    contentScore = Math.round(markers.reduce((n, m) => n + m.weight * m.score, 0) / weightSum);
    const penalty = checks.filter((c) => !c.passed).reduce((n, c) => n + PENALTY[c.severity], 0);
    overall = Math.max(0, Math.min(100, contentScore - penalty));
    band = BANDS.find(([floor]) => overall >= floor)[1];
  }
  // A review stored with the post it scored: nothing changed since, so not stale.
  return {
    overall, content_score: contentScore, band, markers, checks,
    notes: review?.notes || "", scored_at: review?.scored_at || "",
    fingerprint: current, stale: false,
  };
}

// A stored slide is Slide.model_dump(): every field, defaults filled in.
const slideOut = (s) => ({
  slide_id: s.slide_id, kind: "photo", role: "", caption_style: "cap-stroke", headline: "", subtext: "",
  image_prompt: "", aspect_ratio: "9:16", image_asset_id: null, image_url: "", image_prompt_used: "", items: [],
  ...s,
});
// templates.derive_image_prompts.
const imagePromptsOf = (slides) => slides.flatMap((s) =>
  s.items.length
    ? s.items.flatMap((it, i) => ((it.image_prompt || "").trim() ? [{ slide_id: `${s.slide_id}#${i}`, prompt: it.image_prompt, aspect_ratio: it.aspect_ratio || "9:16" }] : []))
    : (s.image_prompt || "").trim() ? [{ slide_id: s.slide_id, prompt: s.image_prompt, aspect_ratio: s.aspect_ratio }] : []);

const byUpdatedDesc = (a, b) => (a.updated_at < b.updated_at ? 1 : a.updated_at > b.updated_at ? -1 : 0);

// ---------------------------------------------------------------------------
// The routes
// ---------------------------------------------------------------------------

export function routes(story, { slidesHtml } = {}) {
  const { STORY, PLAN, POSTS, DRAFT_POST, PLAN_PILLARS } = story;
  const root = findRepo();
  const SLIDES_HTML = slidesHtml ?? readSlidesHtml(root);
  const PROJECT_ID = STORY.project.id;
  const site = STORY.company.site;
  const handle = "solobudget";

  // --- Formats: Solo's own two (the ones its plan days name) and the built-ins.
  const CUSTOM_FORMATS = [
    {
      id: "5d0c7a3e-1f42-4b8e-9a61-0c5f2e7b1a01", slug: "carousel", name: "Carousel", source: "custom",
      data: {
        description: "Solo's six-slide money carousel: the rule on slide one, the why in the middle, a reason to save it last. Use for tax, invoicing and money-habit rules on TikTok and Instagram.",
        media: ["slideshow"],
        channels: ["tiktok", "instagram"],
        spec_markdown: [
          "# Carousel — Solo's six-slide money rule",
          "",
          "**One rule, six slides, saved for later.** Solo's house carousel for TikTok photo mode and Instagram. It wins on saves, so every slide earns the next swipe and the last one gives a reason to keep it.",
          "",
          "## Structure",
          "",
          "1. **Hook (photo):** the rule as a name: \"The 12% rule\", \"Net 30 is a choice\". A real desk, real paperwork, window light.",
          "2. **The rule (text):** one sentence a freelancer could act on today.",
          "3. **What it replaces (photo):** the habit it fixes, said plainly.",
          "4. **Why it works (text):** the mechanism, not a statistic.",
          "5. **How Solo does it (photo):** one feature, out of focus, never a tour of the app.",
          "6. **Save prompt (photo):** a date or an occasion to come back on (\"Save this for the 25th\").",
          "",
          "## Copy",
          "",
          "- Headlines under 8 words, subtext under 12.",
          "- Numbers as digits: 12%, €3,000, day 14.",
          "- No \"financial freedom\", no \"hustle\", no fear of the tax office.",
          "- Never tax advice for one country: the habit transfers, the rate does not.",
          "",
          "## Images",
          "",
          "- 9:16, warm natural light, hands and objects rather than faces.",
          "- No readable text or numbers in the photo; the overlay carries the words.",
          "- One desk across a post, so six slides read as one morning.",
          "",
          "## Caption",
          "",
          "Two or three sentences: the rule again, why, then \"Full breakdown in Solo.\" Four hashtags, the first one the phrase people search (#freelancetax, #selfemployed).",
          "",
        ].join("\n"),
      },
      created_at: iso("2026-08-03T10:20:00Z"), updated_at: iso("2026-09-02T14:05:00Z"),
    },
    {
      id: "5d0c7a3e-1f42-4b8e-9a61-0c5f2e7b1a02", slug: "talking-head", name: "Talking head", source: "custom",
      data: {
        description: "One person to camera for 20 to 40 seconds: the exact line to say, then why it works. Use for invoicing scripts and behind-the-app updates on TikTok and YouTube Shorts.",
        media: ["video"],
        channels: ["tiktok", "youtube"],
        spec_markdown: [
          "# Talking head — one script, said to camera",
          "",
          "**The line to say, then why it works.** 20 to 40 seconds, one person to camera, filmed on a phone at a desk. Used for invoicing scripts and behind-the-app updates, and tested this month against the carousel on saves.",
          "",
          "## Beats",
          "",
          "1. **0–2 s:** the situation in the viewer's words (\"Late-paying client?\").",
          "2. **2–12 s:** the exact line, on screen as text as well as spoken.",
          "3. **12–30 s:** why it works, in one reason.",
          "4. **Last 3 s:** what to do with it (\"Copy it into your next invoice\").",
          "",
          "## Shooting",
          "",
          "- Eye level, window light from the side, no music under the words.",
          "- Captions burned in: most people watch muted.",
          "- One take beats a cut-up one. No jump cuts in the first five seconds.",
          "",
          "## Copy",
          "",
          "- The script is the post. Write it before anything else.",
          "- No client names, no screenshots of real invoices.",
          "- End on the action, never on \"follow for more\".",
          "",
        ].join("\n"),
      },
      created_at: iso("2026-08-03T10:32:00Z"), updated_at: iso("2026-08-28T16:40:00Z"),
    },
  ];
  const builtins = builtinFormats(root);
  const formats = [
    ...CUSTOM_FORMATS.map((f) => ({ ...f, overrides_builtin: builtins.some((b) => b.slug === f.slug) })),
    ...builtins.filter((b) => !CUSTOM_FORMATS.some((f) => f.slug === b.slug)),
  ]
    .sort((a, b) => {
      const ka = [a.name.toLowerCase(), a.slug], kb = [b.name.toLowerCase(), b.slug];
      return ka[0] < kb[0] ? -1 : ka[0] > kb[0] ? 1 : ka[1] < kb[1] ? -1 : ka[1] > kb[1] ? 1 : 0;
    })
    .map((f) => ({
      id: f.id, project_id: PROJECT_ID, slug: f.slug, name: f.name, source: f.source,
      description: f.data.description, media: f.data.media, channels: f.data.channels,
      overrides_builtin: Boolean(f.overrides_builtin), data: f.data,
      created_at: f.created_at, updated_at: f.updated_at,
    }));
  // A post names a format by its row; a built-in has none (format_id null, no name).
  const formatOf = (slug) => CUSTOM_FORMATS.find((f) => f.slug === slug) || null;

  // --- Posts. Three are the story's (the plan's days 1–3); three are text
  // posts Solo wrote outside the plan, so the queue and the Posts tab carry
  // every channel and every status a person meets.
  const day = (i) => PLAN.days[i];
  const shareUrl = {
    post_1: `https://www.tiktok.com/@${handle}/photo/7547120934410028310`,
    post_2: `https://www.tiktok.com/@${handle}/video/7547493108827751702`,
  };
  const SEPTEMBER_PROMPT = "Freelancer's desk in early September, a wall calendar with three dates circled, laptop, coffee, soft morning light, no text";
  const rows = [
    {
      ...POSTS.post_1,
      plan_id: PLAN.id,
      post_dir_slug: "2026-09-08-001",
      format: day(0).format_slug,
      title: POSTS.post_1.topic,
      hook_type: day(0).hook_type,
      hook_emotion: "relief",
      save_cta: "Save this for the next one.",
      strategic_note: "A calm month told as dates opens the week on Money habits before the tax rule lands on day 3.",
      slides: [
        { slide_id: "slide-01", kind: "photo", role: "hook", caption_style: "hook", headline: POSTS.post_1.topic, subtext: "the money side", image_prompt: SEPTEMBER_PROMPT, image_prompt_used: SEPTEMBER_PROMPT, image_url: POSTS.post_1.thumbnail_url },
        { slide_id: "slide-02", kind: "text", role: "finding", caption_style: "body-neutral", headline: "1 Sep: two invoices out.", subtext: "One pays on time. One does not." },
        { slide_id: "slide-03", kind: "text", role: "finding", caption_style: "body-neutral", headline: "10 Sep: the first payment lands.", subtext: "12% moves to the tax pot the same day." },
        { slide_id: "slide-04", kind: "text", role: "finding", caption_style: "body-neutral", headline: "18 Sep: rent, phone, software.", subtext: "Bills come out of what is left, never the tax pot." },
        { slide_id: "slide-05", kind: "text", role: "reveal", caption_style: "body-neutral", headline: "25 Sep: the late one pays.", subtext: "Same split. No exceptions." },
        { slide_id: "slide-06", kind: "text", role: "cta", caption_style: "body-neutral", headline: "Same month. Less panic.", subtext: "Save this for the next one." },
      ],
      publisher: POSTBRIDGE.id,
      publisher_post_id: "pb_story_1",
      published_url: shareUrl.post_1,
      // What a PostBridge sync writes, plus the saves Maya typed in from TikTok.
      perf: {
        saves: 610, manual_keys: ["saves"], manual_updated_at: iso("2026-09-13T19:05:00Z"),
        post_result_id: "pr_story_1_tiktok", platform: "tiktok", platform_post_id: "7547120934410028310",
        view_count: 18400, like_count: 1120, comment_count: 86, share_count: 240,
        share_url: shareUrl.post_1, video_description: POSTS.post_1.caption,
        platform_created_at: "2026-09-08T17:30:41.000Z",
        last_synced_at: iso("2026-09-14T06:10:00Z"),
      },
      daily_perf: [
        ["2026-09-08", 2100, 130, 9, 21], ["2026-09-09", 7900, 480, 35, 96], ["2026-09-10", 12600, 770, 58, 162],
        ["2026-09-11", 15400, 940, 71, 201], ["2026-09-12", 16900, 1030, 79, 222], ["2026-09-13", 17800, 1085, 83, 233],
        ["2026-09-14", 18400, 1120, 86, 240],
      ],
      // The agent reviewed it the evening before it went out.
      review: {
        scored_at: iso("2026-09-07T18:02:00Z"),
        notes: "A calm, saveable post. The dates carry it; slide 4 is the weakest beat.",
        markers: {
          hook_strength: { score: 78, verdict: "A month everyone recognises, named plainly.", why: "Slide 1 promises the money side of a month, not a lecture.", fix: "Put one euro figure on slide 1." },
          narrative_momentum: { score: 72, verdict: "Dates pull the swipe.", why: "Each slide is the next date; slide 4 slows it with three bills at once.", fix: "Give slide 4 one bill, not three." },
          save_worthiness: { score: 84, verdict: "A month to copy.", why: "The 10th and the 25th are steps someone can repeat.", fix: "" },
          shareability_resonance: { score: 70, verdict: "Relatable more than surprising.", why: "The late payer on slide 2 is the shareable moment.", fix: "Name the late payer's excuse." },
          visual_quality: { score: 66, verdict: "One strong photo, then plain cards.", why: "Slides 2–6 are text cards; fine for saves, flat for the first frame.", fix: "" },
          cta_caption_fit: { score: 74, verdict: "The caption repeats the hook.", why: "Slide 6 asks for a save; the caption points to Solo.", fix: "" },
        },
      },
      created_at: iso("2026-09-07T16:40:00Z"), updated_at: iso("2026-09-14T06:10:04Z"),
    },
    {
      ...POSTS.post_2,
      plan_id: PLAN.id,
      post_dir_slug: "2026-09-09-001",
      format: day(1).format_slug,
      hook_type: day(1).hook_type,
      hook_emotion: "frustration",
      strategic_note: "The talking-head test: does a script people can copy save as well as a carousel?",
      slides: [],
      publisher: POSTBRIDGE.id,
      publisher_post_id: "pb_story_2",
      published_url: shareUrl.post_2,
      perf: {
        saves: 296, completion_rate: 41, manual_keys: ["saves", "completion_rate"], manual_updated_at: iso("2026-09-13T19:07:00Z"),
        post_result_id: "pr_story_2_tiktok", platform: "tiktok", platform_post_id: "7547493108827751702",
        view_count: 26300, like_count: 1510, comment_count: 204, share_count: 388,
        share_url: shareUrl.post_2, video_description: POSTS.post_2.caption, duration: 34,
        platform_created_at: "2026-09-09T17:30:18.000Z",
        last_synced_at: iso("2026-09-14T06:10:00Z"),
      },
      daily_perf: [
        ["2026-09-09", 3400, 190, 31, 44], ["2026-09-10", 14800, 860, 118, 215], ["2026-09-11", 21200, 1230, 167, 318],
        ["2026-09-12", 23900, 1380, 188, 356], ["2026-09-13", 25500, 1460, 198, 377], ["2026-09-14", 26300, 1510, 204, 388],
      ],
      created_at: iso("2026-09-08T09:15:00Z"), updated_at: iso("2026-09-14T06:10:02Z"),
    },
    {
      // The carousel the content session is drafting: day 3, first image in.
      ...Object.fromEntries(Object.entries(DRAFT_POST).filter(([k]) => k !== "day_index")),
      post_dir_slug: "2026-09-10-001",
      format: day(DRAFT_POST.day_index).format_slug,
      hook_type: day(DRAFT_POST.day_index).hook_type,
      save_cta: "Save this for the 25th.",
      strategic_note: "Tax posts saved best in August; this one leads with the rule, not the fear.",
      created_at: iso("2026-09-09T15:40:00Z"), updated_at: iso("2026-09-10T11:20:00Z"),
    },
    {
      id: "post_li_tax_calendar",
      plan_id: null,
      post_dir_slug: "2026-09-11-001",
      pillar: "Tax without fear",
      topic: STORY.numbers.blogPost,
      post_type: "text",
      platforms: ["linkedin"],
      status: "scheduled",
      caption: [
        "Four dates decide whether a freelancer's year is calm or a scramble.",
        "Most people learn them the expensive way: a reminder two days before a payment is due, and an account that does not have the money in it.",
        `So we put them on one page. The ${STORY.numbers.blogPost} has every quarterly date, what is due on each, and how much you will already have set aside by then if 12% of every payment moves the day it lands.`,
        "It is free and it fits on a fridge.",
        "Which date caught you out last year?",
      ].join("\n\n"),
      replies: [`The calendar is on our blog: ${site}/blog/freelancer-tax-calendar-2026`],
      hook_type: "number",
      strategic_note: "Points the LinkedIn audience at the guide that lifted organic impressions this month.",
      // Approved from the queue on the 11th at LinkedIn's default slot, 08:00 Madrid.
      scheduled_at: "2026-09-15T06:00:00Z",
      published_via: "duct",
      publisher: POSTBRIDGE.id,
      publisher_post_id: "pb_story_li_1",
      created_at: iso("2026-09-11T08:50:00Z"), updated_at: iso("2026-09-11T09:15:00Z"),
    },
    {
      id: "post_li_rule",
      plan_id: null,
      post_dir_slug: "2026-09-13-001",
      pillar: "Tax without fear",
      topic: "Why Solo starts the tax pot at 12%",
      post_type: "text",
      platforms: ["linkedin"],
      status: "draft",
      caption: [
        "Every guide says to put 30% of each payment aside for tax. Solo starts you at 12%. People ask why.",
        "Because 30% is the number people quit.",
        "It makes the first month feel like a pay cut, so the transfers stop by the second. A smaller share, moved the day a payment lands, keeps going, and most people raise it themselves once it is a habit.",
        "12% is not your tax rate. It is the amount you will not miss.",
        "The right number is the one you are still using in March.",
      ].join("\n\n"),
      hook_type: "contrarian",
      created_at: iso("2026-09-13T10:05:00Z"), updated_at: iso("2026-09-13T10:05:00Z"),
    },
    {
      id: "post_x_late",
      plan_id: null,
      post_dir_slug: "2026-09-13-002",
      pillar: "Invoicing",
      topic: "The email that gets a late invoice paid",
      post_type: "text",
      platforms: ["twitter"],
      status: "draft",
      caption: [
        "A late invoice is a calendar problem, not a relationship problem.",
        "The email that works:\n\"Hi, invoice 0412 was due on the 1st. Can you confirm the date it will be paid?\"",
        "No apology. No \"just checking in\". A question with a date for an answer.",
      ].join("\n\n"),
      replies: ["No answer in three working days? Send the same two lines again with the invoice attached. Most clients pay after the second one."],
      hook_type: "reframe",
      created_at: iso("2026-09-13T18:20:00Z"), updated_at: iso("2026-09-13T18:20:00Z"),
    },
  ];

  // _post_out, field for field; `detail` adds what only GET /posts/{id} carries.
  function postOut(row, { detail = false } = {}) {
    const slides = (row.slides || []).map(slideOut);
    const fmt = formatOf(row.format);
    const post = {
      id: row.id,
      project_id: PROJECT_ID,
      plan_id: row.plan_id ?? null,
      post_dir_slug: row.post_dir_slug,
      pillar: row.pillar || "",
      topic: row.topic || "",
      topic_id: null,
      post_type: row.post_type,
      format_id: fmt?.id ?? null,
      format_slug: fmt?.slug ?? "",
      format_name: fmt?.name ?? "",
      avatar_id: null,
      thumbnail_url: row.thumbnail_url || "",
      layout: row.layout || "full-bleed",
      slide_count: row.slide_count ?? slides.length,
      status: row.status,
      slides,
      slides_html: slides.length ? SLIDES_HTML : "",
      caption: row.caption || "",
      replies: row.replies || [],
      hashtags: row.hashtags || [],
      title: row.title || "",
      hook_type: row.hook_type || "",
      hook_text: row.hook_text || (row.caption || "").split("\n")[0],
      hook_emotion: row.hook_emotion || "",
      save_cta: row.save_cta || "",
      image_prompts: imagePromptsOf(slides),
      audio_note: "",
      bridge_text: "",
      strategic_note: row.strategic_note || "",
      visual_brief: "",
      emotional_arc: "",
      camera_ref_pool: "",
      platforms: row.platforms,
      channel: channelPayload(row.platforms[0]),
      posted_at: row.posted_at ? iso(row.posted_at) : null,
      scheduled_at: row.scheduled_at ? iso(row.scheduled_at) : null,
      published_url: row.published_url || "",
      published_via: row.published_via || "",
      publisher: row.publisher || "",
      publisher_post_id: row.publisher_post_id || "",
      publish_error: "",
      perf: row.perf || {},
      daily_perf: (row.daily_perf || []).map(([snapshot_date, view_count, like_count, comment_count, share_count]) => ({
        snapshot_date, view_count, like_count, comment_count, share_count,
      })),
      notes: "",
      clone_source: null,
      video: null,
      video_takes: [],
      created_at: row.created_at,
      updated_at: row.updated_at,
      active_conversation_id: null,
      assessment: null,
    };
    if (detail) post.assessment = assessment(post, row.review);
    return post;
  }

  // list_posts hides unsaved (pending) drafts and lists newest edit first.
  const listed = rows.filter((r) => r.status !== "pending").map((r) => postOut(r)).sort(byUpdatedDesc);
  const inPlan = rows.filter((r) => r.plan_id === PLAN.id).sort((a, b) => (a.created_at < b.created_at ? -1 : 1));

  // --- The plan, as GET /plans/{id} answers it (_plan_out with posts).
  const plan = {
    id: PLAN.id,
    project_id: PROJECT_ID,
    name: PLAN.name,
    start_date: PLAN.start_date,
    character: { name: STORY.company.name, age_range: "", look: "", voice: PLAN.character, notes: "" },
    strategy: {
      exploit: "slideshow",
      exploit_evidence: "Median save rate 3.1% over 9 carousels in August, against 1.2% for 4 videos.",
      explore: "video",
      explore_evidence: "4 videos so far, too few to judge; two talking-head scripts this week.",
      lesson: "Hooks that open on a rule (a percentage, a deadline) out-saved story openers about 2 to 1, so three of five days lead with one.",
      best_times: "Weekdays 19:30, Madrid time",
      experiment: "Two talking-head videos (days 2 and 5), judged on saves against the carousel median.",
      review_notes: "August's tax and invoicing posts saved best, so they take three of this week's five days.",
      mix: {
        goal: "intent",
        channels: [
          { channel: "tiktok", last_days: 5, standing: "leads", scaling: "slideshow", testing: ["video"] },
          { channel: "instagram", last_days: 0, standing: "holds", scaling: "slideshow", testing: [] },
          { channel: "youtube", last_days: 0, standing: "untested", scaling: "", testing: ["video"] },
        ],
      },
    },
    days: PLAN.days.map((d) => ({ ...d })),
    status: "draft",
    created_at: iso("2026-09-07T16:12:00Z"),
    updated_at: iso("2026-09-10T11:20:00Z"),
    posts: inPlan.map((r) => ({
      id: r.id, post_dir_slug: r.post_dir_slug, pillar: r.pillar, topic: r.topic, status: r.status,
      slide_count: r.slide_count ?? (r.slides || []).length,
    })),
    active_conversation_id: null,
  };

  // --- Brand (BrandContextOut). Voice rules customised: the defaults plus three of Solo's own.
  const voiceRules = { banned_words: [...DEFAULT_BANNED_WORDS, "financial freedom", "side hustle", "passive income"], no_client_names: true, protect_the_edge: true };
  const brand = {
    project_id: PROJECT_ID,
    project_name: STORY.project.name,
    slug: PROJECT_ID,
    tagline: STORY.company.tagline,
    description: "Solo splits every payment the day it lands, tax first, so a freelancer always knows what is safe to spend.",
    url: `https://${site}`,
    content_brand: {
      tone: "Practical, warm, a little dry",
      value_prop: "Tax, bills and pay sorted the day a payment lands, not at the end of the month.",
      content_goal: "App installs from TikTok, earned with money rules freelancers save and send.",
      do_say: "Numbers over adjectives. One rule per post. Name the date, the percentage, the euro amount. Sound like a freelancer who was caught out once.",
      do_not_say: "financial freedom, side hustle, passive income, guaranteed, tax advice for one country, anything that shames late payers or spenders",
      features: [
        { id: "tax_pot", name: "Tax pot", description: "Moves a set share of every payment aside the day it lands." },
        { id: "safe_to_spend", name: "Safe to spend", description: "One number: what is left after tax and bills." },
        { id: "invoice_chaser", name: "Invoice chaser", description: "Reminds a late client on day 1, 7 and 14." },
      ],
      writing_samples: [
        "Freelancers don't have a budgeting problem. They have a timing problem.\n\nThe money arrives in lumps and leaves in a steady drip, and every app built for a monthly salary gets that backwards. Solo splits each payment the day it lands: tax first, bills second, and the rest is yours.",
        "Three invoices went out on the 1st. One paid on the 3rd, one on the 19th, and one is \"being processed\".\n\nSame work, same rates, three different months. That is why Solo plans on the money you have, not the money you are owed.",
        "A rule you keep beats a rule that is right.\n\nWe would rather you set aside 12% every time than 30% twice and then never again.",
      ],
      voice_rules: voiceRules,
    },
    content_pillars: {
      items: PLAN_PILLARS.map((name) => ({
        id: name.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, ""),
        name,
        description: {
          "Money habits": "The rhythm of an irregular income: splitting payments, safe to spend, the quiet months.",
          "Tax without fear": "Setting money aside, the quarterly dates and the 12% rule, without scare tactics.",
          "Invoicing": "Getting paid on time: terms, reminders and the exact words that work.",
          "Behind the app": "What we build and why, including what broke.",
        }[name] || "",
        ...(name === "Tax without fear" ? { research_hint: "how freelancers talk about tax money" } : {}),
      })),
    },
    content_visual_assets: { primary_color: "#1F6F5C", secondary_color: "#F4C95D", style: "warm documentary: real desks, real paperwork, window light" },
    voice_rules: voiceRules,
    voice_rules_default: { banned_words: DEFAULT_BANNED_WORDS, no_client_names: true, protect_the_edge: true },
  };

  // --- Schedulers, accounts and channels.
  const publishers = [POSTBRIDGE, ZERNIO].map((spec) => ({
    id: spec.id, label: spec.label, dashboard_url: spec.dashboard_url, reports: [...spec.metrics].sort(),
    connected: spec.id === POSTBRIDGE.id, own_key: spec.id === POSTBRIDGE.id, is_owner: true,
  }));
  // The accounts at PostBridge (SocialAccountOut); all but Facebook linked to Solo.
  const ACCOUNTS = [
    { id: "31877", platform: "tiktok", username: handle, display_name: "Solo · budgeting for freelancers", linked: true },
    { id: "31878", platform: "instagram", username: handle, display_name: "Solo", linked: true },
    { id: "31879", platform: "youtube", username: handle, display_name: "Solo", linked: true },
    { id: "31880", platform: "linkedin", username: "solo-budget", display_name: "Solo", linked: true },
    { id: "31881", platform: "twitter", username: handle, display_name: "Solo", linked: true },
    { id: "31882", platform: "facebook", username: "solobudgetapp", display_name: "Solo Budget", linked: false },
  ];
  const socialAccounts = ACCOUNTS.map((a) => ({
    id: a.id, publisher: POSTBRIDGE.id, publisher_label: POSTBRIDGE.label, platform: a.platform,
    username: a.username, display_name: a.display_name, avatar_url: "", needs_reconnect: false,
  }));
  const linkedAccounts = ACCOUNTS.filter((a) => a.linked).map((a) => ({
    account_id: a.id, publisher: POSTBRIDGE.id, platform: a.platform, username: a.username,
  }));
  const PROFILES = {
    tiktok: { enabled: true, username: handle, display_name: "Solo · budgeting for freelancers", bio: "Money admin for freelancers, one rule at a time.", notes: "Lead with the rule, not the fear. Real desks and real paperwork, never stock-photo laptops.", target_media: ["video", "slideshow"] },
    instagram: { enabled: true, username: handle, display_name: "Solo", bio: "Budgeting for freelancers. Tax, bills and pay, sorted as payments land.", notes: "Cross-post the carousels. Reels only once a video has worked on TikTok.", target_media: ["slideshow"] },
    youtube: { enabled: true, username: handle, display_name: "Solo", bio: "", notes: "Shorts only, from the TikTok videos.", target_media: ["video"] },
    twitter: { enabled: true, username: handle, display_name: "Solo", bio: "Budgeting for freelancers.", notes: "", target_media: ["text"] },
    linkedin: { enabled: true, username: "solo-budget", display_name: "Solo", bio: "Budgeting for freelancers. Tax, invoices and pay, sorted the day a payment lands.", notes: "Company page. Plain, specific, no growth-hacking talk.", target_media: ["text"] },
  };
  const EMPTY_PROFILE = { enabled: false, username: "", display_name: "", bio: "", notes: "", target_media: [] };
  const channels = {
    primary_publisher: POSTBRIDGE.id,
    chosen: true,
    channels: OFFERED.map((id) => ({
      id,
      label: RULES[id].label,
      enabled: Boolean(PROFILES[id]?.enabled),
      supported: id in PLAYBOOKS,
      long_form: RULES[id].long_form,
      profile: PROFILES[id] || EMPTY_PROFILE,
      guide: { platform: id, ...GUIDES[id], checked: GUIDES_CHECKED },
      accounts: linkedAccounts.filter((a) => a.platform === id),
    })),
  };

  // --- Analytics (AnalyticsOut): what PostBridge reports for the linked
  // platforms, tied back to Solo's posts where Duct sent them. August's
  // TikToks went out from the app itself, before Solo used Duct.
  const local = (id) => rows.find((r) => r.id === id);
  const synced = iso("2026-09-14T06:10:00Z");
  const reported = [
    { ref: "pr_story_1_tiktok", platform: "tiktok", post: "post_1", url: shareUrl.post_1, at: "2026-09-08T17:30:41.000Z", n: [18400, 1120, 86, 240] },
    { ref: "pr_story_1_instagram", platform: "instagram", post: "post_1", url: "https://www.instagram.com/p/DOa1kQ8jH2x/", at: "2026-09-08T17:31:40.000Z", n: [6200, 402, 19, 57] },
    { ref: "pr_story_2_tiktok", platform: "tiktok", post: "post_2", url: shareUrl.post_2, at: "2026-09-09T17:30:18.000Z", n: [26300, 1510, 204, 388] },
    { ref: "pr_story_2_youtube", platform: "youtube", post: "post_2", url: "https://www.youtube.com/shorts/Qm3vT8rLx2E", at: "2026-09-09T17:31:02.000Z", n: [3100, 128, 11, 9] },
    { ref: "pr_aug_27_tiktok", platform: "tiktok", title: "Quarterly tax dates nobody tells you", url: `https://www.tiktok.com/@${handle}/photo/7542680411902955798`, at: "2026-08-27T17:30:05.000Z", n: [41200, 2890, 311, 702] },
    { ref: "pr_aug_20_tiktok", platform: "tiktok", title: "What to set aside from a €3,000 invoice", url: `https://www.tiktok.com/@${handle}/photo/7540081377410387222`, at: "2026-08-20T17:30:12.000Z", n: [33800, 2210, 264, 588] },
    { ref: "pr_aug_13_tiktok", platform: "tiktok", title: "3 invoice lines that get you paid faster", url: `https://www.tiktok.com/@${handle}/photo/7537485960113212694`, at: "2026-08-13T17:30:09.000Z", n: [21900, 1340, 97, 301] },
    { ref: "pr_aug_06_tiktok", platform: "tiktok", title: "POV: your client says \"next week\" again", url: `https://www.tiktok.com/@${handle}/video/7534888320946472214`, at: "2026-08-06T17:30:27.000Z", n: [12700, 880, 143, 96] },
  ];
  const analytics = {
    rows: reported
      .map((r) => {
        const p = r.post ? local(r.post) : null;
        const [view_count, like_count, comment_count, share_count] = r.n;
        return {
          id: `${POSTBRIDGE.id}:${r.ref}`, publisher: POSTBRIDGE.id, platform: r.platform,
          title: p ? p.caption : r.title, share_url: r.url,
          // A scheduler's cover is its own CDN URL, which the mock cannot serve.
          cover_image_url: "",
          view_count, like_count, comment_count, share_count,
          platform_created_at: r.at, last_synced_at: synced,
          pillar: p ? p.pillar : "", format_name: p ? formatOf(p.format)?.name || "" : "",
          published_via: p ? p.published_via : "", post_id: p ? p.id : null,
        };
      })
      .sort((a, b) => b.view_count - a.view_count),
    notices: [],
  };

  // --- GET /content/best-slot, as agents/content/best_time.next_slot answers
  // at 09:30 Madrid on Monday the 14th: no channel has five posts with
  // numbers yet, so each is its default, and LinkedIn steps past Tuesday's
  // scheduled post to Wednesday.
  const slot = (at, posts, hour) => ({ at: iso(at), reason: "default", posts, hour });
  const BEST_SLOTS = {
    tiktok: slot("2026-09-15T07:00:00Z", 2, 9),
    linkedin: slot("2026-09-16T06:00:00Z", 0, 8),
    twitter: slot("2026-09-15T07:00:00Z", 0, 9),
  };
  const q = new URLSearchParams({ project_id: PROJECT_ID }).toString();
  const bestSlot = Object.fromEntries(Object.entries(BEST_SLOTS).map(([channel, body]) => [
    `GET /api/content/best-slot?${new URLSearchParams({ project_id: PROJECT_ID, channel, tz: "Europe/Madrid" })}`, body,
  ]));

  return {
    [`GET /api/content/plans/${PLAN.id}`]: plan,
    [`GET /api/content/posts?${new URLSearchParams({ project_id: PROJECT_ID, plan_id: PLAN.id })}`]: listed.filter((p) => p.plan_id === PLAN.id),
    [`GET /api/content/posts?${q}`]: listed,
    [`GET /api/content/posts?${new URLSearchParams({ project_id: PROJECT_ID, status: "draft" })}`]: listed.filter((p) => p.status === "draft"),
    ...Object.fromEntries(rows.map((r) => [`GET /api/content/posts/${r.id}`, postOut(r, { detail: true })])),
    [`GET /api/content/formats?${q}`]: formats,
    [`GET /api/content/brand?${q}`]: brand,
    [`GET /api/content/publishers?${q}`]: publishers,
    [`GET /api/content/channels?${q}`]: channels,
    // Read once a scheduler is connected, which the publishers above say it is:
    // without them the Accounts tab says "no accounts" and Analytics "link one".
    [`GET /api/content/social-accounts?${q}`]: socialAccounts,
    [`GET /api/content/linked-accounts?${q}`]: linkedAccounts,
    [`GET /api/content/analytics?${q}`]: analytics,
    ...bestSlot,
    // Any other zone the capture runs in gets TikTok's answer rather than an empty `[]`.
    "GET /api/content/best-slot": BEST_SLOTS.tiktok,
  };
}
