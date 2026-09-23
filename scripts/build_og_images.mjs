#!/usr/bin/env node
// Per-page Open Graph images for the site: `node scripts/build_og_images.mjs`.
//
// One 670 KB PNG used to serve every page, so a shared link to the paid-ads
// page previewed the same card as the privacy policy. Each page gets its own
// card now: the wordmark, the page's headline in the site's serif, one line
// under it, and, where the page has one, its product shot bleeding off the
// corner. JPEG, 1200×630, each under 150 KB. Drawn with sharp from app/'s
// node_modules, like scripts/shots; the text is SVG in Georgia, which the
// renderer resolves from the system, so run this on a machine that has it
// (a Mac does) and commit the output.
import { createRequire } from "node:module";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const REPO = resolve(fileURLToPath(new URL("..", import.meta.url)));
const req = createRequire(import.meta.url);
const sharp = req(req.resolve("sharp", { paths: [join(REPO, "app")] }));
const MEDIA = join(REPO, "site/assets/media");
const POSTS = join(REPO, "site/blog/posts");
const OUT = join(REPO, "site/assets/og");
const W = 1200, H = 630, LIMIT = 150 * 1024;

// slug → the card. `shot` is a file in site/assets/media; its top-left corner
// is what shows, so pick shots whose first 620×480 carry the point.
const PAGES = {
  "index": { title: "See the whole picture. Fix it in the same moment.", sub: "Open-source AI agent for product and growth teams.", shot: "insights-session.webp" },
  "for-product-intelligence": { title: "See why the number moved. Fix it before the standup.", sub: "Your product analytics, read as one.", shot: "product-session.webp" },
  "for-organic-growth": { title: "See which content actually converts. Fix it in the same sitting.", sub: "GSC, GA4 and Clarity, read together.", shot: "content-session.webp" },
  "for-paid-ads": { title: "See what your ad spend bought. Move it in the same moment.", sub: "Ads, GA4 and Stripe, read together.", shot: "paid-session.webp" },
  "download": { title: "The whole picture, in one window.", sub: "Mac, Windows and Linux. Free, open source, your own keys.", shot: "insights-session.webp" },
  "seo-audit": { title: "See exactly what's hurting your rankings.", sub: "A free SEO audit from the open-source Duct agent. No account.", shot: "audit-report.webp" },
  "open-source": { title: "Open source, MIT, your own keys.", sub: "What runs where, how to self-host it, and a plain answer on what will cost money." },
  "about": { title: "Built because my tools wouldn't talk.", sub: "Why an agent that reads your whole business is open source." },
  "doctrine": { title: "The Duct doctrine.", sub: "Seven opinions the project is built on, each linked to the file that enforces it." },
  "privacy": { title: "Privacy policy.", sub: "What Duct stores, where, and what never leaves your machine." },
  "terms": { title: "Terms of service.", sub: "The terms for the hosted app and the desktop download." },
  "changelog": { title: "What changed in Duct.", sub: "Release notes, newest first: connectors, agents, desktop builds." },
  "tools": { title: "Free tools for growth teams.", sub: "Calculators and generators that run in your browser. No account." },
  "blog": { title: "What your tools don't tell you on their own.", sub: "Writing on organic growth, product intelligence and the numbers that only make sense read together." },
  "tools/saas-metrics-calculator": { title: "SaaS metrics benchmark calculator.", sub: "Churn, LTV:CAC, payback and trial-to-paid against industry medians.", shot: "insights-session.webp" },
  "tools/cac-ltv-calculator": { title: "CAC and LTV calculator.", sub: "CAC, LTV, the ratio and payback, with benchmark context.", shot: "insights-session.webp" },
  "tools/mrr-growth-calculator": { title: "MRR growth rate calculator.", sub: "Net MRR growth, CMGR, and the rate you need to hit a target.", shot: "insights-session.webp" },
  "tools/ctr-calculator": { title: "CTR calculator.", sub: "Click-through rate, projected clicks, and the CTR you need.", shot: "paid-session.webp" },
  "tools/cpm-calculator": { title: "CPM calculator.", sub: "Cost per thousand impressions, spend scenarios, efficiency targets.", shot: "paid-session.webp" },
  "tools/cpc-calculator": { title: "CPC calculator.", sub: "Cost per click and what spend looks like at your target.", shot: "paid-session.webp" },
  "tools/cpa-calculator": { title: "CPA calculator.", sub: "Cost per acquisition, conversion scenarios, budget-safe CPAs.", shot: "paid-session.webp" },
  "tools/roas-calculator": { title: "ROAS calculator.", sub: "Return on ad spend, target gaps, margin-aware contribution ROAS.", shot: "paid-session.webp" },
  "tools/marketing-roi-calculator": { title: "Marketing ROI calculator.", sub: "ROI, profit and revenue scenarios for campaign decisions.", shot: "paid-session.webp" },
  "tools/utm-builder": { title: "UTM builder.", sub: "GA4-friendly campaign links with live preview and validation.", shot: "paid-session.webp" },
  "tools/weekly-brief-template": { title: "Weekly marketing brief template.", sub: "A report structure for your role and your stack, one slot per tool.", shot: "insights-session.webp" },
  "tools/engagement-rate-calculator": { title: "Engagement rate calculator.", sub: "Engagement by followers, reach or impressions, comparable across posts.", shot: "content-session.webp" },
};

// Blog posts draw their own row from front matter, so a new post needs no
// entry here: its category is the kicker, the author and read time the line
// under the title. The same card is the cover on the blog index, which is why
// the excerpt is left off it: it sits right under the cover there already.
function blogCards() {
  const cards = {};
  for (const file of readdirSync(POSTS).filter((f) => f.endsWith(".md")).sort()) {
    const front = readFileSync(join(POSTS, file), "utf8").split(/^---\s*$/m)[1] ?? "";
    const field = (key) => {
      const m = front.match(new RegExp(`^${key}:\\s*"?(.*?)"?\\s*$`, "m"));
      if (!m) throw new Error(`${file}: front matter has no ${key}`);
      return m[1];
    };
    cards[`blog/${file.slice(0, -3)}`] = {
      kicker: field("category"), title: field("title"),
      sub: `By ${field("author")} · ${field("readTime")} min read`,
    };
  }
  return cards;
}

const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/'/g, "&#39;");
function wrap(text, max) {
  const lines = []; let cur = "";
  for (const w of text.split(" ")) {
    if ((cur + " " + w).trim().length > max) { lines.push(cur.trim()); cur = w; } else cur += " " + w;
  }
  if (cur.trim()) lines.push(cur.trim());
  return lines;
}

async function card(slug, { title, sub, shot, kicker }) {
  const withShot = Boolean(shot);
  const titleLines = wrap(title, withShot ? 18 : 30);
  const size = titleLines.length > 2 ? 54 : 64;
  const x = 72, y = 236;
  const subLines = wrap(sub, withShot ? 36 : 62);
  // Three lines fit under a three-line title with the footer still clear;
  // a fourth runs into it, and a fourth line is a paragraph, not a subtitle.
  if (subLines.length > 3) throw new Error(`${slug}: the line under the title runs to ${subLines.length} lines; shorten it`);
  const subY = y + titleLines.length * size * 1.12 + 22;
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}">
    <defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#fff1e8"/><stop offset=".55" stop-color="#f7f4f0"/><stop offset="1" stop-color="#e9ecf5"/></linearGradient></defs>
    <rect width="${W}" height="${H}" fill="url(#bg)"/>
    <text x="${x}" y="112" font-family="Georgia, serif" font-size="44" fill="#0d0f1a">duct</text><circle cx="${x + 112}" cy="98" r="9" fill="#ff5c00"/>
    ${kicker ? `<rect x="${x}" y="${y - size - 22}" width="22" height="3" rx="1.5" fill="#ff5c00"/><text x="${x + 32}" y="${y - size - 12}" font-family="Helvetica, Arial, sans-serif" font-size="19" font-weight="bold" letter-spacing="2.5" fill="#ff5c00">${esc(kicker.toUpperCase())}</text>` : ""}
    ${titleLines.map((l, i) => `<text x="${x}" y="${y + i * size * 1.12}" font-family="Georgia, serif" font-size="${size}" font-weight="bold" fill="#0d0f1a" letter-spacing="-1">${esc(l)}</text>`).join("")}
    ${subLines.map((l, i) => `<text x="${x}" y="${subY + i * 34}" font-family="Helvetica, Arial, sans-serif" font-size="24" fill="#4b5068">${esc(l)}</text>`).join("")}
    <text x="${x}" y="${H - 56}" font-family="Helvetica, Arial, sans-serif" font-size="20" fill="#7a7f95">getduct.ai · open source · MIT</text>
  </svg>`;
  const layers = [];
  if (withShot) {
    const sw = 600, sh = 470, left = W - sw + 70, top = H - sh + 70;
    const crop = await sharp(join(MEDIA, shot)).resize({ width: 1180 }).extract({ left: 0, top: 0, width: sw, height: sh }).toBuffer();
    const mask = Buffer.from(`<svg width="${sw}" height="${sh}"><rect width="${sw}" height="${sh}" rx="18" fill="#fff"/></svg>`);
    const rounded = await sharp(crop).composite([{ input: mask, blend: "dest-in" }]).png().toBuffer();
    const shadow = Buffer.from(`<svg width="${W}" height="${H}"><defs><filter id="s" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="18"/></filter></defs><rect x="${left}" y="${top + 20}" width="${sw}" height="${sh}" rx="18" fill="#0d0f1a" opacity=".22" filter="url(#s)"/></svg>`);
    layers.push({ input: shadow, left: 0, top: 0 }, { input: rounded, left, top });
  }
  const out = join(OUT, slug.replace("/", "-") + ".jpg");
  await sharp(Buffer.from(svg)).composite(layers).jpeg({ quality: 84, mozjpeg: true }).toFile(out);
  const size_ = statSync(out).size;
  if (size_ > LIMIT) throw new Error(`${out} is ${Math.round(size_ / 1024)} KB, over the 150 KB budget`);
  return size_;
}

const ALL = { ...PAGES, ...blogCards() };
let total = 0;
for (const [slug, spec] of Object.entries(ALL)) total += await card(slug, spec);
console.log(`${Object.keys(ALL).length} cards in site/assets/og, ${Math.round(total / 1024)} KB together`);
