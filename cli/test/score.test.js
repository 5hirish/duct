import { test } from 'node:test';
import assert from 'node:assert/strict';
import { computeScore, rankFixes, bandFor } from '../src/score.js';
import { AREAS } from '../src/catalog.js';

const c = (id, status, extra = {}) => ({ id, status, ...extra });

test('no findings is 100, Ready', () => {
  const s = computeScore([]);
  assert.equal(s.score, 100);
  assert.equal(s.band, 'Ready');
});

test('weights add up to 100', () => {
  assert.equal(AREAS.reduce((n, a) => n + a.weight, 0), 100);
});

test('-25 per FAIL, -10 per WARN, inside the area, weighted', () => {
  // Measurement 75 x 25 + 95 x 75 others at 100 -> 93.75 -> 94
  assert.equal(computeScore([c('M1', 'FAIL')]).score, 94);
  // Search 90 x 20 -> 98
  assert.equal(computeScore([c('S2', 'WARN')]).score, 98);
  const s = computeScore([c('C1', 'FAIL'), c('C5', 'WARN')]);
  assert.equal(s.areas.social.score, 65);
  assert.equal(s.areas.social.fail, 1);
  assert.equal(s.areas.social.warn, 1);
});

test('UNVERIFIED and PASS cost nothing', () => {
  assert.equal(computeScore([c('M3', 'UNVERIFIED'), c('K1', 'UNVERIFIED'), c('S1', 'PASS')]).score, 100);
});

test('an area floors at 0', () => {
  const s = computeScore(['S1', 'S2', 'S3', 'S4', 'S6'].map((id) => c(id, 'FAIL')));
  assert.equal(s.areas.search.score, 0);
  assert.equal(s.score, 80);
});

test('rounding is half up: 96.5 is 97', () => {
  // Measurement 90 (22.5) + First impression 90 (9) + the rest 75 = 96.5
  assert.equal(computeScore([c('M4', 'WARN'), c('F3', 'WARN')]).score, 97);
});

test('band edges', () => {
  assert.equal(bandFor(85), 'Ready');
  assert.equal(bandFor(84), 'Ready after fixes');
  assert.equal(bandFor(70), 'Ready after fixes');
  assert.equal(bandFor(69), 'Needs work');
  assert.equal(bandFor(55), 'Needs work');
  assert.equal(bandFor(54), 'Not ready');
  assert.equal(bandFor(0), 'Not ready');
});

test('fixes rank by impact/effort, then impact, then repository before live site', () => {
  const ranked = rankFixes([
    c('S6', 'FAIL'), // 3 / 2 = 1.5
    c('S10', 'WARN'), // 2 / 1 = 2
    c('A2', 'WARN'), // 1 / 1 = 1
    c('C1', 'FAIL'), // 3 / 1 = 3
    c('M5', 'FAIL', { foundBy: 'repository' }), // 3 / 1 = 3, repository wins the tie
    c('S1', 'PASS'),
  ]);
  assert.deepEqual(ranked.map((f) => f.checkId), ['M5', 'C1', 'S10']);
  assert.equal(ranked.length, 3);
});

test('a check can carry its own impact, effort and fix title', () => {
  const [f] = rankFixes([c('S2', 'WARN', { impact: 3, effort: 1, fix: 'Say what it is in the title' })]);
  assert.equal(f.title, 'Say what it is in the title');
  assert.equal(f.impact, 3);
});

test('fewer than three candidates stays fewer', () => {
  assert.equal(rankFixes([c('S2', 'WARN')]).length, 1);
  assert.equal(rankFixes([c('S2', 'PASS')]).length, 0);
});
