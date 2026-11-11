// The live half of the checklist, as pure functions of a snapshot.
//
// Thresholds are the checklist's, with its tolerance rule: never FAIL or WARN
// on a title or description within 10 characters of a limit. What only the
// repository or a reader's judgement can settle comes back UNVERIFIED, with
// the evidence the agent needs to settle it cheaply.

import { CHECKS } from '../catalog.js';
import { meta, linkRel, jsonLdSummary } from './html.js';
import { isAllowed, AI_CRAWLERS, SEARCH_CRAWLERS } from './robots.js';
import { SITEMAP_MAX_URLS, SITEMAP_MAX_BYTES } from './sitemap.js';

export const TITLE = { min: 30, max: 60 };
export const DESCRIPTION_MAX = 160;
export const TOLERANCE = 10;
export const IMAGE = { minWidth: 600, minHeight: 315, ratio: 1.91, ratioSlack: 0.15 };
export const LLMS_MIN_CHARS = 200;
export const SHELL_TEXT_CHARS = 100;
export const LASTMOD_TODAY_SHARE = 0.95;
export const GENERIC_CTA = ['learn more', 'get started', 'submit', 'click here', 'read more'];
const NOINDEX_OK = /(^|\/)(privacy|terms|legal|cookies?|imprint|impressum|thank-?you|thanks|success|404|login|log-in|signin|sign-in|logout|unsubscribe)(\/|\.|$)/i;
const DEAD = new Set([404, 410]);
const OFF_DOMAIN_CANONICAL = /(^|\.)(localhost|127\.0\.0\.1|0\.0\.0\.0|vercel\.app|netlify\.app|pages\.dev|github\.io|herokuapp\.com|onrender\.com|fly\.dev|railway\.app|workers\.dev|web\.app|firebaseapp\.com)$/i;
const NOT_A_PRODUCT_HOME = ['BlogPosting', 'Article', 'NewsArticle', 'Recipe', 'Event', 'JobPosting', 'Movie', 'Book'];
const REVIEW_SOURCES = /trustpilot|g2\.com|capterra|producthunt\.com\/products\/[^"]*\/reviews|apps\.apple\.com|play\.google\.com/i;

export function sameSite(a, b) {
  const strip = (h) => h.toLowerCase().replace(/^www\./, '');
  return strip(a) === strip(b);
}

const short = (url, base) => {
  try {
    const u = new URL(url, base);
    const b = new URL(base);
    return sameSite(u.hostname, b.hostname) ? (u.pathname + u.search) : u.href;
  } catch { return String(url); }
};

const unverified = (id, note, evidence = []) => ({ id, status: 'UNVERIFIED', note, evidence });
const pass = (id, evidence = [], note) => ({ id, status: 'PASS', evidence, ...(note ? { note } : {}) });
const finding = (id, status, finding, evidence, fix, note) => ({
  id, status, finding, evidence: evidence.slice(0, 20), foundBy: 'live site', fix: fix ?? CHECKS[id].fix, ...(note ? { note } : {}),
});

// The homepage's primary call to action: the first button-like link after the
// H1, outside the navigation; failing that, the first one anywhere in the body.
export function findCta(page) {
  const buttonish = (x) => /\b(btn|button|cta|primary)\b/i.test(x.cls) || /button/i.test(x.role ?? '');
  const usable = (a) => !a.inNav && !a.inFooter && a.text && a.text.length <= 60;
  const anchors = page.anchors.filter(usable);
  const pick = anchors.find((a) => a.afterH1 && buttonish(a))
    ?? anchors.find((a) => buttonish(a) && !a.inHeader)
    ?? anchors.find((a) => a.afterH1 && a.href && !a.href.startsWith('#') && a.inMain);
  if (pick) return { text: pick.text, href: pick.href, kind: 'link' };
  const btn = page.buttons.find((b) => b.afterH1 && b.text && b.type !== 'submit' && buttonish(b));
  return btn ? { text: btn.text, href: null, kind: 'button' } : null;
}

function brandOf(snap) {
  const site = meta(snap.home.page, 'og:site_name');
  const label = snap.host.replace(/^www\./, '').split('.')[0];
  return [site, label].filter(Boolean).map((s) => s.toLowerCase().replace(/[^a-z0-9]/g, ''));
}

function noindex(page, res) {
  const directives = [meta(page, 'robots'), meta(page, 'googlebot'), res.headers['x-robots-tag']].filter(Boolean).join(',');
  return /noindex|\bnone\b/i.test(directives) ? directives : null;
}

export function runChecks(snap) {
  const checks = [];
  const observations = [];
  const base = snap.homeUrl;
  const home = snap.home.page;
  const pages = snap.pages;
  const actionPage = snap.cta?.href ? pages.find((p) => p.why === 'action' && sameUrl(p.url, snap.cta.href, base)) : null;
  const keyPages = [pages[0], actionPage].filter(Boolean);

  // ---- Measurement ----
  const homeTags = pages[0].analytics;
  if (homeTags.size) {
    checks.push(pass('M1', [...homeTags.entries()].map(([n, how]) => `${n}: ${how}`)));
  } else {
    checks.push(finding('M1', 'FAIL', 'No analytics tag in the homepage HTML or the first-party scripts it loads.',
      [`${short(base, base)}: no analytics tag found`], 'Add an analytics tag',
      'WARN instead when the action happens off the site and has a public counter (npm, release downloads); UNVERIFIED when the docs say a tag is added at the edge.'));
  }
  if (!homeTags.size) checks.push(unverified('M2', 'No tag on the homepage, so there is nothing to compare.'));
  else {
    const missing = pages.slice(1).filter((p) => ![...homeTags.keys()].some((n) => p.analytics.has(n)));
    checks.push(missing.length
      ? finding('M2', 'WARN', `The homepage's tag is missing on ${missing.length} of ${pages.length - 1} other sampled pages.`, missing.map((p) => short(p.url, base)))
      : pass('M2', [`${pages.length} pages load ${[...homeTags.keys()].join(', ')}`]));
  }
  for (const id of ['M3', 'M4', 'M5', 'M6', 'M7']) checks.push(unverified(id, 'Needs the repository.'));
  const verification = meta(home, 'google-site-verification');
  checks.push(verification ? pass('M8', ['google-site-verification meta on the homepage'])
    : unverified('M8', 'No verification meta; a DNS record or a file in the repository may verify the site.'));

  // ---- Claims: the agent's reading of the product and the code ----
  for (const id of ['K1', 'K2', 'K3', 'K4']) checks.push(unverified(id, 'Needs the repository and a reading of the product.'));

  // ---- Search ----
  checks.push(checkIndexable(snap, keyPages, base));
  checks.push(checkTitles(snap, pages, base));
  checks.push(checkDescriptions(pages, keyPages, base, observations));
  checks.push(checkCanonicals(snap, pages, base));
  {
    // The checklist's WARN is "no H1, or only the logo". An H1 that is the
    // brand word in text is a judgement call, so it is noted, not charged.
    const bad = pages.filter((p) => !p.page.h1.length || !p.page.h1[0] || p.page.h1LogoOnly[0]);
    for (const p of pages) {
      if (p.page.h1[0] && !p.page.h1LogoOnly[0] && brandOf(snap).includes(p.page.h1[0].toLowerCase().replace(/[^a-z0-9]/g, ''))) {
        observations.push(`Search: the H1 on ${short(p.url, base)} is only the name ("${p.page.h1[0]}")`);
      }
    }
    checks.push(bad.length
      ? finding('S5', 'WARN', 'A page has no H1, or an H1 that is only the logo.', bad.map((p) => `${short(p.url, base)}: ${p.page.h1.length ? `H1 is an image ("${p.page.h1[0]}")` : 'no <h1>'}`))
      : pass('S5', [`${pages.length} pages have an H1`]));
  }
  checks.push(checkSitemap(snap, base, observations));
  checks.push(checkHttps(snap, base));
  {
    const shells = pages.filter((p) => p.page.text.length < SHELL_TEXT_CHARS);
    checks.push(shells.length
      ? finding('S8', 'WARN', 'The raw HTML has almost no text: crawlers that skip JavaScript see an empty page.', shells.map((p) => `${short(p.url, base)}: ${p.page.text.length} characters of text`))
      : pass('S8'));
  }
  checks.push(unverified('S9', 'Needs the repository: the site config that builds canonicals and the sitemap.'));
  checks.push(checkReviews(pages, base));

  // ---- Social card ----
  checks.push(...checkSocial(snap, pages, base, observations));

  // ---- Answer engines ----
  checks.push(checkAiCrawlers(snap));
  checks.push(checkLlms(snap));
  {
    const types = jsonLdSummary(home).types;
    const wrong = types.filter((t) => NOT_A_PRODUCT_HOME.includes(t));
    checks.push(wrong.length
      ? finding('A3', 'WARN', `The homepage's JSON-LD says it is a ${wrong.join(', ')}.`, [`homepage @type: ${types.join(', ')}`])
      : pass('A3', types.length ? [`homepage @type: ${types.join(', ')}`] : ['no JSON-LD (not a finding)']));
  }
  checks.push(unverified('A4', 'Judge it: do these words say what the product is and who it is for?', [home.mainText.slice(0, 200)]));
  checks.push(unverified('A5', 'Judge it: are the price, the install command and the key claims in text, not only in images?'));

  // ---- First impression ----
  checks.push(unverified('F1', 'Judge it: does the headline and subhead say who it is for and what they get?',
    [`headline: ${home.h1[0] ?? '(none)'}`, `subhead: ${home.firstParagraph ?? '(none)'}`]));
  checks.push(checkAction(snap, base));
  {
    const label = (snap.cta?.text ?? '').toLowerCase().replace(/[^a-z ]/g, ' ').replace(/\s+/g, ' ').trim();
    if (!snap.cta) checks.push(unverified('F3', 'No primary call to action found in the HTML.'));
    else if (GENERIC_CTA.includes(label)) {
      checks.push(finding('F3', 'WARN', `The main button says "${snap.cta.text}" where it could name the outcome.`, [`homepage CTA: "${snap.cta.text}"`],
        `Name the outcome on the "${snap.cta.text}" button`));
    } else checks.push(pass('F3', [`homepage CTA: "${snap.cta.text}"`]));
  }
  checks.push(unverified('F4', 'Judge it: users, stars, logos, a quote or a demo on the homepage?'));
  checks.push(checkDeadLinks(snap, base, observations));

  return { checks, observations };
}

function localDay(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function sameUrl(a, b, base) {
  try { return new URL(a, base).href.replace(/\/$/, '') === new URL(b, base).href.replace(/\/$/, ''); } catch { return false; }
}

function checkIndexable(snap, keyPages, base) {
  const fails = [], warns = [];
  const r = snap.robots.parsed;
  if (r) {
    for (const bot of SEARCH_CRAWLERS) if (!isAllowed(r, bot, '/')) fails.push(`robots.txt disallows / for ${bot}`);
  }
  for (const p of snap.pages) {
    const ni = noindex(p.page, p.res);
    if (!ni) continue;
    const line = `${short(p.url, base)}: ${ni}`;
    if (keyPages.includes(p)) fails.push(line);
    else if (!NOINDEX_OK.test(new URL(p.url).pathname)) warns.push(line);
  }
  if (fails.length) return finding('S1', 'FAIL', 'Search engines are told not to index the homepage or the action\'s page.', [...fails, ...warns], 'Let search engines index the homepage');
  if (warns.length) return finding('S1', 'WARN', 'A docs or blog page is marked noindex.', warns, 'Remove noindex from pages that should rank');
  return pass('S1', [r ? 'robots.txt allows search crawlers' : 'no robots.txt (everything allowed)', 'no noindex on sampled pages']);
}

function checkTitles(snap, pages, base) {
  const missing = pages.filter((p) => !p.page.title);
  const byTitle = new Map();
  for (const p of pages) if (p.page.title) byTitle.set(p.page.title, [...(byTitle.get(p.page.title) ?? []), p]);
  const dupes = [...byTitle.entries()].filter(([, ps]) => ps.length > 1);
  if (missing.length || dupes.length) {
    return finding('S2', 'FAIL', missing.length ? 'A sampled page has no <title>.' : 'Two or more pages share one title.',
      [...missing.map((p) => `${short(p.url, base)}: no <title>`), ...dupes.map(([t, ps]) => `"${t}" on ${ps.map((p) => short(p.url, base)).join(', ')}`)],
      missing.length ? 'Give every key page a title' : 'Give every key page its own title');
  }
  const brands = brandOf(snap);
  const warns = [];
  for (const p of pages) {
    const t = p.page.title, n = [...t].length;
    if (brands.includes(t.toLowerCase().replace(/[^a-z0-9]/g, ''))) warns.push(`${short(p.url, base)}: "${t}" is only the brand name`);
    else if (n < TITLE.min - TOLERANCE) warns.push(`${short(p.url, base)}: ${n} characters ("${t}")`);
    else if (n > TITLE.max + TOLERANCE) warns.push(`${short(p.url, base)}: ${n} characters`);
  }
  if (warns.length) {
    const homeBrand = warns.some((w) => w.startsWith(`${short(base, base)}:`) && w.includes('only the brand'));
    return finding('S2', 'WARN', 'A title is too short, too long or only the brand name.', warns,
      homeBrand ? 'Say what it is in the homepage title' : 'Rewrite the titles that search results cut');
  }
  return pass('S2', [`${pages.length} distinct titles`]);
}

function checkDescriptions(pages, keyPages, base, observations) {
  const warns = [];
  for (const p of keyPages) {
    const d = meta(p.page, 'description');
    if (!d) warns.push(`${short(p.url, base)}: no meta description`);
    else if ([...d].length > DESCRIPTION_MAX + TOLERANCE) warns.push(`${short(p.url, base)}: ${[...d].length} characters`);
  }
  for (const p of pages) {
    if (keyPages.includes(p)) continue;
    const d = meta(p.page, 'description');
    if (!d) observations.push(`Search: no meta description on ${short(p.url, base)}`);
    else if ([...d].length > DESCRIPTION_MAX) observations.push(`Search: meta description is ${[...d].length} characters on ${short(p.url, base)}`);
  }
  const counts = new Map();
  for (const p of pages) { const d = meta(p.page, 'description'); if (d) counts.set(d, (counts.get(d) ?? 0) + 1); }
  for (const [, n] of counts) if (n >= 3) observations.push(`Search: ${n} pages share one meta description, which usually means a template fallback`);
  const over = pages.filter((p) => (meta(p.page, 'description') ?? '').length > DESCRIPTION_MAX).length;
  if (over >= 3) observations.push(`Search: ${over} of ${pages.length} descriptions run over 160 characters, which usually means one template fallback`);
  if (warns.length) {
    const none = warns.every((w) => w.endsWith('no meta description'));
    return finding('S3', 'WARN', none ? 'The homepage or the action\'s page has no meta description.' : 'The homepage or the action\'s page has a description search results will cut.', warns,
      none ? 'Write a description for the homepage' : 'Cut the homepage description to 160 characters');
  }
  return pass('S3');
}

function checkCanonicals(snap, pages, base) {
  const fails = [], missing = [], elsewhere = [];
  for (const p of pages) {
    const c = linkRel(p.page, 'canonical');
    if (!c) { missing.push(short(p.url, base)); continue; }
    let cu;
    try { cu = new URL(c, p.res.finalUrl); } catch { fails.push(`${short(p.url, base)}: unparseable canonical "${c}"`); continue; }
    const own = new URL(p.res.finalUrl);
    if (!sameSite(cu.hostname, own.hostname) || (OFF_DOMAIN_CANONICAL.test(cu.hostname) && !OFF_DOMAIN_CANONICAL.test(own.hostname))) {
      fails.push(`${short(p.url, base)}: canonical ${cu.href}`);
    } else if ((cu.pathname.replace(/\/+$/, '') || '/') !== (own.pathname.replace(/\/+$/, '') || '/')) {
      elsewhere.push(`${short(p.url, base)}: canonical ${cu.pathname}`);
    }
  }
  if (fails.length) return finding('S4', 'FAIL', 'A canonical points at another domain, so search engines are told the real site is elsewhere.', fails, 'Point canonicals at the live domain');
  if (missing.length || elsewhere.length) {
    const all = missing.length === pages.length;
    return finding('S4', 'WARN', all ? 'No page declares a canonical URL.' : 'A page has no canonical, or one pointing at a different path.',
      [...(all ? [`none of ${pages.length} sampled pages`] : missing.map((m) => `${m}: no canonical`)), ...elsewhere],
      'Add a canonical link to every page');
  }
  return pass('S4', [`${pages.length} pages declare their own URL as canonical`]);
}

function checkSitemap(snap, base, observations) {
  const files = snap.sitemap.files;
  const found = files.filter((f) => f.status === 200 && (f.entries.length || f.isIndex));
  if (!found.length) {
    if (files.some((f) => f.status === 0 || f.status >= 500)) return unverified('S6', 'The sitemap could not be fetched.', files.map((f) => `${f.url}: ${f.status || f.error}`));
    return finding('S6', 'WARN', 'No sitemap at robots.txt\'s Sitemap: line or /sitemap.xml.', files.map((f) => `${f.url}: ${f.status}`), 'Publish a sitemap');
  }
  const fails = [];
  for (const f of found) {
    if (f.isIndex) continue;
    const n = f.urlCount ?? f.entries.length;
    if (n > SITEMAP_MAX_URLS) fails.push(`${short(f.url, base)}: ${n.toLocaleString('en-US')} URLs in one file (limit 50,000)`);
    if (f.truncated || f.bytes > SITEMAP_MAX_BYTES) fails.push(`${short(f.url, base)}: over 50 MB uncompressed`);
  }
  const warns = [];
  const probe = snap.sitemap.probe;
  const redirecting = probe.filter((p) => p.redirects > 0 && p.status && p.status < 400);
  const broken = probe.filter((p) => p.status >= 400);
  if (redirecting.length) warns.push(`${redirecting.length} of ${probe.length} sampled URLs redirect: ${redirecting.slice(0, 5).map((p) => short(p.url, base)).join(', ')}`);
  if (broken.length) warns.push(`${broken.length} of ${probe.length} sampled URLs fail: ${broken.slice(0, 5).map((p) => `${short(p.url, base)} (${p.status})`).join(', ')}`);
  const entries = found.filter((f) => !f.isIndex).flatMap((f) => f.entries);
  const dated = entries.filter((e) => e.lastmod);
  const today = [snap.now.toISOString().slice(0, 10), localDay(snap.now)];
  // "Every lastmod is today" in the checklist; a generator that stamps the
  // clock leaves a few hand-dated entries behind, so 95% counts as every.
  const stamped = dated.filter((e) => today.some((t) => e.lastmod.startsWith(t))).length;
  if (dated.length >= 5 && stamped / dated.length >= LASTMOD_TODAY_SHARE) {
    warns.push(`${stamped.toLocaleString('en-US')} of ${dated.length.toLocaleString('en-US')} lastmod dates are today: the generator stamps the clock`);
  }
  const total = found.filter((f) => !f.isIndex).reduce((n, f) => n + (f.urlCount ?? f.entries.length), 0);
  if (fails.length) return finding('S6', 'FAIL', 'The sitemap is over the protocol\'s size limit, so search engines can reject the whole file.', [...fails, ...warns], 'Split the sitemap before it is rejected');
  if (warns.length) {
    const clock = warns.some((w) => w.includes('lastmod dates are today'));
    return finding('S6', 'WARN', 'The sitemap lists URLs that redirect or fail, or dates every page today.', warns,
      clock && warns.length === 1 ? 'Date sitemap entries from the content, not the clock' : 'Drop redirecting and dead URLs from the sitemap');
  }
  return pass('S6', [`${total.toLocaleString('en-US')} URLs; ${probe.length} sampled, all 200 without a redirect`]);
}

function checkHttps(snap, base) {
  const hops = snap.home.res.redirects.length;
  const h = snap.http;
  if (h && h.status && h.status < 400 && h.finalUrl.startsWith('http:')) {
    return finding('S7', 'FAIL', 'The homepage is served over plain HTTP with no redirect to HTTPS.', [`${h.finalUrl}: ${h.status}`], 'Redirect HTTP to HTTPS');
  }
  if (hops > 1) {
    return finding('S7', 'WARN', `Reaching the homepage takes ${hops} redirects.`, snap.home.res.redirects.map((r) => `${r.from} (${r.status})`), 'Redirect to the homepage in one hop');
  }
  return pass('S7', [h?.finalUrl?.startsWith('https:') ? 'HTTP redirects to HTTPS' : 'HTTPS', `${hops} redirect${hops === 1 ? '' : 's'} to the homepage`]);
}

function checkReviews(pages, base) {
  const warns = [];
  for (const p of pages) {
    const { reviews } = jsonLdSummary(p.page);
    if (!reviews.length) continue;
    const raw = p.page.jsonLd.join('\n');
    if (REVIEW_SOURCES.test(raw)) { warns.push(`${short(p.url, base)}: review markup names ${raw.match(REVIEW_SOURCES)[0]}`); continue; }
    const text = p.page.text.toLowerCase();
    const hidden = reviews.filter((r) => {
      const body = String(r.reviewBody ?? r.description ?? '').toLowerCase().slice(0, 40).trim();
      const count = r.reviewCount ?? r.ratingCount;
      if (body) return !text.includes(body);
      if (count !== undefined) return !text.includes(String(count));
      return false;
    });
    if (hidden.length) warns.push(`${short(p.url, base)}: ${hidden.length} review or rating item${hidden.length > 1 ? 's' : ''} in JSON-LD not shown on the page`);
  }
  return warns.length
    ? finding('S10', 'WARN', 'Review or rating markup is copied from another site or not visible on the page, which Google\'s review snippet rules forbid.', warns, 'Remove review markup the page does not show')
    : pass('S10');
}

function checkSocial(snap, pages, base, observations) {
  const out = [];
  const imageOf = (p) => {
    const raw = meta(p.page, 'og:image');
    if (!raw) return { raw: null };
    let abs = null;
    try { abs = new URL(raw, p.res.finalUrl).href; } catch { /* reported as unparseable */ }
    return { raw, abs, relative: !/^https?:\/\//i.test(raw), probe: abs ? snap.images.get(abs) : null };
  };
  const problem = (img) => {
    if (!img.raw) return 'no og:image';
    if (img.relative) return `og:image is relative ("${img.raw}"); crawlers need an absolute URL`;
    const pr = img.probe;
    if (!pr) return null;
    if (pr.status !== 200 && pr.status !== 206) return `${img.abs} returns ${pr.status || pr.error}`;
    if (!/^image\//i.test(pr.type ?? '')) return `${img.abs} is ${pr.type ?? 'untyped'}, not an image`;
    return null;
  };
  const homeImg = imageOf(pages[0]);
  const homeProblem = problem(homeImg);
  const others = pages.slice(1).map((p) => [p, problem(imageOf(p))]).filter(([, e]) => e);
  if (homeProblem) {
    const fix = !homeImg.raw ? 'Add a social card image to the homepage' : homeImg.relative ? 'Make the social card image URL absolute' : 'Point the social card at an image that loads';
    out.push(finding('C1', 'FAIL', 'Shared links to the homepage show no image.', [`homepage: ${homeProblem}`, ...others.map(([p, e]) => `${short(p.url, base)}: ${e}`)], fix));
  } else if (others.length) {
    out.push(finding('C1', 'WARN', 'A key page has no working social image.', others.map(([p, e]) => `${short(p.url, base)}: ${e}`), 'Give every key page a social image that loads'));
  } else {
    out.push(pass('C1', [`homepage og:image ${homeImg.abs}`]));
  }
  out.push(unverified('C2', 'Needs the repository: is the file in a folder the build serves?'));

  const size = homeImg.probe?.size;
  if (homeProblem || !homeImg.probe) out.push(unverified('C3', homeProblem ? 'No homepage image to measure.' : 'The image was not fetched.'));
  else if (!size) out.push(unverified('C3', `Could not read the size of ${homeImg.probe.type ?? 'the image'} from its header.`));
  else {
    const ratio = size.width / size.height;
    const small = size.width < IMAGE.minWidth || size.height < IMAGE.minHeight;
    const off = Math.abs(ratio - IMAGE.ratio) > IMAGE.ratioSlack;
    out.push(small || off
      ? finding('C3', 'WARN', small ? 'The social image is smaller than 600x315.' : `The social image is ${ratio.toFixed(2)}:1; X and LinkedIn crop to 1.91:1.`,
        [`${homeImg.abs}: ${size.width}x${size.height}`], 'Export the social image at 1200x630')
      : pass('C3', [`${size.width}x${size.height}`]));
  }

  const h = pages[0].page;
  const missingOg = ['og:title', 'og:description'].filter((k) => !meta(h, k));
  out.push(missingOg.length
    ? finding('C4', 'WARN', `The homepage has no ${missingOg.join(' or ')}.`, [`homepage: missing ${missingOg.join(', ')}`], 'Add og:title and og:description to the homepage')
    : pass('C4'));

  const card = meta(h, 'twitter:card');
  const large = size ? size.width >= IMAGE.minWidth : !!homeImg.raw;
  if (!card) out.push(finding('C5', 'WARN', 'No twitter:card, so X shows the small summary card.', ['homepage: no twitter:card'], 'Use the large card on X'));
  else if (card === 'summary' && large) out.push(finding('C5', 'WARN', 'twitter:card is "summary" where the large card fits.', ['homepage: twitter:card=summary'], 'Use the large card on X'));
  else out.push(pass('C5', [`twitter:card=${card}`]));

  if (pages.length >= 3) {
    const sig = (p) => `${meta(p.page, 'og:image') ?? ''}|${meta(p.page, 'og:title') ?? p.page.title ?? ''}`;
    const all = pages.every((p) => sig(p) === sig(pages[0])) && meta(h, 'og:image');
    out.push(all
      ? finding('C6', 'WARN', 'Every sampled page shares the homepage\'s card, so a shared post looks like the homepage.', [`${pages.length} pages with og:image ${meta(h, 'og:image')}`], 'Give shared pages their own card')
      : pass('C6'));
  } else out.push(unverified('C6', 'Too few pages sampled to compare.'));

  const distinct = new Set(pages.map((p) => imageOf(p).abs).filter(Boolean));
  for (const u of distinct) {
    const s = snap.images.get(u)?.size;
    if (u !== homeImg.abs && s && (s.width < IMAGE.minWidth || Math.abs(s.width / s.height - IMAGE.ratio) > IMAGE.ratioSlack)) {
      observations.push(`Social card: ${short(u, base)} is ${s.width}x${s.height}`);
    }
  }
  return out;
}

function checkAiCrawlers(snap) {
  const r = snap.robots;
  if (r.status === 0 || r.status >= 500) return unverified('A1', `robots.txt could not be fetched (${r.status || r.error}).`);
  if (!r.parsed) return pass('A1', [r.status === 404 ? 'no robots.txt (everything allowed)' : `robots.txt answered ${r.status}`]);
  const blocked = AI_CRAWLERS.filter((b) => !isAllowed(r.parsed, b, '/'));
  return blocked.length
    ? finding('A1', 'FAIL', `robots.txt blocks ${blocked.join(', ')} from the whole site.`, blocked.map((b) => `robots.txt: Disallow: / applies to ${b}`), 'Let AI crawlers read the site')
    : pass('A1', [`${AI_CRAWLERS.length} AI crawlers allowed`]);
}

function checkLlms(snap) {
  const l = snap.llms;
  if (l.status === 0) return unverified('A2', `llms.txt could not be fetched (${l.error}).`);
  if (l.status !== 200 || l.isHtml) {
    return finding('A2', 'WARN', 'No /llms.txt.', [`/llms.txt: ${l.isHtml ? 'returns an HTML page' : l.status}`], 'Publish an llms.txt');
  }
  const n = l.text.trim().length;
  if (n < LLMS_MIN_CHARS) return finding('A2', 'WARN', `/llms.txt is ${n} characters.`, [`/llms.txt: ${n} characters`], 'Write an llms.txt that names your pages');
  if (!/\]\(|https?:\/\//.test(l.text)) return finding('A2', 'WARN', '/llms.txt names no pages.', ['/llms.txt: no links'], 'Write an llms.txt that names your pages');
  return pass('A2', [`/llms.txt: ${n.toLocaleString('en-US')} characters`]);
}

function checkAction(snap, base) {
  const cta = snap.cta;
  if (!cta) return unverified('F2', 'No primary call to action found in the HTML (it may be rendered by JavaScript).');
  if (cta.kind === 'button') return unverified('F2', `The main action is a <button> ("${cta.text}"); what it does needs the code.`);
  const href = (cta.href ?? '').trim();
  if (!href || href === '#' || /^javascript:/i.test(href)) {
    return finding('F2', 'FAIL', `The main button "${cta.text}" goes nowhere.`, [`homepage CTA href="${href}"`], 'Point the main button at the action');
  }
  let u;
  try { u = new URL(href, base); } catch { return finding('F2', 'FAIL', 'The main button\'s link cannot be parsed.', [`href="${href}"`], 'Point the main button at the action'); }
  if (/^(localhost|127\.0\.0\.1|0\.0\.0\.0)$/.test(u.hostname)) return finding('F2', 'FAIL', 'The main button points at localhost.', [u.href], 'Point the main button at the live site');
  const probe = [...snap.links.entries()].find(([k]) => sameUrl(k, u.href, base));
  if (probe && DEAD.has(probe[1].status)) return finding('F2', 'FAIL', `The main button leads to a ${probe[1].status}.`, [`${short(u.href, base)}: ${probe[1].status}`], 'Fix the main button\'s link');
  return pass('F2', [`"${cta.text}" -> ${short(u.href, base)}`], 'Whether it is on the first screen, and competing buttons, are not judged here.');
}

function checkDeadLinks(snap, base, observations) {
  if (!snap.home.page.hasNav) {
    observations.push('Search: the homepage HTML has no <nav> or <header> links; the navigation is rendered by JavaScript, so crawlers that skip it find no internal links there');
  }
  const navDead = [], footDead = [];
  for (const [u, info] of snap.links) {
    if (info.where === 'action') continue;
    if (DEAD.has(info.status)) (info.where === 'navigation' ? navDead : footDead).push(`${short(u, base)} (${info.status}, "${info.text}")`);
    else if (!info.status || info.status >= 500) observations.push(`First impression: ${short(u, base)} did not answer (${info.status || 'no response'})`);
  }
  if (navDead.length) return finding('F5', 'FAIL', 'A link in the main navigation is dead.', [...navDead, ...footDead], 'Fix the dead navigation link');
  if (footDead.length) return finding('F5', 'WARN', 'A footer link is dead.', footDead, 'Fix the dead footer links');
  return pass('F5', [`${snap.links.size} navigation and footer links answer`]);
}
