// A fake fetch that serves the fixture site, so no test touches the network.
// `overrides` replaces or removes (null) a path, or adds a full URL.

import { readFileSync } from 'node:fs';
import { encodePng } from '../src/card/raster.js';
import { runCheck } from '../src/check/index.js';

const DIR = new URL('./fixtures/site/', import.meta.url);
const read = (f) => readFileSync(new URL(f, DIR), 'utf8');
export const ORIGIN = 'https://tinyqueue.dev';

export function png(width, height) {
  return encodePng(new Float32Array(width * height * 3), width, height);
}

const HTML = { 'content-type': 'text/html; charset=utf-8' };

function base() {
  return {
    '/': { body: read('index.html'), headers: HTML },
    '/download': { body: read('download.html'), headers: HTML },
    '/docs/': { body: read('docs.html'), headers: HTML },
    '/pricing': { body: read('pricing.html'), headers: HTML },
    '/blog/': { body: read('blog.html'), headers: HTML },
    '/blog/queue-in-sqlite': { body: read('post.html'), headers: HTML },
    '/privacy': { body: read('privacy.html'), headers: HTML },
    '/robots.txt': { body: read('robots.txt'), headers: { 'content-type': 'text/plain' } },
    '/sitemap.xml': { body: read('sitemap.xml'), headers: { 'content-type': 'application/xml' } },
    '/llms.txt': { body: read('llms.txt'), headers: { 'content-type': 'text/plain' } },
    '/og.png': { body: png(1200, 630), headers: { 'content-type': 'image/png' } },
    '/og-post.png': { body: png(1200, 630), headers: { 'content-type': 'image/png' } },
    'http://tinyqueue.dev/': { status: 301, headers: { location: 'https://tinyqueue.dev/' } },
    'https://github.com/tinyqueue/tinyqueue': { body: 'ok', headers: HTML },
  };
}

export function fakeFetch(overrides = {}) {
  const routes = { ...base(), ...overrides };
  const seen = [];
  const fetch = async (url, opts = {}) => {
    seen.push({ url, method: opts.method ?? 'GET', headers: opts.headers });
    const u = new URL(url);
    const key = u.origin === ORIGIN ? u.pathname + u.search : u.href;
    const route = routes[key] ?? routes[u.href];
    if (route === undefined || route === null) return new Response('not found', { status: 404, headers: HTML });
    const typeFor = (path) => (/\.txt$/.test(path) ? { 'content-type': 'text/plain' } : /\.xml$/.test(path) ? { 'content-type': 'application/xml' } : HTML);
    const r = typeof route === 'string' ? { body: route, headers: typeFor(u.pathname) } : route;
    const status = r.status ?? 200;
    const body = opts.method === 'HEAD' || (status >= 300 && status < 400) ? null : r.body;
    return new Response(body, { status, headers: r.headers ?? {} });
  };
  return { fetch, seen };
}

// Fixed clock: the fixture sitemap's dates are all before it.
export const NOW = new Date('2026-11-11T10:00:00Z');

export async function check(overrides, opts = {}) {
  const { fetch, seen } = fakeFetch(overrides);
  const result = await runCheck(`${ORIGIN}/`, { fetch, now: NOW, ...opts });
  const byId = Object.fromEntries(result.checks.map((c) => [c.id, c]));
  return { result, byId, seen };
}

export const page = (head, body = '<main><h1>Tinyqueue does one thing well</h1><p>Enough text to not be an empty shell, about the job queue in your SQLite file.</p></main>') =>
  ({ body: `<!doctype html><html lang="en"><head>${head}</head><body>${body}</body></html>`, headers: HTML });

export function withHome(replace) {
  let html = read('index.html');
  for (const [a, b] of replace) {
    if (!html.includes(a)) throw new Error(`fixture does not contain: ${a}`);
    html = html.replace(a, b);
  }
  return { '/': { body: html, headers: HTML } };
}
