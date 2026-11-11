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
// cloud metadata endpoint, and prints what came back. So every host is
// refused when any address it resolves to is not public unicast, and a
// host that cannot be resolved is refused too. The one exemption is the
// user's own choice, made explicitly: they typed an IP literal or a
// `localhost` name that is itself private, so that network is theirs.
// What remains is DNS rebinding between this lookup and the fetch's own;
// zero dependencies leaves no way to pin the address global fetch connects
// to, and the output goes only to the person who ran the command.
const BLOCKED_V4 = [
  ['0.0.0.0', 8], ['10.0.0.0', 8], ['100.64.0.0', 10], ['127.0.0.0', 8],
  ['169.254.0.0', 16], ['172.16.0.0', 12], ['192.0.0.0', 24], ['192.0.2.0', 24],
  ['192.168.0.0', 16], ['198.18.0.0', 15], ['198.51.100.0', 24], ['203.0.113.0', 24],
  ['224.0.0.0', 4], ['240.0.0.0', 4],
];
const v4int = (ip) => ip.split('.').reduce((n, part) => n * 256 + Number(part), 0);
const inV4 = (n, [base, bits]) => Math.floor(n / 2 ** (32 - bits)) === Math.floor(v4int(base) / 2 ** (32 - bits));
const blockedV4 = (ip) => { const n = v4int(ip); return BLOCKED_V4.some((r) => inV4(n, r)); };

/** An IPv6 address as 16 bytes, or null. Handles `::` and a dotted IPv4 tail. */
function v6bytes(ip) {
  let a = ip.toLowerCase().split('%')[0];
  const tail = a.match(/(\d+\.\d+\.\d+\.\d+)$/);
  if (tail) {
    const q = tail[1].split('.').map(Number);
    a = a.slice(0, -tail[1].length) + ((q[0] << 8) | q[1]).toString(16) + ':' + ((q[2] << 8) | q[3]).toString(16);
  }
  const halves = a.split('::');
  if (halves.length > 2) return null;
  const head = halves[0] ? halves[0].split(':') : [];
  const rest = halves.length === 2 ? (halves[1] ? halves[1].split(':') : []) : [];
  const fill = halves.length === 2 ? 8 - head.length - rest.length : 0;
  const groups = [...head, ...Array(Math.max(fill, 0)).fill('0'), ...rest];
  if (groups.length !== 8) return null;
  const bytes = [];
  for (const g of groups) {
    const n = parseInt(g, 16);
    if (!/^[0-9a-f]{1,4}$/.test(g) || Number.isNaN(n)) return null;
    bytes.push(n >> 8, n & 0xff);
  }
  return bytes;
}

function blockedV6(ip) {
  const b = v6bytes(ip);
  if (!b) return true; // unparseable: refuse rather than guess
  const zero = (from, to) => b.slice(from, to).every((x) => x === 0);
  const v4 = (o) => b.slice(o, o + 4).join('.');
  if (zero(0, 10) && b[10] === 0xff && b[11] === 0xff) return blockedV4(v4(12)); // ::ffff:a.b.c.d
  if (zero(0, 12)) return true;                                                 // ::, ::1, ::a.b.c.d
  if (b[0] === 0x00 && b[1] === 0x64 && b[2] === 0xff && b[3] === 0x9b && zero(4, 12)) return blockedV4(v4(12)); // 64:ff9b::/96 NAT64
  if (b[0] === 0x20 && b[1] === 0x02) return blockedV4(v4(2));                   // 2002::/16 6to4
  if ((b[0] & 0xfe) === 0xfc) return true;                                      // fc00::/7 unique local
  if (b[0] === 0xfe && (b[1] & 0xc0) === 0x80) return true;                     // fe80::/10 link-local
  if (b[0] === 0xfe && (b[1] & 0xc0) === 0xc0) return true;                     // fec0::/10 site-local
  if (b[0] === 0xff) return true;                                               // ff00::/8 multicast
  if (b[0] === 0x20 && b[1] === 0x01 && b[2] === 0x0d && b[3] === 0xb8) return true; // 2001:db8::/32 documentation
  return false;
}

/** True when an address is not public unicast. */
export function isPrivateAddress(ip) {
  const family = isIP(ip);
  if (family === 4) return blockedV4(ip);
  if (family === 6) return blockedV6(ip);
  return true;
}

const bare = (hostname) => hostname.replace(/^\[|\]$/g, '');
const isLocalName = (host) => host === 'localhost' || host.endsWith('.localhost');

async function hostIsPrivate(host, resolve) {
  if (isLocalName(host)) return true;
  if (isIP(host)) return isPrivateAddress(host);
  try {
    const addrs = await resolve(host, { all: true, verbatim: true });
    if (!addrs?.length) return true;
    return addrs.some((a) => isPrivateAddress(a.address));
  } catch {
    return true; // cannot be checked, so it is not fetched
  }
}

/**
 * The guard for one run, anchored on the URL the user typed. `resolve` is
 * injectable so tests never touch DNS.
 */
export function createGuard(startUrl, { resolve = lookup } = {}) {
  const typed = bare(new URL(startUrl).hostname);
  // Only an explicit choice exempts a network: an IP literal or a localhost
  // name the user typed. A domain that merely resolves privately is not one.
  const userChosePrivate = isLocalName(typed) || (isIP(typed) > 0 && isPrivateAddress(typed));
  const cache = new Map();
  return async function allowed(url) {
    const u = new URL(url);
    if (u.protocol !== 'http:' && u.protocol !== 'https:') return false;
    if (userChosePrivate) return true;
    const host = bare(u.hostname);
    if (!cache.has(host)) cache.set(host, hostIsPrivate(host, resolve));
    return !(await cache.get(host));
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
