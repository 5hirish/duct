// A polite fetcher: names itself, waits for no more than two requests at a
// time, gives up after a timeout, follows redirects itself so it can count
// the hops, and never reads more of a body than it needs.

import { USER_AGENT } from '../version.js';
import { gunzipSync } from 'node:zlib';

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

export function createFetcher({ fetch: fetchImpl = globalThis.fetch, concurrency = LIMITS.concurrency, timeoutMs = LIMITS.timeoutMs } = {}) {
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
    try { buf = gunzipSync(buf); } catch { /* keep the bytes as they are */ }
  }
  return buf.toString('utf8');
}

export function isHtml(res) {
  const type = res?.headers?.['content-type'] ?? '';
  if (type) return /html/i.test(type);
  return /^\s*(<!doctype html|<html)/i.test(text(res).slice(0, 200));
}
