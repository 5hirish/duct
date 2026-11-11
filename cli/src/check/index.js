// Fetch what a launch check reads, then hand a snapshot to the checks.
//
// Order and budget follow the skill's step 2: robots.txt, the sitemap and
// llms.txt; the homepage; then up to `pages - 1` more, picked as the action's
// page, docs, the newest post, the navigation, then the sitemap. Social
// images, up to 50 sitemap URLs and the homepage's links are probed on top and
// do not count toward the page budget.

import { createFetcher, text, isHtml, LIMITS } from './fetch.js';
import { parseHtml, meta, linkRel, jsonLdSummary } from './html.js';
import { parseRobots } from './robots.js';
import { parseSitemap, spread } from './sitemap.js';
import { imageSize } from './image.js';
import { detectInPage, detectInCode } from './analytics.js';
import { runChecks, findCta, sameSite } from './checks.js';
import { computeScore, rankFixes } from '../score.js';
import { SCHEMA_ID } from '../catalog.js';
import { VERSION } from '../version.js';

const SITEMAP_SAMPLE = 50;
const MAX_CHILD_SITEMAPS = 3;
const MAX_IMAGES = 10;
const MAX_LINKS = 40;
const MAX_FIRST_PARTY_SCRIPTS = 6;
const ASSET = /\.(pdf|zip|dmg|exe|msi|pkg|deb|rpm|appimage|tar|gz|tgz|png|jpe?g|gif|webp|svg|avif|mp4|mov|webm|mp3|xml|json|txt|rss|atom|ics|css|js)$/i;
const DOCS = /(^|\/)(docs?|documentation|getting-started|get-started|quick-?start|guides?|tutorial)(\/|$)/i;
const POST = /\/(blog|posts?|articles?|news|journal|changelog)\/[^/]+/i;
const ACTION = /(^|\/)(pricing|download|downloads|signup|sign-up|register|join|waitlist|install|start|get-started|buy|checkout)(\/|$)/i;

export function normalizeUrl(input) {
  let s = String(input).trim();
  if (!/^[a-z][a-z0-9+.-]*:\/\//i.test(s)) s = `https://${s}`;
  const u = new URL(s);
  if (u.protocol !== 'https:' && u.protocol !== 'http:') throw new Error(`only http and https URLs can be checked (got ${u.protocol})`);
  u.hash = '';
  return u.href;
}

function pageKey(href) {
  const u = new URL(href);
  u.hash = '';
  return `${u.host.replace(/^www\./, '')}${u.pathname.replace(/\/+$/, '') || '/'}${u.search}`;
}

function record(url, res, page) {
  if (!page) return { url, finalUrl: res.finalUrl, status: res.status, error: res.error ?? null, redirects: res.redirects?.length ?? 0 };
  const cta = findCta(page);
  return {
    url,
    finalUrl: res.finalUrl,
    status: res.status,
    redirects: res.redirects.length,
    title: page.title,
    description: meta(page, 'description'),
    canonical: linkRel(page, 'canonical'),
    robots: meta(page, 'robots'),
    xRobotsTag: res.headers['x-robots-tag'] ?? null,
    h1: page.h1,
    og: { title: meta(page, 'og:title'), description: meta(page, 'og:description'), image: meta(page, 'og:image'), url: meta(page, 'og:url'), siteName: meta(page, 'og:site_name') },
    twitter: { card: meta(page, 'twitter:card'), image: meta(page, 'twitter:image') },
    jsonLdTypes: jsonLdSummary(page).types,
    analytics: [],
    headline: page.h1[0] ?? null,
    subhead: page.firstParagraph,
    cta: cta ? { text: cta.text, href: cta.href } : null,
    textLength: page.text.length,
  };
}

export async function runCheck(input, { pages = 10, fetch, log = () => {}, now = new Date() } = {}) {
  const start = normalizeUrl(input);
  const f = createFetcher({ fetch });
  log(`Reading ${start}`);

  const home = await f.get(start, { accept: 'text/html,application/xhtml+xml' });
  if (!home.status) throw new Error(`could not reach ${start}: ${home.error}`);
  if (home.status >= 400) throw new Error(`${start} answered ${home.status}; check the URL, or whether the site blocks automated requests`);
  if (!isHtml(home)) throw new Error(`${home.finalUrl} is not an HTML page (${home.headers['content-type'] ?? 'no content type'})`);
  const homeUrl = home.finalUrl;
  const origin = new URL(homeUrl).origin;
  const host = new URL(homeUrl).hostname;
  const homePage = parseHtml(text(home));

  const httpUrl = start.startsWith('https:') ? `http://${new URL(start).host}/` : null;
  const [robotsRes, llmsRes, httpRes] = await Promise.all([
    f.get(`${origin}/robots.txt`, { maxBytes: 512 * 1024 }),
    f.get(`${origin}/llms.txt`, { maxBytes: 512 * 1024 }),
    httpUrl ? f.get(httpUrl, { maxBytes: 1024 }) : null,
  ]);
  const robotsOk = robotsRes.status === 200 && !isHtml(robotsRes);
  const robots = robotsOk ? parseRobots(text(robotsRes)) : null;

  // Sitemap: what robots.txt names, else the conventional path.
  log('Reading the sitemap');
  const sitemapUrls = robots?.sitemaps.length ? robots.sitemaps.slice(0, 2) : [`${origin}/sitemap.xml`];
  const sitemapFiles = [];
  for (const url of sitemapUrls) {
    const res = await f.get(url, { maxBytes: LIMITS.sitemapBytes });
    const file = { url, status: res.status, bytes: res.bytes ?? 0, truncated: !!res.truncated, isIndex: false, entries: [], error: res.error ?? null };
    if (res.status === 200 && !isHtml(res)) {
      const xml = text(res);
      file.bytes = Buffer.byteLength(xml);
      const parsed = parseSitemap(xml);
      file.isIndex = parsed.isIndex;
      file.entries = parsed.entries;
      file.urlCount = (xml.match(/<url[\s>]/gi) ?? []).length;
    }
    sitemapFiles.push(file);
    if (file.isIndex) {
      for (const child of file.entries.slice(0, MAX_CHILD_SITEMAPS)) {
        const cres = await f.get(child.loc, { maxBytes: LIMITS.sitemapBytes });
        const cfile = { url: child.loc, status: cres.status, bytes: cres.bytes ?? 0, truncated: !!cres.truncated, isIndex: false, entries: [], child: true, error: cres.error ?? null };
        if (cres.status === 200) {
          const xml = text(cres);
          cfile.bytes = Buffer.byteLength(xml);
          cfile.entries = parseSitemap(xml).entries;
          cfile.urlCount = (xml.match(/<url[\s>]/gi) ?? []).length;
        }
        sitemapFiles.push(cfile);
      }
    }
  }
  const sitemapEntries = sitemapFiles.filter((s) => !s.isIndex).flatMap((s) => s.entries);

  // Pick the pages.
  const seen = new Set([pageKey(homeUrl), pageKey(start)]);
  const candidates = [];
  const add = (href, why) => {
    if (!href) return;
    let u;
    try { u = new URL(href, homeUrl); } catch { return; }
    if (!/^https?:$/.test(u.protocol) || !sameSite(u.hostname, host) || ASSET.test(u.pathname)) return;
    // The same page in another language says nothing new about the launch.
    if (otherLocale(u.pathname)) return;
    u.hash = '';
    const key = pageKey(u.href);
    if (seen.has(key)) return;
    seen.add(key);
    candidates.push({ url: u.href, why });
  };
  const otherLocale = localeFilter(homePage, homeUrl);
  const cta = findCta(homePage);
  if (cta?.href) add(cta.href, 'action');
  const anchors = homePage.anchors.filter((a) => a.href && !a.href.startsWith('#'));
  for (const a of anchors) if (ACTION.test(safePath(a.href, homeUrl))) add(a.href, 'action');
  for (const a of anchors) if (DOCS.test(safePath(a.href, homeUrl))) { add(a.href, 'docs'); break; }
  const posts = sitemapEntries.filter((e) => POST.test(safePath(e.loc, homeUrl)));
  const newest = posts.filter((e) => e.lastmod).sort((a, b) => b.lastmod.localeCompare(a.lastmod))[0] ?? posts[0];
  if (newest) add(newest.loc, 'newest post');
  else for (const a of anchors) if (POST.test(safePath(a.href, homeUrl))) { add(a.href, 'post'); break; }
  for (const a of anchors) if (a.inNav || a.inHeader) add(a.href, 'navigation');
  // Navigation rendered by JavaScript leaves only the links in the page body.
  for (const a of anchors) if (a.inMain || !homePage.hasNav) add(a.href, 'homepage link');
  for (const e of sitemapEntries.slice(0, 200)) add(e.loc, 'sitemap');

  log(`Reading up to ${pages - 1} more pages`);
  const sampled = [{ url: homeUrl, res: home, page: homePage, why: 'homepage' }];
  const failed = [];
  const skipped = [];
  let ci = 0;
  while (sampled.length < pages && ci < candidates.length) {
    const batch = candidates.slice(ci, ci + (pages - sampled.length));
    ci += batch.length;
    const results = await Promise.all(batch.map((c) => f.get(c.url, { accept: 'text/html' })));
    batch.forEach((c, i) => {
      const res = results[i];
      if (res.status !== 200 || !isHtml(res)) {
        failed.push({ url: c.url, status: res.status, error: res.error ?? null, why: c.why });
        return;
      }
      // A link that redirects off the site (a /github shortcut) is not a page
      // of this site, and a meta-refresh stub (Hugo's aliases) is a redirect.
      if (!sameSite(new URL(res.finalUrl).hostname, host)) {
        skipped.push({ url: c.url, finalUrl: res.finalUrl, reason: 'redirects off the site' });
        return;
      }
      const page = parseHtml(text(res));
      if (page.refresh) {
        skipped.push({ url: c.url, finalUrl: res.finalUrl, reason: 'meta refresh redirect' });
        return;
      }
      sampled.push({ url: c.url, res, page, why: c.why });
    });
  }

  // Analytics on every page, including first-party scripts the homepage loads.
  log('Looking for analytics tags');
  const scriptCache = new Map();
  for (const s of sampled) {
    s.analytics = detectInPage(s.page);
    const firstParty = s.page.scripts
      .map((sc) => { try { return new URL(sc.src, s.res.finalUrl); } catch { return null; } })
      .filter((u) => u && sameSite(u.hostname, host))
      .slice(0, MAX_FIRST_PARTY_SCRIPTS);
    for (const u of firstParty) {
      if (!scriptCache.has(u.href)) {
        const r = await f.get(u.href, { maxBytes: LIMITS.scriptBytes });
        scriptCache.set(u.href, r.status === 200 ? text(r) : '');
      }
      detectInCode(scriptCache.get(u.href), `loaded by ${u.pathname}`, (name, how) => { if (!s.analytics.has(name)) s.analytics.set(name, how); });
    }
  }

  // Social images.
  const imageUrls = [...new Set(sampled.flatMap((s) => {
    const src = meta(s.page, 'og:image');
    try { return src ? [new URL(src, s.res.finalUrl).href] : []; } catch { return []; }
  }))].slice(0, MAX_IMAGES);
  const images = new Map();
  await Promise.all(imageUrls.map(async (u) => {
    const r = await f.get(u, { range: `bytes=0-${LIMITS.imageHeadBytes - 1}`, maxBytes: LIMITS.imageHeadBytes, accept: 'image/*' });
    images.set(u, { status: r.status, type: r.headers?.['content-type'] ?? null, size: imageSize(r.body), error: r.error ?? null });
  }));

  // Sitemap sample and homepage links, HEAD only.
  log('Checking sitemap URLs and links');
  const sample = spread(sitemapEntries.map((e) => e.loc), SITEMAP_SAMPLE);
  const sitemapProbe = await Promise.all(sample.map(async (u) => {
    const r = await f.get(u, { method: 'HEAD' });
    return { url: u, status: r.status, redirects: r.redirects?.length ?? 0, finalUrl: r.finalUrl, error: r.error ?? null };
  }));
  const linkTargets = new Map();
  for (const a of homePage.anchors) {
    if (!a.href || !(a.inNav || a.inHeader || a.inFooter)) continue;
    let u;
    try { u = new URL(a.href, homeUrl); } catch { continue; }
    if (!/^https?:$/.test(u.protocol)) continue;
    u.hash = '';
    if (!linkTargets.has(u.href)) linkTargets.set(u.href, { where: a.inNav || a.inHeader ? 'navigation' : 'footer', text: a.text });
  }
  if (cta?.href) {
    try {
      const u = new URL(cta.href, homeUrl);
      if (/^https?:$/.test(u.protocol)) { u.hash = ''; if (!linkTargets.has(u.href)) linkTargets.set(u.href, { where: 'action', text: cta.text }); }
    } catch { /* an unparseable href is F2's finding, not a crash */ }
  }
  const known = new Map(sampled.map((s) => [pageKey(s.url), 200]));
  for (const fl of failed) known.set(pageKey(fl.url), fl.status);
  const links = new Map();
  await Promise.all([...linkTargets.entries()].slice(0, MAX_LINKS).map(async ([u, info]) => {
    const k = pageKey(u);
    const status = known.has(k) ? known.get(k) : (await f.get(u, { method: 'HEAD' })).status;
    links.set(u, { ...info, status });
  }));

  const snapshot = {
    start, homeUrl, origin, host, now,
    home: { res: home, page: homePage },
    pages: sampled,
    failed,
    robots: { status: robotsRes.status, error: robotsRes.error ?? null, parsed: robots, isHtml: robotsRes.status === 200 && !robotsOk },
    llms: { status: llmsRes.status, error: llmsRes.error ?? null, isHtml: llmsRes.status === 200 && isHtml(llmsRes), text: llmsRes.status === 200 ? text(llmsRes) : '' },
    http: httpRes ? { status: httpRes.status, finalUrl: httpRes.finalUrl, error: httpRes.error ?? null, redirects: httpRes.redirects?.length ?? 0 } : null,
    sitemap: { files: sitemapFiles, probe: sitemapProbe },
    images,
    links,
    cta,
  };
  const { checks, observations } = runChecks(snapshot);
  const scored = computeScore(checks);

  const pageRecords = sampled.map((s) => {
    const r = record(s.url, s.res, s.page);
    r.why = s.why;
    r.analytics = [...s.analytics.entries()].map(([name, how]) => `${name} (${how})`);
    return r;
  });
  for (const fl of failed) pageRecords.push({ url: fl.url, status: fl.status, error: fl.error, why: fl.why });
  for (const sk of skipped) pageRecords.push({ url: sk.url, finalUrl: sk.finalUrl, skipped: sk.reason });

  return {
    schema: SCHEMA_ID,
    tool: { name: 'getduct', version: VERSION },
    url: homeUrl,
    input: String(input),
    host,
    // Local time with its offset: the date on the card is the reader's day, not UTC's.
    checkedAt: localIso(now),
    pagesRead: sampled.length,
    repo: null,
    action: cta ? { label: cta.text, url: cta.href ? safeAbs(cta.href, homeUrl) : null, tracked: null } : null,
    checks,
    score: scored.score,
    band: scored.band,
    areas: scored.areas,
    fixes: rankFixes(checks),
    rankedBy: 'getduct',
    observations,
    pages: pageRecords,
    requests: f.count(),
  };
}

// Path prefixes of the homepage's other-language versions, from its hreflang
// alternates, or the usual /xx/ and /xx-yy/ shape when it declares none.
function localeFilter(page, homeUrl) {
  const homePath = new URL(homeUrl).pathname;
  const prefixes = new Set();
  for (const l of page.links) {
    if (!/alternate/i.test(l.rel ?? '') || !l.hreflang || /x-default/i.test(l.hreflang) || !l.href) continue;
    try {
      const p = new URL(l.href, homeUrl).pathname;
      if (p !== homePath && p !== '/') prefixes.add(p.replace(/\/?$/, '/'));
    } catch { /* ignore a malformed alternate */ }
  }
  const shape = /^\/([a-z]{2})(?:-[a-z]{2,4})?(?=\/|$)/i;
  const homeLocale = shape.exec(homePath)?.[0]?.toLowerCase() ?? null;
  return (path) => {
    if (prefixes.size) {
      const p = path.replace(/\/?$/, '/');
      return [...prefixes].some((x) => p.startsWith(x));
    }
    const m = shape.exec(path);
    return !!m && LOCALES.has(m[1].toLowerCase()) && m[0].toLowerCase() !== homeLocale;
  };
}

const LOCALES = new Set('ar bg bn ca cs da de el en es et fa fi fr he hi hr hu id it ja ko lt lv ms nb nl no pl pt ro ru sk sl sr sv th tr uk vi zh'.split(' '));

export function localIso(d) {
  const off = -d.getTimezoneOffset();
  const pad = (n) => String(Math.floor(Math.abs(n))).padStart(2, '0');
  const local = new Date(d.getTime() + off * 60000).toISOString().slice(0, 19);
  return `${local}${off >= 0 ? '+' : '-'}${pad(off / 60)}:${pad(off % 60)}`;
}

function safePath(href, base) {
  try { return new URL(href, base).pathname; } catch { return ''; }
}

function safeAbs(href, base) {
  try { return new URL(href, base).href; } catch { return href; }
}
