// A polite fetcher: names itself, waits for no more than two requests at a
// time, gives up after a timeout, follows redirects itself so it can count
// the hops, and never reads more of a body than it needs.

import { USER_AGENT } from '../version.js';
import { gunzipSync } from 'node:zlib';
import { lookup } from 'node:dns/promises';
import { isIP } from 'node:net';

export const LIMITS = {
  concurrency: 2,
  timeoutMs: 15000,
  maxRedirects: 10,
  htmlBytes: 5 * 1024 * 1024,
  // One byte past the sitemap protocol's 50 MB cap is all it takes to know.
  sitemapBytes: 50 * 1024 * 1024 + 1,
  imageHeadBytes: 64 * 1024,
  scriptBytes: 1024 * 1024,
};

// A site can point this run anywhere: a redirect, a sitemap child, an
// og:image or a script URL is the site's choice, not the user's. Followed
// blindly, that reaches the machine the CLI runs on, its network and a
// cloud metadata endpoint, and prints what came back. So any host other
// than the one the user typed is refused when it resolves to a loopback,
// private, link-local or unique-local address. A user who points the CLI
// at their own local or private host has chosen that network, so then
// nothing is refused.
const PRIVATE_V4 = [
  ['0.0.0.0', 8], ['10.0.0.0', 8], ['100.64.0.0', 10], ['127.0.0.0', 8],
  ['169.254.0.0', 16], ['172.16.0.0', 12], ['192.168.0.0', 16],
];
const v4 = (ip) => ip.split('.').reduce((n, part) => (n << 8) + Number(part), 0) >>> 0;
const inV4 = (ip, [base, bits]) => bits === 0 || (v4(ip) >>> (32 - bits)) === (v4(base) >>> (32 - bits));

export function isPrivateAddress(ip) {
  const family = isIP(ip);
  if (family === 4) return PRIVATE_V4.some((r) => inV4(ip, r));
  if (family !== 6) return false;
  const a = ip.toLowerCase();
  const mapped = a.match(/^::ffff:(\d+\.\d+\.\d+\.\d+)$/);
  if (mapped) return isPrivateAddress(mapped[1]);
  return a === '::' || a === '::1' || /^f[cd]/.test(a) || /^fe[89ab]/.test(a);
}

async function resolvesPrivate(hostname, resolve) {
  const host = hostname.replace(/^\[|\]$/g, '');
  if (host === 'localhost' || host.endsWith('.localhost')) return true;
  if (isIP(host)) return isPrivateAddress(host);
  try {
    const addrs = await resolve(host, { all: true });
    return addrs.some((a) => isPrivateAddress(a.address));
  } catch {
    return false; // unresolvable: the fetch itself will fail and say so
  }
}

/**
 * The guard for one run, anchored on the URL the user typed. `resolve` is
 * injectable so tests never touch DNS.
 */
export function createGuard(startUrl, { resolve = lookup } = {}) {
  const trusted = new URL(startUrl).hostname;
  let trustedPrivate;
  return async function allowed(url) {
    const u = new URL(url);
    if (u.protocol !== 'http:' && u.protocol !== 'https:') return false;
    if (u.hostname === trusted) return true;
    if (trustedPrivate === undefined) trustedPrivate = await resolvesPrivate(trusted, resolve);
    if (trustedPrivate) return true;
    return !(await resolvesPrivate(u.hostname, resolve));
  };
}

export function createFetcher({ fetch: fetchImpl = globalThis.fetch, concurrency = LIMITS.concurrency, timeoutMs = LIMITS.timeoutMs, guard = null } = {}) {
  let active = 0;
  const queue = [];
  const slot = () => new Promise((resolve) => {
    if (active < concurrency) { active++; resolve(); } else queue.push(resolve);
  });
  const release = () => {
    const next = queue.shift();
    if (next) next(); else active--;
  };
  let requests = 0;

  async function one(url, { method = 'GET', range, maxBytes = LIMITS.htmlBytes, accept } = {}) {
    if (guard && !(await guard(url))) throw new Error('refused: points at a private or local address');
    await slot();
    requests++;
    try {
      const headers = { 'user-agent': USER_AGENT, accept: accept ?? '*/*' };
      if (range) headers.range = range;
      const res = await fetchImpl(url, { method, headers, redirect: 'manual', signal: AbortSignal.timeout(timeoutMs) });
      const out = { url, status: res.status, headers: lowerHeaders(res.headers), body: null, truncated: false, bytes: 0 };
      if (method !== 'HEAD' && !(res.status >= 300 && res.status < 400)) {
        const { buf, truncated } = await readCapped(res, maxBytes);
        out.body = buf; out.truncated = truncated; out.bytes = buf.length;
      } else {
        await res.body?.cancel?.().catch(() => {});
      }
      return out;
    } finally {
      release();
    }
  }

  // Follow redirects by hand: the hop count is a check (S7), and a fetch that
  // follows them silently cannot say where it went.
  async function get(url, opts = {}) {
    const chain = [];
    let current = url;
    for (let i = 0; i <= LIMITS.maxRedirects; i++) {
      let res;
      try {
        res = await one(current, opts);
      } catch (e) {
        return { url, finalUrl: current, status: 0, error: errorText(e), redirects: chain, headers: {}, body: null };
      }
      if (res.status >= 300 && res.status < 400 && res.headers.location) {
        chain.push({ from: current, status: res.status });
        current = new URL(res.headers.location, current).href;
        continue;
      }
      // Some servers refuse HEAD outright; a 405 or 501 says nothing about the page.
      if (opts.method === 'HEAD' && (res.status === 405 || res.status === 501)) {
        return get(current, { ...opts, method: 'GET', range: 'bytes=0-0', maxBytes: 1 });
      }
      return { ...res, url, finalUrl: current, redirects: chain };
    }
    return { url, finalUrl: current, status: 0, error: 'too many redirects', redirects: chain, headers: {}, body: null };
  }

  return { get, count: () => requests };
}

function lowerHeaders(h) {
  const out = {};
  if (typeof h?.forEach === 'function') h.forEach((v, k) => { out[k.toLowerCase()] = v; });
  else for (const [k, v] of Object.entries(h ?? {})) out[k.toLowerCase()] = v;
  return out;
}

async function readCapped(res, max) {
  if (!res.body) return { buf: Buffer.alloc(0), truncated: false };
  if (typeof res.body.getReader !== 'function') {
    const all = Buffer.from(await res.arrayBuffer());
    return { buf: all.subarray(0, max), truncated: all.length > max };
  }
  const reader = res.body.getReader();
  const chunks = [];
  let size = 0, truncated = false;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    chunks.push(Buffer.from(value));
    size += value.length;
    if (size >= max) { truncated = size > max || !(await reader.read()).done; break; }
  }
  await reader.cancel().catch(() => {});
  return { buf: Buffer.concat(chunks).subarray(0, max), truncated };
}

function errorText(e) {
  if (e?.name === 'TimeoutError' || e?.name === 'AbortError') return 'timed out';
  return e?.cause?.code ?? e?.message ?? String(e);
}

export function text(res) {
  if (!res?.body) return '';
  let buf = res.body;
  // A .xml.gz sitemap, or a server that ignores Accept-Encoding on a raw file.
  if (buf[0] === 0x1f && buf[1] === 0x8b) {
    // Capped like every other body: a few kilobytes of gzip can inflate to
    // gigabytes. Past the cap it is treated as unreadable, which the sitemap
    // check already reports.
    try { buf = gunzipSync(buf, { maxOutputLength: LIMITS.sitemapBytes }); } catch { /* keep the bytes as they are */ }
  }
  return buf.toString('utf8');
}

export function isHtml(res) {
  const type = res?.headers?.['content-type'] ?? '';
  if (type) return /html/i.test(type);
  return /^\s*(<!doctype html|<html)/i.test(text(res).slice(0, 200));
}
