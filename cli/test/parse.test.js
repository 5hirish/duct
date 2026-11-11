import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseHtml, meta, linkRel, jsonLdSummary } from '../src/check/html.js';
import { parseRobots, isAllowed } from '../src/check/robots.js';
import { parseSitemap, spread } from '../src/check/sitemap.js';
import { imageSize } from '../src/check/image.js';
import { detectInPage } from '../src/check/analytics.js';
import { findCta } from '../src/check/checks.js';
import { png } from './helpers.js';

test('reads unquoted, single-quoted and entity-laden attributes', () => {
  const p = parseHtml(`<meta name=description content=Short><meta property='og:title' content='A &amp; B'>
    <link rel=canonical href=https://x.dev/a><title>T &mdash; x</title>`);
  assert.equal(meta(p, 'description'), 'Short');
  assert.equal(meta(p, 'og:title'), 'A & B');
  assert.equal(linkRel(p, 'canonical'), 'https://x.dev/a');
  assert.equal(p.title, 'T — x');
});

test('a <br> inside the H1 is a space; the logo-only H1 is told apart', () => {
  const p = parseHtml('<h1>One<br>two <em>three</em></h1><h1><img src=l.svg alt=Acme></h1>');
  assert.deepEqual(p.h1, ['One two three', 'Acme']);
  assert.deepEqual(p.h1LogoOnly, [false, true]);
});

test('a ">" inside a quoted attribute does not end the tag', () => {
  const p = parseHtml('<a href="/x" data-x="a>b" class="btn">Go</a>');
  assert.equal(p.anchors[0].text, 'Go');
  assert.equal(p.anchors[0].attrs['data-x'], 'a>b');
});

test('main text skips the navigation and prefers <main>', () => {
  const p = parseHtml('<a href=#m>Skip to content</a><nav><a href=/>Home</a></nav><main><p>Real words.</p></main><footer>F</footer>');
  assert.equal(p.mainText, 'Real words.');
  assert.equal(p.hasNav, true);
});

test('JSON-LD types, nested reviews, and invalid blocks', () => {
  const p = parseHtml(`<script type="application/ld+json">{"@graph":[{"@type":"Product","aggregateRating":{"@type":"AggregateRating","ratingValue":5,"reviewCount":12}}]}</script>
    <script type="application/ld+json">{not json</script>`);
  const s = jsonLdSummary(p);
  assert.deepEqual(s.types.sort(), ['AggregateRating', 'Product']);
  assert.equal(s.reviews.length, 1);
  assert.equal(s.invalid, 1);
});

test('meta refresh is recorded', () => {
  assert.ok(parseHtml('<meta http-equiv=refresh content="0; url=/new/">').refresh);
});

test('the primary action is the first button-like link after the H1', () => {
  const p = parseHtml('<nav><a class=btn href=/login>Log in</a></nav><main><h1>X</h1><a href=/docs>Docs</a><a class="button primary" href=/signup>Start free</a></main>');
  assert.deepEqual(findCta(p), { text: 'Start free', href: '/signup', kind: 'link' });
});

test('robots: the named group wins, longest rule wins, Allow wins a tie', () => {
  const r = parseRobots('User-agent: *\nDisallow: /\n\nUser-agent: GPTBot\nUser-agent: ClaudeBot\nAllow: /\n\nUser-agent: PerplexityBot\nDisallow: /\nAllow: /\n');
  assert.equal(isAllowed(r, 'Googlebot', '/'), false);
  assert.equal(isAllowed(r, 'GPTBot', '/'), true);
  assert.equal(isAllowed(r, 'ClaudeBot', '/'), true);
  assert.equal(isAllowed(r, 'PerplexityBot', '/'), true);
  assert.equal(isAllowed(parseRobots('User-agent: *\nDisallow:\n'), 'GPTBot', '/'), true);
  assert.equal(isAllowed(parseRobots('User-agent: *\nDisallow: /*.pdf$\n'), 'GPTBot', '/'), true);
});

test('sitemaps: urlset, index, CDATA and an even sample', () => {
  const s = parseSitemap('<urlset><url><loc><![CDATA[https://x.dev/a?b=1&amp;c=2]]></loc><lastmod>2026-01-01</lastmod></url><url><loc>https://x.dev/b</loc></url></urlset>');
  assert.equal(s.isIndex, false);
  assert.deepEqual(s.entries.map((e) => e.loc), ['https://x.dev/a?b=1&c=2', 'https://x.dev/b']);
  assert.equal(parseSitemap('<sitemapindex><sitemap><loc>https://x.dev/s1.xml</loc></sitemap></sitemapindex>').isIndex, true);
  assert.deepEqual(spread([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 5), [1, 3, 5, 7, 9]);
});

test('image sizes from the header: PNG, GIF, JPEG, WebP', () => {
  assert.deepEqual(imageSize(png(1200, 630)), { type: 'png', width: 1200, height: 630 });
  const gif = Buffer.alloc(32); gif.write('GIF89a', 0, 'latin1'); gif.writeUInt16LE(600, 6); gif.writeUInt16LE(315, 8);
  assert.deepEqual(imageSize(gif), { type: 'gif', width: 600, height: 315 });
  const jpg = Buffer.from([0xff, 0xd8, 0xff, 0xe0, 0x00, 0x04, 0, 0, 0xff, 0xc0, 0x00, 0x11, 0x08, 0x02, 0x76, 0x04, 0xb0, 0, 0, 0, 0, 0, 0, 0, 0, 0]);
  assert.deepEqual(imageSize(jpg), { type: 'jpeg', width: 1200, height: 630 });
  const webp = Buffer.alloc(32); webp.write('RIFF', 0, 'latin1'); webp.write('WEBPVP8X', 8, 'latin1'); webp.writeUIntLE(1199, 24, 3); webp.writeUIntLE(629, 27, 3);
  assert.deepEqual(imageSize(webp), { type: 'webp', width: 1200, height: 630 });
  assert.equal(imageSize(Buffer.from('<svg></svg>'.padEnd(40))), null);
});

test('analytics: script URLs, data attributes and inline init calls', () => {
  const p = parseHtml(`<script src="https://plausible.io/js/script.js"></script>
    <script defer src="/s.js" data-website-id="abc"></script>
    <script>posthog.init('phc_x', {api_host: '/ingest'})</script>`);
  const found = detectInPage(p);
  assert.deepEqual([...found.keys()].sort(), ['Plausible', 'PostHog', 'Umami']);
  // A vendor's name in passing is not a tag.
  assert.equal(detectInPage(parseHtml('<script>const label = "posthog"; // just a word</script>')).size, 0);
  assert.equal(detectInPage(parseHtml('<script>var vendors = ["mixpanel docs"]</script>')).size, 0);
  assert.ok(detectInPage(parseHtml('<script>s.src = "/_vercel/insights/script.js"</script>')).has('Vercel Analytics'));
});
