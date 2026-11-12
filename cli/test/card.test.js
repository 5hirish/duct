import { test } from 'node:test';
import assert from 'node:assert/strict';
import { validate } from '../src/schema.js';
import { renderCard, cardData } from '../src/card/index.js';
import { wrap, measure, FACES } from '../src/card/text.js';
import { formatDate, THEMES } from '../src/card/layout.js';
import { imageSize } from '../src/check/image.js';

const result = (extra = {}) => ({
  schema: 'getduct/launch-check@1',
  url: 'https://tinyqueue.dev/',
  checkedAt: '2026-11-10T09:00:00+01:00',
  checks: [{ id: 'M5', status: 'FAIL', foundBy: 'repository' }, { id: 'C1', status: 'FAIL' }, { id: 'S4', status: 'FAIL' }],
  fixes: [
    { title: 'Send an event when someone downloads', checkId: 'M5', impact: 3, effort: 1, foundBy: 'repository' },
    { title: 'Point the social card at a file that ships', checkId: 'C1', impact: 3, effort: 1, foundBy: 'both' },
    { title: 'Fix the canonical domain', checkId: 'S4', impact: 3, effort: 1, foundBy: 'both' },
  ],
  ...extra,
});

test('a complete result validates', () => {
  assert.deepEqual(validate(result()), []);
});

test('validation names what is wrong', () => {
  const errs = (r) => validate(r).join('\n');
  assert.match(errs({ ...result(), schema: 'other' }), /result\.schema must be "getduct\/launch-check@1"/);
  assert.match(errs({ ...result(), checks: undefined }), /result\.checks is required/);
  assert.match(errs({ ...result(), url: 'ftp://x' }), /result\.url does not match/);
  assert.match(errs(result({ checks: [{ id: 'Z9', status: 'FAIL' }] })), /result\.checks\[0\]\.id must be one of/);
  assert.match(errs(result({ checks: [{ id: 'S1', status: 'BAD' }] })), /status must be one of PASS, WARN, FAIL, UNVERIFIED/);
  assert.match(errs(result({ checks: [{ id: 'S1', status: 'FAIL' }, { id: 'S1', status: 'WARN' }] })), /S1 twice/);
  assert.match(errs(result({ fixes: [1, 2, 3, 4].map(() => ({ title: 'Fix it now' })) })), /more than 3 items/);
  assert.match(errs(result({ fixes: [{ title: 'x'.repeat(121) }] })), /longer than 120/);
  assert.match(errs(result({ fixes: [{ title: 'Fix', impact: 4 }] })), /impact is above 3/);
  assert.match(errs(result({ score: 101 })), /score is above 100/);
  assert.match(errs(null), /result must be object/);
});

test('the card recomputes the score and says when the file disagrees', () => {
  const { card, warnings } = cardData(result({ score: 64 }));
  // M5 FAIL (Measurement 75), C1 FAIL (Social 75), S4 FAIL (Search 75) -> 85
  assert.equal(card.score, 85);
  assert.equal(card.band, 'Ready');
  assert.match(warnings[0], /says 64\/100 but its checks add up to 85\/100/);
  assert.equal(cardData(result({ score: 85 })).warnings.length, 0);
});

test('the host drops www and comes from the URL when missing', () => {
  assert.equal(cardData(result({ url: 'https://www.tinyqueue.dev/' })).card.host, 'tinyqueue.dev');
  assert.equal(cardData(result({ host: 'www.example.org' })).card.host, 'example.org');
});

test('an invalid result does not render', () => {
  assert.throws(() => renderCard({ schema: 'getduct/launch-check@1' }), /not a valid launch check result/);
});

test('renders a 1200x630 PNG in both themes, and an SVG', () => {
  for (const theme of Object.keys(THEMES)) {
    const { output } = renderCard(result(), { theme });
    assert.deepEqual(imageSize(output), { type: 'png', width: 1200, height: 630 });
  }
  const { output } = renderCard(result(), { format: 'svg' });
  assert.match(output, /^<svg [^>]*width="1200" height="630"/);
  assert.match(output, /<title>Launch check: tinyqueue\.dev, 85\/100, Ready<\/title>/);
  assert.ok(!/NaN|undefined/.test(output));
});

test('renders the extremes: no fixes, 100, a long host, long and odd titles', () => {
  assert.doesNotThrow(() => renderCard(result({ checks: [], fixes: [] })));
  assert.doesNotThrow(() => renderCard(result({
    url: 'https://a-very-long-product-name-for-the-card-to-fit.example.co.uk/',
    checks: ['S1', 'S2', 'S3', 'S4', 'S6', 'C1', 'C4', 'M1', 'A1', 'F2'].map((id) => ({ id, status: 'FAIL' })),
    fixes: [
      { title: 'Ünïcödé façade—with “smart” quotes… and a tab\there' },
      { title: 'Supercalifragilisticexpialidocious-and-then-some-more-letters-again' },
      { title: '日本語のタイトル and emoji 🚀 fall back to a question mark' },
    ],
  })));
  assert.throws(() => renderCard(result(), { theme: 'neon' }), /unknown theme/);
});

test('wrap: two balanced lines, an ellipsis when it cannot fit', () => {
  const face = FACES.sansBold;
  const two = wrap('Count the downloads consent never sees', face, 30, 538, 2);
  assert.equal(two.length, 2);
  assert.ok(two[1].split(' ').length > 1, 'no one-word widow');
  const cut = wrap('one two three four five six seven eight nine ten eleven twelve thirteen', face, 30, 300, 2);
  assert.equal(cut.length, 2);
  assert.ok(cut[1].endsWith('…'));
  for (const l of cut) assert.ok(measure(l, face, 30) <= 300);
});

test('dates print as day, month, year', () => {
  assert.equal(formatDate('2026-11-10T09:00:00+01:00'), '10 Nov 2026');
  assert.equal(formatDate('2026-01-02'), '2 Jan 2026');
  assert.equal(formatDate('nope'), '');
});

test('text colours hold their contrast on both backgrounds', () => {
  const lum = (hex) => {
    const n = parseInt(hex.slice(1), 16);
    const [r, g, b] = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((v) => { v /= 255; return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; });
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  };
  const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };
  for (const [name, t] of Object.entries(THEMES)) {
    for (const key of ['ink', 'muted', 'brand']) {
      assert.ok(ratio(t[key], t.bg) >= 4.5, `${name}.${key} is ${ratio(t[key], t.bg).toFixed(2)}:1`);
    }
  }
});
