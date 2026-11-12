// The whole check against the fixture site, then one threshold at a time.

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { check, page, withHome, png, ORIGIN } from './helpers.js';
import { validate } from '../src/schema.js';
import { USER_AGENT } from '../src/version.js';

const LIVE_IDS = ['M1', 'M2', 'S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7', 'S8', 'S10', 'C1', 'C3', 'C4', 'C5', 'C6', 'A1', 'A2', 'A3', 'F2', 'F3', 'F5'];

test('the fixture site passes every live check', async () => {
  const { result, byId } = await check();
  for (const id of LIVE_IDS) assert.equal(byId[id].status, 'PASS', `${id}: ${JSON.stringify(byId[id])}`);
  assert.equal(result.score, 100);
  assert.equal(result.band, 'Ready');
  assert.deepEqual(result.fixes, []);
  assert.deepEqual(validate(result), []);
});

test('repository and judgement checks come back UNVERIFIED, never FAIL', async () => {
  const { byId } = await check();
  for (const id of ['M3', 'M4', 'M5', 'M6', 'M7', 'K1', 'K2', 'K3', 'K4', 'S9', 'C2', 'A4', 'A5', 'F1', 'F4']) {
    assert.equal(byId[id].status, 'UNVERIFIED', id);
  }
  assert.match(byId.A4.evidence[0], /^A job queue that lives in your SQLite file/);
});

test('every catalog id is reported exactly once', async () => {
  const { result } = await check();
  const ids = result.checks.map((c) => c.id);
  assert.equal(new Set(ids).size, ids.length);
  assert.equal(ids.length, 38);
});

test('page picking: the action page first, then docs, the newest post, the navigation', async () => {
  const { result } = await check();
  const picked = result.pages.filter((p) => !p.skipped && p.status === 200).map((p) => [p.why, new URL(p.url).pathname]);
  // Pricing is an action page too (the skill's order: signup, download, pricing, checkout).
  assert.deepEqual(picked.slice(0, 5), [['homepage', '/'], ['action', '/download'], ['action', '/pricing'], ['docs', '/docs/'], ['newest post', '/blog/queue-in-sqlite']]);
  assert.equal(result.action.label, 'Download for macOS');
});

test('--pages caps the HTML pages read', async () => {
  const { result } = await check({}, { pages: 2 });
  assert.equal(result.pagesRead, 2);
});

test('requests name getduct and the repository', async () => {
  const { seen } = await check();
  assert.ok(seen.length > 5);
  for (const s of seen) assert.equal(s.headers['user-agent'], USER_AGENT);
  assert.match(USER_AGENT, /^getduct\/\d+\.\d+\.\d+ \(\+https:\/\/github\.com\/5hirish\/duct\)$/);
});

test('an unreachable homepage is an error, not a score', async () => {
  await assert.rejects(check({ '/': { status: 503, body: 'down' } }), /answered 503/);
});

// ---- Measurement ----

test('M1 FAIL with no tag; M2 WARN when a page lacks it', async () => {
  const none = await check(withHome([['<script defer src=https://plausible.io/js/script.js data-domain=tinyqueue.dev></script>', '']]));
  assert.equal(none.byId.M1.status, 'FAIL');
  assert.equal(none.byId.M2.status, 'UNVERIFIED');
  const some = await check({ '/pricing': page('<title>Tinyqueue pricing: free for one project</title><link rel="canonical" href="https://tinyqueue.dev/pricing">') });
  assert.equal(some.byId.M2.status, 'WARN');
  assert.deepEqual(some.byId.M2.evidence, ['/pricing']);
});

test('M1 finds a tag inside a first-party script', async () => {
  const r = await check({
    ...withHome([['<script defer src=https://plausible.io/js/script.js data-domain=tinyqueue.dev></script>', '<script src=/app.js></script>']]),
    '/app.js': { body: "posthog.init('phc_123', { api_host: '/ingest' })", headers: { 'content-type': 'text/javascript' } },
  });
  assert.equal(r.byId.M1.status, 'PASS');
  assert.match(r.byId.M1.evidence[0], /PostHog: loaded by \/app\.js/);
});

// ---- Search ----

test('S1 FAIL on a noindex homepage or a robots block; WARN on a docs page; fine on /privacy', async () => {
  assert.equal((await check(withHome([['<meta charset=utf-8>', '<meta charset=utf-8><meta name=robots content="noindex">']]))).byId.S1.status, 'FAIL');
  assert.equal((await check({ '/robots.txt': 'User-agent: *\nDisallow: /\n' })).byId.S1.status, 'FAIL');
  const docs = await check({ '/docs/': page('<title>Tinyqueue docs: install, enqueue, retry</title><meta name="robots" content="noindex">') });
  assert.equal(docs.byId.S1.status, 'WARN');
  const header = await check({ '/': { body: withHome([])['/'].body, headers: { 'content-type': 'text/html', 'x-robots-tag': 'noindex' } } });
  assert.equal(header.byId.S1.status, 'FAIL');
});

const title = (t) => withHome([['<title>Tinyqueue: a job queue for SQLite apps</title>', `<title>${t}</title>`]]);

test('S2 title length keeps the 10-character tolerance: WARN only under 20 or over 70', async () => {
  assert.equal((await check(title('x'.repeat(70)))).byId.S2.status, 'PASS');
  assert.equal((await check(title('x'.repeat(71)))).byId.S2.status, 'WARN');
  assert.equal((await check(title('Queue for SQLite tea'))).byId.S2.status, 'PASS'); // 20
  assert.equal((await check(title('Queue for SQLite te'))).byId.S2.status, 'WARN'); // 19
  assert.equal((await check(title('TinyQueue'))).byId.S2.fix, 'Say what it is in the homepage title');
});

test('S2 FAIL on a missing or a shared title', async () => {
  assert.equal((await check(title(''))).byId.S2.status, 'FAIL');
  const dup = await check({ '/pricing': page('<title>Tinyqueue docs: install, enqueue, retry</title>') });
  assert.equal(dup.byId.S2.status, 'FAIL');
});

const desc = (d) => withHome([['content="Tinyqueue is a durable job queue that lives inside your SQLite file. One binary, no Redis, retries and schedules built in."', `content="${d}"`]]);

test('S3 description: WARN missing or over 170 on the homepage; observation elsewhere', async () => {
  assert.equal((await check(desc('d'.repeat(170)))).byId.S3.status, 'PASS');
  assert.equal((await check(desc('d'.repeat(171)))).byId.S3.status, 'WARN');
  assert.equal((await check(withHome([['<meta name=description content="Tinyqueue is a durable job queue that lives inside your SQLite file. One binary, no Redis, retries and schedules built in.">', '']]))).byId.S3.status, 'WARN');
  const r = await check({ '/pricing': page(`<title>Tinyqueue pricing: free for one project</title><meta name="description" content="${'p'.repeat(200)}">`) });
  assert.equal(r.byId.S3.status, 'PASS');
  assert.ok(r.result.observations.some((o) => /200 characters on \/pricing/.test(o)));
});

test('S4 canonical: FAIL off the domain, WARN missing or another path, trailing slash is the same page', async () => {
  const canon = (href) => withHome([['<link rel=canonical href=https://tinyqueue.dev/>', href ? `<link rel=canonical href=${href}>` : '']]);
  assert.equal((await check(canon('https://tinyqueue.vercel.app/'))).byId.S4.status, 'FAIL');
  assert.equal((await check(canon('http://localhost:3000/'))).byId.S4.status, 'FAIL');
  assert.equal((await check(canon(null))).byId.S4.status, 'WARN');
  assert.equal((await check(canon('https://tinyqueue.dev/home'))).byId.S4.status, 'WARN');
  assert.equal((await check(canon('https://www.tinyqueue.dev'))).byId.S4.status, 'PASS');
});

test('S5 WARN with no H1 or a logo-only H1; a brand-word H1 is only noted', async () => {
  const h1 = (h) => withHome([['<h1>A job queue that lives in your<br>SQLite file</h1>', h]]);
  assert.equal((await check(h1(''))).byId.S5.status, 'WARN');
  assert.equal((await check(h1('<h1><img src=/logo.svg alt=Tinyqueue></h1>'))).byId.S5.status, 'WARN');
  const word = await check(h1('<h1>Tinyqueue</h1>'));
  assert.equal(word.byId.S5.status, 'PASS');
  assert.ok(word.result.observations.some((o) => o.includes('only the name')));
});

function sitemapOf(n, lastmod = '2026-10-01') {
  const urls = [];
  for (let i = 0; i < n; i++) urls.push(`<url><loc>https://tinyqueue.dev/p/${i}</loc><lastmod>${lastmod}</lastmod></url>`);
  return { body: `<?xml version="1.0"?><urlset>${urls.join('')}</urlset>`, headers: { 'content-type': 'application/xml' } };
}

test('S6 FAIL over 50,000 URLs in one file; fine at 50,000', async () => {
  const at = await check({ '/sitemap.xml': sitemapOf(50000) }, { pages: 1 });
  assert.notEqual(at.byId.S6.status, 'FAIL');
  const over = await check({ '/sitemap.xml': sitemapOf(50001) }, { pages: 1 });
  assert.equal(over.byId.S6.status, 'FAIL');
  assert.match(over.byId.S6.evidence[0], /50,001 URLs/);
});

test('S6 clock-stamped dates alone get their own fix title', async () => {
  const pages = {};
  for (let i = 0; i < 20; i++) pages[`/p/${i}`] = page(`<title>Tinyqueue page number ${i} of twenty</title>`);
  const r = await check({ '/sitemap.xml': sitemapOf(20, '2026-11-11'), ...pages }, { pages: 1 });
  assert.equal(r.byId.S6.fix, 'Date sitemap entries from the content, not the clock');
});

test('S6 WARN: missing, redirecting or dead URLs, or every lastmod stamped today', async () => {
  const none = await check({ '/sitemap.xml': null, '/robots.txt': 'User-agent: *\nAllow: /\n' });
  assert.equal(none.byId.S6.status, 'WARN');
  const redirect = await check({ '/docs/': { status: 301, headers: { location: 'https://tinyqueue.dev/documentation/' } }, '/documentation/': page('<title>Tinyqueue documentation for everyone</title>') });
  assert.equal(redirect.byId.S6.status, 'WARN');
  assert.match(redirect.byId.S6.evidence.join(' '), /redirect/);
  const clock = await check({ '/sitemap.xml': sitemapOf(20, '2026-11-11T09:00:00Z') }, { pages: 1 });
  assert.equal(clock.byId.S6.status, 'WARN');
  assert.ok(clock.byId.S6.evidence.some((e) => /20 of 20 lastmod dates are today/.test(e)));
});

test('S7 FAIL on plain HTTP without a redirect; WARN past one hop', async () => {
  assert.equal((await check({ 'http://tinyqueue.dev/': withHome([])['/'] })).byId.S7.status, 'FAIL');
  const { fetch } = await import('./helpers.js').then((h) => h.fakeFetch({
    'https://www.tinyqueue.dev/': { status: 301, headers: { location: 'https://tinyqueue.dev/start' } },
    '/start': { status: 302, headers: { location: 'https://tinyqueue.dev/' } },
  }));
  const { runCheck } = await import('../src/check/index.js');
  const r = await runCheck('https://www.tinyqueue.dev/', { fetch, pages: 1 });
  assert.equal(r.checks.find((c) => c.id === 'S7').status, 'WARN');
});

test('S8 WARN on an empty app shell', async () => {
  const shell = { '/': { body: '<!doctype html><html><head><title>Tinyqueue: a job queue for SQLite apps</title></head><body><div id="root"></div><script src="/main.js"></script></body></html>', headers: { 'content-type': 'text/html' } } };
  assert.equal((await check(shell, { pages: 1 })).byId.S8.status, 'WARN');
});

test('S10 WARN on review markup the page does not show, or copied from Trustpilot', async () => {
  const ld = (json) => withHome([['{"@context":"https://schema.org","@type":"SoftwareApplication","name":"Tinyqueue"}', json]]);
  const hidden = await check(ld('{"@type":"Product","aggregateRating":{"@type":"AggregateRating","ratingValue":5,"reviewCount":87}}'));
  assert.equal(hidden.byId.S10.status, 'WARN');
  const copied = await check(ld('{"@type":"Product","review":{"@type":"Review","reviewBody":"Used by 1,200 developers","url":"https://www.trustpilot.com/review/x"}}'));
  assert.equal(copied.byId.S10.status, 'WARN');
  const shown = await check(ld('{"@type":"Product","review":{"@type":"Review","reviewBody":"Used by 1,200 developers"}}'));
  assert.equal(shown.byId.S10.status, 'PASS');
});

// ---- Social card ----

test('C1 FAIL when the homepage image is missing, relative or 404; WARN on another page', async () => {
  const img = (v) => withHome([['<meta property=og:image content=https://tinyqueue.dev/og.png>', v]]);
  assert.equal((await check(img(''))).byId.C1.status, 'FAIL');
  assert.equal((await check(img('<meta property=og:image content=/og.png>'))).byId.C1.status, 'FAIL');
  const gone = await check({ '/og.png': null });
  assert.equal(gone.byId.C1.status, 'FAIL');
  assert.equal(gone.byId.C1.fix, 'Point the social card at an image that loads');
  const html = await check({ '/og.png': { body: '<html>', headers: { 'content-type': 'text/html' } } });
  assert.equal(html.byId.C1.status, 'FAIL');
  assert.equal((await check({ '/og-post.png': null })).byId.C1.status, 'WARN');
});

test('C3 WARN under 600x315 or off 1.91:1 by more than 0.15', async () => {
  const sized = async (w, h) => (await check({ '/og.png': { body: png(w, h), headers: { 'content-type': 'image/png' } } }, { pages: 1 })).byId.C3.status;
  assert.equal(await sized(1200, 630), 'PASS');
  assert.equal(await sized(1200, 675), 'PASS'); // 16:9, 1.78
  assert.equal(await sized(599, 314), 'WARN');
  assert.equal(await sized(2400, 1400), 'WARN'); // 1.71, the pagefind case
  assert.equal(await sized(1200, 1200), 'WARN');
});

test('C4 and C5: og text and the large twitter card', async () => {
  assert.equal((await check(withHome([['<meta property=og:description content="A durable job queue inside your SQLite file.">', '']]))).byId.C4.status, 'WARN');
  assert.equal((await check(withHome([['<meta name=twitter:card content=summary_large_image>', '']]))).byId.C5.status, 'WARN');
  assert.equal((await check(withHome([['content=summary_large_image', 'content=summary']]))).byId.C5.status, 'WARN');
});

test('C6 WARN when every page shares the homepage card', async () => {
  const same = '<meta property="og:title" content="Tinyqueue: a job queue for SQLite apps"><meta property="og:image" content="https://tinyqueue.dev/og.png">';
  const r = await check({
    '/download': page(`<title>Download Tinyqueue for macOS and Linux</title>${same}`),
    '/docs/': page(`<title>Tinyqueue docs: install, enqueue, retry</title>${same}`),
    '/blog/queue-in-sqlite': page(`<title>Why we put the job queue inside SQLite</title>${same}`),
    '/pricing': null, '/blog/': null,
  });
  assert.equal(r.byId.C6.status, 'WARN');
});

// ---- Answer engines ----

test('A1 FAIL when robots.txt blocks an AI crawler from the whole site', async () => {
  const r = await check({ '/robots.txt': 'User-agent: *\nAllow: /\n\nUser-agent: GPTBot\nDisallow: /\n' });
  assert.equal(r.byId.A1.status, 'FAIL');
  assert.match(r.byId.A1.finding, /GPTBot/);
  assert.equal(r.byId.S1.status, 'PASS');
  assert.equal((await check({ '/robots.txt': null })).byId.A1.status, 'PASS');
});

test('A2 WARN when llms.txt is missing, an HTML fallback, under 200 characters or names no pages', async () => {
  assert.equal((await check({ '/llms.txt': null })).byId.A2.status, 'WARN');
  assert.equal((await check({ '/llms.txt': withHome([])['/'] })).byId.A2.status, 'WARN');
  const text = (s) => ({ body: s, headers: { 'content-type': 'text/plain' } });
  const links = '- [Docs](https://tinyqueue.dev/docs/)\n';
  assert.equal((await check({ '/llms.txt': text(links + 'x'.repeat(199 - links.length)) })).byId.A2.status, 'WARN');
  assert.equal((await check({ '/llms.txt': text(links + 'x'.repeat(200 - links.length)) })).byId.A2.status, 'PASS');
  assert.equal((await check({ '/llms.txt': text('y'.repeat(400)) })).byId.A2.status, 'WARN');
});

test('A3 WARN when the homepage JSON-LD says it is a blog post', async () => {
  const r = await check(withHome([['"@type":"SoftwareApplication"', '"@type":"BlogPosting"']]));
  assert.equal(r.byId.A3.status, 'WARN');
});

// ---- First impression ----

test('F2 FAIL when the main button goes nowhere or to a 404', async () => {
  const cta = (href) => withHome([['<a class="btn btn-primary" href=/download>', `<a class="btn btn-primary" href="${href}">`]]);
  assert.equal((await check(cta('#'))).byId.F2.status, 'FAIL');
  assert.equal((await check(cta('http://localhost:3000/download'))).byId.F2.status, 'FAIL');
  assert.equal((await check({ '/download': null })).byId.F2.status, 'FAIL');
});

test('F3 WARN on "Get started" and "Learn more", not on a named outcome', async () => {
  const label = (t) => withHome([['>Download for macOS</a>', `>${t}</a>`]]);
  assert.equal((await check(label('Get started →'))).byId.F3.status, 'WARN');
  assert.equal((await check(label('Learn more'))).byId.F3.status, 'WARN');
  assert.equal((await check(label('Get started free'))).byId.F3.status, 'PASS');
});

test('F5 FAIL on a dead navigation link, WARN on a dead footer link', async () => {
  assert.equal((await check({ '/pricing': null })).byId.F5.status, 'FAIL');
  assert.equal((await check({ 'https://github.com/tinyqueue/tinyqueue': null })).byId.F5.status, 'WARN');
});

test('pages that redirect off the site or by meta refresh are not scored', async () => {
  const r = await check({
    '/pricing': { status: 301, headers: { location: 'https://github.com/tinyqueue/tinyqueue' } },
    '/blog/': { body: '<html><head><title>x</title><meta name=robots content=noindex><meta http-equiv=refresh content="0; url=/blog/queue-in-sqlite"></head></html>', headers: { 'content-type': 'text/html' } },
  });
  assert.deepEqual(r.result.pages.filter((p) => p.skipped).map((p) => p.skipped).sort(), ['meta refresh redirect', 'redirects off the site']);
  assert.equal(r.byId.S1.status, 'PASS');
  assert.equal(r.byId.S2.status, 'PASS');
});

test('the other-language copies of a page are not sampled', async () => {
  const r = await check({
    ...withHome([['<a href=/blog/>Blog</a>', '<a href=/blog/>Blog</a><a href=/de/>Deutsch</a><a href=/es/>Español</a>']]),
    '/de/': page('<title>Tinyqueue auf Deutsch</title>'),
    '/es/': page('<title>Tinyqueue en español</title>'),
  });
  assert.ok(!r.result.pages.some((p) => /\/(de|es)\/$/.test(p.url)));
  assert.equal(new URL(r.result.url).origin, ORIGIN);
});
