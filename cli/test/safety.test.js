// The three ways a hostile site could reach past the check: a redirect or
// linked URL into the user's own network, a gzip body that inflates without
// end, and control characters that reach the terminal.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { gzipSync } from 'node:zlib';
import { isPrivateAddress, createGuard, createFetcher, text, LIMITS } from '../src/check/fetch.js';
import { clean } from '../src/report.js';

test('private, loopback, link-local and metadata addresses are private', () => {
  for (const ip of ['127.0.0.1', '10.1.2.3', '172.20.0.1', '192.168.1.1', '169.254.169.254', '100.64.0.1', '0.0.0.0', '224.0.0.1',
    '::1', '::', 'fd00::1', 'fe80::1', 'fec0::1', 'ff02::1', '::ffff:127.0.0.1', '::ffff:7f00:1', '0:0:0:0:0:ffff:a9fe:a9fe',
    '64:ff9b::a9fe:a9fe', '2002:7f00:1::', '::127.0.0.1', '2001:db8::1']) {
    assert.equal(isPrivateAddress(ip), true, ip);
  }
  for (const ip of ['8.8.8.8', '172.32.0.1', '104.21.3.4', '2606:4700::1111', '::ffff:8.8.8.8', '2002:0808:0808::']) {
    assert.equal(isPrivateAddress(ip), false, ip);
  }
});

const fakeDns = (table) => async (host) => (table[host] ?? ['93.184.216.34']).map((address) => ({ address }));

test('a public start refuses other hosts that resolve to private addresses', async () => {
  const allowed = createGuard('https://example.com/', { resolve: fakeDns({ 'internal.example.com': ['10.0.0.5'] }) });
  assert.equal(await allowed('https://example.com/about'), true);
  assert.equal(await allowed('https://cdn.example.net/og.png'), true);
  assert.equal(await allowed('https://internal.example.com/'), false);
  assert.equal(await allowed('http://169.254.169.254/latest/meta-data/'), false);
  assert.equal(await allowed('http://localhost:3000/'), false);
  assert.equal(await allowed('file:///etc/passwd'), false);
});

test('a start the user pointed at a private host allows that network', async () => {
  const allowed = createGuard('http://localhost:3000/', { resolve: fakeDns({}) });
  assert.equal(await allowed('http://127.0.0.1:3000/x'), true);
});

test('a typed domain that only resolves privately exempts nothing', async () => {
  const allowed = createGuard('https://evil.example/', { resolve: fakeDns({ 'evil.example': ['10.0.0.1'], 'meta.example': ['169.254.169.254'] }) });
  assert.equal(await allowed('https://meta.example/'), false);
  assert.equal(await allowed('https://evil.example/'), false);
});

test('a host that cannot be resolved is refused', async () => {
  const allowed = createGuard('https://example.com/', { resolve: async () => { throw new Error('ENOTFOUND'); } });
  assert.equal(await allowed('https://nowhere.example/'), false);
});

test('a redirect into a private address is refused, not followed', async () => {
  const fetch = async (url) => new URL(url).hostname === 'example.com'
    ? { status: 302, headers: new Map([['location', 'http://169.254.169.254/']]), body: null }
    : { status: 200, headers: new Map(), body: null, arrayBuffer: async () => new ArrayBuffer(0) };
  const guard = createGuard('https://example.com/', { resolve: fakeDns({}) });
  const f = createFetcher({ fetch, guard });
  const res = await f.get('https://example.com/');
  assert.equal(res.status, 0);
  assert.match(res.error, /refused/);
});

test('a gzip body that inflates past the cap is not inflated', () => {
  const bomb = gzipSync(Buffer.alloc(LIMITS.sitemapBytes + 1024));
  const out = text({ body: bomb });
  assert.ok(out.length < LIMITS.sitemapBytes, 'kept the compressed bytes');
});

test('control characters never reach the terminal', () => {
  assert.equal(clean('ok\u001b]0;pwned\u0007 title\u009b'), 'ok ]0;pwned  title ');
});
